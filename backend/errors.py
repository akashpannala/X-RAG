"""Central error classification for the AWS API-only deployment.

No fallbacks on ``aws-deploy``: when a remote provider or managed database
fails, callers get an explicit, actionable exception instead of silently
switching to a local model/store. Every classifier keeps the original error
in the message and logs it at the call site.
"""


class XRAGError(RuntimeError):
    """Base error carrying an HTTP status for the API layer."""

    status_code = 502

    def __init__(self, message: str, *, hint: str = "", status_code: int | None = None):
        self.hint = hint
        if status_code is not None:
            self.status_code = status_code
        detail = f"{message} — {hint}" if hint else message
        super().__init__(detail)


class ConfigError(XRAGError):
    status_code = 500


class EmbeddingError(XRAGError):
    status_code = 502


class RerankError(XRAGError):
    status_code = 502


class LLMError(XRAGError):
    status_code = 502


class DatabaseError(XRAGError):
    status_code = 503


class RateLimitError(XRAGError):
    status_code = 429


def _text(exc: BaseException) -> str:
    return str(exc).lower()


def _status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _sqlstate(exc: BaseException) -> str:
    state = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    if isinstance(state, str):
        return state
    diag = getattr(exc, "diag", None)
    state = getattr(diag, "sqlstate", None) if diag is not None else None
    return state if isinstance(state, str) else ""


def is_rate_limit(exc: BaseException) -> bool:
    text = _text(exc)
    return _status(exc) == 429 or any(
        marker in text
        for marker in (
            "rate limit",
            "rate_limit",
            "ratelimit",
            "too many requests",
            "quota",
            "insufficient_quota",
            "limit exceeded",
            "tokens per minute",
            "tokens per day",
            "tpm",
            "tpd",
        )
    )


def is_model_missing(exc: BaseException) -> bool:
    text = _text(exc)
    if _status(exc) in (404, 400) and any(
        marker in text
        for marker in ("model", "does not exist", "not found", "invalid", "unsupported")
    ):
        return True
    return any(
        marker in text
        for marker in (
            "model not found",
            "model_not_found",
            "no such model",
            "unknown model",
            "invalid model",
            "unsupported model",
            "does not support",
            "decommissioned",
        )
    )


def is_auth_error(exc: BaseException) -> bool:
    text = _text(exc)
    return _status(exc) in (401, 403) or any(
        marker in text
        for marker in (
            "unauthorized",
            "forbidden",
            "invalid api key",
            "invalid_api_key",
            "authentication",
            "permission denied",
            "no api key",
        )
    )


def is_db_missing(exc: BaseException) -> bool:
    text = _text(exc)
    return _sqlstate(exc) == "3D000" or "invalidcatalogname" in text or (
        "database" in text and "does not exist" in text
    )


def is_db_unreachable(exc: BaseException) -> bool:
    text = _text(exc)
    return any(
        marker in text
        for marker in (
            "connection refused",
            "could not connect",
            "connection timed out",
            "timeout expired",
            "server closed the connection",
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "network is unreachable",
        )
    )


def classify_provider_error(
    exc: BaseException, *, kind: str, provider: str, model: str = ""
) -> XRAGError:
    """Map a remote API failure to an explicit, user-presentable error."""
    label = f"{kind} model {model!r} ({provider})" if model else f"{kind} ({provider})"
    if is_rate_limit(exc):
        return RateLimitError(f"{label} API limit exceeded. Retry later. ({exc})")
    if is_model_missing(exc):
        return XRAGError(
            f"{label} model missing or unavailable: {exc}",
            hint="check the configured model name and provider account access",
            status_code=502,
        )
    if is_auth_error(exc):
        return XRAGError(
            f"{label} authentication failed: {exc}",
            hint="check the provider API key",
            status_code=502,
        )
    return XRAGError(f"{label} request failed: {exc}", status_code=502)


def classify_db_error(exc: BaseException) -> DatabaseError:
    """Map a Postgres/pgvector failure to an explicit database error."""
    if is_db_missing(exc):
        return DatabaseError(
            f"Database does not exist: {exc}",
            hint="check DB_URL / database name",
        )
    if is_auth_error(exc):
        return DatabaseError(
            f"Database authentication failed: {exc}",
            hint="check DB_URL credentials",
        )
    if is_db_unreachable(exc):
        return DatabaseError(
            f"Database unreachable: {exc}",
            hint="check DB_URL host/port, firewall, and pooler status",
        )
    text = _text(exc)
    if ("extension" in text and "vector" in text) or "vector type not found" in text:
        return DatabaseError(
            f"pgvector extension is missing: {exc}",
            hint="CREATE EXTENSION vector (or enable the vector extension in Supabase)",
        )
    if "relation" in text and "does not exist" in text:
        return DatabaseError(
            f"pgvector schema is missing: {exc}",
            hint="re-run startup so the vectors table is created",
        )
    return DatabaseError(f"Database operation failed: {exc}")
