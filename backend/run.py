"""Single entry: check requirements → compile graph → serve API."""
import sys

import uvicorn

from backend.config import check_requirements
from backend.l18_generation.graph import get_graph


def main(port: int = 8001) -> None:
    if not check_requirements():
        sys.exit(1)
    get_graph()  # compile once, fail fast on wiring errors
    uvicorn.run("backend.api:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8001)
