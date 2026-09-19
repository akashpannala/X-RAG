"""L6-full (sparse): BM25S hybrid. Local pickle index (PRD L7), RRF-fused with dense.

SPLADE-v3 / ColBERTv2 / ColPali stay gated: multi-GB downloads, marginal gain
on this corpus size. The fuse point (retrieve node) accepts them later.
"""
import pickle
from pathlib import Path

import bm25s

from backend.config import settings
from backend.l14_security.acl import allowed

INDEX_PATH = Path("data/bm25.pkl")
_index = None
_meta: list[dict] = []  # parallel to indexed corpus: {doc, chunk_id, text, allowed_groups}


def _load():
    global _index, _meta
    if _index is None:
        if INDEX_PATH.exists():
            with open(INDEX_PATH, "rb") as f:
                _index, _meta = pickle.load(f)
        else:
            _index, _meta = bm25s.BM25(), []
    return _index, _meta


def _save() -> None:
    import os
    import tempfile

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(INDEX_PATH.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump((_index, _meta), f)
        os.replace(tmp, INDEX_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def add(texts: list[str], payloads: list[dict]) -> None:
    idx, meta = _load()
    toks = bm25s.tokenize(texts)
    if not meta:
        idx.index(toks)
    else:
        idx.index(bm25s.tokenize([m["text"] for m in meta] + texts))
    meta.extend([{"doc": p["doc"], "chunk_id": p["chunk_id"], "text": p["text"][:2000],
                  "allowed_groups": list(p.get("allowed_groups") or [])}
                 for p in payloads])
    _save()


def search(query: str, k: int = 20, groups: list[str] | None = None) -> list[dict]:
    idx, meta = _load()
    if not meta:
        return []
    try:
        res = idx.retrieve(bm25s.tokenize(query), k=min(k, len(meta)))
        ids, scores = res[0][0].tolist(), res[1][0].tolist()
    except Exception:
        return []
    hits = [{"doc": meta[i]["doc"], "chunk_id": meta[i]["chunk_id"],
             "text": meta[i]["text"], "score": float(scores[j]),
             "allowed_groups": list(meta[i].get("allowed_groups") or [])}
            for j, i in enumerate(ids)]
    if groups is not None:
        hits = [h for h in hits if allowed(groups, h.get("allowed_groups"))]
    return hits


def reset() -> None:
    global _index, _meta
    _index, _meta = bm25s.BM25(), []
    if INDEX_PATH.exists():
        INDEX_PATH.unlink()
