"""L8: sha256 freshness + meta DB (users, documents, conversations).

Postgres/Supabase is the only deployment backend. SQLite is kept as an
explicit provider for the unit-test suite; it is never used as a fallback
when Postgres is configured or unreachable.
"""
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from backend.errors import ConfigError, classify_db_error

_logger = logging.getLogger(__name__)
_schema_done = False  # ponytail: avoid re-running CREATE TABLE ×4 per call (esp. Postgres TCP)
_pg_schema_done = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, groups_json TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, filename TEXT UNIQUE, allowed_groups_json TEXT, hash TEXT,
  chunks INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS conversations(
  id INTEGER PRIMARY KEY, user_id INTEGER, query TEXT, answer TEXT,
  mode TEXT, score REAL, contexts_json TEXT, citations_json TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def _pg_connect(db_url: str):
    """Connect to Postgres or raise an explicit DatabaseError."""
    import psycopg

    try:
        return psycopg.connect(db_url, connect_timeout=5)
    except Exception as e:
        raise classify_db_error(e) from e


def _ensure_pg_schema(conn) -> None:
    global _pg_schema_done
    if _pg_schema_done:
        return
    pg_schema = SCHEMA.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY").replace(
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
    try:
        for stmt in pg_schema.strip().split(";"):
            if stmt.strip():
                conn.execute(stmt)
        # migrate pre-Phase-2 Postgres tables that lack new columns
        has_docs = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='documents'").fetchall()}
        if "allowed_groups_json" not in has_docs:
            conn.execute("ALTER TABLE documents ADD COLUMN allowed_groups_json TEXT DEFAULT '[\"public\"]'")
        if "chunks" not in has_docs:
            conn.execute("ALTER TABLE documents ADD COLUMN chunks INTEGER DEFAULT 0")
        has_convs = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='conversations'").fetchall()}
        if "contexts_json" not in has_convs:
            conn.execute("ALTER TABLE conversations ADD COLUMN contexts_json TEXT")
        if "citations_json" not in has_convs:
            conn.execute("ALTER TABLE conversations ADD COLUMN citations_json TEXT")
        conn.commit()
        _pg_schema_done = True
    except Exception as e:
        raise classify_db_error(e) from e


def meta_conn(path: str | None = None):
    """Return a Postgres connection, or an explicit SQLite test connection.

    No fallback: a configured Postgres/Supabase database that is missing,
    unreachable, or unauthenticated raises ``DatabaseError``.
    """
    global _schema_done
    from backend.config import settings

    provider = (settings.db_provider or "").strip().lower()
    db_url = (settings.db_url or "").strip()

    if provider in ("postgres", "supabase"):
        if not db_url or not _is_postgres_url(db_url):
            raise ConfigError(
                "DB_URL must be a postgresql:// URL for postgres/supabase",
                hint="set DB_URL (IPv4 Supabase pooler recommended)",
            )
        conn = _pg_connect(db_url)
        _ensure_pg_schema(conn)
        return conn

    if provider == "sqlite":
        sqlite_path = path or settings.db_path
        if not sqlite_path:
            raise ConfigError(
                "DB_PATH is required when DB_PROVIDER=sqlite",
                hint="SQLite is test-only on aws-deploy; set DB_PROVIDER=supabase for deployment",
            )
        c = sqlite3.connect(sqlite_path)
        c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(documents)")}
        if "allowed_groups_json" not in cols:
            c.execute("ALTER TABLE documents ADD COLUMN allowed_groups_json TEXT DEFAULT '[\"public\"]'")
        if "chunks" not in cols:
            c.execute("ALTER TABLE documents ADD COLUMN chunks INTEGER DEFAULT 0")
        ccols = {r[1] for r in c.execute("PRAGMA table_info(conversations)")}
        if "contexts_json" not in ccols:
            c.execute("ALTER TABLE conversations ADD COLUMN contexts_json TEXT")
        if "citations_json" not in ccols:
            c.execute("ALTER TABLE conversations ADD COLUMN citations_json TEXT")
        c.commit()
        _schema_done = True
        return c

    raise ConfigError(
        f"Unsupported DB_PROVIDER={settings.db_provider!r}",
        hint="aws-deploy supports postgres/supabase (sqlite only for tests)",
    )


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
