#!/bin/sh
# Container boot: extra args replace the boot sequence (docker run xrag <cmd>).
set -e
mkdir -p data/uploads data/logs

# WSO2/Choreo exposes configuration groups as files (/x.env/<key>), not env vars.
# Import them (uppercased) so the app sees the same names as a local .env.
if [ -d /x.env ]; then
  n=0
  for f in /x.env/*; do
    [ -f "$f" ] || continue
    name=$(basename "$f" | tr '[:lower:]' '[:upper:]')
    eval "cur=\${$name-}"
    if [ -z "$cur" ]; then
      export "$name=$(cat "$f")"
      n=$((n + 1))
    fi
  done
  echo "config: imported $n keys from /x.env"
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

if [ "${SEED:-1}" = "1" ]; then
  python -m backend.run seed || true
fi

exec python -m backend.run