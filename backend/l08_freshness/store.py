"""L8: sha256 freshness + SQLite meta (PRD §7: users, documents, conversations)."""
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

_logger = logging.getLogger(__name__)
_schema_done = False  # ponytail: avoid re-running CREATE TABLE ×6 per call (esp. Postgres TCP)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, groups_json TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, filename TEXT UNIQUE, allowed_groups_json TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS conversations(
  id INTEGER PRIMARY KEY, user_id INTEGER, query TEXT, answer TEXT,
  mode TEXT, score REAL, contexts_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS query_telemetry(
  id INTEGER PRIMARY KEY, user_id INTEGER, mode TEXT, cache_hit INTEGER,
  latency_ms REAL, n_queries INTEGER, n_hits INTEGER, rerank_stage TEXT,
  supported_ratio REAL, provider TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS eval_goldens(
  id INTEGER PRIMARY KEY, query TEXT UNIQUE, golden_answer TEXT,
  gold_cites_json TEXT, groups_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS mined_hard_negatives(
  id INTEGER PRIMARY KEY, query TEXT, doc TEXT, chunk_id INTEGER,
  label_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
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
    """Env-driven: if DATABASE_URL is postgres/supabase, use psycopg; else sqlite at path/SQLITE_PATH."""
    global _schema_done
    from backend.config import settings

    db_url = (settings.database_url or "").strip()
    if _is_postgres_url(db_url):
        try:
            import psycopg

            c = psycopg.connect(db_url)
        except ImportError:
            raise RuntimeError("psycopg not installed — pip install psycopg[binary] for postgres DATABASE_URL")
        except Exception as e:
            raise RuntimeError(f"postgres connect failed for {db_url[:30]}...: {e}") from e
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
    # SQLite path (also used by l20_cache)
    sqlite_path = path or settings.sqlite_path
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
