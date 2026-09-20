"""Answer-cache keys isolate by mode+groups; clear wipes all partitions."""
import pytest

from backend.l19_cache import cache as qcache


@pytest.fixture(autouse=True)
def _fake_embeds(monkeypatch, tmp_path):
    """Deterministic unit vectors — no network / model load."""
    import hashlib

    import numpy as np

    def _vec(text: str):
        h = hashlib.sha256(text.encode()).digest()
        raw = np.frombuffer(h[:32], dtype=np.uint8).astype(np.float64)
        raw = (raw / 255.0) - 0.5
        n = np.linalg.norm(raw) + 1e-9
        return list(raw / n)

    monkeypatch.setattr(qcache, "embed_cached", _vec)
    monkeypatch.setattr(qcache, "_embed_cached", lambda model, text: tuple(_vec(text)))
    db = tmp_path / "cache.db"
    from backend.config import settings

    monkeypatch.setattr(settings, "db_path", str(db))
    yield


def test_key_partition_includes_mode_and_sorted_groups():
    a = qcache._key("q", "quick", ["hr", "public"])
    b = qcache._key("q", "deep", ["hr", "public"])
    c = qcache._key("q", "quick", ["public", "hr"])  # same sorted groups
    d = qcache._key("q", "quick", ["eng", "public"])
    assert a != b
    assert a == c
    assert a != d
    assert a.endswith("|quick|hr,public")


def test_store_lookup_same_partition_only():
    q = "what are free journals"
    qcache.store(q, "quick", ["hr", "public"], "hr-answer", ["doc#1"])
    hit = qcache.lookup(q, "quick", ["hr", "public"])
    assert hit is not None
    assert hit[0] == "hr-answer"
    # different mode / groups → miss (no cross-role leak)
    assert qcache.lookup(q, "deep", ["hr", "public"]) is None
    assert qcache.lookup(q, "quick", ["eng", "public"]) is None


def test_clear_removes_everything():
    qcache.store("a", "quick", ["public"], "x", [])
    qcache.store("b", "deep", ["hr"], "y", [])
    assert qcache.clear() >= 2
    assert qcache.lookup("a", "quick", ["public"]) is None
    assert qcache.lookup("b", "deep", ["hr"]) is None
