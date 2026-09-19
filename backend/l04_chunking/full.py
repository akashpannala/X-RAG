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


def late_chunks(text: str, size: int = 2000):
    """Late Chunking: embed whole doc with BGE-M3 long ctx then mean-pool per chunk span.
    Returns (texts, pooled_vectors) where pooled_vectors are the late-pooled embeddings.
    Remote embed (EMBED_URL/choreo) has no tokenizer — returns (parts, None).
    """
    parts = _base.split_text(text)
    if len(parts) < 2:
        return parts, None
    # remote has no tokenizer/model — skip heavy work
    from backend.config import settings, _resolve_embed_url

    if _resolve_embed_url() or settings.embed_provider == "choreo":
        _logger.info("late_chunks: remote embed, skipping token-pool, plain split")
        return parts, None
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
            import numpy as np
            pooled_arr = [p.cpu().numpy() for p in pooled]
            return parts, pooled_arr
    except Exception as e:
        _logger.warning("late_chunks fallback to plain split: %s", e)
    return parts, None


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
    from backend.l17_generation.llm import get_llm

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
    from backend.l17_generation.llm import get_llm

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


def full_chunk(text: str, doc_title: str = "", enrich_llm: bool = True):
    """All strategies merged, deduped. Returns (texts, late_vectors) where late_vectors
    are the pooled embeddings from late_chunks (aligned to late_chunks texts).
    enrich_llm=False skips the two LLM strategies for late+semantic+parent+window only."""
    late_texts, late_vecs = late_chunks(text)
    pooled_texts = late_texts + semantic_chunks(text) + [c for _, kids in parent_chunks(text) for c in kids] + window_chunks(text)[:50]
    if enrich_llm:
        pooled_texts += propositional_chunks(text) + contextual_chunks(text, doc_title)
    seen: set[str] = set()
    out_texts: list[str] = []
    out_late_vecs: list = []
    late_set = set(late_texts)
    for chunk in pooled_texts:
        stripped = chunk.strip()
        if not stripped:
            continue
        if stripped not in seen:
            seen.add(stripped)
            out_texts.append(chunk)
            if chunk in late_set and late_vecs:
                idx = late_texts.index(chunk)
                if idx < len(late_vecs):
                    out_late_vecs.append(late_vecs[idx])
    return out_texts, out_late_vecs
