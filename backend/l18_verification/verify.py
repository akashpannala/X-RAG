"""L19 verification — LLM sentence labels (deep mode).

Local HHEM/CrossEncoder is removed on ``aws-deploy``; verification uses the
remote LLM judges-pass only. Each answer sentence is labelled Supported /
Unsupported / Contradicted against the retrieved contexts.
"""
import logging
import re

_logger = logging.getLogger(__name__)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if len(p.split()) >= 4]


def llm_labels(answer: str, contexts: list[str]) -> list[tuple[str, str]]:
    """LLM labels each sentence against the retrieved context."""
    from backend.l17_generation.llm import get_llm

    sents = split_sentences(answer)
    if not sents:
        return []
    ctx = "\n".join(contexts)[:5000]
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sents))
    msg = get_llm().invoke(
        "For each numbered sentence, reply ONE line: `<i> Supported|Unsupported|Contradicted`. "
        "A sentence is Supported only if the context states it.\n"
        f"Context:\n{ctx}\nSentences:\n{numbered}")
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    out = []
    for i, s in enumerate(sents):
        m = re.search(rf"^{i}\s+(Supported|Unsupported|Contradicted)", text, re.M | re.I)
        out.append((s, m.group(1).capitalize() if m else "Unsupported"))
    return out


def verify(answer: str, contexts: list[str]) -> dict:
    """Returns {labels: [(sentence, label)], supported_ratio: float}.

    A verifier failure returns ``supported_ratio=-1.0`` (unavailable) instead
    of failing the whole answer — the caller logs a warning.
    """
    sents = split_sentences(answer)
    if not sents or not contexts:
        return {"labels": [(s, "Unsupported") for s in sents], "supported_ratio": 0.0}
    try:
        labels = llm_labels(answer, contexts)
    except Exception as e:
        _logger.warning("LLM verification unavailable: %s", e)
        return {"labels": [(s, "Unsupported") for s in sents], "supported_ratio": -1.0}
    supported = sum(1 for _, label in labels if label == "Supported")
    return {"labels": labels, "supported_ratio": supported / max(1, len(labels))}
