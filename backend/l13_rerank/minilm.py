"""L14: MiniLM single-stage rerank (Quick mode). Cascade second stage = Phase 3."""
from sentence_transformers import CrossEncoder

from backend.config import settings

_model = None
_model_name = settings.reranker_model if hasattr(settings, "reranker_model") else "cross-encoder/ms-marco-MiniLM-L-6-v2"


def get_reranker(name: str | None = None):
    global _model, _model_name
    if name:
        _model_name = name
    if _model is None:
        _model = CrossEncoder(_model_name)
    return _model


def rerank(query: str, hits: list[dict], top_n: int) -> list[dict]:
    if not hits:
        return hits
    try:
        scores = get_reranker().predict([(query, h["text"]) for h in hits])
    except Exception:
        return hits  # MiniLM is the ultimate fallback — return as-is rather than crash
    ranked = sorted(zip(scores, hits), key=lambda x: float(x[0]), reverse=True)
    for sc, h in ranked:
        h["score"] = float(sc)  # write rerank score back so downstream gates use it
    return [h for _, h in ranked[:top_n]]
