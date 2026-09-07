"""Phase 3 pure-function tests — no models, no network."""
from backend.l11_transforms.transforms import rrf_fuse
from backend.l14_rerank.cascade import mmr
from backend.l19_verification.verify import split_sentences


def _hit(doc, cid, text="t"):
    return {"doc": doc, "chunk_id": cid, "text": text, "score": 0.5}


def test_rrf_prefers_top_ranks():
    a = [_hit("x", 0), _hit("y", 0)]
    b = [_hit("y", 0), _hit("x", 0)]
    fused = rrf_fuse([a, b])
    assert [ (h["doc"], h["chunk_id"]) for h in fused] == [("x", 0), ("y", 0)]


def test_mmr_diversifies():
    hits = [_hit("a", 0), _hit("a", 1), _hit("b", 0)]
    vecs = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]
    out = mmr([1.0, 0.0], hits, vecs, 2, lamb=0.0)
    docs = {h["doc"] for h in out}
    assert docs == {"a", "b"}  # pure diversity picks one of each


def test_split_sentences():
    sents = split_sentences("Hello world today here. Short. This is a longer third sentence here.")
    assert sents == ["Hello world today here.", "This is a longer third sentence here."]
