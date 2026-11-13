# SPEC: X-RAG — Completion Checklist

| Field | Detail |
|---|---|
| **Product** | X-RAG |
| **Stack** | Pluggable: `LLM` (Groq / Ollama / llama.cpp / OpenAI / Anthropic) + `Vector` (pgvector / Qdrant) + `DB` (SQLite / Postgres / Supabase) + `Embed` (BGE-M3 / Jina / Voyage / Cohere) + `Sparse` (BM25S / SPLADE-v3 gated) + `Graph` (Kuzu) + FastAPI + static UI |
| **Deploy** | `local` (laptop) · `ssh` (Oracle VPS tunnel) · `online` (Groq / Qdrant Cloud / Supabase) — all via `.env` |
| **Network** | Works offline (local) or online — `.env` decides |
| **Status** | **Phases 1–3 complete; 17/20 layers complete, 3 partial (deferred sub-features); L21/L22 removed** |

> **Routing = Manual Toggle Only.** No ML classifier. Quick/Deep toggle is the permanent mechanism.

Full documentation, API reference, env vars, and guides live in [README.md](README.md).

---

## 1. Success Criteria

- [x] **Phase 1** — cited answers `[doc#chunk]`, offline mode with `HF_HUB_OFFLINE=1`, Quick p95 < 3 s
- [x] **Phase 2** — HR document invisible to ENG, role-defaulted toggle, per-question override
- [x] **Phase 3** — Deep > Quick on multi-hop questions, p95 < 15 s warm

---

## 2. Layers (20) — Provider-Pluggable

Legend: `[x]` complete · `[ ]` partial (core works; named sub-feature deferred/gated).

- [x] **L1 Connector** — local loaders PDF/DOCX/PPTX/CSV/MD + images · `l01_connectors/`
- [ ] **L2 Doc Intelligence** — Docling local + RapidOCR fallback · `l02_docintel/` · *deferred: Qwen2-VL*
- [x] **L3 Cleaning** — MinHash dedup + Presidio PII (spaCy sm/lg) · `l03_cleaning/`
- [x] **L4 Chunking** — 8 strategies: Late/Contextual/Recursive/Semantic/Propositional/Parent/Window/Table-Code · `l04_chunking/`
- [x] **L5 Enrichment** — RAPTOR-lite + 3 HyQ + NER (LLM + spaCy) · `l05_enrichment/`
- [x] **L6a Embeddings (dense)** — `EMBED_PROVIDER` BGE / Jina / Voyage / Cohere · `l06_embedding/`
- [x] **L6b Sparse retrieval** — BM25S + SPLADE-v3 gated · `L06_sparse/`
- [x] **L7 Storage** — pgvector primary (Supabase/Postgres) with Qdrant fallback + Kuzu · `l07_storage/`
- [x] **L8 Freshness** — sha256 + `DB_URL`/`DB_PATH` re-embed, cache clear · `l08_freshness/`
- [x] **L9 Quick/Deep toggle** — UI toggle, role-defaulted via `DEFAULT_MODE_BY_GROUP` · `l09_toggle/`
- [x] **L10 Memory rewrite** — MemoRAG-lite from `conversations` · `l10_memory/`
- [x] **L11 Query transform** — multi-query + RRF + decomposition + step-back + HyDE · `l11_transforms/`
- [x] **L12 Routing (manual)** — manual toggle only · `l09_toggle/`
- [x] **L13 Multi-agent retrieval** — vector + graph + SQL + image agents · `l12_agents/`
- [x] **L14 Fusion + rerank** — RRF + MiniLM + Jina → BGE → MiniLM fallback + RankGPT + MMR · `l13_rerank/`
- [x] **L15 Security + ACL** — JWT + pre-search `allowed_groups` filter + injection screen + optional Nemo rail · `l14_security/`
- [ ] **L16 Budget optimizer** — RECOMP-lite extractive via MiniLM · `l15_compression/` · *deferred: full abstractive RECOMP*
- [x] **L17 Assembly** — budget 6000 + citations `[doc#chunk]` · `l16_assembly/`
- [x] **L18 Generation** — Self-RAG + CRAG via `LLM_PROVIDER` · `l17_generation/`
- [ ] **L19 Verification** — CoVe-lite + sentence labels; LLM judge when HHEM unavailable · `l18_verification/` · *deferred: HHEM*
- [x] **L20 Memory + cache** — `answer_cache` (cosine > 0.96) + LRU · `l19_cache/`

