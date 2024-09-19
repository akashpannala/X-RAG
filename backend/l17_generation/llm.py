"""L18: LLM factory — Groq / Ollama / llama.cpp / OpenAI / Anthropic via unified config."""
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings, _resolve_llm_url

_LLM = None  # memoized client — get_llm() is the hottest call in the pipeline


def get_llm() -> BaseChatModel:
    global _LLM
    if _LLM is not None:
        return _LLM
    provider = (settings.llm_provider or "").strip().lower()
    base_url = _resolve_llm_url()
    model = settings.llm_model
    api_key = settings.llm_api_key

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        _LLM = ChatOllama(base_url=base_url, model=model, temperature=0.2)
    elif provider == "llama.cpp":
        from langchain_openai import ChatOpenAI

        _LLM = ChatOpenAI(base_url=base_url, api_key="local", model=model, temperature=0.2)
    elif provider == "groq":
        from langchain_groq import ChatGroq

        _LLM = ChatGroq(api_key=api_key, base_url=base_url, model=model, temperature=0.2)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        _LLM = ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0.2)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        _LLM = ChatAnthropic(api_key=api_key, model=model, temperature=0.2)
    else:
        raise ValueError(
            f"unknown LLM_PROVIDER={settings.llm_provider!r} — "
            f"expected one of: groq, ollama, llama.cpp, openai, anthropic")
    return _LLM