# SPEC: X-RAG — Provider-Pluggable Enterprise RAG

| Field | Detail |
|---|---|
| **Product** | X-RAG |
| **Stack** | Pluggable: `LLM` (Groq / Ollama / llama.cpp / OpenAI / Anthropic) + `Vector` (Qdrant) + `DB` (SQLite / Postgres / Supabase) + `Embed` (BGE-M3 / Jina / Voyage / Cohere) + `Sparse` (BM25S / SPLADE-v3 gated) + `Graph` (Kuzu) + FastAPI + Next.js |
| **Deploy** | `local` (laptop) · `ssh` (Oracle VPS tunnel) · `online` (Groq / Qdrant Cloud / Supabase) — all via `.env`, no Docker |
| **Network** | Works offline (local) or online — `.env` decides; no `docker compose` required |
| **Status** | **Phases 1–3 shipped, L21/L22 removed** (see §6) |

> **Routing = Manual Toggle Only.** No ML classifier. Quick/Deep toggle is the permanent mechanism.

---

## 1. What It Does

Employees upload documents, chat with cited answers `[doc#chunk]`, on company WiFi. Department isolation via ACL — HR docs stay HR-only. Every query is observable via `answer_cache`.

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

# --- LLM ---
LLM_PROVIDER=groq              # groq | ollama | llama.cpp | openai | anthropic
LLM_BASE_URL=https://api.groq.com
LLM_MODEL=openai/gpt-oss-20b
LLM_API_KEY=sk-...

# --- Embeddings ---
EMBED_PROVIDER=bge             # bge | jina | voyage | cohere | choreo
EMBED_BASE_URL=                # https://api.jina.ai/v1 | https://api.voyageai.com/v1 | https://api.cohere.ai/v1
EMBED_MODEL=BAAI/bge-m3
EMBED_API_KEY=

# --- Vector Store (Qdrant only) ---
VECTOR_BASE_URL=http://localhost:6333
VECTOR_API_KEY=
VECTOR_COLLECTION=offline_rag

# --- Database (SQL) ---
DB_PROVIDER=sqlite             # sqlite | postgres | supabase
DB_URL=                        # postgresql://... for postgres/supabase
DB_PATH=data/meta.db

# --- Storage ---
UPLOAD_DIR=data/uploads
```

Frontend needs only one var (bake-time): `frontend/.env` → `NEXT_PUBLIC_API_URL=http://localhost:8001` (or `https://api.<vps>`). Rebuild (`npm run build`) after changing.

---

## 3. Provider Matrix — Local / SSH / Online

| Capability | Local (`local`) | SSH / VPS (`ssh`) | Online (`online`) |
|---|---|---|---|
| **LLM** | `ollama` @ `localhost:11434` · `llama.cpp` @ `:8080` | `LLM_BASE_URL=http://localhost:11434` via `ssh -L 11434:localhost:11434 vps` (Oracle A1 Flex, 24GB holds 7–8GB stack) | `groq` @ `api.groq.com` (0 local RAM, fastest for laptop) |
| **Embedding** | `bge` `BAAI/bge-m3` 2.3GB local (`HuggingFaceEmbeddings`) | `EMBED_BASE_URL=http://localhost:8002/embed` via VPS | `jina` `jina-embeddings-v3` / `voyage-3-large` / `cohere` (API) |
| **Vector** | `qdrant` native `./qdrant --storage-path data/qdrant_storage` | `VECTOR_BASE_URL=http://localhost:6333` via `ssh -L 6333:localhost:6333 vps` | Qdrant Cloud (`VECTOR_BASE_URL=https://xxx.qdrant.io`) |
| **DB** | `sqlite` `data/meta.db` | `postgres` local on VPS `postgresql://...` | `supabase` `postgresql://...` |
| **Sparse/Graph** | `bm25s` `data/bm25.pkl`, `splade` gated, `kuzu` `data/kuzu` | same via VPS volume | same (file) |
| ** laptop load** | 7–12GB RAM (heavy) | ~0GB (all on VPS) | ~0GB |

**Priority at runtime:** `local` if provider URL reachable → `ssh` if tunnel active → `online` API fallback. App probes in `config.check_requirements()` and `llm.get_llm()` / `bge.get_embeddings()` switching.

---

## 4. Detection Logic (how `.env` drives code)

