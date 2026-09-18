# SPEC: X-RAG — Provider-Pluggable Enterprise RAG

| Field | Detail |
|---|---|
| **Product** | X-RAG |
| **Stack** | Pluggable: `LLM` (Groq / Ollama / llama.cpp) + `Vector` (Qdrant / Supabase pgvector) + `DB` (SQLite / Postgres / Supabase) + `Embed` (BGE-M3 / Choreo) + `Queue` (none / Redis / Upstash) + `Kuzu` + `BM25S` + FastAPI + Next.js |
| **Deploy** | `local` (laptop) · `ssh` (Oracle VPS tunnel) · `online` (Groq / Supabase / Upstash) — all via `.env`, no Docker |
| **Network** | Works offline (local) or online — `.env` decides; no `docker compose` required |
| **Status** | **Phases 1–3 shipped, L22 removed Sep-15 pending rewrite** (see §6) |

> **Routing = Manual Toggle Only.** No ML classifier. Quick/Deep toggle is the permanent mechanism.

---

## 1. What It Does

Employees upload documents, chat with cited answers `[doc#chunk]`, on company WiFi. Department isolation via ACL — HR docs stay HR-only. Every query is judged (`judge_score` → `conversations.score`) and observable via `query_telemetry` + `answer_cache`.

---

## 2. Env — Single Source of Truth

**All model and storage APIs live in `.env`.** Same code runs `local`, via `ssh` tunnel to Oracle VPS, or `online` with hosted APIs — app auto-detects at boot. No `docker compose`, no hardcoded URLs.

```ini
# --- App ---
HOST=0.0.0.0
PORT=8001
CORS_ORIGINS=http://localhost:3000,https://your-choreo-frontend
JWT_SECRET=change-me
JWT_EXPIRE_MIN=480
DEFAULT_MODE_BY_GROUP={"hr":"quick","eng":"deep","public":"quick"}

# --- LLM: groq (api) | ollama (local) | llama.cpp (local) ---
LLM_PROVIDER=groq
GROQ_API_KEY=sk-...
GROQ_BASE_URL=https://api.groq.com
GROQ_MODEL=openai/gpt-oss-20b
OLLAMA_URL=http://localhost:11434          # local or ssh -L 11434:localhost:11434 vps
OLLAMA_MODEL=llama3.1:8b-q4_0
LLAMA_CPP_URL=http://localhost:8080        # llama.cpp server
LLAMA_CPP_MODEL=llama3.1:8b

# --- Embedding: bge (local) | choreo (remote) ---
EMBED_PROVIDER=bge
EMBED_MODEL=BAAI/bge-m3
EMBED_URL=                                   # https://<choreo>.choreoapps.dev/embed or http://vps:8002/embed
HF_HUB_OFFLINE=0
TRANSFORMERS_OFFLINE=0

# --- Vector Store: qdrant | supabase ---
VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=http://localhost:6333            # local or ssh -L 6333:localhost:6333 vps
QDRANT_COLLECTION=offline_rag
QDRANT_API_KEY=                              # for Qdrant Cloud

# --- Database: sqlite (local) | postgres (local) | supabase (cloud) ---
# DATABASE_URL takes precedence; fallback is SQLITE_PATH
SQLITE_PATH=data/meta.db
DATABASE_URL=                                # postgresql://user:pass@localhost:5432/xrag
# SUPABASE_URL=https://xxx.supabase.co
# SUPABASE_KEY=eyJ...

# --- Queue: none | redis (local) | upstash (cloud) ---
QUEUE_PROVIDER=none
REDIS_URL=redis://localhost:6379/0
UPSTASH_REDIS_REST_URL=https://...upstash.io
UPSTASH_REDIS_REST_TOKEN=...

# --- Storage ---
UPLOAD_DIR=data/uploads
```

Frontend needs only one var (bake-time): `frontend/.env` → `NEXT_PUBLIC_API_URL=http://localhost:8001` (or `https://api.<vps>`). Rebuild (`npm run build`) after changing.

---

## 3. Provider Matrix — Local / SSH / Online

