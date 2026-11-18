# SPEC: X-RAG — Completion Checklist

| Field | Detail |
|---|---|
| **Product** | X-RAG |
| **Stack (`aws-deploy`)** | API-only: `LLM` (Groq / OpenAI / Anthropic) + `Vector` (pgvector only) + `DB` (Postgres / Supabase) + `Embed` (Jina / Voyage / Cohere) + `Sparse` (BM25S + local SPLADE) + `Graph` (Kuzu) + FastAPI + static UI |
| **Deploy (`aws-deploy`)** | `container` (Docker Compose `xrag` + Caddy) with remote LLM/embeddings/reranker + Supabase/Postgres pgvector; no Qdrant, SQLite metadata, or local inference fallbacks |
| **Live** | <https://xrag.duckdns.org> (EC2 · Docker Compose · Caddy) |
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
- [x] **L6a Embeddings (dense)** — remote `EMBED_PROVIDER` Jina / Voyage / Cohere · `l06_embedding/`
- [x] **L6b Sparse retrieval** — BM25S + SPLADE-v3 local (no API alternative) · `L06_sparse/`
- [x] **L7 Storage** — pgvector only (Supabase/Postgres) + Kuzu · `l07_storage/`
- [x] **L8 Freshness** — sha256 + Postgres `DB_URL` re-embed, cache clear · `l08_freshness/`
- [x] **L9 Quick/Deep toggle** — UI toggle, role-defaulted via `DEFAULT_MODE_BY_GROUP` · `l09_toggle/`
- [x] **L10 Memory rewrite** — MemoRAG-lite from `conversations` · `l10_memory/`
- [x] **L11 Query transform** — multi-query + RRF + decomposition + step-back + HyDE · `l11_transforms/`
- [x] **L12 Routing (manual)** — manual toggle only · `l09_toggle/`
- [x] **L13 Multi-agent retrieval** — vector + graph + SQL + image agents · `l12_agents/`
- [x] **L14 Fusion + rerank** — RRF + Jina API rerank + RankGPT + MMR (remote embeddings) · `l13_rerank/`
- [x] **L15 Security + ACL** — JWT + pre-search `allowed_groups` filter + injection screen + optional Nemo rail · `l14_security/`
- [ ] **L16 Budget optimizer** — deterministic truncation budget · `l15_compression/` · *deferred: full abstractive RECOMP*
- [x] **L17 Assembly** — budget 6000 + citations `[doc#chunk]` · `l16_assembly/`
- [x] **L18 Generation** — Self-RAG + CRAG via `LLM_PROVIDER` · `l17_generation/`
- [ ] **L19 Verification** — LLM-only sentence labels (local HHEM removed) · `l18_verification/` · *deferred: local NLI*
- [x] **L20 Memory + cache** — `answer_cache` (cosine > 0.96) + LRU · `l19_cache/`

