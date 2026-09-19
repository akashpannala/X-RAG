"""Single entry: check requirements → compile graph → serve API. Or: seed users."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from backend.config import check_requirements
from backend.l17_generation.graph import get_graph


def setup_logging() -> None:
    logdir = Path("data/logs")
    logdir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        fh = RotatingFileHandler(logdir / "api.log", maxBytes=10_000_000,
                                 backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def seed() -> None:
    """Demo users. Passwords are short by request — hash directly (skip validate_password)."""
    from passlib.context import CryptContext

    from backend.l08_freshness.store import jdump, meta_conn
    from backend.config import settings

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    con = meta_conn(settings.db_path)
    try:
        for username, password, groups in [
            ("admin", "pass", ["hr", "eng", "public"]),
            ("luffy", "pass", ["hr", "public"]),
            ("zoro", "pass", ["eng", "public"]),
        ]:
            try:
                ph = ", ".join(["%s"] * 3) if type(con).__module__.startswith("psycopg") else ", ".join(["?"] * 3)
                cur = con.execute(
                    f"INSERT INTO users(username, password_hash, groups_json) VALUES ({ph}) RETURNING id",
                    (username, pwd.hash(password), jdump(groups)),
                )
                con.commit()
                print(f"created {username} {groups}")
            except Exception as e:
                con.rollback()
                if type(e).__name__ == "UniqueViolation" or "unique" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"skip: username taken: {username}")
                else:
                    raise
    finally:
        con.close()


def main(port: int | None = None) -> None:
    from backend.config import settings

    setup_logging()
    if not check_requirements():
        sys.exit(1)
    get_graph()  # compile once, fail fast on wiring errors
    host = settings.host
    use_port = int(port) if port is not None else int(settings.port)
    uvicorn.run("backend.api:app", host=host, port=use_port)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed()
    else:
        arg_port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
        main(port=arg_port)
