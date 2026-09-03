"""All routes — /health, /ingest, /query. Swagger at /docs."""
from pathlib import Path

from fastapi import FastAPI, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.l01_connectors.loaders import check_supported
from backend.l02_docintel.docling import parse as docling_parse
from backend.l03_cleaning.cleaning import redact
from backend.l04_chunking.splitter import chunk
from backend.l07_storage import qdrant as store
from backend.l08_freshness.store import meta_conn, sha256_file
from backend.l18_generation.graph import answer


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResponse(BaseModel):
    answer: str
    citations: list[str] = []
    provider: str = ""


class IngestResponse(BaseModel):
    filename: str
    chunks: int
    hash: str


app = FastAPI(title="OFFLINE-RAG Phase 1")
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider, "qdrant": settings.qdrant_url}


@app.post("/ingest", response_model=IngestResponse)
def ingest(f: UploadFile):
    dest = Path(settings.upload_dir) / f.filename
    check_supported(dest)
    dest.write_bytes(f.file.read())
    h = sha256_file(dest)
    text, _ = redact(docling_parse(dest))
    chunks = chunk(text)
    store.add_docs(chunks, [{"doc": dest.stem, "chunk_id": i, "text": c} for i, c in enumerate(chunks)])
    con = meta_conn(settings.sqlite_path)
    con.execute("INSERT OR REPLACE INTO documents(filename, hash) VALUES (?,?)", (f.filename, h))
    con.commit()
    return IngestResponse(filename=f.filename, chunks=len(chunks), hash=h[:12])


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    text, cites = answer(req.query, req.top_k)
    return QueryResponse(answer=text, citations=cites, provider=settings.llm_provider)
