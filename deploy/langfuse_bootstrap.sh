#!/usr/bin/env bash
# L22/RAGOps bootstrap: provision the Langfuse tenant for the X-RAG tracing seam.
#
# Does NOT create the API key — that must be done in the Langfuse UI so the key
# is minted through the app (project Settings -> API Keys -> "Create new key").
# This script completes every step that can be automated (signup, login,
# org + project creation) and prints the two env lines to paste into .env.
#
# Idempotent: skips steps that already exist.
set -euo pipefail

BASE="${LANGFUSE_BASE:-http://localhost:8080}"
EMAIL="${LANGFUSE_EMAIL:-admin@offline-rag.local}"
PASSWORD="${LANGFUSE_PASSWORD:-Xrag2026!}"
NAME="${LANGFUSE_NAME:-admin}"
ORG="${LANGFUSE_ORG:-Offline RAG}"
PROJECT="${LANGFUSE_PROJECT:-RAG}"
COOKIE=/tmp/lf_bootstrap_cookies.txt

json_field() { /home/zoro/X-RAG/.venv/bin/python -c "import json,sys;d=json.load(sys.stdin);print(d$1)" 2>/dev/null || echo ""; }

health=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/public/health" || true)
if [ "$health" != "200" ]; then
  echo "ERROR: langfuse not healthy at $BASE (HTTP $health). Start the stack first:"
  echo "  docker compose -f deploy/docker-compose.ops.yml up -d"
  exit 1
fi

if ! curl -s -o /dev/null "$BASE/api/auth/csrf"; then exit 1; fi

exists=$(docker exec deploy-langfuse-db-1 psql -U langfuse -d langfuse -tAc \
  "SELECT count(*) FROM users WHERE email='$EMAIL';" | tr -d '[:space:]')
if [ "$exists" = "0" ]; then
  echo "signing up $EMAIL ..."
  curl -s -X POST "$BASE/api/auth/signup" -H "Content-Type: application/json" \
    -d "{\"name\":\"$NAME\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | head -c 200
  echo
else
  echo "user $EMAIL already exists"
fi

rm -f "$COOKIE"
csrf=$(json_field "['csrfToken']" <<< "$(curl -s -c "$COOKIE" "$BASE/api/auth/csrf")")
curl -s -b "$COOKIE" -c "$COOKIE" -X POST "$BASE/api/auth/callback/credentials" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "csrfToken=$csrf" \
  --data-urlencode "email=$EMAIL" --data-urlencode "password=$PASSWORD" \
  -o /dev/null || true

org_id=$(curl -s -b "$COOKIE" -X POST "$BASE/api/trpc/projects.list?batch=1" \
  -H "Content-Type: application/json" -d '{"0":{"json":{}}}' | head -c 0; echo "")
have_org=$(docker exec deploy-langfuse-db-1 psql -U langfuse -d langfuse -tAc \
  "SELECT count(*) FROM organizations WHERE name='$ORG';" | tr -d '[:space:]')
if [ "$have_org" = "0" ]; then
  echo "creating organization '$ORG' ..."
  org_resp=$(curl -s -b "$COOKIE" -X POST "$BASE/api/trpc/organizations.create?batch=1" \
    -H "Content-Type: application/json" -d "{\"0\":{\"json\":{\"name\":\"$ORG\"}}}")
  ORG_ID=$(json_field "[0]['result']['data']['json']['id']" <<< "$org_resp")
  echo "org id: $ORG_ID"
else
  ORG_ID=$(docker exec deploy-langfuse-db-1 psql -U langfuse -d langfuse -tAc \
    "SELECT id FROM organizations WHERE name='$ORG' LIMIT 1;" | tr -d '[:space:]')
fi

have_project=$(docker exec deploy-langfuse-db-1 psql -U langfuse -d langfuse -tAc \
  "SELECT count(*) FROM projects WHERE name='$PROJECT';" | tr -d '[:space:]')
if [ "$have_project" = "0" ]; then
  echo "creating project '$PROJECT' ..."
  proj_resp=$(curl -s -b "$COOKIE" -X POST "$BASE/api/trpc/projects.create?batch=1" \
    -H "Content-Type: application/json" -d "{\"0\":{\"json\":{\"orgId\":\"$ORG_ID\",\"name\":\"$PROJECT\"}}}")
  PROJ_ID=$(json_field "[0]['result']['data']['json']['id']" <<< "$proj_resp")
  echo "project id: $PROJ_ID"
fi

echo
echo "Stack ready. Final step (manual, ~1 min) — mint an API key via the UI:"
echo "  1) open $BASE  (login: $EMAIL / $PASSWORD)"
echo "  2) project 'RAG' -> Settings -> API Keys -> Create new key (note: backend)"
echo "  3) copy the two values into backend/.env:"
echo "     LANGFUSE_ENABLED=true"
echo "     LANGFUSE_HOST=$BASE"
echo "     LANGFUSE_PUBLIC_KEY=pk-lf-<value>"
echo "     LANGFUSE_SECRET_KEY=sk-lf-<value>"
echo "  4) restart the backend; each /query then lands a chain observation."
echo
echo "NOTE: provision orgs/projects/keys ONLY via the app or this script. Raw SQL "
echo "inserts of tenant rows are reliably reaped by Langfuse's internal hygiene."