"""Single entry: check requirements → compile graph → serve API. Or: seed users."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from backend.config import check_requirements
from backend.l18_generation.graph import get_graph


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
    from backend.l15_security.auth import create_user

    for username, password, groups in [
        ("admin", "admin123", ["hr", "eng", "public"]),
        ("hr_amy", "hr123456", ["hr", "public"]),
        ("eng_bob", "eng12345", ["eng", "public"]),
    ]:
        try:
            create_user(username, password, groups)
            print(f"created {username} {groups}")
        except ValueError as e:
            print(f"skip: {e}")


def main(port: int = 8001) -> None:
    setup_logging()
    if not check_requirements():
        sys.exit(1)
    get_graph()  # compile once, fail fast on wiring errors
    uvicorn.run("backend.api:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed()
    else:
        main(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8001)
