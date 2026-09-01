# PRD: OFFLINE-RAG — Air-Gapped Enterprise RAG

| Field | Detail |
|---|---|
| **Product** | OFFLINE-RAG |
| **Stack** | SQLite + Qdrant Local + Kuzu + Ollama + FastAPI + Next.js |
| **Deploy** | `docker-compose -f deploy/docker-compose.offline.yml up` → `192.168.1.10:3000` |
| **Network** | 0 internet after install — fully air-gapped |
| **Status** | Planning / Not Started |

> **Routing = Manual Toggle Only.** No ML classifier, no policy model. Quick/Deep toggle is the permanent mechanism.

---

## 1. What It Does

Employees upload documents, chat with cited answers `[doc#chunk]`, on company WiFi, fully offline. Department isolation via ACL — HR docs stay HR-only.

## 2. Quick / Deep Mode — Manual Toggle Only

Running every query through full pipeline (multi-query, multi-agent, cascade rerank, verification) = 8-10 sequential model calls — not achievable at low latency on one consumer GPU.

| | Quick | Deep |
|---|---|---|
| Retrieval | Dense only | Multi-query + Multi-agent |
| Rerank | Single-stage (MiniLM) | Cascade (MiniLM → BGE-Reranker) |
| Verification | Off | On (HHEM) |
| Target p95 | < 3 sec | < 15 sec |
| Default for | HR-type roles | Eng-type roles |

- Default set by `user.groups` at login; user can flip per query.
- No auto-classifier, no XGBoost policy model, no training data pipeline.

## 3. Personas

Employee (asks) · IT Admin (deploys) · Dept Head (needs HR docs locked to HR group)

## 4. Phases (Build Order)

| Phase | Ships | Key Layers |
|---|---|---|
| **1 — MVP** | Core loop | 1, 2, 3, 4, 6, 7, 8, 17, 18 |
| **2 — Access + Modes** | ACL + Toggle + Cache | 5, 9T, 14, 15, 20, 21 |
| **3 — Depth** | Deep-mode power | 2-full, 4-full, 5-full, 6-full, 10, 11, 13, 14-full, 15-full, 16, 18-full, 19 |
| **4 — Ops** | Observability | 21-full, 22 |

**Non-goals:** OpenAI API, Qdrant Cloud, Google OAuth, online mode, any ML-based query router.

## 5. Layers — Full Requirement With Offline Tech (Nothing Trimmed)

Everything below is **⬜ Not Started** — planning stage, nothing built yet.