| Capability | Local (`local`) | SSH / VPS (`ssh`) | Online (`online`) |
|---|---|---|---|
| **LLM** | `ollama` @ `localhost:11434` · `llama.cpp` @ `:8080` | `OLLAMA_URL=http://localhost:11434` via `ssh -L 11434:localhost:11434 vps` (Oracle A1 Flex, 24GB holds 7–8GB stack) | `groq` @ `api.groq.com` (0 local RAM, fastest for laptop) |
| **Embedding** | `bge` `BAAI/bge-m3` 2.3GB local (`HuggingFaceEmbeddings`) | `EMBED_URL=http://localhost:8002/embed` via VPS | `choreo` `BAAI/bge-small-en-v1.5` 130MB (Choreo 512MB limit) or proxy to VPS |
| **Vector** | `qdrant` native `./qdrant --storage-path data/qdrant_storage` | `QDRANT_URL=http://localhost:6333` via `ssh -L 6333:localhost:6333 vps` | Qdrant Cloud (`QDRANT_API_KEY`) or Supabase pgvector |
| **DB** | `sqlite` `data/meta.db` | `postgres` local on VPS `postgresql://...` | `supabase` `postgresql://...` |
| **Queue** | `none` (BackgroundTasks) | `redis` `redis://...` on VPS | `upstash` REST |
| **Graph/Sparse** | `kuzu` `data/kuzu`, `bm25s` `data/bm25.pkl` | same via VPS volume | same (file) |
| ** laptop load** | 7–12GB RAM (heavy) | ~0GB (all on VPS) | ~0GB |

**Priority at runtime:** `local` if provider URL reachable → `ssh` if tunnel active → `online` API fallback. App probes in `config.check_requirements()` and `llm.get_llm()` / `bge.get_embeddings()` switching.

---

## 4. Detection Logic (how `.env` drives code)

*   `backend/config.py:Settings` (`pydantic_settings`, `extra="ignore"`) — every provider is a field. Unknown envs ignored.
*   `backend/l18_generation/llm.py:get_llm()` — `if llm_provider=="ollama": ChatOllama(...)` `elif=="llama.cpp": ChatOpenAI(base_url=LLAMA_CPP_URL+"/v1")` `else: ChatGroq(...)`.
*   `backend/l06_embedding/bge.py:get_embeddings()` — if `EMBED_URL`/`EMBED_PROVIDER=="choreo"`: `httpx.post(EMBED_URL, {"texts":...})` shim, same `embed_documents/embed_query` signature; else local `HuggingFaceEmbeddings`.
*   `backend/l07_storage/qdrant.py:_client()` — adds `api_key=QDRANT_API_KEY` when set; future `VECTOR_STORE_PROVIDER==supabase` would swap to pgvector client.
*   `backend/l08_freshness/store.py:meta_conn()` — if `DATABASE_URL` starts with `postgresql://`/`postgres://` → `psycopg` else `sqlite3` (`SQLITE_PATH` fallback). Same `SCHEMA` works on both. Supabase reuses postgres URL.
*   `backend/api.py` + `graph.py:_record_telemetry` — queue `none` keeps `BackgroundTasks` judge; `redis`/`upstash` would enqueue (L22 rewrite).

---

## 5. Quick / Deep Mode — Manual Toggle Only

| | Quick | Deep |
|---|---|---|
| Retrieval | Dense only (BGE → Qdrant/Supabase) | Multi-query + Multi-agent (vector/graph/SQL/image) + BM25/SPLADE, RRF-fused |
| Rerank | Single-stage MiniLM | Cascade MiniLM 50→30 → BGE-reranker gated → RankGPT-listwise 10→5 + MMR |
| Verification | Off | On (CoVe-lite + sentence labels; LLM judge when HHEM unavailable) |
| Target p95 | < 3s | < 15s |
| Default | `hr`→quick, `eng`→deep (via `DEFAULT_MODE_BY_GROUP`) | overridable per query |

---

## 6. Layers — Provider-Pluggable (L22 removed)

L22 Infra+RAGOps removed Sep-15 (Sep-13 second `54dc80a` + Sep-14 docs reverted). Will be rewritten env-driven.

