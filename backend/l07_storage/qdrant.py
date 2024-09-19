"""L7: Qdrant via raw client + LC embeddings. Flat {doc, chunk_id, text} payloads.

langchain-qdrant was dropped on purpose: it only round-trips its own
"page_content"/"metadata" keys and silently drops this contract ([?#0] bug).
"""
import logging
import uuid
from copy import deepcopy

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from backend.config import settings
from backend.l06_embedding.bge import get_embeddings

_logger = logging.getLogger(__name__)
_client_singleton = None  # ponytail: per-process singleton; reuse across add/search


def _client() -> QdrantClient:
    global _client_singleton
    if _client_singleton is None:
        kwargs = {"url": settings.vector_base_url}
        if settings.vector_api_key:
            kwargs["api_key"] = settings.vector_api_key
        _client_singleton = QdrantClient(**kwargs)
    return _client_singleton


def ensure_collection(dim: int) -> None:
    c = _client()
    if not c.collection_exists(settings.vector_collection):
        c.create_collection(
            settings.vector_collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def add_docs(texts: list[str], payloads: list[dict], vectors: list[list[float]] | None = None) -> None:
    if not texts:
        return  # ponytail: empty batch (all chunks filtered by L3) — no collection
    if vectors is None:
        vectors = get_embeddings(settings.embed_model).embed_documents([t[:2000] for t in texts])
    ensure_collection(len(vectors[0]))
    # ponytail: fail-closed — missing allowed_groups => [] not ["public"]; caller (api.py) always passes groups
    _client().upsert(settings.vector_collection, [
        PointStruct(id=str(uuid.uuid4()), vector=v,
                    payload={"doc": p["doc"], "chunk_id": p["chunk_id"], "text": p["text"][:2000],
                             "allowed_groups": list(p.get("allowed_groups") or [])})
        for v, p in zip(vectors, payloads)
    ])


def search(query: str, top_k: int, qfilter: Filter | None = None) -> list[dict]:
    try:
        qv = get_embeddings(settings.embed_model).embed_query(query)
        hits = _client().query_points(
            collection_name=settings.vector_collection, query=qv,
            limit=top_k, query_filter=qfilter).points
    except Exception as e:
        _logger.warning("qdrant search failed -> []: %s", e)
        return []
    return [{"doc": h.payload.get("doc", "?"), "chunk_id": h.payload.get("chunk_id", 0),
             "text": h.payload.get("text", ""), "score": h.score} for h in hits]


def fetch_by_doc(doc: str, groups: list[str], n: int) -> list[dict]:
    """Top-n chunks of one doc, ACL-respecting. Feeds graph/SQL agents."""
    from backend.l14_security.acl import groups_filter

    base = groups_filter(groups)
    filt = deepcopy(base)
    if filt.must is None:
        filt.must = []
    filt.must.append(FieldCondition(key="doc", match=MatchValue(value=doc)))
    pts, _ = _client().scroll(settings.vector_collection, scroll_filter=filt,
                              limit=n, with_payload=True)
    # ponytail: scroll has no relevance score; 0.5 placeholder ignored by RRF rank (not score)
    return [{"doc": p.payload.get("doc", "?"), "chunk_id": p.payload.get("chunk_id", 0),
             "text": p.payload.get("text", ""), "score": 0.5} for p in pts]


def reset_collection() -> None:
    c = _client()
    if c.collection_exists(settings.vector_collection):
        c.delete_collection(settings.vector_collection)