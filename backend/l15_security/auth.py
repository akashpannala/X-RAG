"""L15: auth — register/login (passlib+bcrypt), JWT (PyJWT), FastAPI dependency."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel

from backend.config import settings
from backend.l08_freshness.store import jdump, jload, meta_conn

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


def create_user(username: str, password: str, groups: list[str]) -> int:
    con = meta_conn(settings.sqlite_path)
    try:
        cur = con.execute(
            "INSERT INTO users(username, password_hash, groups_json) VALUES (?,?,?)",
            (username, _pwd.hash(password), jdump(groups)),
        )
        con.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(f"username taken: {username}") from e
    finally:
        con.close()


def authenticate(username: str, password: str) -> User:
    con = meta_conn(settings.sqlite_path)
    try:
        row = con.execute(
            "SELECT id, username, password_hash, groups_json FROM users WHERE username=?",
            (username,),
        ).fetchone()
    finally:
        con.close()
    if not row or not _pwd.verify(password, row[2]):
        raise ValueError("bad credentials")
    return User(id=row[0], username=row[1], groups=jload(row[3]))


def mint(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user.id), "username": user.username, "groups": user.groups,
         "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_min)},
        settings.jwt_secret, algorithm="HS256",
    )


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "missing bearer token")
    try:
        p = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        return User(id=int(p["sub"]), username=p["username"], groups=list(p.get("groups", [])))
    except Exception:
        raise HTTPException(401, "invalid/expired token")


def default_mode(groups: list[str]) -> str:
    try:
        mapping = json.loads(settings.default_mode_by_group)
    except Exception:
        mapping = {}
    for g in groups:
        if g in mapping:
            return mapping[g]
    return "quick"
