#!/bin/sh
set -e

mkdir -p /app/data/uploads /app/data/logs /app/data/kuzu

# No Qdrant wait: aws-deploy is pgvector-only and the database is remote.
# Probe the configured remote providers/DB before seeding for a readable failure.
python -m backend.run check

if [ "${SEED:-1}" = "1" ]; then
  python -m backend.run seed
fi

exec python -m backend.run
