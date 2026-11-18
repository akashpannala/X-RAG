"""Remote rerank cascade: 0-1 scores, no local MiniLM, confidence still applies."""
import importlib

cascade = importlib.import_module("backend.l13_rerank.cascade")
from backend.l14_security.injection import confident


class FakeProvider:
    def __init__(self, ordered_scores=None):
        self.ordered_scores = ordered_scores

    def rerank(self, query, docs, top_n):
        if self.ordered_scores is not None:
            return list(zip(range(len(docs)), self.ordered_scores))[:top_n]
        n = min(top_n, len(docs))
        return [(i, 1.0 - i * 0.1) for i in range(n)]


def test_rerank_api_preserves_provider_order(monkeypatch):
    hits = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    monkeypatch.setattr(cascade, "get_reranker_provider",
                        lambda: FakeProvider([0.1, 0.9, 0.4]))
    out = cascade.rerank_api("q", hits, 3)
    assert [h["text"] for h in out] == ["a", "b", "c"]
    assert out[0]["score"] == 0.1
    assert out[1]["score"] == 0.9


def test_quick_cascade_returns_five_and_normalizes(monkeypatch):
    hits = [{"text": f"t{i}"} for i in range(10)]
    monkeypatch.setattr(cascade, "get_reranker_provider", lambda: FakeProvider())
    out = cascade.cascade("q", hits, "quick")
    assert len(out) == 5
    assert all(0.0 <= h["score"] <= 1.0 for h in out)
    assert confident(out)


def test_deep_cascade_uses_remote_only(monkeypatch):
    hits = [{"text": f"t{i}"} for i in range(50)]
    monkeypatch.setattr(cascade, "get_reranker_provider", lambda: FakeProvider())
    monkeypatch.setattr(cascade, "rankgpt_listwise", lambda q, h, n: h[:n])
    monkeypatch.setattr(cascade, "mmr", lambda qv, h, vecs, n: h[:n])
    out = cascade.cascade("q", hits, "deep")
    assert len(out) == 5
    assert all(0.0 <= h["score"] <= 1.0 for h in out)
    assert confident(out)


def test_cascade_empty_hits():
    assert cascade.cascade("q", [], "quick") == []
    assert cascade.cascade("q", [], "deep") == []