Removed: **L21 Evaluation** (replaced by a dev-only benchmark) and **L22 Infra**. Rationale: [README § What is deliberately left out](README.md#about-whats-deliberately-left-out).

---

## 3. Provider Matrix — Local / SSH / Online

| Capability | Local (`local`) | SSH / VPS (`ssh`) | Online (`online`) |
|---|---|---|---|
| **LLM** | `ollama` @ `localhost:11434` · `llama.cpp` @ `:8080` | Ollama via `ssh -L 11434:localhost:11434` | `groq` @ `api.groq.com` |
| **Embedding** | `bge` `BAAI/bge-m3` local | `EMBED_BASE_URL=http://localhost:8002/embed` via VPS | `jina` / `voyage` / `cohere` API |
| **Vector** | `qdrant` native | Qdrant via `ssh -L 6333:localhost:6333` | Qdrant Cloud or pgvector |
| **DB** | `sqlite` `data/meta.db` | `postgres` on VPS | `supabase` `postgresql://...` |
| **Sparse/Graph** | `bm25s`, gated `splade`, `kuzu` | same via VPS volume | same (file) |
| **Laptop load** | 7–12 GB RAM (heavy) | ~0 GB | ~0 GB |

**Selection at boot:** configured provider → next fallback → refuse to start with a named failing row. Storage uses pgvector when reachable, otherwise Qdrant.

---

## 4. Quick / Deep Mode — Manual Toggle Only

| | Quick | Deep |
|---|---|---|
| Retrieval | Dense only | Multi-query + multi-agent (vector/graph/SQL/image) + BM25/SPLADE, RRF-fused |
| Rerank | Single-stage MiniLM | Cascade MiniLM 50→30 → Jina (m0) → BGE → MiniLM 30→10 → RankGPT 10→5 + MMR |
| Verification | Off | On (CoVe-lite + sentence labels; LLM judge when HHEM unavailable) |
| Target p95 | < 3 s | < 15 s |
| Default | `hr`→quick, `eng`→deep | overridable per query |

---

## 5. Auth & DB Schema

```sql
users[id, username, password_hash, groups JSON]
documents[id, filename, allowed_groups JSON, hash, chunks]
conversations[id, user_id, query, answer, mode, score, contexts_json, citations_json, created_at]
answer_cache[key, answer, cites_json, qvec_json]   -- SQLite
```

ACL is enforced **before** search on every path (dense, sparse, graph, cache key).

---

## 6. Models (pluggable via `.env`)

| Model | Default | Via | Size | Env |
|---|---|---|---|---|
| LLM Groq | `openai/gpt-oss-20b` | `ChatGroq` | API | `LLM_API_KEY` |
| LLM Ollama | `llama3.1:8b-q4_0` | `ChatOllama` | 4.9 GB | `LLM_BASE_URL` |
| LLM llama.cpp | `llama3.1:8b` | `ChatOpenAI` compat | local | `LLM_BASE_URL` |
| LLM OpenAI | `gpt-4o-mini` | `ChatOpenAI` | API | `LLM_API_KEY` |
| LLM Anthropic | `claude-3-haiku` | `ChatAnthropic` | API | `LLM_API_KEY` |
| BGE-M3 | `BAAI/bge-m3` | `HuggingFaceEmbeddings` | 2.2 GB | `EMBED_MODEL` |
| Jina v3 | `jina-embeddings-v3` | HTTP | API | `EMBED_API_KEY` |
| Voyage 3 | `voyage-3-large` | HTTP | API | `EMBED_API_KEY` |
| Cohere | `embed-english-v3.0` | HTTP | API | `EMBED_API_KEY` |
| MiniLM | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `CrossEncoder` | 80 MB | — |
| BM25S / SPLADE-v3 | — | `bm25s` / `transformers` | — / 500 MB gated | — |

---

## 7. Deployment — No App Container

**Local:**

```bash
python3 -m venv .venv && .venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
cp .env.example .env
docker run -d --name xrag-qdrant -p 6333:6333 qdrant/qdrant
.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run
```

**SSH / Oracle VPS:**

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

---

## 8. Verification Status

- [x] Unit/integration suite — `pytest` (80 tests)
- [x] Browser e2e suite — `node frontend/e2e.mjs`
- [x] Dev-only answer benchmark — 80% pass (8/10), avg 7.74 s, p95 12.80 s → [`data/evaluation.md`](data/evaluation.md)
- [x] Remote-primary + local-fallback storage selection verified
- [x] Documentation consolidated into [README.md](README.md); obsolete `docs/` removed
- [x] Logo/banner moved to repo root (`logo.png`, `banner.png`)
