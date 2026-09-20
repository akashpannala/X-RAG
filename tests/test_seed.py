"""Seed path: duplicate users print skip (ValueError), not crash — Postgres UniqueViolation mapped."""
import pytest

from backend.l14_security.auth import create_user


def test_unique_violation_mapped_to_valueerror(tmp_settings, monkeypatch):
    """Simulate the Supabase path where IntegrityError is UniqueViolation, not sqlite."""
    create_user("admin", "password1", ["hr"], force_groups=True)

    real_conn = __import__("backend.l08_freshness.store", fromlist=["meta_conn"]).meta_conn

    class FakeUnique(Exception):
        pass

    FakeUnique.__name__ = "UniqueViolation"

    class Cur:
        def execute(self, *a, **k):
            raise FakeUnique("duplicate key value violates unique constraint")

        def fetchone(self):
            return (1,)

    class Con:
        def execute(self, *a, **k):
            return Cur().execute(*a, **k)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        "backend.l14_security.auth.meta_conn", lambda *a, **k: Con()
    )
    with pytest.raises(ValueError, match="username taken"):
        create_user("admin", "password1", ["hr"], force_groups=True)


def test_seed_loop_style_skip(tmp_settings):
    """Mirrors backend.run.seed: catch ValueError and continue."""
    created, skipped = [], []
    for username in ("admin", "luffy", "zoro"):
        try:
            create_user(username, "pass", ["public"], force_groups=False)
            # pass is too short — validate_password raises before insert
            created.append(username)
        except ValueError as e:
            skipped.append(username)
    # short password rejected for all three via create_user
    assert created == []
    assert skipped == ["admin", "luffy", "zoro"]
