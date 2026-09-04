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
    """CRAG-lite: retrieval is usable only if the best hit clears the threshold."""
    return bool(hits) and float(hits[0].get("score", 0.0)) >= threshold
