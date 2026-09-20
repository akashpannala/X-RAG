"""Shared fixtures — force SQLite + temp paths so tests never touch Supabase/live data."""
import os
import tempfile
from pathlib import Path

import pytest

# Point config at a throwaway SQLite DB before app modules bind settings.
os.environ.setdefault("DB_PROVIDER", "sqlite")
os.environ.setdefault("DB_URL", "")
os.environ.setdefault("DB_PATH", "data/test_meta.db")


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    """Isolate db_path, uploads, and schema state onto a temp dir."""
    from backend.config import settings
    from backend.l08_freshness import store as meta_store

    db = tmp_path / "meta.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(settings, "db_provider", "sqlite")
    monkeypatch.setattr(settings, "db_url", "")
    monkeypatch.setattr(settings, "db_path", str(db))
    monkeypatch.setattr(settings, "upload_dir", str(uploads))
    monkeypatch.setattr(meta_store, "_schema_done", False)
    yield settings


@pytest.fixture()
def sqlite_conn(tmp_settings):
    from backend.l08_freshness.store import meta_conn

    con = meta_conn(tmp_settings.db_path)
    yield con
    try:
        con.rollback()
    except Exception:
        pass
    con.close()


@pytest.fixture(autouse=True)
def _isolate_sparse_index(tmp_path, monkeypatch):
    """Keep BM25/SPLADE pickles out of data/ during tests."""
    from backend.L06_sparse import bm25

    path = tmp_path / "bm25.pkl"
    monkeypatch.setattr(bm25, "INDEX_PATH", path)
    monkeypatch.setattr(bm25, "_index", None)
    monkeypatch.setattr(bm25, "_meta", [])
    yield
