# Reference

Base URL: `http://localhost:8001` · Swagger UI: `/docs` · all endpoints JSON unless noted.

## HTTP API

### Authentication

Most endpoints require `Authorization: Bearer <token>`.

| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| POST | `/auth/register` | `{"username", "password", "groups"?}` | `{"id", "username"}` | `409` duplicate or password < 8 chars |
| POST | `/auth/login` | `{"username", "password"}` | `{"access_token", "token_type":"bearer"}` | `401` bad credentials |

- Default registration group: `["public"]`. Self-registration can only assign `public`.
- Token TTL: `JWT_EXPIRE_MIN` (default 480 minutes). Payload: `sub`, `username`, `groups`, `iat`, `exp`.

### Health

`GET /health` — no auth.

```json
{"status":"ok","llm":"groq","vector_store":"pgvector","qdrant":"http://localhost:6333","db":"postgres"}
```

### Ingest

`POST /ingest` — multipart field `f` (the file).

| Query param | Default | Meaning |
|---|---|---|
| `allowed_groups` | `public` | comma-separated groups that may retrieve this document |
| `enrich` | `true` | run enrichment (RAPTOR-lite, hypothetical questions, NER) |

```json
{"filename":"policy.pdf","chunks":1986,"hash":"99fcdbaa8edb"}
```

- Supported extensions: `.pdf .docx .pptx .csv .md .txt .png .jpg .jpeg`; anything else → `500` with the supported list.
- Re-uploading an existing filename replaces its vectors, index entries, groups, and file (replace-on-reingest).
- Errors: `401`, `502` on LLM failure during enrichment.

### Query

`POST /query`

```json
{"query":"What is our vacation policy?","top_k":5,"mode":"quick"}
```

| Field | Default | Notes |
|---|---|---|
| `query` | — | required |
| `top_k` | `5` | retrieval depth |
| `mode` | role default | `"quick"` or `"deep"`; default from `DEFAULT_MODE_BY_GROUP` |

```json
{
  "answer": "...Employees accrue 1.5 days per month [vacation_policy#12]...",
  "citations": ["[vacation_policy#12]", "[vacation_policy#13]"],
  "provider": "groq",
  "mode": "quick",
  "cache_hit": false,
  "verification": {"supported_ratio": 0.83}
}
```

Errors: `401`, `502` (LLM provider error).

### Documents

`GET /documents` — list visible to the caller's groups (newest first).

```json
[{"filename":"Free Journals.pdf","chunks":81,"hash":"99fcdbaa8edb",
  "allowed_groups":["eng"],"size_bytes":69079}]
```

`size_bytes` is `null` if the file is missing on disk.

`DELETE /documents/{filename}` — removes vectors, BM25/SPLADE entries, metadata row, uploaded
file, and clears the answer cache.

| Status | Meaning |
|---|---|
| `200` | `{"deleted": "<filename>"}` |
| `400` | filename contains a path separator |
| `404` | not visible to caller, or already gone (existence hidden) |
| `401` | missing/invalid token |

### Conversations

`GET /conversations` — caller's own history, newest first, limit 100.

```json
[{"id":32,"query":"...","answer":"...","mode":"quick",
  "citations":["[doc#0]"],"created_at":"2026-09-27 16:32:38.923514"}]
```

`DELETE /conversations/{id}` — `200 {"deleted": id}`; `404` if not the caller's; `401` unauthenticated.

## CLI

| Command | Effect |
|---|---|
| `python -m backend.run` | boot checks, then serve on `HOST:PORT` |
| `python -m backend.run <port>` | serve on the given port |
| `python -m backend.run seed` | create demo users (`LUFFY`, `ZORO`), idempotent |

Exit code `1` if a configured provider fails its boot check (message names the failing row).

## Configuration (`.env`)

Single source of truth; auto-detected at boot. Template: `.env.example`.

| Variable | Default | Values / notes |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8001` | bind address |
| `CORS_ORIGINS` | `http://localhost:3000,...` | comma-separated |
| `JWT_SECRET` | `change-me-in-env` | HS256 signing key |
| `JWT_EXPIRE_MIN` | `480` | token TTL |
| `DEFAULT_MODE_BY_GROUP` | `{"hr":"quick","eng":"deep","public":"quick"}` | JSON map |
| `UPLOAD_DIR` | `data/uploads` | stored files |
| `LLM_PROVIDER` | `groq` | `groq \| ollama \| llama.cpp \| openai \| anthropic` |
| `LLM_BASE_URL` | provider default | resolved per provider (e.g. Ollama `http://localhost:11434`) |
| `LLM_MODEL` | `openai/gpt-oss-20b` | |
| `LLM_API_KEY` | — | required for `groq/openai/anthropic` |
| `EMBED_PROVIDER` | `bge` | `bge \| jina \| voyage \| cohere \| choreo` |
| `EMBED_BASE_URL` | — | remote providers only |
| `EMBED_MODEL` | `BAAI/bge-m3` | |
| `EMBED_API_KEY` | — | remote providers only |
| `RERANK_PROVIDER` | `minilm` | `minilm \| jina \| bge` (fallback chain: configured → next → MiniLM) |
| `RERANK_BASE_URL` | `https://api.jina.ai/v1` | |
| `RERANK_MODEL` | `jina-reranker-m0` | |
| `RERANK_API_KEY` | — | required for `jina` |
| `VECTOR_BASE_URL` | `http://localhost:6333` | Qdrant |
| `VECTOR_API_KEY` | — | Qdrant Cloud |
| `VECTOR_COLLECTION` | `offline_rag` | |
| `DB_PROVIDER` | `sqlite` | `sqlite \| postgres \| supabase` |
| `DB_URL` | — | Postgres DSN; also selects pgvector as the vector store |
| `DB_PATH` | `data/meta.db` | SQLite path |

**Storage selection at boot:** pgvector if `DB_PROVIDER` is `postgres|supabase` and `DB_URL`
connects; otherwise Qdrant at `VECTOR_BASE_URL`; if neither works the server refuses to start.

## Seed users

| Username | Password | Groups |
|---|---|---|
| `LUFFY` | `password` | `hr`, `public` |
| `ZORO` | `password` | `eng`, `public` |

## Citations

- Server format: `[doc#chunk]`, e.g. `[Free Journals#80]` — `doc` is the filename stem, `chunk` is 0-based.
- `citations` in responses is the list of exact tags used in `answer`.
- The frontend renders numbered chips `[1]`, `[2]`… in order of first appearance; clicking a chip
  flashes the matching sources-rail row.
