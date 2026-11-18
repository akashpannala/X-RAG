"""L20: answer cache (cosine>0.96 short-circuit) + embedding LRU.

Storage is Postgres/Supabase in deployment (same managed DB as metadata);
SQLite is used only when ``DB_PROVIDER=sqlite`` (unit tests). There is no
silent fallback between backends.

Keys are `<queryhash>|<mode>|<groups>` so each role/mode partition is
isolated; clear() runs on every ingest so permission changes can't leak
through stale rows.
"""
import functools
import hashlib
import json
import logging

import numpy as np

from backend.config import settings
from backend.l06_embedding.bge import get_embeddings

_logger = logging.getLogger(__name__)

SCHEMA = """CREATE TABLE IF NOT EXISTS answer_cache(
  key TEXT PRIMARY KEY, answer TEXT, cites_json TEXT, qvec_json TEXT)"""

_PARTITION_CAP = 500  # per <mode>|<groups> partition, not global


def _is_pg() -> bool:
    return settings.is_postgres


def _ph() -> str:
    return "%s" if _is_pg() else "?"


def _rowid() -> str:
    return "ctid" if _is_pg() else "rowid"


def _escape_like(value: str) -> str:
    return value.replace("%", r"\%").replace("_", r"\_")


def _conn():
    from backend.l08_freshness.store import meta_conn

    c = meta_conn(settings.db_path)
    try:
        c.execute(SCHEMA)
        c.commit()
    except Exception:
        c.close()
        raise
    return c


def _key(query: str, mode: str, groups: list[str]) -> str:
    qh = hashlib.sha256(query.encode()).hexdigest()
    return f"{qh}|{mode}|{','.join(sorted(groups))}"


def _suffix(mode: str, groups: list[str]) -> str:
    return f"|{mode}|{','.join(sorted(groups))}"


@functools.lru_cache(maxsize=512)
def _embed_cached(model_name: str, text: str) -> tuple:
    return tuple(get_embeddings(model_name).embed_query(text))


def embed_cached(text: str) -> list[float]:
    return list(_embed_cached(settings.embed_model, text))


def lookup(query: str, mode: str, groups: list[str]) -> tuple[str, list[str]] | None:
    """Same mode+groups partition only; cosine>0.96 catches paraphrases."""
    suffix = _suffix(mode, groups)
    qv = np.array(embed_cached(query))
    con = _conn()
    try:
        rows = con.execute(
            f"SELECT key, answer, cites_json, qvec_json FROM answer_cache "
            f"WHERE key LIKE {_ph()} ESCAPE '\\'",
            (f"%{_escape_like(suffix)}",),
        ).fetchall()
    finally:
        con.close()
    best, best_sim = None, 0.0
    for key, ans, cites, qvec in rows:
        if not key.endswith(suffix):  # belt-and-suspenders against LIKE edge cases
            continue
        cv = np.array(json.loads(qvec))
        sim = float(qv @ cv / (np.linalg.norm(qv) * np.linalg.norm(cv) + 1e-9))
        if sim > best_sim:
            best, best_sim = (ans, json.loads(cites)), sim
    return best if best_sim > 0.96 else None


def store(query: str, mode: str, groups: list[str], answer: str, cites: list[str]) -> None:
    con = _conn()
    try:
        ph = _ph()
        con.execute(
            f"INSERT INTO answer_cache(key, answer, cites_json, qvec_json) "
            f"VALUES ({ph},{ph},{ph},{ph}) "
            "ON CONFLICT (key) DO UPDATE SET "
            "answer=EXCLUDED.answer, cites_json=EXCLUDED.cites_json, "
            "qvec_json=EXCLUDED.qvec_json",
            (_key(query, mode, groups), answer, json.dumps(cites), json.dumps(embed_cached(query))),
        )
        suffix = _suffix(mode, groups)
        pattern = f"%{_escape_like(suffix)}%"
        con.execute(
            f"DELETE FROM answer_cache WHERE key LIKE {ph} ESCAPE '\\' "
            f"AND key NOT IN (SELECT key FROM answer_cache WHERE key LIKE {ph} ESCAPE '\\' "
            f"ORDER BY {_rowid()} DESC LIMIT {ph})",
            (pattern, pattern, _PARTITION_CAP),
        )
        con.commit()
    finally:
        con.close()


def clear() -> int:
    """Drop all cached answers. Called on ingest — vectors changed, rows stale."""
    con = _conn()
    try:
        n = con.execute("DELETE FROM answer_cache").rowcount
        con.commit()
        return n
    finally:
        con.close()