| # | Layer | Offline Tech | Where | Phase | Status |
|---|---|---|---|---|---|
| 1 | Connector | Local file loaders PDF/DOCX/PPTX/CSV/MD | ingestion/ | 1 | ⬜ Not started |
| 2 | Doc Intelligence | Docling local + PaddleOCR local + Qwen2-VL-2B local | ingestion/parsing/ | 1 / 3 | ⬜ Not started |
| 3 | Cleaning | MinHash dedup + Presidio PII local | ingestion/cleaning/ | 1 | ⬜ Not started |
| 4 | Chunking Router | Late Chunking [BGE-M3 long ctx] + Contextual [Qwen2.5 7B local header] + Recursive + Semantic + Propositional + Parent + Window + Table/Code | chunking/ | 1 / 3 | ⬜ Not started |
| 5 | Enrichment | RAPTOR tree via Llama 3.1 8B local + 3 Hypothetical Questions + NER | enrichment/ | 2 / 3 | ⬜ Not started |
| 6 | Embedding | Dense: BGE-M3 local, Sparse: BM25S + SPLADE-v3 local, Multi-Vector: ColBERTv2 + ColPali 2B local | indexing/ | 1 / 3 | ⬜ Not started |
| 7 | Storage | **Qdrant Local file** `data/qdrant_storage/`, Kuzu embedded file `data/kuzu/`, BM25 pickle, S3 folder `data/uploads/` | indexing/ | 1 | ⬜ Not started |
| 8 | Freshness | File watcher + hash, re-embed doc, update graph | core/ | 1 | ⬜ Not started |
| 9 | Quick/Deep Toggle (Replaces Adaptive Gate) | UI toggle, role-defaulted, user-overridable — Replaces `Phi-3.5-mini 3.8B Q4_K_M local` | retrieval/ | 2 | ⬜ Not started |
| 9-ORIG | ~~Adaptive Gate~~ | ~~Phi-3.5-mini 3.8B Q4_K_M local~~ — **Removed, replaced by manual Quick/Deep toggle** | retrieval/ | — | ❌ Cut from scope |
| 10 | Memory Rewrite | MemoRAG local | retrieval/ + SQLite | 3 | ⬜ Not started |
| 11 | Query Transform | Multi-Query + RAG-Fusion + Decomposition + Step-Back + HyDE via Qwen2.5 7B local | retrieval/ | 3 | ⬜ Not started |
| 12-ORIG | ~~Intent + Policy Model~~ | ~~XGBoost policy local - learns `Fact->Dense only 80%`~~ — **Removed, replaced by manual Quick/Deep toggle** | retrieval/router/ | — | ❌ Cut from scope |
| 12 | Quick/Deep Routing Logic | Manual toggle only — No ML classifier | retrieval/router/ | 2 | ⬜ Not started |
| 13 | Multi-Agent Retrieval | Research Agent -> Vector + Graph [Local/Global/PathRAG] + SQL + Image agents parallel | retrieval/agents/ | 3 | ⬜ Not started |
| 14 | Fusion + Rerank | Learned RRF + Cascade MiniLM 100->30 -> BGE-Reranker-v2-M3 30->10 -> RankGPT local 10->5 + MMR | retrieval/ | 2 / 3 | ⬜ Not started |
| 15 | Security + AUTH + ACL | CRAG + LLMLingua + Injection Filter + PII + **SQLite `auth.db` + Qdrant payload filter `allowed_groups`** | core/security.py + auth/ | 2 / 3 | ⬜ Not started |
| 16 | Budget Optimizer | Selective Context + RECOMP local | retrieval/compression/ | 3 | ⬜ Not started |
| 17 | Assembly | 6k token budget + Citations `[doc#chunk]` | generation/ | 1 | ⬜ Not started |
| 18 | Generation | ReAct + FLARE + Self-RAG tokens + Llama 3.1 8B Q4_K_M via Ollama | generation/ | 1 / 3 | ⬜ Not started |
| 19 | Verification + Localization | HHEM NLI local + CoVe + Sentence-level Supported/Unsupported/Contradicted | verification/ | 3 | ⬜ Not started |
| 20 | Memory + Cache | GPTCache local cosine>0.96 + Embedding cache + Kuzu long-term | memory_cache/ | 2 | ⬜ Not started |
| 21 | Eval + Online Judge | RAGAS offline + Online Judge local LLM scores every query | evaluation/ | 2 / 4 | ⬜ Not started |
| 22 | Infra + RAGOps | Kafka async + Quant INT8 + Langfuse Local + Phoenix + Hard Negative Mining retrain | deploy/ | 4 | ⬜ Not started |

> **Note:** Layers 9-ORIG and 12-ORIG are struck through and marked cut — routing is manual toggle only. The toggle itself (Layer 9 / Layer 12) is Phase 2 work, also ⬜ Not started.

## 6. Detailed Specs With Full Offline Tech Preserved

### L1 Connector
- **Where:** `ingestion/`
- **Offline Tech:** Local file loaders PDF/DOCX/PPTX/CSV/MD — no cloud parsers
- **Output:** Raw text + metadata

### L2 Doc Intelligence
- **Where:** `ingestion/parsing/`
- **Offline Tech:** Docling local + PaddleOCR local + Qwen2-VL-2B local (1.8GB)
- **Phase:** 1 Basic (Docling only) / 3 Full (OCR + VL for charts/images)

### L3 Cleaning
- **Where:** `ingestion/cleaning/`
- **Offline Tech:** MinHash dedup + Presidio PII local

### L4 Chunking Router
- **Where:** `chunking/`
- **Offline Tech:** Late Chunking [BGE-M3 long ctx] + Contextual [Qwen2.5 7B local header] + Recursive + Semantic + Propositional + Parent + Window + Table/Code
- **Phase:** 1 Basic (Recursive + Table/Code) / 3 Full (all 8)

### L5 Enrichment
- **Where:** `enrichment/`
- **Offline Tech:** RAPTOR tree via Llama 3.1 8B local + 3 Hypothetical Questions + NER

### L6 Embedding
- **Where:** `indexing/`
- **Offline Tech:** Dense: BGE-M3 local (2.2GB), Sparse: BM25S + SPLADE-v3 local, Multi-Vector: ColBERTv2 + ColPali 2B local

### L7 Storage
- **Where:** `indexing/`
- **Offline Tech:** Qdrant Local file `data/qdrant_storage/`, Kuzu embedded file `data/kuzu/`, BM25 pickle, S3 folder `data/uploads/` (local folder mimic)

### L8 Freshness
- **Where:** `core/`
- **Offline Tech:** File watcher + hash, re-embed doc, update graph

