"""L6: BGE-M3 via langchain-huggingface. Supports local or remote (Choreo/VPS) via .env."""
from backend.config import settings

_embeddings = None


def get_embeddings(model_name: str):
    """Returns object with embed_documents(list[str]) and embed_query(str).
    If EMBED_URL / EMBED_PROVIDER==choreo is set, uses remote HTTP; else local HF."""
    global _embeddings
    if settings.embed_url or settings.embed_provider == "choreo":
        url = (settings.embed_url or "").rstrip("/") or "http://localhost:8002"
        # lightweight shim with same surface as HuggingFaceEmbeddings
        class _Remote:
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                import httpx
                r = httpx.post(f"{url}/embed", json={"texts": texts}, timeout=60)
                r.raise_for_status()
                return r.json()["vectors"]
            def embed_query(self, text: str) -> list[float]:
                return self.embed_documents([text])[0]
            @property
            def model_name(self): return model_name
        return _Remote()
    if _embeddings is None or getattr(_embeddings, "model_name", None) != model_name:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"trust_remote_code": True},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings
