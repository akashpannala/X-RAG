"""L16 RECOMP-lite: deterministic extractive compression (budget truncation).

No local MiniLM sentence scorer on ``aws-deploy``. Each hit gets an equal
share of the character budget and is truncated on a sentence/word boundary;
provenance (doc/chunk_id) is preserved so citations still render.
"""
import logging
import re

_logger = logging.getLogger(__name__)
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _truncate(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    head = text[:budget]
    # Prefer ending on a sentence boundary, then a word boundary.
    parts = _SENT_RE.split(head)
    if len(parts) > 1:
        head = " ".join(parts[:-1])
    if head:
        head = head.rsplit(" ", 1)[0] if " " in head else head
    return head.rstrip()


def compress_hits(query: str, hits: list[dict], budget_chars: int = 5500) -> list[dict]:
    """Fit hits into a global character budget without dropping provenance."""
    if not hits:
        return hits
    total = sum(len(h.get("text", "")) for h in hits)
    if total <= budget_chars:
        return hits
    share = max(1, budget_chars // len(hits))
    out: list[dict] = []
    truncated = 0
    for h in hits:
        text = h.get("text", "")
        new_text = _truncate(text, share)
        if len(new_text) < len(text):
            truncated += 1
        out.append({**h, "text": new_text})
    if truncated:
        _logger.info(
            "compress_hits truncated %d/%d hits to ~%d chars each (query=%r)",
            truncated, len(hits), share, query[:80],
        )
    return out
