#!/bin/sh
# Container boot: extra args replace the boot sequence (docker run xrag <cmd>).
set -e
mkdir -p data/uploads data/logs

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

if [ "${SEED:-1}" = "1" ]; then
  python -m backend.run seed || true
fi

exec python -m backend.run