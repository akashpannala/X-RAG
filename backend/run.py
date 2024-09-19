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
    from backend.l14_security.auth import create_user

    for username, password, groups in [
        ("admin", "admin123", ["hr", "eng", "public"]),
        ("hr_amy", "hr123456", ["hr", "public"]),
        ("eng_bob", "eng12345", ["eng", "public"]),
    ]:
        try:
            create_user(username, password, groups, force_groups=True)
            print(f"created {username} {groups}")
        except ValueError as e:
            print(f"skip: {e}")


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
