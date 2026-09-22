"""L14: MiniLM single-stage rerank (Quick mode). Cascade second stage = Phase 3."""
import math

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


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def rerank(query: str, hits: list[dict], top_n: int) -> list[dict]:
    if not hits:
        return hits
    try:
        scores = get_reranker().predict([(query, h["text"]) for h in hits])
    except Exception:
        return hits  # MiniLM is the ultimate fallback — return as-is rather than crash
    ranked = sorted(zip(scores, hits), key=lambda x: float(x[0]), reverse=True)
    for sc, h in ranked:
        # CrossEncoder emits raw logits; confident() and cascade() document a
        # 0-1 reranker scale — map through sigmoid before writing back.
        h["score"] = _sigmoid(float(sc))
    return [h for _, h in ranked[:top_n]]
