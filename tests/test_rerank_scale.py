"""Rerank score scale: minilm.rerank must emit 0-1 scores that confident() accepts."""
from backend.l13_rerank import minilm
from backend.l14_security.injection import confident


class FakeCE:
    def __init__(self, logits):
        self.logits = logits

    def predict(self, pairs):
        assert len(pairs) == len(self.logits)
        return self.logits


def test_rerank_writes_sigmoid_scores(monkeypatch):
    monkeypatch.setattr(minilm, "get_reranker", lambda *a, **k: FakeCE([-3.0, 0.0, 2.0]))
    hits = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    out = minilm.rerank("q", hits, 3)
    assert [h["text"] for h in out] == ["c", "b", "a"]  # order preserved
    scores = [h["score"] for h in out]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert abs(out[0]["score"] - 0.8808) < 0.001  # sigmoid(2)
    assert abs(out[1]["score"] - 0.5) < 0.001  # sigmoid(0)
    assert abs(out[2]["score"] - 0.0474) < 0.001  # sigmoid(-3)


def test_gate_passes_for_relevant_hit(monkeypatch):
    """A relevant pair (logit ~ -0.02, i.e. ~49%) must clear confident()."""
    monkeypatch.setattr(minilm, "get_reranker", lambda *a, **k: FakeCE([-0.025]))
    out = minilm.rerank("q", [{"text": "vacation policy"}], 5)
    assert confident(out)


def test_gate_still_blocks_irrelevant_hits(monkeypatch):
    """Logit -6 (~0.25%) must still be refused."""
    monkeypatch.setattr(minilm, "get_reranker", lambda *a, **k: FakeCE([-6.0]))
    out = minilm.rerank("q", [{"text": "noise"}], 5)
    assert not confident(out)
