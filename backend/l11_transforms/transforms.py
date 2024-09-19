"""L11 Query transforms — multi-query + HyDE + step-back + decomposition (PRD).

All ride get_llm() (Groq dev / Qwen2.5-7B-Ollama prod). RRF fuses the
per-query rank lists into one. Quick mode skips this entirely.
"""
from backend.l17_generation.llm import get_llm


def _lines(text: str, n: int) -> list[str]:
    out = []
    for l in text.splitlines():
        l = l.strip().lstrip("1234567890.-) ")
        if l and l not in out:
            out.append(l)
    return out[:n]


def multi_query(query: str, n: int = 4) -> list[str]:
    try:
        msg = get_llm().invoke(
            f"Write {n} different search queries that would each retrieve passages "
            f"answering the question below. One per line, no numbering.\nQuestion: {query}")
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
    except Exception:
        return [query]
    lines = _lines(text, n)
    query_norm = query.lower().strip()
    deduped = [l for l in lines if l.lower().strip() != query_norm]
    return [query] + deduped


def hyde(query: str) -> str:
    """Hypothetical answer passage — embedded and searched as a query vector."""
    try:
        msg = get_llm().invoke(
            f"Write a short paragraph that directly answers this question "
            f"(it may be imperfect; style matters, not facts).\nQuestion: {query}")
        return msg.content if isinstance(msg.content, str) else str(msg.content)
    except Exception:
        return ""


def step_back(query: str) -> str:
    """Abstract principle behind a specific question (multi-hop helper)."""
    try:
        msg = get_llm().invoke(
            f"What general principle or background fact would help answer this? "
            f"Reply with ONE search query for that background.\nQuestion: {query}")
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
    except Exception:
        return query
    back = _lines(text, 1)
    return back[0] if back else query


def decompose(query: str) -> list[str]:
    """Split a multi-hop question into ordered sub-questions."""
    try:
        msg = get_llm().invoke(
            f"Split this question into 2-4 simple sub-questions that must each be "
            f"answered in order. One per line, no numbering.\nQuestion: {query}")
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
    except Exception:
        return [query]
    steps = _lines(text, 4)
    return steps if len(steps) >= 2 else [query]


def rrf_fuse(rank_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion over (doc, chunk_id); keeps best-seen text/score."""
    fused: dict[tuple, float] = {}
    best: dict[tuple, dict] = {}
    for lst in rank_lists:
        for rank, h in enumerate(lst):
            key = (h.get("doc"), h.get("chunk_id"))
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in best or h.get("score", 0) > best[key].get("score", 0):
                best[key] = h
    result = [best[key] for key in sorted(fused, key=fused.get, reverse=True)]  # type: ignore
    for h in result:
        h["score"] = fused[(h.get("doc"), h.get("chunk_id"))]
    return result
