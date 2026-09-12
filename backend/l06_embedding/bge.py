"""L6: BGE-M3 via langchain-huggingface. Module singleton — ST load is expensive."""
from langchain_huggingface import HuggingFaceEmbeddings

from backend.l22_ragops.quant import quantize_dynamic_if_enabled

_embeddings = None


def get_embeddings(model_name: str) -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None or _embeddings.model_name != model_name:
        _embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"trust_remote_code": True},
            encode_kwargs={"normalize_embeddings": True},
        )
        quantize_dynamic_if_enabled(_embeddings._client)
    return _embeddings
