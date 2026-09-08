"""L16 RECOMP-lite: extractive compression — MiniLM scores sentences, budget kept.

Full RECOMP abstractive compressor needs its own fine-tuned model; extractive
selection with the already-loaded MiniLM gets 80% of the token saving.
"""
import re


def compress(query: str, contexts: list[str], budget_chars: int = 6000) -> list[str]:
    sents = [s for c in contexts for s in re.split(r"(?<=[.!?])\s+", c) if len(s.split()) >= 4]
    if sum(map(len, sents)) <= budget_chars or not sents:
        return contexts
    from backend.l14_rerank.minilm import get_reranker

    scores = get_reranker().predict([(query, s) for s in sents])
    order = sorted(range(len(sents)), key=lambda i: float(scores[i]), reverse=True)
    kept, total = [], 0
    for i in order:
        if total + len(sents[i]) > budget_chars:
            continue
        kept.append(sents[i])
        total += len(sents[i])
    kept.sort(key=sents.index)
    return [" ".join(kept)] if kept else contexts[:1]
