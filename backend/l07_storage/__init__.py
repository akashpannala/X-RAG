"""L7 Storage — pgvector only (Supabase/Postgres). No local Qdrant fallback."""
from backend.config import settings
from backend.errors import ConfigError, XRAGError, classify_db_error


def _load_pgvector():
    if not settings.is_postgres or not settings.db_url:
        raise ConfigError(
            "pgvector requires DB_PROVIDER=postgres|supabase and DB_URL",
            hint="aws-deploy is pgvector-only; set Supabase/Postgres in .env",
        )
    try:
        from backend.l07_storage.pgvector import (
            add_docs,
            delete_doc,
            fetch_by_doc,
            reset_collection,
            search,
        )
        from backend.l07_storage.pgvector import _conn

        _conn()  # fail fast with an actionable DB/pgvector error
    except XRAGError:
        raise
    except Exception as e:
        raise classify_db_error(e) from e
    return add_docs, delete_doc, search, fetch_by_doc, reset_collection


add_docs, delete_doc, search, fetch_by_doc, reset_collection = _load_pgvector()

__all__ = ["add_docs", "delete_doc", "search", "fetch_by_doc", "reset_collection"]
