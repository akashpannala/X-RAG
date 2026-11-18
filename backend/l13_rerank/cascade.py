"""L14-full: cascade remote rerank → RankGPT-listwise + MMR diversity.

Quick: remote rerank → top-5. Deep: remote rerank 50→30 → remote rerank
30→10 → RankGPT-listwise 10→5 → MMR interleave. The Jina API is the only
reranker; there is no local BGE/MiniLM fallback.
"""
import logging

from backend.l13_rerank.provider import get_reranker_provider

_logger = logging.getLogger(__name__)


def rerank_api(query: str, hits: list[dict], top_n: int) -> list[dict]:
    """Score candidates with the remote reranker and return the top-n."""
    if not hits:
        return []
    provider = get_reranker_provider()
    ranked = provider.rerank(query, [h["text"] for h in hits], min(top_n, len(hits)))
    out: list[dict] = []
    for idx, score in ranked:
        if 0 <= idx < len(hits):
            out.append({**hits[idx], "score": float(score)})
    return out


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
    except Exception as e:
        _logger.warning("RankGPT LLM rerank failed — keeping reranker order: %s", e)
        return hits[:top_n]
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


def _normalize_scores(out: list[dict]) -> None:
    """Write a normalized position score (1.0..~0) on the reranker 0-1 scale."""
    for i, h in enumerate(out):
        h["score"] = h.get("score", 1.0) if i == 0 else max(
            h.get("score", 0.0), (len(out) - i) / len(out)
        )


def cascade(query: str, hits: list[dict], mode: str) -> list[dict]:
    if not hits:
        return hits
    if mode == "quick":
        out = rerank_api(query, hits, 5)
        _normalize_scores(out)
        return out

    stage1 = rerank_api(query, hits, min(30, len(hits)))
    stage2 = rerank_api(query, stage1, min(10, len(stage1)))
    final = rankgpt_listwise(query, stage2, 5)
    try:
        from backend.config import settings
        from backend.l06_embedding.bge import get_embeddings

        emb = get_embeddings(settings.embed_model)
        vecs = emb.embed_documents([h["text"][:1000] for h in final])
        qv = emb.embed_query(query)
        out = mmr(qv, final, vecs, len(final))
    except Exception as e:
        _logger.warning("MMR skipped (remote embedding unavailable) — keeping order: %s", e)
        out = final
    _normalize_scores(out)
    return out
