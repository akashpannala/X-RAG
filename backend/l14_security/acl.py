"""L15: ACL — allowed_groups enforced as a pre-search filter (never post-filter)."""


def groups_filter(groups: list[str]) -> dict:
    """Portable pre-search filter for pgvector (dict, not a Qdrant model).

    Empty request groups stay empty so retrieval fails closed.
    """
    return {"groups": list(groups)}


def allowed(groups: list[str], hit_groups: list[str] | None) -> bool:
    """Set-membership ACL check for non-vector legs (BM25/SPLADE/Kuzu).

    Empty request groups => fail-closed (matches nothing). A hit with no recorded
    groups (legacy index built before ACL was added) is treated as public so it
    stays retrievable by the default "public" group, matching prior behaviour.
    """
    if not groups:
        return False
    hg = hit_groups or ["public"]
    return bool(set(groups) & set(hg))
