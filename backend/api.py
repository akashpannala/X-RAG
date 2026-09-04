"""All routes — /health, /auth/*, /ingest, /query, /eval/ragas. Swagger at /docs."""
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.l01_connectors.loaders import check_supported
from backend.l02_docintel.docling import parse as docling_parse
from backend.l03_cleaning.cleaning import redact
from backend.l04_chunking.splitter import chunk
from backend.l07_storage import qdrant as store
from backend.l07_storage.kuzu_min import record as kuzu_record
from backend.l08_freshness.store import jdump, meta_conn, sha256_file
from backend.l15_security.auth import (
    LoginRequest,
    RegisterRequest,
    User,
    authenticate,
    create_user,
    current_user,
    mint,
)
from backend.l18_generation.graph import answer


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    mode: str | None = None  # quick|deep override; default by role


class QueryResponse(BaseModel):
    answer: str
    citations: list[str] = []
    provider: str = ""
    mode: str = ""
    cache_hit: bool = False


class IngestRequest(BaseModel):
    allowed_groups: list[str] = ["public"]
    enrich: bool = True


class IngestResponse(BaseModel):
    filename: str
    chunks: int
    hash: str


app = FastAPI(title="OFFLINE-RAG Phase 2")
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok", "llm": settings.llm_provider, "qdrant": settings.qdrant_url}


@app.post("/auth/register")
def register(req: RegisterRequest):
    try:
        uid = create_user(req.username, req.password, req.groups)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"id": uid, "username": req.username}


@app.post("/auth/login")
def login(req: LoginRequest):
    try:
        return {"access_token": mint(authenticate(req.username, req.password)), "token_type": "bearer"}
    except ValueError:
        raise HTTPException(401, "bad credentials")


@app.post("/ingest", response_model=IngestResponse)
def ingest(f: UploadFile, allowed_groups: str = "public", enrich: bool = True,
           user: User = Depends(current_user)):
    groups = [g.strip() for g in allowed_groups.split(",") if g.strip()]
    dest = Path(settings.upload_dir) / f.filename
    check_supported(dest)
    dest.write_bytes(f.file.read())
    h = sha256_file(dest)
    text, _ = redact(docling_parse(dest))
    chunks = chunk(text)
    payloads = [{"doc": dest.stem, "chunk_id": i, "text": c, "allowed_groups": groups}
                for i, c in enumerate(chunks)]
    texts = list(chunks)
    if enrich and len(chunks) > 1:
        from backend.l05_enrichment.enrich import (
            hypothetical_questions,
            raptor_parents,
        )

        parents = raptor_parents(chunks)
        base = len(texts)
        texts += parents
        payloads += [{"doc": dest.stem, "chunk_id": base + i, "text": p, "allowed_groups": groups}
                     for i, p in enumerate(parents)]
        for q in hypothetical_questions(dest.stem, chunks[0]):
            texts.append(f"[answers in {dest.stem}] {q}")
            payloads.append({"doc": dest.stem, "chunk_id": 0, "text": q, "allowed_groups": groups})
    store.add_docs(texts, payloads)
    try:
        from backend.l05_enrichment.enrich import extract_entities

        kuzu_record(dest.stem, len(chunks))
        for ent, label in extract_entities(text):
            kuzu_record(f"{label}:{ent}", 0)
    except Exception:
        pass
    con = meta_conn(settings.sqlite_path)
    con.execute("INSERT OR REPLACE INTO documents(filename, allowed_groups_json, hash) VALUES (?,?,?)",
                (f.filename, jdump(groups), h))
    con.commit()
    con.close()
    return IngestResponse(filename=f.filename, chunks=len(texts), hash=h[:12])


def _judge_and_score(conv_id: int, query: str, ans: str, cites: list[str]):
    from backend.l21_eval.eval import judge_score, record_score

    record_score(conv_id, judge_score(query, ans, cites))


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, bg: BackgroundTasks, user: User = Depends(current_user)):
    from backend.l21_eval.eval import log_conversation

    text, cites, contexts, mode, hit = answer(req.query, req.top_k, user.groups, req.mode)
    cid = log_conversation(user.id, req.query, text, mode, contexts)
    bg.add_task(_judge_and_score, cid, req.query, text, cites)
    return QueryResponse(answer=text, citations=cites, provider=settings.llm_provider,
                         mode=mode, cache_hit=hit)


@app.post("/eval/ragas")
def eval_ragas(limit: int = 20, user: User = Depends(current_user)):
    from backend.l21_eval.eval import ragas_offline

    return ragas_offline(limit)
