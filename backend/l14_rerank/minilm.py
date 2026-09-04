"""L14: MiniLM single-stage rerank (Quick mode). Cascade second stage = Phase 3."""
from sentence_transformers import CrossEncoder

_model = None


def get_reranker(name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    global _model
    if _model is None:
        _model = CrossEncoder(name)
    return _model


def rerank(query: str, hits: list[dict], top_n: int) -> list[dict]:
    if not hits:
        return hits
    scores = get_reranker().predict([(query, h["text"]) for h in hits])
    ranked = sorted(zip(scores, hits), key=lambda x: float(x[0]), reverse=True)
    return [h for _, h in ranked[:top_n]]
