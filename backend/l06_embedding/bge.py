"""L6a: Embeddings — BGE-M3 local or remote (Jina/Voyage/Cohere/Choreo) via unified config."""
from backend.config import settings, _resolve_embed_url

_embeddings = None


def get_embeddings(model_name: str):
    """Returns object with embed_documents(list[str]) and embed_query(str).
    If EMBED_BASE_URL / EMBED_PROVIDER is remote, uses HTTP; else local HF."""
    global _embeddings
    embed_url = _resolve_embed_url()
    provider = settings.embed_provider.lower()

    if provider in ("jina", "voyage", "cohere", "choreo") or embed_url:
        url = embed_url.rstrip("/")
        # lightweight shim with same surface as HuggingFaceEmbeddings
        class _Remote:
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                import httpx

                if provider == "jina":
                    payload = {"input": texts, "model": model_name}
                    endpoint = f"{url}/embeddings"
                elif provider == "voyage":
                    payload = {"input": texts, "model": model_name}
                    endpoint = f"{url}/embeddings"
                elif provider == "cohere":
                    payload = {"texts": texts, "model": model_name, "input_type": "search_document"}
                    endpoint = f"{url}/embed"
                else:
                    # choreo/generic - assume /embed with {"texts": [...]}
                    payload = {"texts": texts}
                    endpoint = f"{url}/embed"

                headers = {}
                if settings.embed_api_key:
                    headers["Authorization"] = f"Bearer {settings.embed_api_key}"
                r = httpx.post(endpoint, json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                data = r.json()
                # Handle different response formats
                if "data" in data:
                    return [d["embedding"] for d in data["data"]]
                if "vectors" in data:
                    return data["vectors"]
                if "embeddings" in data:
                    return data["embeddings"]
                return data  # fallback

            def embed_query(self, text: str) -> list[float]:
                return self.embed_documents([text])[0]

            @property
            def model_name(self):
                return model_name

        return _Remote()

    if _embeddings is None or getattr(_embeddings, "model_name", None) != model_name:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"trust_remote_code": True},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings