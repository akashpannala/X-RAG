"""Backend settings + check_requirements(). Checks only — never installs."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # --- App ---
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # --- LLM: groq (api) | ollama (local) | llama.cpp (local) ---
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com"
    groq_model: str = "openai/gpt-oss-20b"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-q4_0"
    llama_cpp_url: str = "http://localhost:8080"
    llama_cpp_model: str = "llama3.1:8b"
    # --- Embedding: bge (local) | choreo (remote) ---
    embed_provider: str = "bge"
    embed_model: str = "BAAI/bge-m3"
    embed_url: str = ""
    # --- Vector Store: qdrant | supabase ---
    vector_store_provider: str = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "offline_rag"
    qdrant_api_key: str = ""
    # --- Database: sqlite (local) | postgres | supabase ---
    sqlite_path: str = "data/meta.db"
    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    # --- Queue: none | redis | upstash ---
    queue_provider: str = "none"
    redis_url: str = "redis://localhost:6379/0"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
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


def check_requirements() -> bool:
    """Verify providers from .env. Works local / ssh VPS / online — no Docker."""
    from rich.console import Console
    from rich.table import Table

    c = Console()
    rows: list[tuple[str, bool, str]] = []

    # Vector store
    try:
        from qdrant_client import QdrantClient

        kwargs = {"url": settings.qdrant_url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        QdrantClient(**kwargs).get_collections()
        rows.append(("Qdrant", True, settings.qdrant_url))
    except Exception as e:
        hint = f"QDRANT_URL={settings.qdrant_url} unreachable ({e}) — start native qdrant or set QDRANT_URL/ssh -L"
        if settings.vector_store_provider == "supabase":
            hint = f"Supabase pgvector not wired; set QDRANT_URL or VECTOR_STORE_PROVIDER=qdrant ({e})"
        rows.append(("Qdrant", False, hint))

    # LLM
    if settings.llm_provider == "groq":
        ok = bool(settings.groq_api_key)
        rows.append(("Groq key", ok, "set GROQ_API_KEY in .env" if not ok else settings.groq_model))
    elif settings.llm_provider == "llama.cpp":
        try:
            import httpx
            httpx.get(f"{settings.llama_cpp_url}/health", timeout=5).raise_for_status()
            rows.append(("llama.cpp", True, settings.llama_cpp_url))
        except Exception:
            try:
                import httpx
                httpx.get(f"{settings.llama_cpp_url}/v1/models", timeout=5).raise_for_status()
                rows.append(("llama.cpp", True, settings.llama_cpp_url))
            except Exception:
                rows.append(("llama.cpp", False, f"llama.cpp not at {settings.llama_cpp_url} — start server"))
    else:
        try:
            import httpx
            httpx.get(f"{settings.ollama_url}/api/tags", timeout=5).raise_for_status()
            rows.append(("Ollama", True, settings.ollama_model))
        except Exception:
            rows.append(("Ollama", False, f"ollama serve + ollama pull {settings.ollama_model} @ {settings.ollama_url}"))

    # Embed
    if settings.embed_provider == "choreo" or settings.embed_url:
        try:
            import httpx
            httpx.get(settings.embed_url or "http://localhost:8002/health", timeout=3).raise_for_status()
            rows.append(("Embed (choreo)", True, settings.embed_url or settings.embed_provider))
        except Exception:
            rows.append(("Embed (choreo)", False, f"EMBED_URL={settings.embed_url or 'not set'} unreachable"))
    else:
        rows.append(("BGE-M3", _bge_cached(), ".venv/bin/hf download BAAI/bge-m3" if not _bge_cached() else "cached"))

    # DB
    if settings.database_url.startswith("postgresql://") or settings.database_url.startswith("postgres://"):
        rows.append(("Postgres", True, settings.database_url[:40] + "..."))
    elif settings.supabase_url:
        rows.append(("Supabase", True, settings.supabase_url))
    else:
        rows.append(("SQLite", True, settings.sqlite_path))

    # Queue
    if settings.queue_provider == "upstash":
        ok = bool(settings.upstash_redis_rest_url and settings.upstash_redis_rest_token)
        rows.append(("Upstash", ok, "set UPSTASH_REDIS_REST_URL/TOKEN" if not ok else "ok"))
    elif settings.queue_provider == "redis":
        rows.append(("Redis", True, settings.redis_url))

    try:
        import docling  # noqa
        rows.append(("Docling", True, "ok"))
    except ImportError:
        rows.append(("Docling", False, "uv pip install --python .venv/bin/python docling"))

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
    fatal = [n for n, ok, _ in rows if not ok and n in ("Qdrant", "Groq key", "Ollama", "llama.cpp")]
    return not fatal