| # | Layer | Provider (env, default) | Where | Phase | Status |
|---|---|---|---|---|---|
| 1 | Connector | Local loaders PDF/DOCX/PPTX/CSV/MD + images | ingestion/ | 1 | ✅ |
| 2 | Doc Intelligence | `Docling` local + `RapidOCR` fallback | ingestion/parsing/ | 1/3 | ◐ Qwen2-VL deferred |
| 3 | Cleaning | `MinHash` dedup + `Presidio` PII (`spacy` sm/lg) | ingestion/cleaning/ | 1 | ✅ |
| 4 | Chunking Router | 8 strategies: Late/Contextual/Recursive/Semantic/Propositional/Parent/Window/Table-Code | chunking/ | 1/3 | ✅ |
| 5 | Enrichment | RAPTOR-lite + 3 HyQ + NER (LLM + spaCy) | enrichment/ | 2/3 | ✅ |
| 6 | Embedding | `EMBED_PROVIDER` `bge` (`EMBED_MODEL=BAAI/bge-m3`) or `choreo` (`EMBED_URL`) + `bm25s` + `SPLADE-v3` gated | indexing/ | 1/3 | ✅ |
| 7 | Storage | `VECTOR_STORE_PROVIDER` `qdrant` (`QDRANT_URL`) or `supabase` + `kuzu` `data/kuzu` + `bm25.pkl` | indexing/ | 1 | ✅ |
| 8 | Freshness | `sha256` + `DATABASE_URL`/`SQLITE_PATH` re-embed, cache clear | core/ | 1 | ✅ |
| 9 | Quick/Deep Toggle | UI toggle, role-defaulted via `DEFAULT_MODE_BY_GROUP` | retrieval/ | 2 | ✅ |
| 9-ORIG | ~~Adaptive Gate~~ | Removed — manual toggle only | retrieval/ | — | ❌ Cut |
| 10 | Memory Rewrite | MemoRAG-lite from `conversations` (DB) | retrieval/ + DB | 3 | ◐ |
| 11 | Query Transform | Multi-Query + RRF + Decomposition + Step-Back + HyDE via `LLM_PROVIDER` | retrieval/ | 3 | ✅ |
| 12-ORIG | ~~Intent + Policy Model~~ | Removed — manual toggle only | retrieval/router/ | — | ❌ Cut |
| 12 | Quick/Deep Routing | Manual toggle only | retrieval/router/ | 2 | ✅ |
| 13 | Multi-Agent Retrieval | vector + graph + SQL + image agents (parallel in deep) | retrieval/agents/ | 3 | ✅ |
| 14 | Fusion + Rerank | `RRF` + `MiniLM` + `RankGPT` + `MMR` (BGE-reranker gated) | retrieval/ | 2/3 | ✅ |
| 15 | Security + AUTH + ACL | `JWT` + `QDRANT` pre-search `allowed_groups` filter | core/security | 2/3 | ✅ |
| 16 | Budget Optimizer | `RECOMP-lite` extractive via `MiniLM` | retrieval/compression/ | 3 | ◐ |
| 17 | Assembly | Budget `6000` + citations `[doc#chunk]` | generation/ | 1 | ✅ |
| 18 | Generation | `Self-RAG` + `CRAG` via `LLM_PROVIDER` (`groq`/`ollama`/`llama.cpp`) | generation/ | 1/3 | ✅ |
| 19 | Verification | `CoVe-lite` + `HHEM` parked → LLM fallback | verification/ | 3 | ◐ |
| 20 | Memory + Cache | `answer_cache` (`cosine>0.96` + `EMBED_PROVIDER`) + LRU (`DB`) | memory_cache/ | 2 | ✅ |
| 21 | Eval + Online Judge | `RAGAS` offline + `judge_score` → `conversations.score` (DB) via `QUEUE_PROVIDER` | evaluation/ | 2 | ✅ |
| 22 | Infra + RAGOps | **Removed** — was Redis Streams + INT8 quant + Langfuse v3 + mining + Prometheus | deploy/+l22 | 4 | ⏸ Sep-15 revert, rewrite pending |

> Layers 9-ORIG/12-ORIG struck. Every `◐` keeps pluggable `.env` philosophy; docs in `SPEC.md` §2–4.

