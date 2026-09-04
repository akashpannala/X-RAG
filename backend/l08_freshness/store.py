"""L8: sha256 freshness + SQLite meta (PRD §7: users, documents, conversations)."""
import hashlib
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, groups_json TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, filename TEXT UNIQUE, allowed_groups_json TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS conversations(
  id INTEGER PRIMARY KEY, user_id INTEGER, query TEXT, answer TEXT,
  mode TEXT, score REAL, contexts_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def meta_conn(path: str):
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    # migrate pre-Phase-2 DBs that lack the new tables/columns
    cols = {r[1] for r in c.execute("PRAGMA table_info(documents)")}
    if "allowed_groups_json" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN allowed_groups_json TEXT DEFAULT '[\"public\"]'")
    ccols = {r[1] for r in c.execute("PRAGMA table_info(conversations)")}
    if "contexts_json" not in ccols:
        c.execute("ALTER TABLE conversations ADD COLUMN contexts_json TEXT")
    c.commit()
    return c


def jdump(groups: list[str]) -> str:
    return json.dumps(groups)


def jload(s: str | None) -> list[str]:
    try:
        return json.loads(s or "[]")
    except Exception:
        return []
