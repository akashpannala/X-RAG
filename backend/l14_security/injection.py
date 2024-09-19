"""L15: thin-slice guards — prompt-injection screen + retrieval-confidence gate.

Full CRAG loop + LLMLingua compression are Phase 3. Here: reject obvious
injections before retrieval, refuse to hallucinate when retrieval is weak.
"""
import re

_INJECTION = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+instructions|"
    r"system\s*prompt|jailbreak|do\s+anything\s+now|reveal\s+.*(password|secret|key))",
    re.I,
)


def screen(text: str) -> str | None:
    """Return a refusal reason if input looks like prompt injection, else None."""
    if _INJECTION.search(text):
        return "request blocked by injection filter"
    return None


def confident(hits: list[dict], threshold: float = 0.30) -> bool:
    """CRAG-lite: retrieval is usable only if the best hit clears the threshold.

    Scores come from two different scales: RRF fused scores (<= ~0.1, since
    k=60 makes even rank-1 ≈ 0.016) and reranker scores (0-1). A fixed 0.30
    floor would reject every RRF-ranked result, so pick the floor by scale:
    rerank scores use 0.30, RRF scores use a small floor relative to k=60.
    """
    if not hits:
        return False
    best = float(hits[0].get("score", 0.0))
    if best > 0.5:  # reranker 0-1 scale
        return best >= threshold
    # RRF scale: rank-1 alone ≈ 0.016; require at least ~double that of noise
    return best >= 0.02
