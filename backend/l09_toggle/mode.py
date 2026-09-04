"""L9 toggle — manual Quick/Deep only. Role default, per-query override. No ML."""
from backend.l15_security.auth import default_mode


def resolve(groups: list[str], override: str | None) -> str:
    if override in ("quick", "deep"):
        return override
    return default_mode(groups)
