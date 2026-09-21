<p align="center">
  <img src="doc_data/long_logo.png" alt="X-RAG" width="480" />
</p>

# X-RAG

Provider-pluggable enterprise RAG: upload documents, ask questions, get answers with citations `[doc#chunk]`, department ACL on every retrieval path.

**Stack:** FastAPI · pgvector (Supabase) or Qdrant · Jina/BGE embeddings · Groq/Ollama LLM · JWT groups (`hr` / `eng` / `public`).

---

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill keys / DB_URL as needed

.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run          # http://localhost:8001
```

Swagger: [http://localhost:8001/docs](http://localhost:8001/docs)  
Health: `GET /health` → `{"status":"ok", ...}`

### Seed users

| Username | Password | Groups |
|----------|----------|--------|
| `admin`  | `pass`   | hr, eng, public |
| `luffy`  | `pass`   | hr, public |
| `zoro`   | `pass`   | eng, public |

---

## Typical flow (API)

1. **Login** — `POST /auth/login` → `access_token`
2. **Ingest** — `POST /ingest?allowed_groups=hr&enrich=true` with multipart file field `f`
3. **Query** — `POST /query` body `{"query": "...", "top_k": 5, "mode": "quick"}`  
   - `mode`: `"quick"` | `"deep"` | omit for role default (`hr`→quick, `eng`→deep)

ACL is pre-search: a user’s `groups` must intersect the document’s `allowed_groups` or chunks are never retrieved.

---

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Covers ACL, pgvector cast, BM25 group filtering, auth, modes, cache, API surface.

---

## Docs map

| Kind | Where |
|------|--------|
| Product / layers / deploy matrix | [SPEC.md](SPEC.md) |
| Interactive API | `/docs` on a running server |
| Config template | [.env.example](.env.example) |
| This project entry point | this README |

Architecture deep-dives, how-to guides, and a full tutorial live under `docs/` when added — for now use SPEC + Swagger.

---

## Logos

| File | Use |
|------|-----|
| `doc_data/long_logo.png` | Wide wordmark (README header) |
| `doc_data/short_logo.png` | Shield mark (compact / avatar) |
