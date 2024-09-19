"""Reranker provider abstraction: Jina API → Local BGE-reranker → Local MiniLM."""
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple

_logger = logging.getLogger(__name__)


class RerankerProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, docs: List[str], top_n: int) -> List[Tuple[int, float]]:
        """Returns [(doc_index, score), ...] sorted by relevance desc."""


class JinaReranker(RerankerProvider):
    """Jina Reranker API v1 (/v1/rerank)."""

    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def rerank(self, query: str, docs: List[str], top_n: int) -> List[Tuple[int, float]]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "query": query,
            "documents": docs,
            "top_n": top_n,
            "model": self.model,
        }
        try:
            r = httpx.post(
                f"{self.base_url}/rerank",
                json=payload,
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            return [(item["index"], float(item["relevance_score"])) for item in results]
        except Exception as e:
            _logger.warning("Jina rerank API failed: %s", e)
            raise


class LocalCrossEncoder(RerankerProvider):
    """Local sentence-transformers CrossEncoder (BGE-reranker or MiniLM)."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._encoder = None

    def _get_encoder(self):
        if self._encoder is None:
            from sentence_transformers import CrossEncoder

            self._encoder = CrossEncoder(self.model_name)
        return self._encoder

    def rerank(self, query: str, docs: List[str], top_n: int) -> List[Tuple[int, float]]:
        encoder = self._get_encoder()
        scores = encoder.predict([(query, d) for d in docs])
        ranked = sorted(enumerate(scores), key=lambda x: float(x[1]), reverse=True)
        return ranked[:top_n]


def get_reranker_provider() -> RerankerProvider:
    """Factory with fallback chain: Jina API → Local BGE-reranker → Local MiniLM."""
    from backend.config import settings

    # 1. Jina API
    if settings.rerank_provider == "jina" and settings.rerank_api_key:
        try:
            return JinaReranker(settings.rerank_base_url, settings.rerank_model, settings.rerank_api_key)
        except Exception as e:
            _logger.warning("JinaReranker init failed, falling back: %s", e)

    # 2. Local BGE-reranker (fallback for jina, or explicit bge)
    if settings.rerank_provider in ("bge", "jina"):
        try:
            return LocalCrossEncoder("BAAI/bge-reranker-v2-m3")
        except Exception as e:
            _logger.warning("Local BGE-reranker init failed, falling back: %s", e)

    # 3. Local MiniLM (final fallback)
    return LocalCrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")