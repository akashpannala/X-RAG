# About retrieval, access control, and modes in X-RAG

Explanation, not instructions: this document is about *why* the system is shaped the way it is.
For commands see the [how-to guides](how-to.md); for endpoints and env vars the
[reference](reference.md).

## About the two pipelines

Everything X-RAG does is one of two pipelines.

**Ingestion** turns a file into retrievable evidence:

```text
connector → doc intelligence (Docling/OCR) → cleaning (dedup, PII redaction)
         → chunking → enrichment (summaries, hypothetical questions, entities)
         → dense embedding + sparse index → storage (pgvector/Qdrant, BM25, SPLADE, Kuzu)
```

**Querying** turns a question into a cited answer:

```text
memory rewrite → (deep: query transforms, multi-agent retrieval) → fusion + rerank
               → budgeted assembly → generation → verification → answer cache
```

The layer numbering (`l01`…`l19`) follows ingestion order; the query pipeline borrows from it.
Each layer is a small package with one job, and the provider behind it is selected by `.env` —
the same code runs fully local or fully hosted. This is deliberate: deployment topology is a
configuration concern, not a code concern.

## About access control

Documents carry `allowed_groups`; users carry `groups`. A document is visible only when the two
sets intersect — and the intersection is checked **before** retrieval, not after.

Post-filtering (retrieve everything, then drop what the user may not see) is the classic
approach, and it is a leak vector: result counts, latencies, cache behaviour and rank positions
all still depend on documents the user must not know exist. Pre-search filtering makes the vector
search itself operate on an already-authorized candidate set, so nothing downstream can leak.
The cost is that filtering must be pushed into every retrieval path — dense, sparse, graph, and
the answer cache key. That is why `allowed_groups` appears in every storage signature.

Related consequences:

- `GET /documents` and `DELETE` return `404` (not `403`) for invisible documents — existence is
  itself information.
- Registration may self-assign only `public`; department groups are granted, never requested.
- The answer cache is keyed by groups, so a cached answer for `hr` is never served to `eng`.

## About quick and deep modes

Routing is a **manual toggle**, never an ML classifier. With exactly two modes, a learned router
would add a failure mode (misclassification) without adding capacity: the user already knows
whether they want a fast lookup or a thorough investigation.

- *Quick* is the default path: retrieve, rerank, generate. Optimised for latency.
- *Deep* adds query rewriting (multi-query, step-back, HyDE), parallel agents (vector, graph,
  SQL, image where available), and a heavier verification pass.

Roles get sensible defaults through `DEFAULT_MODE_BY_GROUP` (`eng` starts in deep, everyone else
in quick), which the user can override per question. The default exists so the toggle starts in
the right position, not so it can be ignored.

## About citations as a contract

The generator is instructed to repeat the exact retrieval tags (`[name#chunk]`) inside its
answer text. Those tags are the contract between generation and presentation:

- The server returns the raw tags in `citations`.
- The frontend parses the answer body, converts tags into numbered chips, and maps chip →
  document stem for the sources-rail flash.

If the model emits a placeholder (`[doc#3]`) or echoes the instruction (`[doc#chunk]`), the parser
resolves or strips it rather than trusting the model to be consistent — the model is the weakest
link in any citation scheme, so the parser assumes the tag is a hint, not a promise. Chunk ids
are 0-based positions within a document's chunk list; they are stable only while the document is
not re-ingested (re-ingest replaces chunks and therefore ids).

## About the answer cache

Repeated questions are expensive: retrieval, rerank, generation, verification. The cache stores
answers keyed by query, mode, and groups, and serves a hit when a new query is semantically
near-duplicates a stored one (cosine > 0.96 against cached queries — a threshold, not a
string match, so "what is RSI?" and "what does RSI mean?" share an answer).

Cache entries are invalidated by anything that changes the evidence: ingesting a document clears
it, deleting a document clears it. A stale citation is worse than a slow answer, so the cache
errs toward invalidation.

## About provider pluggability

One `.env` decides LLM, embeddings, reranker, vector store, and metadata DB. At boot the server
runs `check_requirements()`: it probes only the *configured* providers and refuses to start if
one fails — checks only, never installs, never silently substitutes. The rerank step is the one
place with an explicit fallback chain (configured provider → BGE → MiniLM) because reranking is
quality-degrading but non-fatal if degraded; everything else fails loudly instead.
