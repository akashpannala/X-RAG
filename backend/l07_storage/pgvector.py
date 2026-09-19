"""L7: Supabase pgvector via psycopg. Flat {doc, chunk_id, text} payloads with ACL."""
import json
import logging
import uuid

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

from backend.config import settings
from backend.l06_embedding.bge import get_embeddings

_logger = logging.getLogger(__name__)
_conn_singleton = None

TABLE = "vectors"

def _conn():
    global _conn_singleton
    if _conn_singleton is None:
        db_url = settings.db_url or ""
        if not db_url.startswith("postgresql://") and not db_url.startswith("postgres://"):
            raise RuntimeError("DATABASE_URL must be postgresql:// for pgvector")
        _conn_singleton = psycopg.connect(db_url, row_factory=dict_row)
        register_vector(_conn_singleton)
        _ensure_schema(_conn_singleton)
    return _conn_singleton


def _ensure_schema(conn) -> None:
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


def add_docs(texts: list[str], payloads: list[dict], vectors: list[list[float]] | None = None) -> None:
    if not texts:
        return
    if vectors is None:
        vectors = get_embeddings(settings.embed_model).embed_documents([t[:2000] for t in texts])

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


def search(query: str, top_k: int, qfilter: object | None = None) -> list[dict]:
    """qfilter can be Qdrant Filter (from groups_filter) or dict with 'doc'/'groups'."""
    try:
        qv = get_embeddings(settings.embed_model).embed_query(query)
        conn = _conn()
        with conn.cursor() as cur:
            where_clauses = []
            filter_params: list = []

            # Extract groups from Qdrant Filter if passed
            groups = None
            doc = None
            if qfilter is not None:
                # Qdrant Filter object from groups_filter()
                if hasattr(qfilter, "must"):
                    for cond in qfilter.must or []:
                        if hasattr(cond, "key") and cond.key == "allowed_groups" and hasattr(cond, "match"):
                            match = cond.match
                            if hasattr(match, "any"):
                                groups = list(match.any)
                # Dict format
                elif isinstance(qfilter, dict):
                    groups = qfilter.get("groups")
                    doc = qfilter.get("doc")

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
        _logger.warning("pgvector search failed -> []: %s", e)
        return []

    return [
        {"doc": r["doc"], "chunk_id": r["chunk_id"], "text": r["text"], "score": float(r["score"])}
        for r in rows
    ]


def fetch_by_doc(doc: str, groups: list[str], n: int) -> list[dict]:
    """Top-n chunks of one doc, ACL-respecting."""
    try:
        conn = _conn()
        with conn.cursor() as cur:
            params = [doc]
            where = "WHERE doc = %s"
            if groups:
                placeholders = ",".join(["%s"] * len(groups))
                where += f" AND allowed_groups ?| ARRAY[{placeholders}]"
                params.extend(groups)
            cur.execute(
                f"SELECT doc, chunk_id, text FROM {TABLE} {where} LIMIT %s",
                params + [n],
            )
            rows = cur.fetchall()
    except Exception:
        return []
    return [{"doc": r["doc"], "chunk_id": r["chunk_id"], "text": r["text"], "score": 0.5} for r in rows]


def reset_collection() -> None:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.commit()