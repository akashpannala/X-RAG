"""BM25 must attach allowed_groups to hits and filter by ACL (deep-mode leak regression)."""
from backend.L06_sparse import bm25


def test_hits_carry_allowed_groups_and_acl_filters(tmp_settings):
    bm25.reset()
    bm25.add(
        [
            "free diamond open access journals in quantum physics",
            "jwt secret configuration test document",
        ],
        [
            {"doc": "Free Journals", "chunk_id": 0, "text": "free diamond open access journals", "allowed_groups": ["hr"]},
            {"doc": "test", "chunk_id": 0, "text": "jwt secret configuration", "allowed_groups": ["public"]},
        ],
    )

    raw = bm25.search("free diamond open access journals", k=10, groups=None)
    assert raw, "expected retrieval hits"
    assert all("allowed_groups" in h for h in raw)

    hr = bm25.search("free diamond open access journals", k=10, groups=["hr", "public"])
    eng = bm25.search("free diamond open access journals", k=10, groups=["eng", "public"])
    pub = bm25.search("jwt secret configuration", k=10, groups=["public"])

    # HR sees the HR-only doc
    assert any(h["doc"] == "Free Journals" for h in hr)
    # eng must NOT see HR-only chunks (regression: missing allowed_groups → treated as public)
    assert all(h["doc"] != "Free Journals" for h in eng)
    # public group still reaches public test doc
    assert any(h["doc"] == "test" for h in pub)
    # empty groups fail closed
    assert bm25.search("free journals", k=10, groups=[]) == []


def test_empty_index_returns_empty():
    bm25.reset()
    assert bm25.search("anything", k=5, groups=["public"]) == []
