"""L9 toggle — manual Quick/Deep only. Role default, per-query override. No ML."""
import logging

from backend.l15_security.auth import default_mode

_logger = logging.getLogger(__name__)  # ponytail: manual toggle, role-defaults not restrictions


def resolve(groups: list[str], override: str | None) -> str:
    if override in ("quick", "deep"):
        return override
    if override is not None:
        _logger.warning("invalid mode %r -> role default %r", override, default_mode(groups))
    return default_mode(groups)