### L9 Toggle + L9-ORIG Cut
- **Where:** `retrieval/`
- **Active:** UI toggle, role-defaulted, user-overridable
- **Cut:** Phi-3.5-mini 3.8B Q4_K_M local — removed, replaced by manual Quick/Deep toggle

### L10 Memory Rewrite
- **Where:** `retrieval/ + SQLite`
- **Offline Tech:** MemoRAG local

### L11 Query Transform
- **Where:** `retrieval/`
- **Offline Tech:** Multi-Query + RAG-Fusion + Decomposition + Step-Back + HyDE via Qwen2.5 7B local

### L12 Routing + L12-ORIG Cut
- **Where:** `retrieval/router/`
- **Active:** Manual toggle only — No ML classifier
- **Cut:** XGBoost policy local - learns `Fact->Dense only 80%` — removed

### L13 Multi-Agent Retrieval
- **Where:** `retrieval/agents/`
- **Offline Tech:** Research Agent -> Vector + Graph [Local/Global/PathRAG] + SQL + Image agents parallel

### L14 Fusion + Rerank
- **Where:** `retrieval/`
- **Offline Tech:** Learned RRF + Cascade MiniLM 100->30 -> BGE-Reranker-v2-M3 30->10 -> RankGPT local 10->5 + MMR

### L15 Security + AUTH + ACL
- **Where:** `core/security.py + auth/`
- **Offline Tech:** CRAG + LLMLingua + Injection Filter + PII + SQLite `auth.db` + Qdrant payload filter `allowed_groups`

### L16 Budget Optimizer
- **Where:** `retrieval/compression/`
- **Offline Tech:** Selective Context + RECOMP local

### L17 Assembly
- **Where:** `generation/`
- **Offline Tech:** 6k token budget + Citations `[doc#chunk]`

### L18 Generation
- **Where:** `generation/`
- **Offline Tech:** ReAct + FLARE + Self-RAG tokens + Llama 3.1 8B Q4_K_M via Ollama

### L19 Verification + Localization
- **Where:** `verification/`
- **Offline Tech:** HHEM NLI local + CoVe + Sentence-level Supported/Unsupported/Contradicted

### L20 Memory + Cache
- **Where:** `memory_cache/`
- **Offline Tech:** GPTCache local cosine>0.96 + Embedding cache + Kuzu long-term

### L21 Eval + Online Judge
- **Where:** `evaluation/`
- **Offline Tech:** RAGAS offline + Online Judge local LLM scores every query

### L22 Infra + RAGOps
- **Where:** `deploy/`
- **Offline Tech:** Kafka async + Quant INT8 + Langfuse Local + Phoenix + Hard Negative Mining retrain

## 7. Auth (Phase 2)

```sql
users[id, username, password_hash, groups JSON]
documents[id, filename, allowed_groups JSON, hash]
conversations[id, user_id, query, answer, mode]  -- mode: quick|deep
```

Qdrant filter `allowed_groups` enforced **before** search. Mode default = `users.groups → default_mode` config, overridable client-side per query.

## 8. Models (14.6GB total)

| Model | Size | Use | Phase |
|---|---|---|---|
| Llama 3.1 8B Q4 | 4.9GB | Generation | 1 |
| BGE-M3 | 2.2GB | Dense embed | 1 |
| MiniLM cross-encoder | 80MB | Quick-mode rerank | 2 |
| BGE-Reranker-v2-M3 | 1.1GB | Deep-mode rerank | 3 |
| Qwen2.5 7B Q4 | 4.4GB | Deep-mode query transform | 3 |
| Qwen2-VL-2B | 1.8GB | Image/chart parsing | 3 |
| ColPali, SPLADE-v3 | 2.5GB | Deep-mode retrieval | 3 |
| HHEM | 400MB | Verification | 3 |

Phase 1 minimal set = Llama 3.1 8B + BGE-M3 = **7.1GB**, fits the 8GB CPU fallback.

## 9. Offline Packaging

1. `docker pull` + `docker save` the `ollama` and `qdrant` images on an internet-connected machine → tarballs in `vendor/images/`.
2. Copy tarballs + `models/` to the air-gapped server; `docker load` before `compose up`.
3. CI gate = actually run the container with `--network none` and confirm it serves a query — not just a `requests.get` grep. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.

## 10. Success Criteria

| Phase | Bar |
|---|---|
| 1 | Deploy < 5 min, 0 packets out with `--network none`, cited answers, Quick p95 < 3 sec |
| 2 | HR doc invisible to Eng (tested live), toggle defaults correctly by role, overridable without reload |
| 3 | Deep mode measurably better on multi-hop queries, p95 < 15 sec |
| 4 | Faithfulness > 0.9 (RAGAS), async eval adds no user-facing latency |
