"""Backend settings + check_requirements(). Checks only — never installs."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com"
    groq_model: str = "openai/gpt-oss-20b"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b-q4_0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "offline_rag"
    embed_model: str = "BAAI/bge-m3"
    upload_dir: str = "data/uploads"
    sqlite_path: str = "data/meta.db"


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
    """Verify everything Phase 1 needs. Returns True if bootable. Check-only."""
    from rich.console import Console
    from rich.table import Table

    c = Console()
    rows: list[tuple[str, bool, str]] = []

    try:
        from qdrant_client import QdrantClient

        QdrantClient(url=settings.qdrant_url).get_collections()
        rows.append(("Qdrant", True, settings.qdrant_url))
    except Exception as e:
        rows.append(("Qdrant", False, f"start it: docker start xrag-qdrant ({e})"))

    if settings.llm_provider == "groq":
        ok = bool(settings.groq_api_key)
        rows.append(("Groq key", ok, "set GROQ_API_KEY in .env" if not ok else settings.groq_model))
    else:
        try:
            import httpx

            httpx.get(f"{settings.ollama_url}/api/tags", timeout=5).raise_for_status()
            rows.append(("Ollama", True, settings.ollama_model))
        except Exception:
            rows.append(("Ollama", False, f"ollama serve + ollama pull {settings.ollama_model}"))

    try:
        import docling  # noqa

        rows.append(("Docling", True, "ok"))
    except ImportError:
        rows.append(("Docling", False, "uv pip install --python .venv/bin/python docling"))

    try:
        import spacy

        spacy.load("en_core_web_lg")
        rows.append(("spaCy PII model", True, "en_core_web_lg"))
    except Exception:
        rows.append(("spaCy PII model", False, "auto-downloads on first ingest (slow once)"))

    rows.append((
        "BGE-M3",
        _bge_cached(),
        ".venv/bin/hf download BAAI/bge-m3" if not _bge_cached() else "cached",
    ))

    t = Table(title="OFFLINE-RAG requirements")
    t.add_column("Check")
    t.add_column("OK")
    t.add_column("Hint")
    for name, ok, hint in rows:
        t.add_row(name, "✅" if ok else "❌", "" if ok else hint)
    c.print(t)
    fatal = [n for n, ok, _ in rows if not ok and n in ("Qdrant", "Groq key", "Ollama")]
    return not fatal
