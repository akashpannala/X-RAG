"""L14-full: cascade MiniLM → BGE-reranker → RankGPT-listwise + MMR diversity.

Quick: MiniLM → top-5 (unchanged). Deep: MiniLM 50→30 → BGE 30→10 →
RankGPT-listwise 10→5 → MMR interleave. BGE + RankGPT ride get_llm();
missing BGE weights degrade gracefully to MiniLM-only.
"""
from backend.l14_rerank.minilm import rerank as minilm_rerank

_bge = None


def get_bge_reranker(name: str = "BAAI/bge-reranker-v2-m3"):
    global _bge
    if _bge is None:
        from sentence_transformers import CrossEncoder

        from backend.l22_ragops.quant import quantize_dynamic_if_enabled

        _bge = CrossEncoder(name)
        quantize_dynamic_if_enabled(_bge.model)
    return _bge


def bge_rerank(query: str, hits: list[dict], top_n: int) -> list[dict]:
    scores = get_bge_reranker().predict([(query, h["text"]) for h in hits])
    ranked = sorted(zip(scores, hits), key=lambda x: float(x[0]), reverse=True)
    return [h for _, h in ranked[:top_n]]


def rankgpt_listwise(query: str, hits: list[dict], top_n: int) -> list[dict]:
    """Local RankGPT: LLM orders passage indices by relevance (deep final cut)."""
    from backend.l18_generation.llm import get_llm

    if len(hits) <= top_n:
        return hits
    numbered = "\n".join(f"[{i}] {h['text'][:600]}" for i, h in enumerate(hits))
    msg = get_llm().invoke(
        f"Rank these passages by relevance to the question. Reply with ONLY "
        f"the {top_n} best indices as comma-separated numbers, most relevant first.\n"
        f"Question: {query}\nPassages:\n{numbered}")
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    order = []
    for tok in text.replace(",", " ").split():
        if tok.strip().isdigit() and int(tok.strip()) < len(hits) and int(tok.strip()) not in order:
            order.append(int(tok.strip()))
    order += [i for i in range(len(hits)) if i not in order]
    return [hits[i] for i in order[:top_n]]


def mmr(query_vec: list[float], hits: list[dict], vecs: list[list[float]],
        top_n: int, lamb: float = 0.7) -> list[dict]:
    """Maximal Marginal Relevance: relevance vs already-picked redundancy."""
    import numpy as np

    q = np.array(query_vec)
    V = [np.array(v) / (np.linalg.norm(v) + 1e-9) for v in vecs]
    qn = q / (np.linalg.norm(q) + 1e-9)
    picked, remaining = [], list(range(len(hits)))
    while remaining and len(picked) < top_n:
        best, best_s = -1, -1e9
        for i in remaining:
            rel = float(qn @ V[i])
            red = max(float(V[i] @ V[j]) for j in picked) if picked else 0.0
            s = lamb * rel - (1 - lamb) * red
            if s > best_s:
                best, best_s = i, s
        picked.append(best)
        remaining.remove(best)
    return [hits[i] for i in picked]


def cascade(query: str, hits: list[dict], mode: str) -> list[dict]:
    if mode == "quick" or not hits:
        return minilm_rerank(query, hits, 5)
    stage1 = minilm_rerank(query, hits, min(30, len(hits)))
    try:
        stage2 = bge_rerank(query, stage1, min(10, len(stage1)))
    except Exception:
        stage2 = stage1[:10]  # BGE weights absent → MiniLM-only fallback
    final = rankgpt_listwise(query, stage2, 5)
    try:
        from backend.l06_embedding.bge import get_embeddings
        from backend.config import settings

        vecs = get_embeddings(settings.embed_model).embed_documents([h["text"][:1000] for h in final])
        qv = get_embeddings(settings.embed_model).embed_query(query)
        return mmr(qv, final, vecs, len(final))
    except Exception:
        return final
