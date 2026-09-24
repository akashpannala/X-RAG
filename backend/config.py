"""Backend settings + check_requirements(). Checks only — never installs."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # --- App ---
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # --- LLM ---
    llm_provider: str = "groq"
    llm_base_url: str = ""
    llm_model: str = "openai/gpt-oss-20b"
    llm_api_key: str = ""
    # --- Embeddings ---
    embed_provider: str = "bge"
    embed_base_url: str = ""
    embed_model: str = "BAAI/bge-m3"
    embed_api_key: str = ""
    # --- Rerankers ---
    rerank_provider: str = "minilm"      # minilm | jina | bge
    rerank_base_url: str = "https://api.jina.ai/v1"
    rerank_model: str = "jina-reranker-m0"
    rerank_api_key: str = ""
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # --- Vector Store (Qdrant only) ---
    vector_base_url: str = "http://localhost:6333"
    vector_api_key: str = ""
    vector_collection: str = "offline_rag"
    # --- Database (SQL) ---
    db_provider: str = "sqlite"
    db_url: str = ""
    db_path: str = "data/meta.db"
    # --- Storage / Auth ---
    upload_dir: str = "data/uploads"
    jwt_secret: str = "change-me-in-env"
    jwt_expire_min: int = 480
    default_mode_by_group: str = '{"hr": "quick", "eng": "deep", "public": "quick"}'

settings = Settings()


def _resolve_llm_url() -> str:
    """Resolve LLM base URL with local defaults."""
    url = settings.llm_base_url.strip()
    if not url:
        if settings.llm_provider == "ollama":
            return "http://localhost:11434"
        if settings.llm_provider == "llama.cpp":
            return "http://localhost:8080/v1"
    if settings.llm_provider == "llama.cpp" and not url.endswith("/v1"):
        return url.rstrip("/") + "/v1"
    return url


def _resolve_embed_url() -> str:
    """Resolve embedding base URL."""
    url = settings.embed_base_url.strip()
    if not url and settings.embed_provider in ("jina", "voyage", "cohere", "choreo"):
        return "https://api.jina.ai/v1"  # default to Jina
    return url


def _resolve_rerank_url() -> str:
    """Resolve reranker base URL with default."""
    url = settings.rerank_base_url.strip()
    if not url and settings.rerank_provider == "jina":
        return "https://api.jina.ai/v1"
    return url


def _hf_cached(repo: str) -> bool:
    """True if a local HuggingFace snapshot of repo has weights on disk."""
    base = Path.home() / ".cache/huggingface/hub" / f"models--{repo.replace('/', '--')}" / "snapshots"
    if not base.is_dir():
        return False
    return any(
        (s / f).exists()
        for s in base.iterdir()
        for f in ("pytorch_model.bin", "model.safetensors")
    )


def check_requirements() -> bool:
    """Verify providers from .env. Works local / ssh VPS / online — no Docker."""
    import httpx

    rows: list[tuple[str, bool, str]] = []

    # LLM — configured provider only
    provider = settings.llm_provider.lower()
    if provider == "groq":
        ok = bool(settings.llm_api_key)
        rows.append(("Groq key", ok, settings.llm_model if ok else "set LLM_API_KEY in .env"))
    elif provider in ("openai", "anthropic"):
        ok = bool(settings.llm_api_key)
        rows.append((provider.capitalize(), ok, settings.llm_model if ok else "set LLM_API_KEY in .env"))
    elif provider in ("ollama", "llama.cpp"):
        url = _resolve_llm_url()
        path = "/api/tags" if provider == "ollama" else "/models"
        try:
            httpx.get(f"{url}{path}", timeout=5).raise_for_status()
            rows.append((provider, True, url))
        except Exception:
            rows.append((provider, False, f"{provider} not at {url} — start server"))
    else:
        rows.append((f"LLM ({provider})", False, f"unknown provider: {provider}"))

    # Embeddings — configured provider only
    embed_url = _resolve_embed_url()
    if settings.embed_provider == "bge" and not embed_url:
        cached = _hf_cached("BAAI/bge-m3")
        rows.append(("BGE-M3", cached, ".venv/bin/hf download BAAI/bge-m3" if not cached else "cached"))
    else:
        test_url = (embed_url or "https://api.jina.ai/v1").rstrip("/")
        headers = {"Authorization": f"Bearer {settings.embed_api_key}"} if settings.embed_api_key else {}
        try:
            httpx.post(
                f"{test_url}/embeddings",
                json={"input": ["test"], "model": settings.embed_model},
                headers=headers,
                timeout=30,
            ).raise_for_status()
            rows.append((f"Embed ({settings.embed_provider})", True, test_url))
        except Exception:
            rows.append((f"Embed ({settings.embed_provider})", False, f"EMBED_BASE_URL={embed_url or 'not set'} unreachable"))

    # Reranker — configured provider only
    rerank_provider = settings.rerank_provider.lower()
    if rerank_provider == "jina":
        if not settings.rerank_api_key:
            rows.append(("Rerank (Jina)", False, "RERANK_API_KEY not set"))
        else:
            try:
                httpx.post(
                    f"{_resolve_rerank_url().rstrip('/')}/rerank",
                    json={"query": "test", "documents": ["test"], "top_n": 1, "model": settings.rerank_model},
                    headers={"Authorization": f"Bearer {settings.rerank_api_key}"},
                    timeout=10,
                ).raise_for_status()
                rows.append((f"Rerank (Jina {settings.rerank_model})", True, _resolve_rerank_url()))
            except Exception as e:
                rows.append(("Rerank (Jina)", False, f"Jina rerank API unreachable ({e})"))
    elif rerank_provider == "bge":
        cached = _hf_cached("BAAI/bge-reranker-v2-m3")
        rows.append(("Rerank (BGE)", cached, ".venv/bin/hf download BAAI/bge-reranker-v2-m3" if not cached else "cached"))
    else:
        rows.append(("Rerank (MiniLM)", True, "local cross-encoder"))

    # Database + vector store (runtime: Postgres/pgvector, falls back to Qdrant — mirrors l07)
    pg_ok = False
    if settings.db_provider in ("postgres", "supabase") and settings.db_url:
        try:
            import psycopg

            conn = psycopg.connect(settings.db_url, connect_timeout=5)
            conn.close()
            rows.append(("Postgres", True, settings.db_url[:40] + "..."))
            pg_ok = True
        except Exception as e:
            rows.append(("Postgres", False, f"DB_URL unreachable ({e})"))
    else:
        rows.append(("SQLite", True, settings.db_path))
    if not pg_ok:
        try:
            from qdrant_client import QdrantClient

            kwargs = {"url": settings.vector_base_url}
            if settings.vector_api_key:
                kwargs["api_key"] = settings.vector_api_key
            QdrantClient(**kwargs).get_collections()
            rows.append(("Qdrant", True, settings.vector_base_url))
        except Exception as e:
            rows.append(("Qdrant", False, f"VECTOR_BASE_URL={settings.vector_base_url} unreachable ({e})"))

    for name, ok, hint in rows:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f" — {hint}"))
    fatal = [n for n, ok, _ in rows if not ok and n in ("Groq key", "Ollama", "llama.cpp", "Qdrant")]
    return not fatal
