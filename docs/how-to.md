# How-to guides

Short, self-contained recipes. Commands assume you are at the repo root. Env facts live in the
[reference](reference.md).

## How to run X-RAG with Docker

Build:

```bash
docker build -t xrag .
```

You need a `.env` (copy `.env.example`) and a vector store the container can reach — either a
Postgres/pgvector `DB_URL`, or a Qdrant:

```bash
docker run -d --name xrag-qdrant -p 6333:6333 qdrant/qdrant
```

Run (Linux — recommended, host networking; needed when your `DB_URL` host is IPv6-only, as
Supabase poolers are, and lets the container reach a Qdrant on the host):

```bash
docker run -d --name xrag \
  --network host \
  -v "$PWD/.env:/app/.env:ro" \
  -v xrag-data:/app/data \
  -v xrag-models:/models \
  xrag
```

If host ports are already taken by a host-side deploy, shift the port:

```bash
docker run -d --name xrag --network host \
  -e PORT=8002 \
  -v "$PWD/.env:/app/.env:ro" -v xrag-data:/app/data -v xrag-models:/models \
  xrag
```

UI and API move together — the container serves both on the single `PORT`
(`frontend/app.js` uses same-origin outside localhost, `localhost:8001` in local dev).

Bridge networking works too when everything you depend on is IPv4-reachable:

```bash
docker run -d --name xrag -p 8001:8001 \
  -v "$PWD/.env:/app/.env:ro" -v xrag-data:/app/data -v xrag-models:/models \
  xrag
```

- UI + Swagger on the same port: <http://localhost:8001> (UI at `/`, Swagger at `/docs`)
- `SEED=0 docker run ...` skips demo-user creation (default: creates/updates `LUFFY` and `ZORO`).
- `xrag-data` holds uploads, indexes, logs. `xrag-models` holds Hugging Face models (`HF_HOME`).
- With `EMBED_PROVIDER=bge`, pull the model into the volume once:

  ```bash
  docker run --rm -v xrag-models:/models xrag hf download BAAI/bge-m3
  ```

- Any command after the image name replaces the normal boot sequence:

  ```bash
  docker logs -f xrag
  docker run --rm xrag python -m pytest -q
  ```

## How to switch providers

Edit `.env`, restart the server. The boot check in the log tells you immediately whether the new
provider came up.

| To change | Set |
|---|---|
| LLM → local Ollama | `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://localhost:11434`, `LLM_MODEL=llama3.1:8b-q4_0` |
| LLM → hosted OpenAI | `LLM_PROVIDER=openai`, `LLM_API_KEY=sk-...` |
| Embeddings → Jina API | `EMBED_PROVIDER=jina`, `EMBED_BASE_URL=https://api.jina.ai/v1`, `EMBED_API_KEY=jina_...` |
| Reranker → Jina | `RERANK_PROVIDER=jina`, `RERANK_API_KEY=...` |
| Metadata DB → Supabase | `DB_PROVIDER=supabase`, `DB_URL=postgresql://...` (vector store follows: pgvector) |
| Vector store → Qdrant Cloud | `VECTOR_BASE_URL=https://xxx.qdrant.io`, `VECTOR_API_KEY=...` |

Switching the embedding provider changes the vector space — re-upload affected documents
(same filename replaces the old vectors automatically).

## How to restrict a document to a department

Via the UI: when uploading, keep only the group chips that should see the document
(e.g. `hr` only).

Via the API:

```bash
curl -X POST "http://localhost:8001/ingest?allowed_groups=hr&enrich=true" \
  -H "Authorization: Bearer $TOKEN" -F "f=@policy.pdf"
```

A user whose groups do not intersect the document's `allowed_groups` will not see it in
`GET /documents`, and its chunks are excluded from retrieval before search runs. See
[explanation](explanation.md) for why filtering happens pre-search.

## How to delete a document or a chat

- **UI:** hover a row in the sources rail (or in the chat history) and press the trash icon.
- **API:**

  ```bash
  curl -X DELETE "http://localhost:8001/documents/policy.pdf" -H "Authorization: Bearer $TOKEN"
  curl -X DELETE "http://localhost:8001/conversations/42" -H "Authorization: Bearer $TOKEN"
  ```

Deleting a document removes its vectors, BM25/SPLADE entries, metadata row, uploaded file, and
invalidates the answer cache. Deletion requires group access (same ACL as reading); a
non-visible document returns `404`.

## How to run the tests

Unit/integration suite:

```bash
.venv/bin/python -m pytest -q
```

Browser end-to-end (needs a running backend + frontend and a Chrome on CDP port 9222):

```bash
CHROME_PATH=/path/to/chrome npx -y @accesslint/chrome@latest ensure
node frontend/e2e.mjs
```

The e2e run uploads fixture documents and asks fixture questions — clean them up afterwards
(delete `vacation_e2e_*` documents and conversations matching "vacation policy").

## How to use the built-in quality controls

No eval harness, no tracing stack — but the thin slices are usable today.
(Rationale: [explanation](explanation.md#about-whats-deliberately-left-out).)

- **Verification pill:** every answer carries `verification.supported_ratio`; the UI shows
  "RAG Verified" (≥60% of claims supported by cited chunks) or "Partially Grounded".
  Treat a low ratio like a test failure — inspect the cited chunks, not just the prose.
- **Refusals are a feature:** "I can't answer that: low retrieval confidence" means the
  confidence gate fired (nothing retrievable cleared the floor). Fix it by uploading the
  missing document, not by rephrasing.
- **Cache-hit pill:** a repeated (or paraphrased, cosine > 0.96) question shows "Cache Hit".
  Ingesting or deleting any document clears the cache, so citations never go stale.
- **Audit trail:** `GET /conversations` (or the `conversations` table) shows who asked
  what, with which citations — enough to replay any reported bad answer alongside
  `data/logs/api.log`.
- **Boot checks:** if the server won't start, the log names the failing provider row
  (`FAIL Groq key`, `FAIL Postgres`…). Fix the env var, not the code.
