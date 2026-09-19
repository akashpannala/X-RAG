"""L8: sha256 freshness + meta DB (PRD §7: users, documents, conversations)."""
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

_logger = logging.getLogger(__name__)
_schema_done = False  # ponytail: avoid re-running CREATE TABLE ×4 per call (esp. Postgres TCP)

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


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def meta_conn(path: str | None = None):
    """Env-driven: if DB_URL is postgres/supabase, use psycopg; else sqlite at path/DB_PATH.
    Postgres failure falls back to SQLite instead of raising."""
    global _schema_done
    from backend.config import settings

    db_url = (settings.db_url or "").strip()
    if settings.db_provider in ("postgres", "supabase") and db_url and _is_postgres_url(db_url):
        try:
            import psycopg

            c = psycopg.connect(db_url, connect_timeout=5)
        except Exception as e:
            _logger.warning("postgres unavailable, falling back to SQLite: %s", e)
            # fall through to SQLite below
        else:
            if not _schema_done:
                pg_schema = SCHEMA.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY").replace(
                    "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
                for stmt in pg_schema.strip().split(";"):
                    if stmt.strip():
                        c.execute(stmt)
                # migrate pre-Phase-2 Postgres tables that lack new columns (information_schema, not PRAGMA)
                try:
                    has_docs = {r[0] for r in c.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_name='documents'").fetchall()}
                    if "allowed_groups_json" not in has_docs:
                        c.execute("ALTER TABLE documents ADD COLUMN allowed_groups_json TEXT DEFAULT '[\"public\"]'")
                    has_convs = {r[0] for r in c.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_name='conversations'").fetchall()}
                    if "contexts_json" not in has_convs:
                        c.execute("ALTER TABLE conversations ADD COLUMN contexts_json TEXT")
                    c.commit()
                except Exception as e:
                    _logger.warning("postgres migration check failed: %s", e)
                _schema_done = True
            return c
    # SQLite path (also used by l19_cache)
    sqlite_path = path or settings.db_path
    c = sqlite3.connect(sqlite_path)
    if not _schema_done:
        c.executescript(SCHEMA)
        _schema_done = True
    else:
        # still exec DDL idempotently; cheap for sqlite file
        c.executescript(SCHEMA)
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
        # ponytail: warn on corrupted contexts_json, but stay fail-closed [] (no group access) for ACL path
        if s:
            _logger.warning("jload corrupted JSON -> []: %r", s[:200])
        return []