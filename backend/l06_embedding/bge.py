"""L6a: Embeddings — remote API only (Jina / Voyage / Cohere).

No local BGE-M3 model and no remote→local fallback on ``aws-deploy``. Provider
failures raise ``EmbeddingError``/``RateLimitError`` with actionable messages.
"""
import logging

import httpx

from backend.config import _resolve_embed_url, settings
from backend.errors import ConfigError, classify_provider_error

_logger = logging.getLogger(__name__)
_EMBED_PROVIDERS = ("jina", "voyage", "cohere")
_embeddings: dict[str, object] = {}


def _endpoint(provider: str, url: str) -> str:
    base = url.rstrip("/")
    return f"{base}/embed" if provider == "cohere" else f"{base}/embeddings"


class _Remote:
    def __init__(self, provider: str, url: str, model_name: str):
        self.provider = provider
        self.url = url
        self.model_name = model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        provider = self.provider
        if provider == "cohere":
            payload = {"texts": texts, "model": self.model_name, "input_type": "search_document"}
        else:
            payload = {"input": texts, "model": self.model_name}
        headers = {"Content-Type": "application/json"}
        if settings.embed_api_key:
            headers["Authorization"] = f"Bearer {settings.embed_api_key}"
        try:
            r = httpx.post(_endpoint(provider, self.url), json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise classify_provider_error(
                e, kind="Embedding", provider=provider, model=self.model_name
            ) from e

        if "data" in data:
            vectors = [d["embedding"] for d in data["data"]]
        elif "vectors" in data:
            vectors = data["vectors"]
        elif "embeddings" in data:
            vectors = data["embeddings"]
        else:
            raise classify_provider_error(
                ValueError(f"unexpected embedding response keys: {list(data)}"),
                kind="Embedding", provider=provider, model=self.model_name,
            )
        if len(vectors) != len(texts):
            raise classify_provider_error(
                ValueError(f"embedding count mismatch: {len(vectors)} != {len(texts)}"),
                kind="Embedding", provider=provider, model=self.model_name,
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        if self.provider == "cohere":
            # Cohere distinguishes query/document input types.
            headers = {"Content-Type": "application/json"}
            if settings.embed_api_key:
                headers["Authorization"] = f"Bearer {settings.embed_api_key}"
            payload = {"texts": [text], "model": self.model_name, "input_type": "search_query"}
            try:
                r = httpx.post(_endpoint(self.provider, self.url), json=payload,
                               headers=headers, timeout=60)
                r.raise_for_status()
                data = r.json()
                if "embeddings" in data:
                    return data["embeddings"][0]
                if "data" in data:
                    return data["data"][0]["embedding"]
                raise ValueError(f"unexpected embedding response keys: {list(data)}")
            except Exception as e:
                raise classify_provider_error(
                    e, kind="Embedding", provider=self.provider, model=self.model_name
                ) from e
        return self.embed_documents([text])[0]


def get_embeddings(model_name: str):
    """Remote embedding client. Raises ``ConfigError`` when misconfigured."""
    provider = (settings.embed_provider or "").strip().lower()
    if provider not in _EMBED_PROVIDERS:
        raise ConfigError(
            f"Unsupported EMBED_PROVIDER={settings.embed_provider!r}",
            hint="aws-deploy supports jina/voyage/cohere (no local BGE fallback)",
        )
    url = _resolve_embed_url()
    if not url:
        raise ConfigError(
            "EMBED_BASE_URL is required for the remote embedding provider",
            hint="set EMBED_BASE_URL (Jina defaults to https://api.jina.ai/v1)",
        )
    if not settings.embed_api_key:
        raise ConfigError(
            "EMBED_API_KEY is required for the remote embedding provider",
            hint="set the provider API key in .env",
        )
    key = f"{provider}|{url}|{model_name}"
    if key not in _embeddings:
        _embeddings[key] = _Remote(provider, url, model_name)
    return _embeddings[key]
