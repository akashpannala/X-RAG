| # | Layer | Offline Tech (as built) | Where | Phase | Status |
|---|---|---|---|---|---|
| 1 | Connector | Local file loaders PDF/DOCX/PPTX/CSV/MD + images | ingestion/ | 1 | ✅ |
| 2 | Doc Intelligence | Docling local + OCR fallback for scanned PDFs/images | ingestion/parsing/ | 1 / 3 | ◐ Qwen2-VL deferred (not needed on corpus) |
| 3 | Cleaning | MinHash dedup + Presidio PII redaction | ingestion/cleaning/ | 1 | ✅ |
| 4 | Chunking Router | 8 strategies: Late/Contextual/Recursive/Semantic/Propositional/Parent/Window/Table-Code | chunking/ | 1 / 3 | ✅ |
| 5 | Enrichment | RAPTOR-lite + 3 Hypothetical Questions + NER | enrichment/ | 2 / 3 | ✅ |
| 6 | Embedding | Dense: BGE-M3; Sparse: BM25S + SPLADE-v3 | indexing/ | 1 / 3 | ◐ ColBERT/ColPali gated (multi-GB, cut for 7.5GB box) |
| 7 | Storage | Qdrant Local `data/qdrant_storage`, Kuzu embedded `data/kuzu`, BM25 pickle, `data/uploads` | indexing/ | 1 | ✅ |
| 8 | Freshness | File watcher + sha256, re-embed doc, cache clear on ingest | core/ | 1 | ✅ |
| 9 | Quick/Deep Toggle | UI toggle, role-defaulted, user-overridable (replaces Phi-3.5 gate) | retrieval/ | 2 | ✅ |
| 9-ORIG | ~~Adaptive Gate~~ | Removed — replaced by manual Quick/Deep toggle | retrieval/ | — | ❌ Cut |
| 10 | Memory Rewrite | MemoRAG-lite: conversation-aware rewrite from SQLite | retrieval/ + SQLite | 3 | ◐ full MemoRAG gen deferred |
| 11 | Query Transform | Multi-Query + RAG-Fusion (RRF) + Decomposition + Step-Back + HyDE via LLM | retrieval/ | 3 | ✅ |
| 12-ORIG | ~~Intent + Policy Model~~ | Removed — manual toggle only | retrieval/router/ | — | ❌ Cut |
| 12 | Quick/Deep Routing Logic | Manual toggle only — no ML classifier | retrieval/router/ | 2 | ✅ |
| 13 | Multi-Agent Retrieval | Research Agent → vector + graph + SQL + image agents (parallel in deep) | retrieval/agents/ | 3 | ✅ |
| 14 | Fusion + Rerank | Learned RRF + MiniLM + RankGPT-listwise + MMR | retrieval/ | 2 / 3 | ◐ BGE-Reranker-v2-M3 gated on weights (degrades to MiniLM) |
| 15 | Security + AUTH + ACL | Injection screen + PII + JWT + Qdrant pre-search payload filter `allowed_groups` | core/security.py + auth/ | 2 / 3 | ✅ |
| 16 | Budget Optimizer | RECOMP-lite: extractive sentence compression via MiniLM | retrieval/compression/ | 3 | ◐ abstractive compressor deferred |
| 17 | Assembly | Token budget + citations `[doc#chunk]` | generation/ | 1 | ✅ |
| 18 | Generation | Self-RAG revise + CRAG retry + ReAct/FLARE stripe; LLM = Groq (dev) / Ollama Llama 3.1 8B (prod) | generation/ | 1 / 3 | ✅ |
| 19 | Verification + Localization | CoVe-lite + sentence Supported/Unsupported/Contradicted; HHEM parked → LLM judges when weights unloadable | verification/ | 3 | ◐ |
| 20 | Memory + Cache | SQLite answer cache (cosine>0.96) + embedding LRU | memory_cache/ | 2 | ✅ |
| 21 | Eval + Online Judge | RAGAS offline (pinned) + Online Judge scores every query via Redis Streams worker | evaluation/ + l22 | 2 / 4 | ✅ |
| 22 | Infra + RAGOps | **Redis Streams eval queue** + **INT8 dynamic quant** + **Langfuse Local (v3)** + **hard-negative mining** + Prometheus + runbook | deploy/ + l22 | 4 | ✅ |

> **Notes:** Layers 9-ORIG and 12-ORIG are struck through — routing is manual toggle only. Every ◐ substitution keeps the offline-first philosophy; the home for all of them is documented in `deploy/README.md`.
