"""L15: auth — register/login (passlib+bcrypt), JWT (PyJWT), FastAPI dependency."""
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.config import settings
from backend.l08_freshness.store import jdump, jload, meta_conn

_logger = logging.getLogger(__name__)

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    username: str
    password: str
    groups: list[str] = ["public"]


class LoginRequest(BaseModel):
    username: str
    password: str


class User(BaseModel):
    id: int
    username: str
    groups: list[str]


# groups a normal registration is allowed to self-assign; anything else must be
# granted by an admin route, not requested at registration.
_ALLOWED_SELF_GROUPS = {"public"}


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("password must be at least 8 characters")


def _ph(con) -> str:
    """Return placeholder for current connection: %s for PostgreSQL/psycopg, ? for SQLite."""
    try:
        import psycopg
        if isinstance(con, psycopg.Connection):
            return "%s"
    except ImportError:
        pass
    return "?"


def _ph_n(con, n: int) -> str:
    """Return n placeholders for current connection."""
    try:
        import psycopg
        if isinstance(con, psycopg.Connection):
            return ", ".join(["%s"] * n)
    except ImportError:
        pass
    return ", ".join(["?"] * n)


def create_user(username: str, password: str, groups: list[str], force_groups: bool = False) -> int:
    validate_password(password)
    if force_groups:
        safe_groups = list(groups) or ["public"]
    else:
        safe_groups = [g for g in groups if g in _ALLOWED_SELF_GROUPS] or ["public"]
    con = meta_conn(settings.db_path)
    try:
        ph = _ph_n(con, 3)
        cur = con.execute(
            f"INSERT INTO users(username, password_hash, groups_json) VALUES ({ph}) RETURNING id",
            (username, _pwd.hash(password), jdump(safe_groups)),
        )
        con.commit()
        return cur.fetchone()[0]
    except sqlite3.IntegrityError as e:
        raise ValueError(f"username taken: {username}") from e
    finally:
        con.close()


def authenticate(username: str, password: str) -> User:
    con = meta_conn(settings.db_path)
    try:
        row = con.execute(
            f"SELECT id, username, password_hash, groups_json FROM users WHERE username={_ph(con)}",
            (username,),
        ).fetchone()
    finally:
        con.close()
    if not row or not _pwd.verify(password, row[2]):
        raise ValueError("bad credentials")
    return User(id=row[0], username=row[1], groups=jload(row[3]))


def mint(user: User) -> str:
    now = datetime.now(timezone.utc)
    expire_min = settings.jwt_expire_min
    if not isinstance(expire_min, int) or expire_min <= 0 or expire_min > 60 * 24 * 30:
        expire_min = 480  # clamp misconfiguration to a sane bound
    return jwt.encode(
        {"sub": str(user.id), "username": user.username, "groups": user.groups,
         "iat": now, "exp": now + timedelta(minutes=expire_min)},
        settings.jwt_secret, algorithm="HS256",
    )


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "missing bearer token")
    try:
        p = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "invalid/expired token")
    # deleted-user / stale-revocation guard: re-check the user still exists
    uid = p.get("sub")
    try:
        from backend.l08_freshness.store import meta_conn

        con = meta_conn(settings.db_path)
        try:
            row = con.execute(
                f"SELECT username, groups_json FROM users WHERE id={_ph(con)}",
                (int(uid),),
            ).fetchone()
        finally:
            con.close()
        if not row:
            raise HTTPException(401, "user no longer exists")
        return User(id=int(uid), username=row[0], groups=jload(row[1]))
    except HTTPException:
        raise
    except Exception:
        # DB unreachable — fall back to token claims rather than lock everyone out
        return User(id=int(uid), username=p.get("username", ""), groups=list(p.get("groups", [])))


def default_mode(groups: list[str]) -> str:
    try:
        mapping = json.loads(settings.default_mode_by_group)
    except Exception as e:
        _logger.warning("invalid DEFAULT_MODE_BY_GROUP (%r) — defaulting all to quick: %s",
                        settings.default_mode_by_group, e)
        mapping = {}
    for g in groups:
        if g in mapping:
            return mapping[g]
    return "quick"
