"""L15: ACL — allowed_groups enforced as Qdrant pre-search Filter (never post-filter)."""
from qdrant_client.models import FieldCondition, Filter, MatchAny


def groups_filter(groups: list[str]) -> Filter:
    return Filter(must=[FieldCondition(key="allowed_groups", match=MatchAny(any=list(groups)))])


def allowed(groups: list[str], hit_groups: list[str] | None) -> bool:
    """Set-membership ACL check for non-Qdrant legs (BM25/SPLADE/Kuzu).

    Empty request groups => fail-closed (matches nothing). A hit with no recorded
    groups (legacy index built before ACL was added) is treated as public so it
    stays retrievable by the default "public" group, matching prior behaviour.
    """
    if not groups:
        return False
    hg = hit_groups or ["public"]
    return bool(set(groups) & set(hg))
