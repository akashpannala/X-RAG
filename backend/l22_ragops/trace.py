"""L22: Langfuse tracing seam.

No-op unless LANGFUSE_ENABLED=true and keys are set — the API process never
depends on Langfuse. Two attach strategies, both dependency-safe:

1. The LangChain CallbackHandler, when the installed langchain-core matrix is
   compatible with the langfuse integration. Every graph node then appears as
   an observation on the trace.
2. A bare-SDK manual query trace (start/update/flush) used as a fallback when
   the CallbackHandler cannot be imported (e.g. langchain-core 1.x dropped the
   symbols the integration uses). Input, output and telemetry metadata are
   still recorded per query.
"""
from backend.config import settings


def langfuse_handler():
    if not available():
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        return None


def start_query_trace(query: str):
    """Bare-SDK fallback: returns a Langfuse chain span or None.

    The span carries a `_client` attribute so the caller can flush
    deterministically after ending it. No LangChain dependency involved.
    """
    if not available():
        return None
    try:
        from langfuse import Langfuse

        client = Langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        span = client.start_observation(
            name="rag-query", as_type="chain", input={"query": query})
        span._client = client
        return span
    except Exception:
        return None


def available() -> bool:
    return bool(settings.langfuse_enabled
                and settings.langfuse_public_key and settings.langfuse_secret_key)