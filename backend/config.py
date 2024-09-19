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


def _bge_cached() -> bool:
    base = Path.home() / ".cache/huggingface/hub/models--BAAI--bge-m3/snapshots"
    if not base.is_dir():
        return False
    return any(
        (s / f).exists()
        for s in base.iterdir()
        for f in ("pytorch_model.bin", "model.safetensors")
    )


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


def _bge_reranker_cached() -> bool:
    base = Path.home() / ".cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots"
    if not base.is_dir():
        return False
    return any(
        (s / f).exists()
        for s in base.iterdir()
        for f in ("pytorch_model.bin", "model.safetensors")
    )


def check_requirements() -> bool:
    """Verify providers from .env. Works local / ssh VPS / online — no Docker."""
    from rich.console import Console
    from rich.table import Table

    c = Console()
    rows: list[tuple[str, bool, str]] = []

    # LLM
    provider = settings.llm_provider.lower()
    base_url = _resolve_llm_url()
    if provider == "groq":
        ok = bool(settings.llm_api_key)
        rows.append(("Groq key", ok, "set LLM_API_KEY in .env" if not ok else settings.llm_model))
    elif provider == "llama.cpp":
        try:
            import httpx
            httpx.get(f"{base_url}/health", timeout=5).raise_for_status()
            rows.append(("llama.cpp", True, base_url))
        except Exception:
            try:
                import httpx
                httpx.get(f"{base_url}/models", timeout=5).raise_for_status()
                rows.append(("llama.cpp", True, base_url))
            except Exception:
                rows.append(("llama.cpp", False, f"llama.cpp not at {base_url} — start server"))
    elif provider == "ollama":
        try:
            import httpx
            httpx.get(f"{base_url}/api/tags", timeout=5).raise_for_status()
            rows.append(("Ollama", True, settings.llm_model))
        except Exception:
            rows.append(("Ollama", False, f"ollama serve + ollama pull {settings.llm_model} @ {base_url}"))
    elif provider in ("openai", "anthropic"):
        ok = bool(settings.llm_api_key)
        rows.append((provider.capitalize(), ok, f"set LLM_API_KEY in .env" if not ok else settings.llm_model))
    else:
        rows.append((f"LLM ({provider})", False, f"unknown provider: {provider}"))

    # Embeddings
    embed_url = _resolve_embed_url()
    if settings.embed_provider in ("jina", "voyage", "cohere", "choreo") or embed_url:
        try:
            import httpx
            test_url = embed_url or "https://api.jina.ai/v1"
            httpx.get(f"{test_url.rstrip('/')}/health", timeout=3).raise_for_status()
            rows.append((f"Embed ({settings.embed_provider})", True, embed_url or "default"))
        except Exception:
            try:
                import httpx
                headers = {}
                if settings.embed_api_key:
                    headers["Authorization"] = f"Bearer {settings.embed_api_key}"
                httpx.post(
                    f"{test_url.rstrip('/')}/embeddings",
                    json={"input": ["test"], "model": settings.embed_model},
                    headers=headers,
                    timeout=30
                ).raise_for_status()
                rows.append((f"Embed ({settings.embed_provider})", True, embed_url or "default"))
            except Exception:
                rows.append((f"Embed ({settings.embed_provider})", False, f"EMBED_BASE_URL={embed_url or 'not set'} unreachable"))
    else:
        rows.append(("BGE-M3", _bge_cached(), ".venv/bin/hf download BAAI/bge-m3" if not _bge_cached() else "cached"))

    # Reranker
    rerank_provider = settings.rerank_provider.lower()
    if rerank_provider == "jina":
        rerank_url = _resolve_rerank_url()
        if settings.rerank_api_key:
            try:
                import httpx
                headers = {"Authorization": f"Bearer {settings.rerank_api_key}"}
                httpx.post(
                    f"{rerank_url.rstrip('/')}/rerank",
                    json={"query": "test", "documents": ["test"], "top_n": 1, "model": settings.rerank_model},
                    headers=headers, timeout=10
                ).raise_for_status()
                rows.append((f"Rerank (Jina {settings.rerank_model})", True, rerank_url))
            except Exception as e:
                rows.append((f"Rerank (Jina)", False, f"Jina rerank API unreachable ({e})"))
        else:
            rows.append(("Rerank (Jina)", False, "RERANK_API_KEY not set"))
    elif rerank_provider == "bge":
        rows.append(("Rerank (BGE)", _bge_reranker_cached(), ".venv/bin/hf download BAAI/bge-reranker-v2-m3" if not _bge_reranker_cached() else "cached"))
    else:
        rows.append(("Rerank (MiniLM)", True, "local cross-encoder"))

    # Qdrant
    try:
        from qdrant_client import QdrantClient

        kwargs = {"url": settings.vector_base_url}
        if settings.vector_api_key:
            kwargs["api_key"] = settings.vector_api_key
        QdrantClient(**kwargs).get_collections()
        rows.append(("Qdrant", True, settings.vector_base_url))
    except Exception as e:
        rows.append(("Qdrant", False, f"VECTOR_BASE_URL={settings.vector_base_url} unreachable ({e})"))

    # Database
    if settings.db_provider in ("postgres", "supabase") and settings.db_url:
        try:
            import psycopg

            conn = psycopg.connect(settings.db_url)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            rows.append(("Postgres", True, settings.db_url[:40] + "..."))
        except Exception as e:
            rows.append(("Postgres", False, f"DB_URL unreachable ({e})"))
    else:
        rows.append(("SQLite", True, settings.db_path))

    # Docling
    try:
        import docling  # noqa
        rows.append(("Docling", True, "ok"))
    except ImportError:
        rows.append(("Docling", False, "uv pip install --python .venv/bin/python docling"))

    # spaCy PII
    try:
        import spacy
        for model in ("en_core_web_sm", "en_core_web_lg"):
            try:
                spacy.load(model)
                rows.append(("spaCy PII", True, model))
                break
            except Exception:
                continue
        else:
            rows.append(("spaCy PII", False, "auto-downloads on first ingest"))
    except ImportError:
        rows.append(("spaCy PII", False, "uv pip install presidio-analyzer"))

    t = Table(title="X-RAG requirements (env-driven)")
    t.add_column("Check")
    t.add_column("OK")
    t.add_column("Hint")
    for name, ok, hint in rows:
        t.add_row(name, "✅" if ok else "❌", "" if ok else hint)
    c.print(t)
    fatal = [n for n, ok, _ in rows if not ok and n in ("Groq key", "Qdrant")]
    if provider in ("ollama", "llama.cpp"):
        fatal = [n for n, ok, _ in rows if not ok and n in ("Ollama", "llama.cpp", "Qdrant")]
    return not fatal