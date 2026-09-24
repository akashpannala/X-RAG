"""L18: LLM factory — API first (Groq/OpenAI/Anthropic) → Local fallback (Ollama/llama.cpp)."""
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings, _resolve_llm_url

_LLM = None  # memoized client — get_llm() is the hottest call in the pipeline
_API_PROVIDERS = ("groq", "openai", "anthropic")
_LOCAL_PROVIDERS = ("ollama", "llama.cpp")


def _try_api_llm(provider: str, model: str, api_key: str) -> BaseChatModel | None:
    """Try API provider (Groq/OpenAI/Anthropic)."""
    try:
        if provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(api_key=api_key, base_url=settings.llm_base_url or "https://api.groq.com", model=model, temperature=0.2)
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(api_key=api_key, base_url=settings.llm_base_url or None, model=model, temperature=0.2)
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(api_key=api_key, model=model, temperature=0.2)
    except Exception:
        return None
    return None


def _try_local_llm(provider: str, model: str) -> BaseChatModel | None:
    """Try local provider (Ollama/llama.cpp)."""
    try:
        base_url = _resolve_llm_url() if settings.llm_provider == provider else (
            "http://localhost:11434" if provider == "ollama" else "http://localhost:8080/v1")
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
    """Configured provider first, then one fallback side (API→local, local→API if keyed)."""
    global _LLM
    if _LLM is not None:
        return _LLM

    provider = (settings.llm_provider or "").strip().lower()
    if provider not in (*_API_PROVIDERS, *_LOCAL_PROVIDERS):
        raise ValueError(
            f"unknown LLM_PROVIDER={settings.llm_provider!r} — "
            f"expected one of: {', '.join((*_API_PROVIDERS, *_LOCAL_PROVIDERS))}")

    if provider in _API_PROVIDERS:
        order = [provider, *(p for p in _LOCAL_PROVIDERS)]
    else:
        order = [provider, *(p for p in _API_PROVIDERS if settings.llm_api_key)]

    for p in order:
        llm = (_try_api_llm(p, settings.llm_model, settings.llm_api_key) if p in _API_PROVIDERS
               else _try_local_llm(p, settings.llm_model))
        if llm:
            _LLM = llm
            return _LLM
    raise RuntimeError("No LLM provider available")
