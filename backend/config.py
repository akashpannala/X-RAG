"""Backend settings + check_requirements(). Checks only — never installs.

On the ``aws-deploy`` branch this is deliberately API-only: remote LLM,
remote embeddings, remote reranker, and Postgres/Supabase pgvector. Local
providers (Ollama/llama.cpp, BGE embeddings, MiniLM/BGE rerankers, SQLite
metadata, Qdrant) are rejected so there is no silent fallback.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.errors import classify_db_error, classify_provider_error, is_db_missing

_API_PROVIDERS = ("groq", "openai", "anthropic")
_EMBED_PROVIDERS = ("jina", "voyage", "cohere")
_RERANK_PROVIDERS = ("jina",)
_SQL_PROVIDERS = ("postgres", "supabase")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # --- App ---
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # --- LLM (remote only) ---
    llm_provider: str = "groq"
    llm_base_url: str = ""
    llm_model: str = "openai/gpt-oss-20b"
    llm_api_key: str = ""
    # --- Embeddings (remote only) ---
    embed_provider: str = "jina"
    embed_base_url: str = ""
    embed_model: str = "jina-embeddings-v3"
    embed_api_key: str = ""
    # --- Reranker (remote only) ---
    rerank_provider: str = "jina"
    rerank_base_url: str = "https://api.jina.ai/v1"
    rerank_model: str = "jina-reranker-m0"
    rerank_api_key: str = ""
    # --- Vector Store (pgvector only) ---
    vector_collection: str = "offline_rag"
    # --- Database (Postgres/Supabase only for deployment) ---
    db_provider: str = "supabase"
    db_url: str = ""
    # SQLite is retained for the unit-test suite only; it is never a fallback.
    db_path: str = "data/meta.db"
    # --- Storage / Auth ---
    upload_dir: str = "data/uploads"
    jwt_secret: str = "change-me-in-env"
    jwt_expire_min: int = 480
    default_mode_by_group: str = '{"hr": "quick", "eng": "deep", "public": "quick"}'

    @property
    def is_postgres(self) -> bool:
        return (self.db_provider or "").strip().lower() in _SQL_PROVIDERS


settings = Settings()


def _resolve_llm_url() -> str:
    """Resolve the remote LLM base URL (custom gateways only)."""
    return settings.llm_base_url.strip()


def _resolve_embed_url() -> str:
    """Resolve embedding base URL. Only remote providers are supported."""
    url = settings.embed_base_url.strip()
    if not url and settings.embed_provider.lower() == "jina":
        return "https://api.jina.ai/v1"
    return url


def _resolve_rerank_url() -> str:
    """Resolve the remote reranker base URL."""
    url = settings.rerank_base_url.strip()
    if not url and settings.rerank_provider.lower() == "jina":
        return "https://api.jina.ai/v1"
    return url


def _provider_error(kind: str, exc: BaseException, provider: str, model: str = "") -> str:
    err = classify_provider_error(exc, kind=kind, provider=provider, model=model)
    return str(err)


def _db_error(exc: BaseException) -> str:
    return str(classify_db_error(exc))


def check_requirements() -> bool:
    """Verify remote providers + Postgres/pgvector. Fatal on any failure."""
    import httpx
    import psycopg

    rows: list[tuple[str, bool, str]] = []

    # --- LLM ---
    provider = (settings.llm_provider or "").strip().lower()
    if provider not in _API_PROVIDERS:
        rows.append((f"LLM ({provider or 'unset'})", False,
                     f"aws-deploy requires one of: {', '.join(_API_PROVIDERS)}"))
    elif not settings.llm_api_key:
        rows.append((f"LLM ({provider})", False, "set LLM_API_KEY in .env"))
    else:
        rows.append((f"LLM ({provider})", True, settings.llm_model))

    # --- Embeddings ---
    embed_provider = (settings.embed_provider or "").strip().lower()
    embed_url = _resolve_embed_url()
    if embed_provider not in _EMBED_PROVIDERS:
        rows.append((f"Embed ({embed_provider or 'unset'})", False,
                     f"aws-deploy requires one of: {', '.join(_EMBED_PROVIDERS)}"))
    elif not embed_url:
        rows.append((f"Embed ({embed_provider})", False, "set EMBED_BASE_URL in .env"))
    elif not settings.embed_api_key:
        rows.append((f"Embed ({embed_provider})", False, "set EMBED_API_KEY in .env"))
    else:
        try:
            endpoint = (f"{embed_url.rstrip('/')}/embed" if embed_provider == "cohere"
                        else f"{embed_url.rstrip('/')}/embeddings")
            payload = ({"texts": ["test"], "model": settings.embed_model,
                        "input_type": "search_query"}
                       if embed_provider == "cohere"
                       else {"input": ["test"], "model": settings.embed_model})
            r = httpx.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {settings.embed_api_key}"},
                timeout=30,
            )
            r.raise_for_status()
            rows.append((f"Embed ({embed_provider} {settings.embed_model})", True, embed_url))
        except Exception as e:
            rows.append((f"Embed ({embed_provider} {settings.embed_model})", False,
                         _provider_error("Embedding", e, embed_provider, settings.embed_model)))

    # --- Reranker ---
    rerank_provider = (settings.rerank_provider or "").strip().lower()
    if rerank_provider not in _RERANK_PROVIDERS:
        rows.append((f"Rerank ({rerank_provider or 'unset'})", False,
                     "aws-deploy requires RERANK_PROVIDER=jina"))
    elif not settings.rerank_api_key:
        rows.append(("Rerank (jina)", False, "set RERANK_API_KEY in .env"))
    else:
        try:
            r = httpx.post(
                f"{_resolve_rerank_url().rstrip('/')}/rerank",
                json={"query": "test", "documents": ["test"], "top_n": 1,
                      "model": settings.rerank_model},
                headers={"Authorization": f"Bearer {settings.rerank_api_key}"},
                timeout=15,
            )
            r.raise_for_status()
            rows.append((f"Rerank (jina {settings.rerank_model})", True, _resolve_rerank_url()))
        except Exception as e:
            rows.append((f"Rerank (jina {settings.rerank_model})", False,
                         _provider_error("Rerank", e, "jina", settings.rerank_model)))

    # --- Database + pgvector ---
    if not settings.is_postgres:
        rows.append((f"Database ({settings.db_provider or 'unset'})", False,
                     "aws-deploy requires DB_PROVIDER=postgres|supabase with a DB_URL"))
    elif not settings.db_url:
        rows.append(("Postgres", False, "set DB_URL in .env"))
    else:
        try:
            conn = psycopg.connect(settings.db_url, connect_timeout=5)
        except Exception as e:
            label = "Database does not exist" if is_db_missing(e) else "Postgres"
            rows.append((label, False, _db_error(e)))
        else:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.execute(
                        "SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                    has_vector = cur.fetchone() is not None
                rows.append(("Postgres", True, settings.db_url.split("@")[-1][:40]))
                rows.append(("pgvector extension", has_vector,
                             "CREATE EXTENSION vector" if not has_vector else "installed"))
            except Exception as e:
                rows.append(("Postgres", False, _db_error(e)))
            finally:
                conn.close()

    for name, ok, hint in rows:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f" — {hint}"))
    return all(ok for _, ok, _ in rows)
