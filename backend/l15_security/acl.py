"""L15: ACL — allowed_groups enforced as Qdrant pre-search Filter (never post-filter)."""
from qdrant_client.models import FieldCondition, Filter, MatchAny


def groups_filter(groups: list[str]) -> Filter:
    return Filter(must=[FieldCondition(key="allowed_groups", match=MatchAny(any=list(groups)))])
