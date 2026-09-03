"""L18: LLM factory — ChatGroq (dev) / ChatOllama (prod). One .invoke() surface."""
from langchain_core.language_models.chat_models import BaseChatModel

from backend.config import settings


def get_llm() -> BaseChatModel:
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(base_url=settings.ollama_url, model=settings.ollama_model, temperature=0.2)
    from langchain_groq import ChatGroq

    return ChatGroq(api_key=settings.groq_api_key, base_url=settings.groq_base_url,
                    model=settings.groq_model, temperature=0.2)