Removed: **L21 Evaluation** (replaced by a dev-only benchmark) and **L22 Infra**. Rationale: [README § What is deliberately left out](README.md#about-whats-deliberately-left-out).

---

## 3. Provider Matrix — Local / SSH / Online

| Capability | `aws-deploy` (this branch) |
|---|---|
| **LLM** | remote `groq` / `openai` / `anthropic` only |
| **Embedding** | remote `jina` / `voyage` / `cohere` only |
| **Rerank** | remote Jina API only |
| **Vector** | pgvector only (Supabase/Postgres) |
| **DB** | `postgres` / `supabase` only (`sqlite` reserved for unit tests) |
| **Sparse/Graph** | `bm25s`, local `splade`, `kuzu` (no API alternative) |
| **Local inference** | none except SPLADE (kept by decision) |

**Selection at boot:** remote providers + pgvector only. Any missing key/model, 429/quota limit, missing/unreachable database, or missing pgvector extension is reported and the server refuses to start. No fallback chain and no Qdrant/SQLite storage.

---

## 4. Quick / Deep Mode — Manual Toggle Only

| | Quick | Deep |
|---|---|---|
| Retrieval | Dense (+BM25 if available) | Multi-query + multi-agent (vector/graph/SQL/image) + BM25/SPLADE, RRF-fused |
| Rerank | Remote Jina top-k | Remote Jina 50→30 → 30→10 → RankGPT 10→5 + MMR (remote embeddings) |
| Verification | Off | On (LLM-only sentence labels) |
| Target p95 | < 3 s | < 15 s |
| Default | `hr`→quick, `eng`→deep | overridable per query |

---

## 5. Auth & DB Schema

```sql
users[id, username, password_hash, groups JSON]
documents[id, filename, allowed_groups JSON, hash, chunks]
conversations[id, user_id, query, answer, mode, score, contexts_json, citations_json, created_at]
answer_cache[key, answer, cites_json, qvec_json]   -- Postgres/Supabase
```

ACL is enforced **before** search on every path (dense, sparse, graph, cache key).

---

## 6. Models (pluggable via `.env`)

| Model | Default | Via | Size | Env |
|---|---|---|---|---|
| LLM Groq | `openai/gpt-oss-20b` | `ChatGroq` | API | `LLM_API_KEY` |
| LLM OpenAI | `gpt-4o-mini` | `ChatOpenAI` | API | `LLM_API_KEY` |
| LLM Anthropic | `claude-3-haiku` | `ChatAnthropic` | API | `LLM_API_KEY` |
| Jina v3 | `jina-embeddings-v3` | HTTP | API | `EMBED_API_KEY` |
| Voyage 3 | `voyage-3-large` | HTTP | API | `EMBED_API_KEY` |
| Cohere | `embed-english-v3.0` | HTTP | API | `EMBED_API_KEY` |
| Jina reranker | `jina-reranker-m0` | HTTP | API | `RERANK_API_KEY` |
| BM25S / SPLADE-v3 | — | `bm25s` / `transformers` | — / 500 MB local | — |

Local BGE-M3 embeddings, MiniLM/BGE rerankers, and HHEM verification are removed on `aws-deploy`.

---

## 7. Deployment — Container (aws-deploy)

**Local dev (requires remote services):**

```bash
python3 -m venv .venv && .venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m backend.run seed
.venv/bin/python -m backend.run
```

**Container (AWS EC2 demo):**

```bash
# cp deploy.env.example deploy.env
# deploy.env: DOMAIN, XRAG_DATA_DIR=/mnt/xrag/data, XRAG_MODELS_DIR=/mnt/xrag/models
docker compose --env-file deploy.env up -d --build
```

`xrag` + `caddy`; Caddy terminates TLS for `DOMAIN`; runtime state stays on EBS. No Qdrant container and no SQLite state. See [Deploy on AWS EC2](README.md#deploy-on-aws-ec2-api-demo).

**Required `.env`:**

```ini
LLM_PROVIDER=groq
LLM_API_KEY=...
EMBED_PROVIDER=jina
EMBED_API_KEY=...
RERANK_PROVIDER=jina
RERANK_API_KEY=...
DB_PROVIDER=supabase
DB_URL=postgresql://...pooler.supabase.com:5432/postgres?sslmode=require
```

---

## 8. Verification Status

- [x] Unit/integration suite — `pytest` (81 tests)
- [x] Browser e2e suite — `node frontend/e2e.mjs`
- [x] Dev-only answer benchmark — 80% pass (8/10), avg 7.74 s, p95 12.80 s → [`data/evaluation.md`](data/evaluation.md)
- [x] API-only/no-fallback behavior verified (explicit missing-model/rate-limit/DB errors)
- [x] Documentation consolidated into [README.md](README.md); obsolete `docs/` removed
- [x] Logo/banner moved to repo root (`logo.png`, `banner.png`)
- [x] Container deployment — Docker Compose (`xrag` + Caddy), pgvector-only, live at <https://xrag.duckdns.org>
- [x] AWS EC2 + DuckDNS + Let's Encrypt; EBS-backed data/models volumes
- [x] Supabase IPv4 session pooler verified (direct `db.<ref>.supabase.co` host is IPv6-only)