*   `backend/config.py:Settings` (`pydantic_settings`, `extra="ignore"`) — every provider is a field. Unknown envs ignored.
*   `backend/l17_generation/llm.py:get_llm()` — unified config: `LLM_PROVIDER` + `LLM_BASE_URL` + `LLM_MODEL` + `LLM_API_KEY`. Local defaults: Ollama `http://localhost:11434`, llama.cpp `http://localhost:8080/v1`.
*   `backend/l06_embedding/bge.py:get_embeddings()` — unified config: `EMBED_PROVIDER` + `EMBED_BASE_URL` + `EMBED_MODEL` + `EMBED_API_KEY`. Supports Jina, Voyage, Cohere, Choreo, and local BGE.
*   `backend/l13_rerank/provider.py:get_reranker_provider()` — unified config: `RERANK_PROVIDER` + `RERANK_BASE_URL` + `RERANK_MODEL` + `RERANK_API_KEY`. Fallback chain: Jina API (m0) → Local BGE-reranker → Local MiniLM.
*   `backend/l07_storage/qdrant.py:_client()` — unified config: `VECTOR_BASE_URL` + `VECTOR_API_KEY` + `VECTOR_COLLECTION`.
*   `backend/l08_freshness/store.py:meta_conn()` — unified config: `DB_PROVIDER` + `DB_URL` (Postgres/Supabase) or `DB_PATH` (SQLite).

---

## 5. Quick / Deep Mode — Manual Toggle Only

| | Quick | Deep |
|---|---|---|
| Retrieval | Dense only (BGE → Qdrant) | Multi-query + Multi-agent (vector/graph/SQL/image) + BM25/SPLADE, RRF-fused |
| Rerank | Single-stage MiniLM | Cascade MiniLM 50→30 → **Jina API (m0) → BGE-reranker → MiniLM fallback** 30→10 → RankGPT-listwise 10→5 + MMR |
| Verification | Off | On (CoVe-lite + sentence labels; LLM judge when HHEM unavailable) |
| Target p95 | < 3s | < 15s |
| Default | `hr`→quick, `eng`→deep (via `DEFAULT_MODE_BY_GROUP`) | overridable per query |

---

## 6. Layers — Provider-Pluggable (20 Layers)

| # | Layer | Provider (env, default) | Where | Phase | Status |
|---|---|---|---|---|---|
| 1 | Connector | Local loaders PDF/DOCX/PPTX/CSV/MD + images | `l01_connectors/` | 1 | ✅ |
| 2 | Doc Intelligence | `Docling` local + `RapidOCR` fallback | `l02_docintel/` | 1/3 | ◐ Qwen2-VL deferred |
| 3 | Cleaning | `MinHash` dedup + `Presidio` PII (`spacy` sm/lg) | `l03_cleaning/` | 1 | ✅ |
| 4 | Chunking | 8 strategies: Late/Contextual/Recursive/Semantic/Propositional/Parent/Window/Table-Code | `l04_chunking/` | 1/3 | ✅ |
| 5 | Enrichment | RAPTOR-lite + 3 HyQ + NER (LLM + spaCy) | `l05_enrichment/` | 2/3 | ✅ |
| 6a | Embeddings (Dense) | `EMBED_PROVIDER` `bge` (`EMBED_MODEL=BAAI/bge-m3`) or remote (`EMBED_BASE_URL`) | `l06_embedding/` | 1/3 | ✅ |
| 6b | Sparse Retrieval | `bm25s` + `SPLADE-v3` gated (500MB model) | `L06_sparse/` | 1/3 | ✅ |
| 7 | Storage | `VECTOR_BASE_URL` + `VECTOR_API_KEY` (Qdrant) + `kuzu` `data/kuzu` | `l07_storage/` | 1 | ✅ |
| 8 | Freshness | `sha256` + `DB_URL`/`DB_PATH` re-embed, cache clear | `l08_freshness/` | 1 | ✅ |
| 9 | Quick/Deep Toggle | UI toggle, role-defaulted via `DEFAULT_MODE_BY_GROUP` | `l09_toggle/` | 2 | ✅ |
| 10 | Memory Rewrite | MemoRAG-lite from `conversations` (DB) | `l10_memory/` + DB | 3 | ✅ |
| 11 | Query Transform | Multi-Query + RRF + Decomposition + Step-Back + HyDE via `LLM_PROVIDER` | `l11_transforms/` | 3 | ✅ |
| 12 | Routing (Manual) | Manual toggle only | `l09_toggle/` | 2 | ✅ |
| 13 | Multi-Agent Retrieval | vector + graph + SQL + image agents (parallel in deep) | `l12_agents/` | 3 | ✅ |
| 14 | Fusion + Rerank | `RRF` + `MiniLM` + **Jina API (m0) → BGE-reranker → MiniLM fallback** + `RankGPT` + `MMR` | `l13_rerank/` | 2/3 | ✅ |
| 15 | Security + ACL | `JWT` + vector pre-search `allowed_groups` filter | `l14_security/` | 2/3 | ✅ |
| 16 | Budget Optimizer | `RECOMP-lite` extractive via `MiniLM` | `l15_compression/` | 3 | ◐ |
| 17 | Assembly | Budget `6000` + citations `[doc#chunk]` | `l16_assembly/` | 1 | ✅ |
| 18 | Generation | `Self-RAG` + `CRAG` via `LLM_PROVIDER` (`groq`/`ollama`/`llama.cpp`/OpenAI/Anthropic) | `l17_generation/` | 1/3 | ✅ |
| 19 | Verification | `CoVe-lite` + `HHEM` parked → LLM fallback | `l18_verification/` | 3 | ◐ |
| 20 | Memory + Cache | `answer_cache` (`cosine>0.96` + `EMBED_PROVIDER`) + LRU (`DB`) | `l19_cache/` | 2 | ✅ |

