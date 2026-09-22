"""API surface: /health shape, /ops/telemetry gone, auth register/login basics."""
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _install_stub_store():
    """Provide backend.l07_storage without requiring Supabase/Qdrant at import time.

    Sets __path__ so `backend.l07_storage.kuzu_min` still resolves as a submodule.
    """
    from pathlib import Path

    name = "backend.l07_storage"
    real_pkg_dir = Path(__file__).resolve().parents[1] / "backend" / "l07_storage"
    mod = ModuleType(name)
    mod.__path__ = [str(real_pkg_dir)]  # mark as package for submodule imports
    mod.search = MagicMock(return_value=[])
    mod.add_docs = MagicMock()
    mod.fetch_by_doc = MagicMock(return_value=[])
    mod.reset_collection = MagicMock()
    mod.search.__module__ = "backend.l07_storage.pgvector"  # health reports pgvector
    sys.modules[name] = mod
    import backend

    backend.l07_storage = mod


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from backend.config import settings

    db = tmp_path_factory.mktemp("api") / "meta.db"
    settings.db_provider = "sqlite"
    settings.db_url = ""
    settings.db_path = str(db)

    from backend.l08_freshness import store as meta_store

    meta_store._schema_done = False

    _install_stub_store()

    from backend.api import app

    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["vector_store"] in ("pgvector", "qdrant")
    assert body["llm"]


def test_telemetry_route_removed(client):
    assert client.get("/ops/telemetry").status_code == 404


def test_register_login_roundtrip(client):
    r = client.post(
        "/auth/register",
        json={"username": "testuser", "password": "password1", "groups": ["hr"]},
    )
    assert r.status_code == 200

    r = client.post(
        "/auth/login", json={"username": "testuser", "password": "password1"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token

    from backend.l14_security.auth import authenticate

    u = authenticate("testuser", "password1")
    assert u.groups == ["public"]  # self-register stripped hr


def test_register_duplicate_409(client):
    client.post(
        "/auth/register", json={"username": "dup", "password": "password1"}
    )
    r = client.post(
        "/auth/register", json={"username": "dup", "password": "password1"}
    )
    assert r.status_code == 409


def test_login_bad_credentials_401(client):
    r = client.post("/auth/login", json={"username": "nope", "password": "password1"})
    assert r.status_code == 401


def test_query_requires_auth(client):
    r = client.post("/query", json={"query": "hi"})
    assert r.status_code == 401


def _headers(client, username):
    client.post(
        "/auth/register", json={"username": username, "password": "password1"}
    )
    r = client.post("/auth/login", json={"username": username, "password": "password1"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_documents_conversations_require_auth(client):
    assert client.get("/documents").status_code == 401
    assert client.get("/conversations").status_code == 401


def test_documents_acl_filter(client):
    from backend.config import settings
    from backend.l08_freshness.store import jdump, meta_conn

    con = meta_conn(settings.db_path)
    con.execute(
        "INSERT INTO documents(filename, allowed_groups_json, hash, chunks) VALUES (?,?,?,?)",
        ("acl_hr_only.pdf", jdump(["hr"]), "f" * 64, 3),
    )
    con.execute(
        "INSERT INTO documents(filename, allowed_groups_json, hash, chunks) VALUES (?,?,?,?)",
        ("acl_shared.md", jdump(["public"]), "e" * 64, 5),
    )
    con.commit()
    con.close()

    r = client.get("/documents", headers=_headers(client, "acluser"))
    assert r.status_code == 200
    docs = {d["filename"]: d for d in r.json()}
    assert "acl_shared.md" in docs
    assert "acl_hr_only.pdf" not in docs  # caller has no hr group
    assert docs["acl_shared.md"]["chunks"] == 5
    assert docs["acl_shared.md"]["hash"] == "e" * 12
    assert docs["acl_shared.md"]["allowed_groups"] == ["public"]
    assert "size_bytes" in docs["acl_shared.md"]


def test_conversations_returns_own_rows(client):
    from backend.config import settings
    from backend.l08_freshness.store import jdump, meta_conn
    from backend.l14_security.auth import authenticate

    headers = _headers(client, "histuser")
    uid = authenticate("histuser", "password1").id

    con = meta_conn(settings.db_path)
    con.execute(
        "INSERT INTO conversations(user_id, query, answer, mode, score, contexts_json, citations_json) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, "what is X?", "it is Y [docA#1]", "quick", 0.0, jdump([]), jdump(["[docA#1]"])),
    )
    con.execute(
        "INSERT INTO conversations(user_id, query, answer, mode, score, contexts_json, citations_json) "
        "VALUES (?,?,?,?,?,?,?)",
        (999999, "not yours", "secret", "quick", 0.0, jdump([]), jdump([])),
    )
    con.commit()
    con.close()

    r = client.get("/conversations", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert rows, "own conversation row must be returned"
    assert all(r_["query"] != "not yours" for r_ in rows)
    mine = next(r_ for r_ in rows if r_["query"] == "what is X?")
    assert mine["answer"] == "it is Y [docA#1]"
    assert mine["citations"] == ["[docA#1]"]
    assert mine["mode"] == "quick"
    assert mine["created_at"]
