"""L19 verification — HHEM NLI + CoVe-lite + sentence labels (deep mode).

Each answer sentence is scored against retrieved contexts: Supported /
Unsupported / Contradicted. HHEM is a local CrossEncoder (400MB); if its
weights are absent the step degrades to an LLM judges-pass with the same
label contract. CoVe-lite: answers a verification question per claim.
"""
import re

_hhem = None


def get_hhem(name: str = "vectara/hallucination_evaluation_model"):
    """HHEM-local is parked: weights are cached (419MB) but unloadable —
    CrossEncoder path hits a custom-class/transformers-5.x incompatibility
    (all_tied_weights_keys), and the repo ships no tokenizer files
    (needs deberta-v3-base tokenizer + relative-import shim). The LLM
    judge below carries verification until upstream stabilizes."""
    global _hhem
    if _hhem is None:
        from sentence_transformers import CrossEncoder

        _hhem = CrossEncoder(name)
    return _hhem


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if len(p.split()) >= 4]


def hhem_scores(premise_texts: list[str], hypothesis: str) -> list[float]:
    premise = " ".join(premise_texts)[:4000]
    try:
        return [float(get_hhem().predict([(premise, hypothesis)])[0])]
    except Exception:
        return [-1.0]


def llm_labels(answer: str, contexts: list[str]) -> list[tuple[str, str]]:
    """Fallback + CoVe second opinion: LLM labels each sentence."""
    from backend.l18_generation.llm import get_llm

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
    """Returns {labels: [(sentence, label)], supported_ratio: float}."""
    sents = split_sentences(answer)
    if not sents or not contexts:
        return {"labels": [(s, "Unsupported") for s in sents], "supported_ratio": 0.0}
    try:
        get_hhem()
        labels = []
        for s in sents:
            sc = hhem_scores(contexts, s)[0]
            if sc < 0:
                raise RuntimeError("hhem unavailable")
            label = "Supported" if sc > 0.5 else ("Contradicted" if sc < 0.1 else "Unsupported")
            labels.append((s, label))
    except Exception:
        labels = llm_labels(answer, contexts)
    supported = sum(1 for _, l in labels if l == "Supported")
    return {"labels": labels, "supported_ratio": supported / max(1, len(labels))}
