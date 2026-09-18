"""L6-full (sparse, neural): SPLADE lexical-expansion retrieval.

Complements BM25S (exact match) with learned expansion. Model-gated: loads
naver/splade-cocondenser-selfdistil on first use (~500MB); absent weights →
empty list, dense+BM25 carry the query. Fused by RRF in deep retrieve.
"""
import logging
import os
import pickle
import tempfile
from pathlib import Path

_logger = logging.getLogger(__name__)

INDEX_PATH = Path("data/splade.pkl")
_model = None
_tok = None
_meta: list[dict] = []
_vecs = None  # list[dict[token_id, weight]] parallel to _meta
_loaded = False
_loaded_failed = False

# ponytail: thresholds — 0.1 sparsity (keep ~50-100 terms/doc), 0 absolute search floor
SPARSE_THRESH = 0.1
SEARCH_FLOOR = 0.0


def _load():
    global _model, _tok, _loaded_failed
    if _loaded_failed:
        raise RuntimeError("splade weights missing")
    if _model is None:
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        name = "naver/splade-cocondenser-selfdistil"
        try:
            _tok = AutoTokenizer.from_pretrained(name)
            _model = AutoModelForMaskedLM.from_pretrained(name)
            _model.eval()
        except Exception as e:
            _loaded_failed = True
            _logger.warning("splade weights missing — sparse degraded to dense+BM25: %s", e)
            raise
    return _model, _tok


def _encode(texts: list[str], batch: int = 16) -> list[dict[int, float]]:
    # ponytail: batch 16 with padding; increase if VPS has RAM
    import torch

    model, tok = _load()
    out: list[dict[int, float]] = []
    for i in range(0, len(texts), batch):
        batch_texts = texts[i:i + batch]
        enc = tok(batch_texts, return_tensors="pt", truncation=True, padding=True, max_length=512)
        with torch.no_grad():
            logits = model(**enc).logits
        for j in range(len(batch_texts)):
            w = torch.log1p(torch.relu(logits[j])).max(dim=0).values
            idx = (w > SPARSE_THRESH).nonzero().flatten().tolist()
            out.append({int(k): float(w[k]) for k in idx})
    return out


def _read_index():
    global _meta, _vecs, _loaded
    if _loaded:
        return _meta, _vecs
    if INDEX_PATH.exists():
        with open(INDEX_PATH, "rb") as f:
            _meta, _vecs = pickle.load(f)
    else:
        _meta, _vecs = [], []
    _loaded = True
    return _meta, _vecs


def _save_atomic(obj) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(INDEX_PATH.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(obj, f)
        os.replace(tmp, INDEX_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def add(texts: list[str], payloads: list[dict]) -> None:
    global _loaded
    meta, vecs = _read_index()
    try:
        vecs.extend(_encode([t[:2000] for t in texts]))
    except Exception:
        # graceful degradation per docstring — missing weights etc. -> no sparse, dense+BM25 carry query
        return
    meta.extend([{"doc": p["doc"], "chunk_id": p["chunk_id"], "text": p["text"][:2000]}
                 for p in payloads])
    _loaded = True
    _save_atomic((meta, vecs))


def search(query: str, k: int = 20) -> list[dict]:
    meta, vecs = _read_index()
    if not meta:
        return []
    try:
        q = _encode([query])[0]
    except Exception:
        return []
    # ponytail: brute-force scan over all vecs; swap to scipy.sparse csr or inverted index at 5k+ chunks
    scored = sorted(
        ((sum(q.get(t, 0.0) * w for t, w in v.items()), i) for i, v in enumerate(vecs)),
        reverse=True,
    )
    return [{"doc": meta[i]["doc"], "chunk_id": meta[i]["chunk_id"],
             "text": meta[i]["text"], "score": float(s)}
            for s, i in scored[:k] if s > SEARCH_FLOOR]


def reset() -> None:
    global _meta, _vecs, _loaded
    _meta, _vecs = [], []
    _loaded = True
    if INDEX_PATH.exists():
        INDEX_PATH.unlink()
