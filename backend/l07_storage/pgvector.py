"""L7: Supabase pgvector via psycopg. Flat {doc, chunk_id, text} payloads with ACL."""
import json
import logging
import os
import socket
import threading
import uuid

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

from backend.config import settings
from backend.errors import ConfigError, XRAGError, classify_db_error
from backend.l06_embedding.bge import get_embeddings

_logger = logging.getLogger(__name__)
_conn_singleton = None
_lock = threading.Lock()  # singleton connection: serialize probes/statements across threads

TABLE = "vectors"

_TCP_USER_TIMEOUT = 0x18  # Linux: abort after N ms of unacked writes (stale pooler conn)
_TCP_KEEPIDLE = 4


def _tune(conn) -> None:
    try:
        fd2 = os.dup(conn.pgconn.socket)
    except OSError:
        return
    s = None
    try:
        s = socket.socket(fileno=fd2)
        s.setsockopt(socket.IPPROTO_TCP, _TCP_USER_TIMEOUT, 10000)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        s.setsockopt(socket.IPPROTO_TCP, _TCP_KEEPIDLE, 30)
    except OSError:
        pass
    finally:
        if s is not None:
            s.detach()
        try:
            os.close(fd2)
        except OSError:
            pass


def _reset_conn() -> None:
    global _conn_singleton
    old, _conn_singleton = _conn_singleton, None
    if old is not None:
        try:
            old.close()
        except Exception:
            pass


def _conn():
    global _conn_singleton
    if _conn_singleton is not None:
        try:
            if _conn_singleton.closed:
                _reset_conn()
            else:
                # fast-fail + end any idle-in-transaction (pooler may have dropped us)
                _conn_singleton.execute("SELECT 1")
                _conn_singleton.rollback()
                return _conn_singleton
        except Exception:
            _reset_conn()
    db_url = settings.db_url or ""
    if not db_url.startswith("postgresql://") and not db_url.startswith("postgres://"):
        raise ConfigError(
            "DB_URL must be a postgresql:// URL for pgvector",
            hint="aws-deploy is pgvector-only; use the Supabase IPv4 pooler URL",
        )
    try:
        _conn_singleton = psycopg.connect(db_url, row_factory=dict_row, connect_timeout=10)
        _tune(_conn_singleton)
        _ensure_schema(_conn_singleton)  # extension + tables before type registration
        register_vector(_conn_singleton)
    except XRAGError:
        _reset_conn()
        raise
    except Exception as e:
        _reset_conn()
        raise classify_db_error(e) from e
    return _conn_singleton


