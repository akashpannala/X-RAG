"""L7 Storage factory — API first (Supabase pgvector) → Local fallback (Qdrant)."""
from backend.config import settings


def _try_pgvector():
    """Try Supabase pgvector first (API)."""
    if settings.db_provider in ("postgres", "supabase") and settings.db_url:
        try:
            import psycopg
            from pgvector.psycopg import register_vector

            conn = psycopg.connect(settings.db_url, connect_timeout=5)
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            from backend.l07_storage.pgvector import (
                add_docs,
                search,
                fetch_by_doc,
                reset_collection,
            )
            return add_docs, search, fetch_by_doc, reset_collection
        except Exception:
            return None


def _try_qdrant():
    """Try Qdrant local/Cloud second (fallback)."""
    try:
        from qdrant_client import QdrantClient

        kwargs = {"url": settings.vector_base_url}
        if settings.vector_api_key:
            kwargs["api_key"] = settings.vector_api_key
        QdrantClient(**kwargs).get_collections()
        from backend.l07_storage.qdrant import (
            add_docs,
            search,
            fetch_by_doc,
            reset_collection,
        )
        return add_docs, search, fetch_by_doc, reset_collection
    except Exception:
        return None


# Try API first (Supabase pgvector), then local Qdrant
_pgvector = _try_pgvector()
if _pgvector:
    add_docs, search, fetch_by_doc, reset_collection = _pgvector
else:
    _qdrant = _try_qdrant()
    if _qdrant:
        add_docs, search, fetch_by_doc, reset_collection = _qdrant
    else:
        raise RuntimeError("No vector store available (tried Supabase pgvector, then Qdrant)")

__all__ = ["add_docs", "search", "fetch_by_doc", "reset_collection"]