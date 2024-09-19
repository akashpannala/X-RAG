"""L14-full: cascade MiniLM → Jina/BGE-reranker/MiniLM → RankGPT-listwise + MMR diversity.

Quick: MiniLM → top-5 (unchanged). Deep: MiniLM 50→30 → Jina/BGE/MiniLM 30→10 →
RankGPT-listwise 10→5 → MMR interleave. Jina API preferred, falls back to local BGE → MiniLM.
"""
from backend.config import settings
from backend.l13_rerank.minilm import rerank as minilm_rerank
from backend.l13_rerank.provider import get_reranker_provider


def rankgpt_listwise(query: str, hits: list[dict], top_n: int) -> list[dict]:
    """Local RankGPT: LLM orders passage indices by relevance (deep final cut)."""
    from backend.l17_generation.llm import get_llm

    if len(hits) <= top_n:
        return hits
    numbered = "\n".join(f"[{i}] {h['text'][:600]}" for i, h in enumerate(hits))
    try:
        msg = get_llm().invoke(
            f"Rank these passages by relevance to the question. Reply with ONLY "
            f"the {top_n} best indices as comma-separated numbers, most relevant first. "
            f"No trailing punctuation, just digits separated by commas.\n"
            f"Question: {query}\nPassages:\n{numbered}")
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
    except Exception:
        return hits[:top_n]  # LLM unavailable → keep MiniLM/BGE order, don't crash
    order = []
    for tok in text.replace(",", " ").replace(".", " ").split():
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
    # Stage 2: Jina API → Local BGE-reranker → MiniLM fallback
    provider = get_reranker_provider()
    top_n = min(10, len(stage1))
    try:
        docs = [h["text"] for h in stage1]
        ranked = provider.rerank(query, docs, top_n)
        stage2 = [stage1[idx] for idx, _ in ranked]
        for (idx, score), hit in zip(ranked, stage2):
            hit["score"] = float(score)
    except Exception:
        stage2 = stage1[:top_n]  # fallback to MiniLM order
    try:
        final = rankgpt_listwise(query, stage2, 5)
    except Exception:
        final = stage2[:5]
    try:
        from backend.l06_embedding.bge import get_embeddings
        from backend.config import settings

        vecs = get_embeddings(settings.embed_model).embed_documents([h["text"][:1000] for h in final])
        qv = get_embeddings(settings.embed_model).embed_query(query)
        out = mmr(qv, final, vecs, len(final))
    except Exception:
        out = final
    # write a normalized position score (1.0..~0) so downstream confident() has a
    # consistent 0-1 scale regardless of which reranker produced the ranking
    for i, h in enumerate(out):
        h["score"] = h.get("score", 1.0) if i == 0 else max(h.get("score", 0.0), (len(out) - i) / len(out))
    return out
