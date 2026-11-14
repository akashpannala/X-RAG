#!/bin/sh
set -e

mkdir -p /app/data/uploads /app/data/logs /app/data/kuzu

if [ "${WAIT_FOR_QDRANT:-1}" = "1" ]; then
  python - <<'PY'
import os
import socket
import time

host = os.getenv("QDRANT_HOST", "qdrant")
port = int(os.getenv("QDRANT_PORT", "6333"))
for _ in range(30):
    try:
        socket.create_connection((host, port), 1).close()
        break
    except OSError:
        time.sleep(1)
PY
fi

if [ "${SEED:-1}" = "1" ]; then
  python -m backend.run seed || true
fi

exec python -m backend.run