---

## 7. Auth & DB Schema

```sql
users[id, username, password_hash, groups JSON]
documents[id, filename, allowed_groups JSON, hash]
conversations[id, user_id, query, answer, mode, score, contexts_json]
query_telemetry[id, user_id, mode, cache_hit, latency_ms, n_queries, n_hits, rerank_stage, supported_ratio, provider]
eval_goldens[id, query, golden_answer, gold_cites_json, groups_json]        -- orphaned after L22 removal, kept for rewrite
mined_hard_negatives[id, query, doc, chunk_id, label_json]                  -- orphaned after L22 removal
```

Qdrant/Supabase filter `allowed_groups` enforced **before** search. Mode default from `DEFAULT_MODE_BY_GROUP`.

---

## 8. Models (pluggable via `.env`)

| Model | Default | Via | Size | Env |
|---|---|---|---|---|
| LLM Groq | `openai/gpt-oss-20b` | `ChatGroq` | API 0GB | `GROQ_API_KEY` |
| LLM Ollama | `llama3.1:8b-q4_0` | `ChatOllama` | 4.9GB | `OLLAMA_URL` |
| LLM llama.cpp | `llama3.1:8b` | `ChatOpenAI` compat | local | `LLAMA_CPP_URL` |
| BGE-M3 | `BAAI/bge-m3` | `HuggingFaceEmbeddings` | 2.2GB | `EMBED_MODEL` |
| BGE-small (Choreo) | `BAAI/bge-small-en-v1.5` | `httpx` to `EMBED_URL` | 130MB | `EMBED_URL` |
| MiniLM | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `CrossEncoder` | 80MB | — |
| BM25S / SPLADE-v3 | — | `bm25s` / `transformers` | — / 500MB gated | — |
| HHEM | `vectara/...` | `CrossEncoder` | 400MB parked | — |

Minimal laptop `local` set = BGE-M3 + MiniLM = ~2.3GB without LLM (Groq removes 4.9GB). SSH to VPS = 0GB on laptop.

---

## 9. Deployment — No Docker

**Local:**
```bash
python3 -m venv .venv && .venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # fill GROQ_API_KEY or OLLAMA_URL, DATABASE_URL etc.
./qdrant --storage-path data/qdrant_storage &  # native binary
.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run                # :8001
cd frontend && npm ci && npm run build && npm run start -- -p 3000 -H 0.0.0.0
```

**SSH / Oracle VPS (laptop fast):**
```bash
ssh -L 6333:localhost:6333 -L 11434:localhost:11434 ubuntu@<vps-ip> -N &
# .env: QDRANT_URL=http://localhost:6333  OLLAMA_URL=http://localhost:11434  LLM_PROVIDER=ollama
```

**Online (Choreo + hosted):**
```ini
LLM_PROVIDER=groq
GROQ_API_KEY=...
DATABASE_URL=postgresql://...supabase...
VECTOR_STORE_PROVIDER=qdrant  # QDRANT_URL=https://xxx.qdrant.io  QDRANT_API_KEY=...
QUEUE_PROVIDER=upstash
```

Systemd on VPS (no Docker): `xrag-qdrant.service`, `xrag-api.service` (`WorkingDirectory=/home/ubuntu/X-RAG`, `EnvironmentFile=.env`), `xrag-web.service`. Caddy/Nginx proxies `api.<domain>` → `127.0.0.1:8001`.

---

## 10. Success Criteria

| Phase | Bar | Result |
|---|---|---|
| 1 | Cited answers, 0 packets out with `HF_HUB_OFFLINE=1`, Quick p95 <3s | ✅ |
| 2 | HR doc invisible to Eng, toggle by role, overridable | ✅ |
| 3 | Deep > Quick on multi-hop, p95 <15s warm | ✅ |
| 4 | **Removed** — async eval / telemetry / tracing / quant / mining pending rewrite env-driven | ⏸ |

L22 rewrite will re-add `QUEUE_PROVIDER redis|upstash` durable eval, `Langfuse` optional tracing, `INT8` perf, mining/finetune — all via `.env`, no Docker.
