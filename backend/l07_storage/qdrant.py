"""L7: Qdrant via raw client + LC embeddings. Flat {doc, chunk_id, text} payloads.

langchain-qdrant was dropped on purpose: it only round-trips its own
"page_content"/"metadata" keys and silently drops this contract ([?#0] bug).
"""
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from backend.config import settings
from backend.l06_embedding.bge import get_embeddings


def _client() -> QdrantClient:
    kwargs = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


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
                    payload={"doc": p["doc"], "chunk_id": p["chunk_id"], "text": p["text"][:2000],
                             "allowed_groups": list(p.get("allowed_groups", ["public"]))})
        for v, p in zip(vecs, payloads)
    ])


def search(query: str, top_k: int, qfilter: Filter | None = None) -> list[dict]:
    try:
        qv = get_embeddings(settings.embed_model).embed_query(query)
        hits = _client().query_points(
            collection_name=settings.qdrant_collection, query=qv,
            limit=top_k, query_filter=qfilter).points
    except Exception:
        return []
    return [{"doc": h.payload.get("doc", "?"), "chunk_id": h.payload.get("chunk_id", 0),
             "text": h.payload.get("text", ""), "score": h.score} for h in hits]


def fetch_by_doc(doc: str, groups: list[str], n: int) -> list[dict]:
    """Top-n chunks of one doc, ACL-respecting. Feeds graph/SQL agents."""
    from backend.l15_security.acl import groups_filter

    filt = groups_filter(groups)
    filt.must.append(FieldCondition(key="doc", match=MatchValue(value=doc)))
    pts, _ = _client().scroll(settings.qdrant_collection, scroll_filter=filt,
                              limit=n, with_payload=True)
    return [{"doc": p.payload.get("doc", "?"), "chunk_id": p.payload.get("chunk_id", 0),
             "text": p.payload.get("text", ""), "score": 0.5} for p in pts]


def reset_collection() -> None:
    c = _client()
    if c.collection_exists(settings.qdrant_collection):
        c.delete_collection(settings.qdrant_collection)
