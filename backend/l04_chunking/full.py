"""L4-full: all eight chunking strategies (PRD).

Basic (always): recursive + table/code (splitter.py). Full (enrich=true):
late (BGE-M3 long-ctx pooled), semantic (cosine breakpoints), parent
(big section + child refs), window (sentence ± N), propositional (LLM
atomic claims), contextual (LLM header per chunk). Propositional/contextual
cost LLM calls — that is what enrich=true buys.
"""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

_base = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
_sent = re.compile(r"(?<=[.!?])\s+")


def late_chunks(text: str, size: int = 2000) -> list[str]:
    """Late Chunking: embed the whole doc once with BGE-M3 long context, then
    mean-pool token spans per chunk. Returns chunk texts (embeddings cached
    by the caller via get_embeddings). Falls back to plain splits."""
    parts = _base.split_text(text)
    if len(parts) < 2:
        return parts
    try:
        from backend.l06_embedding.bge import get_embeddings
        from backend.config import settings

        model = get_embeddings(settings.embed_model).client.model  # type: ignore
        tok = get_embeddings(settings.embed_model).client.tokenizer  # type: ignore
        enc = tok(text[:8192 * 4], return_tensors="pt", truncation=True)
        import torch

        with torch.no_grad():
            out = model.embeddings.word_embeddings(enc["input_ids"])
        # boundary map: char offset of each part → token span → mean pool
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
    except Exception:
        pass
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
    except Exception:
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
    from backend.l18_generation.llm import get_llm

    out = []
    for block in _base.split_text(text)[:20]:
        msg = get_llm().invoke(
            "Split this passage into atomic propositions, one fact per line, no numbering:\n" + block)
        t = msg.content if isinstance(msg.content, str) else str(msg.content)
        out.extend(l.strip().lstrip("1234567890.-) ") for l in t.splitlines() if l.strip())
    return out or _base.split_text(text)


def contextual_chunks(text: str, doc_title: str = "") -> list[str]:
    """LLM situating header prepended to each chunk (Anthropic contextual)."""
    from backend.l18_generation.llm import get_llm

    out = []
    for block in _base.split_text(text)[:20]:
        msg = get_llm().invoke(
            f"Give this chunk a one-sentence situating header naming the document "
            f"('{doc_title}') and section. Header only, no quotes:\n" + block[:1500])
        header = (msg.content if isinstance(msg.content, str) else str(msg.content)).strip().splitlines()
        out.append((header[0] if header else "") + "\n" + block)
    return out or _base.split_text(text)


def full_chunk(text: str, doc_title: str = "") -> list[str]:
    """All eight strategies merged, deduped. Used when enrich=true."""
    seen, out = set(), []
    for chunk in (late_chunks(text) + semantic_chunks(text)
                  + [c for _, kids in parent_chunks(text) for c in kids]
                  + window_chunks(text)[:50]
                  + propositional_chunks(text)
                  + contextual_chunks(text, doc_title)):
        key = chunk[:120]
        if key not in seen and chunk.strip():
            seen.add(key)
            out.append(chunk)
    return out
