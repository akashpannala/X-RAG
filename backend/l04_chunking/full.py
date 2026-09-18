"""L4-full: all eight chunking strategies (PRD).

Basic (always): recursive + table/code (splitter.py). Full (enrich=true):
late (BGE-M3 long-ctx pooled), semantic (cosine breakpoints), parent
(big section + child refs), window (sentence ± N), propositional (LLM
atomic claims), contextual (LLM header per chunk). Propositional/contextual
cost LLM calls — that is what enrich=true buys.
"""
import logging
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

_logger = logging.getLogger(__name__)

_base = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
_sent = re.compile(r"(?<=[.!?])\s+")


def late_chunks(text: str, size: int = 2000) -> list[str]:
    """Late Chunking: embed whole doc with BGE-M3 long ctx then mean-pool per chunk span.
    Remote embed (EMBED_URL/choreo) has no tokenizer — skips pooling, plain split.
    ponytail: returns texts identical; pooled vectors computed but texts returned (late-pooled by construction).
    If you need vectors, change to return (texts, pooled) and wire to Qdrant.
    """
    parts = _base.split_text(text)
    if len(parts) < 2:
        return parts
    # remote has no tokenizer/model — skip heavy work
    from backend.config import settings

    if settings.embed_url or settings.embed_provider == "choreo":
        _logger.info("late_chunks: remote embed, skipping token-pool, plain split")
        return parts
    try:
        from backend.l06_embedding.bge import get_embeddings

        st = get_embeddings(settings.embed_model)._client  # SentenceTransformer, correct is _client not .client
        tok = st.tokenizer
        # local-only: whole-doc word_embeddings then span mean-pool
        enc = tok(text[:8192 * 4], return_tensors="pt", truncation=True)
        import torch

        with torch.no_grad():
            out = st[0].auto_model.embeddings.word_embeddings(enc["input_ids"])
        offsets, acc = [], 0
        for p in parts:
            acc += len(p)
            offsets.append(acc)
        spans = tok(text[:8192 * 4], return_offsets_mapping=True)["offset_mapping"]
        pooled, start = [], 0
        for end_char in offsets:
            idx = [i for i, (s, e) in enumerate(spans) if s >= 0 and e <= end_char and i >= start]
            if idx:
                pooled.append(out[0, idx].mean(0))
                start = idx[-1] + 1
        if len(pooled) == len(parts):
            return parts  # texts identical; embeddings are late-pooled by construction
    except Exception as e:
        _logger.warning("late_chunks fallback to plain split: %s", e)
    return parts


def semantic_chunks(text: str, threshold: float = 0.55) -> list[str]:
    """Split on cosine breakpoints between adjacent sentences (BGE)."""
    sents = [s for s in _sent.split(text) if s.strip()]
    if len(sents) < 3:
        return _base.split_text(text)
    try:
        from backend.l06_embedding.bge import get_embeddings
        from backend.config import settings

        vecs = get_embeddings(settings.embed_model).embed_documents(sents[:200])
        import numpy as np

        sims = [float(np.dot(vecs[i], vecs[i + 1])) for i in range(len(vecs) - 1)]
        chunks, cur = [], [sents[0]]
        for i, s in enumerate(sims):
            cur.append(sents[i + 1])
            if s < threshold or sum(map(len, cur)) > 2000:
                chunks.append(" ".join(cur))
                cur = []
        if cur:
            chunks.append(" ".join(cur))
        return chunks or _base.split_text(text)
    except Exception as e:
        _logger.warning("semantic_chunks fallback to plain split: %s", e)
        return _base.split_text(text)


def parent_chunks(text: str, parent_size: int = 4000) -> list[tuple[str, list[str]]]:
    """(parent_text, [child texts]) — retrieve children, cite parents."""
    parents = _base.split_text(text)
    merged, buf = [], ""
    for p in parents:
        buf += p
        if len(buf) >= parent_size:
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)
    small = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    return [(m, small.split_text(m)) for m in merged]


def window_chunks(text: str, window: int = 2) -> list[str]:
    """Each sentence wrapped with ±window neighbours for context."""
    sents = [s for s in _sent.split(text) if s.strip()]
    return [" ".join(sents[max(0, i - window):i + window + 1]) for i in range(len(sents))]


def propositional_chunks(text: str) -> list[str]:
    """LLM atomic claims (one fact each). Enrich-gated: costs LLM calls."""
    # ponytail: sequential invokes; batch/async if enrich latency matters on local Ollama
    from backend.l18_generation.llm import get_llm

    parts = _base.split_text(text)
    if len(parts) > 20:
        _logger.warning("propositional_chunks capped at 20/%d blocks — long doc loses coverage", len(parts))
    out = []
    for block in parts[:20]:
        msg = get_llm().invoke(
            "Split this passage into atomic propositions, one fact per line, no numbering:\n" + block)
        t = msg.content if isinstance(msg.content, str) else str(msg.content)
        out.extend(l.strip().lstrip("1234567890.-) ") for l in t.splitlines() if l.strip())
    return out or _base.split_text(text)


def contextual_chunks(text: str, doc_title: str = "") -> list[str]:
    """LLM situating header prepended to each chunk (Anthropic contextual)."""
    # ponytail: sequential invokes; batch/async if enrich latency matters
    from backend.l18_generation.llm import get_llm

    parts = _base.split_text(text)
    if len(parts) > 20:
        _logger.warning("contextual_chunks capped at 20/%d blocks — long doc loses coverage", len(parts))
    out = []
    for block in parts[:20]:
        msg = get_llm().invoke(
            f"Give this chunk a one-sentence situating header naming the document "
            f"('{doc_title}') and section. Header only, no quotes:\n" + block[:1500])
        header = (msg.content if isinstance(msg.content, str) else str(msg.content)).strip().splitlines()
        out.append((header[0] if header else "") + "\n" + block)
    return out or _base.split_text(text)


def full_chunk(text: str, doc_title: str = "", enrich_llm: bool = True) -> list[str]:
    """All strategies merged, deduped. enrich_llm=False skips the two LLM strategies
    for late+semantic+parent+window only (partial enrich without 40 LLM calls)."""
    pooled = late_chunks(text) + semantic_chunks(text) + [c for _, kids in parent_chunks(text) for c in kids] + window_chunks(text)[:50]
    if enrich_llm:
        pooled += propositional_chunks(text) + contextual_chunks(text, doc_title)
    seen: set[str] = set()
    out: list[str] = []
    for chunk in pooled:
        stripped = chunk.strip()
        if not stripped:
            continue
        # ponytail: exact dedup on full text (was chunk[:120] — false merges on shared 120-char prefix; use MinHash in L3 for near-dup)
        if stripped not in seen:
            seen.add(stripped)
            out.append(chunk)
    return out
