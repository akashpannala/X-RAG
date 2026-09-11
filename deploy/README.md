# RAGOps stack (Phase 4 / L22)

One compose file for every side service the offline RAG backend talks to
(Qdrant, Redis, Langfuse). Bring the whole stack up with:

```bash
docker compose -f deploy/docker-compose.ops.yml up -d
```

| Port | Service        | Purpose                                        |
|------|----------------|------------------------------------------------|
| 6333 | qdrant         | dense + sparse (SPLADE) vector store            |
| 6379 | redis          | eval queue (Redis Streams) + Langfuse cache     |
| 8000 | portainer      | container management (running separately)       |
| 8080 | langfuse-web   | tracing UI + public ingestion API               |
| —    | langfuse-db    | Langfuse postgres (migrations, users, projects) |
| —    | clickhouse     | Langfuse event store (traces/observations)      |
| —    | clickhouse-keeper | distributed coordination for ClickHouse      |
| —    | langfuse-worker| background trace/deletion/score processors      |

## Versions to note

- postgres 16 via `langfuse/langfuse:3`'s bundled `langfuse-db` image.
- ClickHouse `24.8-alpine` (v3 requires ClickHouse; older 2.x traces live in postgres only).
- Langfuse image tag `langfuse/langfuse:3` and `langfuse/langfuse-worker:3` (web `3.225.7`).

## Secrets (generated, commit-safe for the dev box)

- `NEXTAUTH_SECRET=b8c7e522…45ad3`
- `SALT=7516c425…3d8`
- `ENCRYPTION_KEY=7f53c84f…8362` (64 hex — `openssl rand -hex 32`)

Rotate these before any environment shared beyond the dev box.

## ClickHouse layout

- `deploy/clickhouse/keeper_config.xml` — dedicated **clickhouse-keeper** container
  (embedded keeper in the server image fails with `server id 1 not found in
  raft_configuration`; keep raft servers listed under `raft_configuration`).
- `deploy/clickhouse/listen.xml` — listen on IPv4 only; the host has IPv6 off.
- `deploy/clickhouse/keeper.xml` — `zookeeper` node → `clickhouse-keeper:9181`
  plus `macros` (shard/replica) required by ReplicatedMergeTree.

## Langfuse environment traps (v3)

- Redis var is `REDIS_CONNECTION_STRING`, **not** `REDIS_URL`.
- ClickHouse: `CLICKHOUSE_URL=http://clickhouse:8123/…` (HTTP), while
  `CLICKHOUSE_MIGRATION_URL` must be **native**
  (`clickhouse://user:pass@clickhouse:9000/…`).
- `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` is required even though local uploads are
  unused.
- Migration errors like `There is no Zookeeper configuration` mean the
  clickhouse-keeper service is not reachable yet.
- Signup requires a password with a non-alphanumeric character (UI enforces).
- `LANGFUSE_INIT_USER_*`/`LANGFUSE_INIT_PROJECT_*` provisioning did NOT fire on
  fresh boots here; use `deploy/langfuse_bootstrap.sh` instead.

## Tenant bootstrap

```bash
deploy/langfuse_bootstrap.sh
```

Automates signup + login + org/project creation (the app's tRPC endpoints),
then prints the one manual step left — create the API key in the UI
(project → Settings → API Keys). Paste `pk-lf-…`/`sk-lf-…` into the backend
`.env` under `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` and set
`LANGFUSE_ENABLED=true`.

> Only create orgs/projects/keys through the app or script. Direct SQL inserts
> of tenant rows are consistently reaped by Langfuse's internal sweeps; rows
> minted through the app persist.

## Backend wiring

- `backend/l22_ragops/trace.py` — no-op unless enabled + keyed. Prefers the
  LangChain CallbackHandler; falls back to a bare-SDK chain observation
  (`start_observation`) so tracing survives `langchain-core` 1.x incompatibles.
- `backend/l18_generation/graph.py:answer()` attaches the handler / starts the
  fallback trace; `_finish_trace` writes output + telemetry metadata, then
  flushes. Tracing never raises into the request path.

## Verification

```bash
curl -s localhost:8080/api/public/health          # {"status":"OK",...}
curl -s localhost:6333/healthz | head -c 200
docker logs deploy-langfuse-worker-1 --tail 20    # no repeated "traces table does not exist"
```

Every `/query` (cache miss) records a `query_telemetry` row; with `LANGFUSE_*`
keys set, each miss lands one chain observation in Langfuse
(`POST /api/public/otel/v1/traces`).