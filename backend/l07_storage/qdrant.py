"""L7: Qdrant via raw client + LC embeddings. Flat {doc, chunk_id, text} payloads.

langchain-qdrant was dropped on purpose: it only round-trips its own
"page_content"/"metadata" keys and silently drops this contract ([?#0] bug).
"""
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.config import settings
from backend.l06_embedding.bge import get_embeddings


def _client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(dim: int) -> None:
    c = _client()
    if not c.collection_exists(settings.qdrant_collection):
        c.create_collection(
            settings.qdrant_collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def add_docs(texts: list[str], payloads: list[dict]) -> None:
    vecs = get_embeddings(settings.embed_model).embed_documents([t[:2000] for t in texts])
    ensure_collection(len(vecs[0]))
    _client().upsert(settings.qdrant_collection, [
        PointStruct(id=str(uuid.uuid4()), vector=v,
                    payload={"doc": p["doc"], "chunk_id": p["chunk_id"], "text": p["text"][:2000]})
        for v, p in zip(vecs, payloads)
    ])


def search(query: str, top_k: int) -> list[dict]:
    try:
        qv = get_embeddings(settings.embed_model).embed_query(query)
        hits = _client().query_points(
            collection_name=settings.qdrant_collection, query=qv, limit=top_k).points
    except Exception:
        return []
    return [{"doc": h.payload.get("doc", "?"), "chunk_id": h.payload.get("chunk_id", 0),
             "text": h.payload.get("text", ""), "score": h.score} for h in hits]


def reset_collection() -> None:
    c = _client()
    if c.collection_exists(settings.qdrant_collection):
        c.delete_collection(settings.qdrant_collection)
