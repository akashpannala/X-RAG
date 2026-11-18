"""L18: LLM factory — remote API only (Groq / OpenAI / Anthropic).

No Ollama/llama.cpp and no API→local fallback on ``aws-deploy``. A missing
key, invalid model, auth failure, or rate limit raises an explicit error.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings
from backend.errors import ConfigError, LLMError, classify_provider_error

_LLM = None  # memoized client — get_llm() is the hottest call in the pipeline
_API_PROVIDERS = ("groq", "openai", "anthropic")


def _build(provider: str, model: str, api_key: str) -> BaseChatModel:
    try:
        if provider == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(
                api_key=api_key,
                base_url=settings.llm_base_url or "https://api.groq.com",
                model=model,
                temperature=0.2,
            )
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=api_key,
                base_url=settings.llm_base_url or None,
                model=model,
                temperature=0.2,
            )
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(api_key=api_key, model=model, temperature=0.2)
    except Exception as e:
        raise classify_provider_error(e, kind="LLM", provider=provider, model=model) from e
    raise ConfigError(
        f"Unsupported LLM_PROVIDER={provider!r}",
        hint=f"aws-deploy supports: {', '.join(_API_PROVIDERS)}",
    )


def get_llm() -> BaseChatModel:
    """Return the configured remote LLM. Raises on misconfiguration."""
    global _LLM
    if _LLM is not None:
        return _LLM

    provider = (settings.llm_provider or "").strip().lower()
    if provider not in _API_PROVIDERS:
        raise LLMError(
            f"LLM provider {settings.llm_provider!r} is not supported on aws-deploy",
            hint=f"use one of: {', '.join(_API_PROVIDERS)}",
            status_code=500,
        )
    if not settings.llm_api_key:
        raise LLMError(
            f"LLM_API_KEY is required for {provider}",
            hint="remote LLM is mandatory on aws-deploy (no local fallback)",
            status_code=500,
        )
    _LLM = _build(provider, settings.llm_model, settings.llm_api_key)
    return _LLM
