"""Reranker provider — Jina API only. No local BGE/MiniLM fallback."""
import logging
from typing import List, Tuple

import httpx

from backend.config import _resolve_rerank_url, settings
from backend.errors import ConfigError, classify_provider_error

_logger = logging.getLogger(__name__)


class JinaReranker:
    """Jina Reranker API v1 (/v1/rerank)."""

    def __init__(self, base_url: str, model: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def rerank(self, query: str, docs: List[str], top_n: int) -> List[Tuple[int, float]]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"query": query, "documents": docs, "top_n": top_n, "model": self.model}
        try:
            r = httpx.post(f"{self.base_url}/rerank", json=payload, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            _logger.warning("Jina rerank API failed: %s", e)
            raise classify_provider_error(
                e, kind="Rerank", provider="jina", model=self.model
            ) from e
        results = data.get("results", [])
        return [(item["index"], float(item["relevance_score"])) for item in results]


def get_reranker_provider() -> JinaReranker:
    """Return the remote reranker. Raises instead of degrading to a local model."""
    provider = (settings.rerank_provider or "").strip().lower()
    if provider != "jina":
        raise ConfigError(
            f"Unsupported RERANK_PROVIDER={settings.rerank_provider!r}",
            hint="aws-deploy supports the Jina rerank API only",
        )
    if not settings.rerank_api_key:
        raise ConfigError(
            "RERANK_API_KEY is required for the Jina reranker",
            hint="set RERANK_API_KEY in .env (no local reranker fallback)",
        )
    url = _resolve_rerank_url()
    if not url:
        raise ConfigError("RERANK_BASE_URL is required for the Jina reranker")
    return JinaReranker(url, settings.rerank_model, settings.rerank_api_key)
