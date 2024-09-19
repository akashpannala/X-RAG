"""L20: SQLite answer cache (cosine>0.96 short-circuit) + embedding LRU.

Keys are `<queryhash>|<mode>|<groups>` so each role/mode partition is
isolated; clear() runs on every ingest so permission changes can't leak
through stale rows.
"""
import functools
import hashlib
import json
import sqlite3

import numpy as np

from backend.config import settings
from backend.l06_embedding.bge import get_embeddings

SCHEMA = """CREATE TABLE IF NOT EXISTS answer_cache(
  key TEXT PRIMARY KEY, answer TEXT, cites_json TEXT, qvec_json TEXT)"""

_PARTITION_CAP = 500  # per <mode>|<groups> partition, not global


def _conn():
    c = sqlite3.connect(settings.db_path)
    c.execute(SCHEMA)
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
        # filter in SQL by the partition suffix — exact tail match, not endswith, so a
        # group name can't collide with another at a delimiter boundary
        rows = con.execute(
            "SELECT key, answer, cites_json, qvec_json FROM answer_cache "
            "WHERE key LIKE ? ESCAPE '\\'",
            (f"%{suffix.replace('%', r'\%').replace('_', r'\_')}",),
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
        con.execute(
            "INSERT OR REPLACE INTO answer_cache(key, answer, cites_json, qvec_json) VALUES (?,?,?,?)",
            (_key(query, mode, groups), answer,
             json.dumps(cites), json.dumps(embed_cached(query))),
        )
        # evict per-partition: keep the most recent _PARTITION_CAP rows for this mode|groups
        suffix = _suffix(mode, groups)
        con.execute(
            "DELETE FROM answer_cache WHERE key LIKE ? ESCAPE '\\' "
            "AND rowid NOT IN (SELECT rowid FROM answer_cache WHERE key LIKE ? ESCAPE '\\' "
            "ORDER BY rowid DESC LIMIT ?)",
            (f"%{suffix.replace('%', r'\%').replace('_', r'\_')}",
             f"%{suffix.replace('%', r'\%').replace('_', r'\_')}", _PARTITION_CAP),
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