def _ensure_schema(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE EXTENSION IF NOT EXISTS vector;
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id UUID PRIMARY KEY,
                    doc TEXT NOT NULL,
                    chunk_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    allowed_groups JSONB NOT NULL DEFAULT '[]'::jsonb,
                    embedding VECTOR(1024)
                );
                CREATE INDEX IF NOT EXISTS {TABLE}_embedding_idx ON {TABLE} USING hnsw (embedding vector_cosine_ops);
                CREATE INDEX IF NOT EXISTS {TABLE}_doc_idx ON {TABLE} (doc);
                CREATE INDEX IF NOT EXISTS {TABLE}_groups_idx ON {TABLE} USING GIN (allowed_groups);
            """)
            conn.commit()
    except Exception as e:
        raise classify_db_error(e) from e


def add_docs(texts: list[str], payloads: list[dict], vectors: list[list[float]] | None = None) -> None:
    if not texts:
        return
    if vectors is None:
        vectors = get_embeddings(settings.embed_model).embed_documents([t[:2000] for t in texts])

    last = None
    with _lock:
        for attempt in (1, 2):
            try:
                conn = _conn()
                with conn.cursor() as cur:
                    for v, p in zip(vectors, payloads):
                        cur.execute(
                            f"INSERT INTO {TABLE} (id, doc, chunk_id, text, allowed_groups, embedding) VALUES (%s,%s,%s,%s,%s,%s)",
                            (
                                str(uuid.uuid4()),
                                p["doc"],
                                p["chunk_id"],
                                p["text"][:2000],
                                json.dumps(p.get("allowed_groups") or []),
                                v,
                            ),
                        )
                    conn.commit()
                return
            except (psycopg.OperationalError, psycopg.InterfaceError, OSError) as e:
                last = e
                _logger.warning("add_docs attempt %d failed: %s", attempt, e)
                _reset_conn()
    raise classify_db_error(last) from last


def delete_doc(doc: str) -> None:
    """Replace-on-reingest: drop all vectors of a doc before re-adding it."""
    with _lock:
        last = None
        for attempt in (1, 2):
            try:
                conn = _conn()
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {TABLE} WHERE doc = %s", (doc,))
                conn.commit()
                return
            except (psycopg.OperationalError, psycopg.InterfaceError, OSError) as e:
                last = e
                _logger.warning("delete_doc attempt %d failed: %s", attempt, e)
                _reset_conn()
    raise classify_db_error(last) from last


def search(query: str, top_k: int, qfilter: object | None = None) -> list[dict]:
    """qfilter is a dict ``{"groups": [...], "doc": ...}`` from groups_filter()."""
    qv = get_embeddings(settings.embed_model).embed_query(query)
    with _lock:
        try:
            conn = _conn()
        except Exception as e:
            raise classify_db_error(e) from e
        with conn.cursor() as cur:
            where_clauses = []
            filter_params: list = []

            groups = None
            doc = None
            if isinstance(qfilter, dict):
                groups = qfilter.get("groups")
                doc = qfilter.get("doc")
            elif qfilter is not None and hasattr(qfilter, "must"):
                # Backwards-compatible with pre-aws-deploy Qdrant-shaped filters
                for cond in qfilter.must or []:
                    match = getattr(cond, "match", None)
                    if getattr(cond, "key", None) == "allowed_groups" and hasattr(match, "any"):
                        groups = list(match.any)

            if doc:
                where_clauses.append("doc = %s")
                filter_params.append(doc)
            if groups:
                placeholders = ",".join(["%s"] * len(groups))
                where_clauses.append(f"allowed_groups ?| ARRAY[{placeholders}]")
                filter_params.extend(groups)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            qv_s = str(qv)
            params = [qv_s] + filter_params + [qv_s, top_k]
            try:
                cur.execute(
                    f"""
                    SELECT doc, chunk_id, text, 1 - (embedding <=> %s::vector) AS score
                    FROM {TABLE}
                    {where_sql}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
            except Exception as e:
                raise classify_db_error(e) from e

    return [
        {"doc": r["doc"], "chunk_id": r["chunk_id"], "text": r["text"], "score": float(r["score"])}
        for r in rows
    ]


def fetch_by_doc(doc: str, groups: list[str], n: int) -> list[dict]:
    """Top-n chunks of one doc, ACL-respecting."""
    with _lock:
        try:
            conn = _conn()
        except Exception as e:
            raise classify_db_error(e) from e
        with conn.cursor() as cur:
            params = [doc]
            where = "WHERE doc = %s"
            if groups:
                placeholders = ",".join(["%s"] * len(groups))
                where += f" AND allowed_groups ?| ARRAY[{placeholders}]"
                params.extend(groups)
            try:
                cur.execute(
                    f"SELECT doc, chunk_id, text FROM {TABLE} {where} LIMIT %s",
                    params + [n],
                )
                rows = cur.fetchall()
            except Exception as e:
                raise classify_db_error(e) from e
    return [{"doc": r["doc"], "chunk_id": r["chunk_id"], "text": r["text"], "score": 0.5} for r in rows]


def reset_collection() -> None:
    with _lock:
        try:
            conn = _conn()
        except Exception as e:
            raise classify_db_error(e) from e
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
            conn.commit()
        _ensure_schema(conn)  # leave a usable empty table behind