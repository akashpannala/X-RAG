"""Error classification: explicit provider/database failures, no fallbacks."""
from backend.errors import (
    DatabaseError,
    RateLimitError,
    XRAGError,
    classify_db_error,
    classify_provider_error,
)


class _StatusError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def test_rate_limit_by_text_and_status():
    text = classify_provider_error(
        Exception("429 Too Many Requests: tokens per day exhausted"),
        kind="LLM", provider="groq", model="openai/gpt-oss-20b",
    )
    status = classify_provider_error(
        _StatusError("slow down", 429), kind="embed", provider="jina"
    )
    assert isinstance(text, RateLimitError) and text.status_code == 429
    assert isinstance(status, RateLimitError)


def test_missing_model_is_502_and_names_model():
    err = classify_provider_error(
        _StatusError("model not found", 404),
        kind="embed", provider="jina", model="jina-embeddings-v3",
    )
    assert isinstance(err, XRAGError) and err.status_code == 502
    assert "jina-embeddings-v3" in str(err) and "jina" in str(err)


def test_provider_auth_error():
    err = classify_provider_error(
        _StatusError("unauthorized", 401), kind="LLM", provider="groq"
    )
    assert err.status_code == 502 and "authentication" in str(err).lower()


def test_db_missing_by_sqlstate():
    exc = Exception("database error")
    exc.sqlstate = "3D000"
    err = classify_db_error(exc)
    assert isinstance(err, DatabaseError) and err.status_code == 503
    assert "does not exist" in str(err)


def test_db_missing_pgvector_type_is_extension_hint():
    err = classify_db_error(Exception("vector type not found in the database"))
    assert "pgvector extension" in str(err)
    assert "CREATE EXTENSION vector" in err.hint


def test_db_unreachable_and_auth():
    unreachable = classify_db_error(Exception("connection refused"))
    auth = classify_db_error(Exception("password authentication failed"))
    assert "unreachable" in str(unreachable).lower()
    assert "authentication" in str(auth).lower()


def test_hint_is_appended_to_message():
    err = XRAGError("boom", hint="fix it", status_code=418)
    assert str(err) == "boom — fix it" and err.status_code == 418
