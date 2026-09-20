"""Meta DB: schema has no telemetry table; sha256 + JSON helpers."""
import hashlib
from pathlib import Path

from backend.l08_freshness.store import SCHEMA, jdump, jload, sha256_file


def test_schema_has_no_telemetry():
    assert "query_telemetry" not in SCHEMA
    assert "users" in SCHEMA
    assert "documents" in SCHEMA
    assert "conversations" in SCHEMA


def test_sqlite_creates_expected_tables(tmp_settings, sqlite_conn):
    rows = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"users", "documents", "conversations"} <= names
    assert "query_telemetry" not in names


def test_jdump_jload_roundtrip():
    assert jload(jdump(["hr", "public"])) == ["hr", "public"]
    assert jload(None) == []
    assert jload("not-json") == []  # fail-closed


def test_sha256_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello")
    assert sha256_file(p) == hashlib.sha256(b"hello").hexdigest()