> ◐ = core works, named sub-feature deferred/gated per spec (Qwen2-VL, full abstractive RECOMP, HHEM). L21 Eval + L22 Infra removed.

---

## 7. Auth & DB Schema

```sql
users[id, username, password_hash, groups JSON]
documents[id, filename, allowed_groups JSON, hash]
conversations[id, user_id, query, answer, mode, score, contexts_json]
```

Qdrant filter `allowed_groups` enforced **before** search. Mode default from `DEFAULT_MODE_BY_GROUP`.

---

## 8. Models (pluggable via `.env`)

| Model | Default | Via | Size | Env |
|---|---|---|---|---|
| LLM Groq | `openai/gpt-oss-20b` | `ChatGroq` | API 0GB | `LLM_API_KEY` |
| LLM Ollama | `llama3.1:8b-q4_0` | `ChatOllama` | 4.9GB | `LLM_BASE_URL` |
| LLM llama.cpp | `llama3.1:8b` | `ChatOpenAI` compat | local | `LLM_BASE_URL` |
| LLM OpenAI | `gpt-4o-mini` | `ChatOpenAI` | API 0GB | `LLM_API_KEY` |
| LLM Anthropic | `claude-3-haiku` | `ChatAnthropic` | API 0GB | `LLM_API_KEY` |
| BGE-M3 | `BAAI/bge-m3` | `HuggingFaceEmbeddings` | 2.2GB | `EMBED_MODEL` |
| Jina v3 | `jina-embeddings-v3` | HTTP to `EMBED_BASE_URL` | API | `EMBED_API_KEY` |
| Voyage 3 | `voyage-3-large` | HTTP to `EMBED_BASE_URL` | API | `EMBED_API_KEY` |
| Cohere | `embed-english-v3.0` | HTTP to `EMBED_BASE_URL` | API | `EMBED_API_KEY` |
| MiniLM | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `CrossEncoder` | 80MB | — |
| BM25S / SPLADE-v3 | — | `bm25s` / `transformers` | — / 500MB gated | — |

Minimal laptop `local` set = BGE-M3 + MiniLM = ~2.3GB without LLM (Groq removes 4.9GB). SSH to VPS = 0GB on laptop.

---

## 9. Deployment — No Docker

**Local:**
```bash
python3 -m venv .venv && .venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # fill LLM_API_KEY or LLM_BASE_URL, DB_URL etc.
./qdrant --storage-path data/qdrant_storage &  # native binary
.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run                # :8001
cd frontend && npm ci && npm run build && npm run start -- -p 3000 -H 0.0.0.0
```

**SSH / Oracle VPS (laptop fast):**
```bash
ssh -L 6333:localhost:6333 -L 11434:localhost:11434 ubuntu@<vps-ip> -N &
# .env: VECTOR_BASE_URL=http://localhost:6333  LLM_BASE_URL=http://localhost:11434  LLM_PROVIDER=ollama
```

**Online (hosted):**
```ini
LLM_PROVIDER=groq
LLM_API_KEY=...
DB_PROVIDER=supabase
DB_URL=postgresql://...supabase...
VECTOR_BASE_URL=https://xxx.qdrant.io
VECTOR_API_KEY=...
```

Systemd on VPS (no Docker): `xrag-qdrant.service`, `xrag-api.service` (`WorkingDirectory=/home/ubuntu/X-RAG`, `EnvironmentFile=.env`), `xrag-web.service`. Caddy/Nginx proxies `api.<domain>` → `127.0.0.1:8001`.

---

## 10. Success Criteria

| Phase | Bar | Result |
|---|---|---|
| 1 | Cited answers, 0 packets out with `HF_HUB_OFFLINE=1`, Quick p95 <3s | ✅ |
| 2 | HR doc invisible to Eng, toggle by role, overridable | ✅ |
| 3 | Deep > Quick on multi-hop, p95 <15s warm | ✅ |

---

**Models for full high (Deep) mode on laptop:** 3 models minimum — BGE-M3 (2.2GB) + MiniLM (80MB) + LLM via Ollama (4.9GB for llama3.1:8b) = ~7.2GB. With Groq API: 2 local models (BGE-M3 + MiniLM) = ~2.3GB.