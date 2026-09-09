"""L6-full (sparse, neural): SPLADE lexical-expansion retrieval.

Complements BM25S (exact match) with learned expansion. Model-gated: loads
naver/splade-cocondenser-selfdistil on first use (~500MB); absent weights →
empty list, dense+BM25 carry the query. Fused by RRF in deep retrieve.
"""
import pickle
from pathlib import Path

INDEX_PATH = Path("data/splade.pkl")
_model = None
_tok = None
_meta: list[dict] = []
_vecs = None  # list[dict[token_id, weight]] parallel to _meta


def _load():
    global _model, _tok
    if _model is None:
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        name = "naver/splade-cocondenser-selfdistil"
        _tok = AutoTokenizer.from_pretrained(name)
        _model = AutoModelForMaskedLM.from_pretrained(name)
        _model.eval()
    return _model, _tok


def _encode(texts: list[str]) -> list[dict[int, float]]:
    import torch

    model, tok = _load()
    out = []
    for t in texts:
        enc = tok(t[:512], return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = model(**enc).logits[0]
        w = torch.log1p(torch.relu(logits)).max(dim=0).values
        idx = (w > 0.1).nonzero().flatten().tolist()
        out.append({int(i): float(w[i]) for i in idx})
    return out


def _read_index():
    global _meta, _vecs
    if _meta is not None and _vecs is not None and (_meta or _vecs):
        return _meta, _vecs
    if INDEX_PATH.exists():
        with open(INDEX_PATH, "rb") as f:
            _meta, _vecs = pickle.load(f)
    else:
        _meta, _vecs = [], []
    return _meta, _vecs


def add(texts: list[str], payloads: list[dict]) -> None:
    meta, vecs = _read_index()
    vecs.extend(_encode([t[:2000] for t in texts]))
    meta.extend([{"doc": p["doc"], "chunk_id": p["chunk_id"], "text": p["text"][:2000]}
                 for p in payloads])
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "wb") as f:
        pickle.dump((meta, vecs), f)


def search(query: str, k: int = 20) -> list[dict]:
    meta, vecs = _read_index()
    if not meta:
        return []
    q = _encode([query])[0]
    scored = sorted(
        ((sum(q.get(t, 0.0) * w for t, w in v.items()), i) for i, v in enumerate(vecs)),
        reverse=True,
    )
    return [{"doc": meta[i]["doc"], "chunk_id": meta[i]["chunk_id"],
             "text": meta[i]["text"], "score": float(s)}
            for s, i in scored[:k] if s > 0]


def reset() -> None:
    global _meta, _vecs
    _meta, _vecs = [], []
    if INDEX_PATH.exists():
        INDEX_PATH.unlink()
