"""L8: sha256 freshness + SQLite meta (documents)."""
import hashlib
import sqlite3
from pathlib import Path

SCHEMA = "CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, filename TEXT UNIQUE, hash TEXT)"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def meta_conn(path: str):
    c = sqlite3.connect(path)
    c.execute(SCHEMA)
    return c
