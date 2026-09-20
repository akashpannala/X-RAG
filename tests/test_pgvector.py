"""pgvector SQL must cast query vectors (::vector) and filter allowed_groups.

Loads backend/l07_storage/pgvector.py by path so tests do not execute the
package factory in __init__.py (which requires a live vector store).
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_pgvector():
    path = Path(__file__).resolve().parents[1] / "backend" / "l07_storage" / "pgvector.py"
    name = "backend_l07_pgvector_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pg():
    return _load_pgvector()


def _mock_conn(rows=None):
    conn = MagicMock()
    cur = MagicMock()
    # `with conn.cursor() as cur` uses the context manager return value
    conn.cursor.return_value = cur
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = False
    cur.fetchall.return_value = rows or []
    return conn, cur


def test_search_uses_vector_cast(pg, monkeypatch):
    """Regression: list param without ::vector → operator does not exist."""
    emb = MagicMock()
    emb.embed_query.return_value = [0.1] * 8
    monkeypatch.setattr(pg, "get_embeddings", lambda m: emb)
    monkeypatch.setattr(pg.settings, "embed_model", "test-model")

    conn, cur = _mock_conn([{"doc": "d", "chunk_id": 0, "text": "t", "score": 0.9}])
    monkeypatch.setattr(pg, "_conn", lambda: conn)

    out = pg.search("hello", 5, None)
    assert out and out[0]["doc"] == "d"

    sql = cur.execute.call_args[0][0]
    assert "::vector" in sql
    params = cur.execute.call_args[0][1]
    assert isinstance(params[0], str)
    assert params[0].startswith("[")
    assert params[-1] == 5  # top_k


def test_search_acl_where_clause(pg, monkeypatch):
    # minimal Qdrant-shaped filter (same structure groups_filter produces)
    cond = MagicMock()
    cond.key = "allowed_groups"
    cond.match.any = ["hr", "public"]
    qf = MagicMock()
    qf.must = [cond]

    emb = MagicMock()
    emb.embed_query.return_value = [0.1] * 8
    monkeypatch.setattr(pg, "get_embeddings", lambda m: emb)

    conn, cur = _mock_conn([])
    monkeypatch.setattr(pg, "_conn", lambda: conn)

    pg.search("q", 10, qf)
    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]
    assert "allowed_groups ?|" in sql
    assert "hr" in params
    assert "public" in params


def test_search_error_returns_empty(pg, monkeypatch):
    emb = MagicMock()
    emb.embed_query.return_value = [0.1] * 4
    monkeypatch.setattr(pg, "get_embeddings", lambda m: emb)

    conn, cur = _mock_conn()
    cur.fetchall.side_effect = RuntimeError("boom")
    monkeypatch.setattr(pg, "_conn", lambda: conn)
    assert pg.search("q", 5, None) == []
