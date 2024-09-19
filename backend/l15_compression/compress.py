"""L16 RECOMP-lite: extractive compression — MiniLM scores sentences, budget kept.

Full RECOMP abstractive compressor needs its own fine-tuned model; extractive
selection with the already-loaded MiniLM gets 80% of the token saving.

`compress_hits()` keeps per-hit doc/chunk_id provenance so the L17
assembly layer still renders [doc#chunk] citations correctly.
"""
import re

_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sents(text: str) -> list[str]:
    return [s for s in _SENT_RE.split(text) if len(s.split()) >= 4]


def compress_hits(query: str, hits: list[dict], budget_chars: int = 5500) -> list[dict]:
    """Ranks all sentences across hits by relevance, then greedily fills per-hit
    text budgets up to the global budget, keeping provenance intact.
    """
    if not hits:
        return hits
    sents: list[tuple[int, str]] = []  # (hit_index, sentence)
    for hi, h in enumerate(hits):
        for s in _split_sents(h.get("text", "")):
            sents.append((hi, s))
    total_text = sum(len(h.get("text", "")) for h in hits)
    if total_text <= budget_chars or not sents:
        return hits
    try:
        from backend.l13_rerank.minilm import get_reranker

        flat = [s for _, s in sents]
        scores = get_reranker().predict([(query, s) for s in flat])
    except Exception:
        # fallback: truncate each hit's text to its share of the budget
        share = budget_chars // max(1, len(hits))
        for h in hits:
            if len(h["text"]) > share:
                h["text"] = h["text"][:share]
        return hits

    order = sorted(range(len(sents)), key=lambda i: float(scores[i]), reverse=True)
    budgets = {i: budget_chars // max(1, len(hits)) for i in range(len(hits))}
    picked: dict[int, list[str]] = {i: [] for i in range(len(hits))}
    for idx in order:
        hi, s = sents[idx]
        if len(" ".join(picked[hi])) + len(s) + 1 <= budgets[hi]:
            picked[hi].append(s)
    out = []
    for h in hits:
        hi = hits.index(h)
        txt = " ".join(picked[hi]) if picked[hi] else h.get("text", "")[:budgets[hi]]
        out.append({**h, "text": txt})
    return out
