"""L18: LLM factory — API first (Groq/OpenAI/Anthropic) → Local fallback (Ollama/llama.cpp)."""
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings, _resolve_llm_url

_LLM = None  # memoized client — get_llm() is the hottest call in the pipeline


def _try_api_llm(provider: str, base_url: str, model: str, api_key: str) -> BaseChatModel | None:
    """Try API provider (Groq/OpenAI/Anthropic)."""
    try:
        if provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(api_key=api_key, base_url=base_url, model=model, temperature=0.2)
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0.2)
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(api_key=api_key, model=model, temperature=0.2)
    except Exception:
        return None
    return None


def _try_local_llm(provider: str, base_url: str, model: str) -> BaseChatModel | None:
    """Try local provider (Ollama/llama.cpp)."""
    try:
        if provider == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(base_url=base_url, model=model, temperature=0.2)
        elif provider == "llama.cpp":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(base_url=base_url, api_key="local", model=model, temperature=0.2)
    except Exception:
        return None
    return None


def get_llm() -> BaseChatModel:
    global _LLM
    if _LLM is not None:
        return _LLM

    provider = (settings.llm_provider or "").strip().lower()
    base_url = _resolve_llm_url()
    model = settings.llm_model
    api_key = settings.llm_api_key

    # API-first providers
    api_providers = ("groq", "openai", "anthropic")
    local_providers = ("ollama", "llama.cpp")

    # Try primary provider first
    if provider in api_providers:
        llm = _try_api_llm(provider, base_url, model, api_key)
        if llm:
            _LLM = llm
            return _LLM
        # Fall back to local
        for local in local_providers:
            llm = _try_local_llm(local, _resolve_llm_url(), settings.llm_model)
            if llm:
                _LLM = llm
                return _LLM

    elif provider in local_providers:
        # Local primary, try API as fallback
        llm = _try_local_llm(provider, base_url, model)
        if llm:
            _LLM = llm
            return _LLM
        # Try API providers as fallback
        for api in api_providers:
            if settings.llm_api_key:  # Only try if API key is set
                llm = _try_api_llm(api, _resolve_llm_url(), settings.llm_model, settings.llm_api_key)
                if llm:
                    _LLM = llm
                    return _LLM

    else:
        raise ValueError(
            f"unknown LLM_PROVIDER={settings.llm_provider!r} — "
            f"expected one of: groq, openai, anthropic, ollama, llama.cpp")

    # Final fallback: try any available
    for p in (*api_providers, *local_providers):
        if p in api_providers:
            llm = _try_api_llm(p, base_url, model, api_key)
        else:
            llm = _try_local_llm(p, _resolve_llm_url(), model)
        if llm:
            _LLM = llm
            return _LLM

    raise RuntimeError("No LLM provider available")