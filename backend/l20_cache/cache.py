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


def _conn():
    c = sqlite3.connect(settings.sqlite_path)
    c.execute(SCHEMA)
    return c


def _key(query: str, mode: str, groups: list[str]) -> str:
    qh = hashlib.sha256(query.encode()).hexdigest()
    return f"{qh}|{mode}|{','.join(sorted(groups))}"


@functools.lru_cache(maxsize=512)
def _embed_cached(model_name: str, text: str) -> tuple:
    return tuple(get_embeddings(model_name).embed_query(text))


def embed_cached(text: str) -> list[float]:
    return list(_embed_cached(settings.embed_model, text))


def lookup(query: str, mode: str, groups: list[str]) -> tuple[str, list[str]] | None:
    """Same mode+groups partition only; cosine>0.96 catches paraphrases."""
    suffix = f"|{mode}|{','.join(sorted(groups))}"
    qv = np.array(embed_cached(query))
    con = _conn()
    try:
        rows = con.execute("SELECT key, answer, cites_json, qvec_json FROM answer_cache").fetchall()
    finally:
        con.close()
    best, best_sim = None, 0.0
    for key, ans, cites, qvec in rows:
        if not key.endswith(suffix):
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
        con.execute("DELETE FROM answer_cache WHERE key NOT IN "
                    "(SELECT key FROM answer_cache ORDER BY rowid DESC LIMIT 500)")
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
