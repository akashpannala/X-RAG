"""All routes — /health, /auth/*, /ingest, /query. Swagger at /docs."""
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import settings
from backend.l01_connectors.loaders import check_supported, is_image
from backend.l02_docintel.docling import parse as docling_parse
from backend.l03_cleaning.cleaning import redact
from backend import l07_storage as store
from backend.l07_storage.kuzu_min import record as kuzu_record
from backend.l08_freshness.store import jdump, jload, meta_conn, sha256_file
from backend.l19_cache.cache import clear as clear_cache
from backend.l14_security.auth import (
    LoginRequest,
    RegisterRequest,
    User,
    authenticate,
    create_user,
    current_user,
    mint,
    _ph_n,
)
from backend.l17_generation.graph import answer

log = logging.getLogger("xrag.ingest")


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
    verification: dict = {}


class IngestRequest(BaseModel):
    allowed_groups: list[str] = ["public"]
    enrich: bool = True


class IngestResponse(BaseModel):
    filename: str
    chunks: int
    hash: str


app = FastAPI(title="X-RAG")
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    vs = "pgvector" if "pgvector" in store.search.__module__ else "qdrant"
    return {"status": "ok", "llm": settings.llm_provider, "vector_store": vs,
            "qdrant": settings.vector_base_url, "db": "postgres" if settings.db_url else "sqlite"}


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
    from backend.config import settings
    groups = [g.strip() for g in allowed_groups.split(",") if g.strip()]
    dest = Path(settings.upload_dir) / f.filename
    check_supported(dest)
    dest.write_bytes(f.file.read())
    h = sha256_file(dest)
    if is_image(dest):
        from backend.l02_docintel.ocr import ocr_image

        raw = ocr_image(dest)
    else:
        try:
            raw = docling_parse(dest)
        except Exception:
            from backend.l02_docintel.ocr import ocr_image

            raw = ocr_image(dest)  # scanned PDF fallback
    text, _ = redact(raw)
    from backend.l04_chunking.splitter import chunk as basic_chunk

    if enrich:
        try:
            from backend.l04_chunking.full import full_chunk

            chunks, late_vecs = full_chunk(text, dest.stem)
        except Exception as e:  # enrichment is best-effort — never fail ingest
            log.warning("full_chunk failed (%s) — falling back to basic chunking", e)
            chunks = basic_chunk(text)
            late_vecs = None
    else:
        chunks = basic_chunk(text)
        late_vecs = None
    payloads = [{"doc": dest.stem, "chunk_id": i, "text": c, "allowed_groups": groups}
                for i, c in enumerate(chunks)]
    texts = list(chunks)
    if enrich and len(chunks) > 1:
        try:
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
        except Exception as e:  # best-effort: keep chunks already appended
            log.warning("raptor/hypothetical enrichment skipped: %s", e)
    # Build vectors: use late_chunk pooled vectors for late_chunks texts, compute rest
    vectors = None
    if late_vecs:
        from backend.l06_embedding.bge import get_embeddings
        emb = get_embeddings(settings.embed_model)
        # late_vecs aligns with late_chunks texts which are first in chunks
        # But chunks is deduped, so need to match by text
        late_texts_set = set()
        # Re-get late_chunks texts to know which ones have vectors
        from backend.l04_chunking.full import late_chunks
        late_texts, _ = late_chunks(text)
        late_texts_set = set(late_texts)
        vectors = []
        for t in texts:
            if t in late_texts_set:
                idx = late_texts.index(t)
                if idx < len(late_vecs):
                    vectors.append(late_vecs[idx].tolist() if hasattr(late_vecs[idx], 'tolist') else late_vecs[idx])
                else:
                    vectors.append(None)
            else:
                vectors.append(None)
        # Replace None with computed embeddings
        to_embed = [t[:2000] for t, v in zip(texts, vectors) if v is None]
        if to_embed:
            computed = emb.embed_documents(to_embed)
            it = iter(computed)
            vectors = [v if v is not None else next(it) for v in vectors]
    # replace-on-reingest: old vectors keep their old allowed_groups — drop them first
    try:
        store.delete_doc(dest.stem)
    except Exception as e:
        log.warning("store.delete_doc(%s) failed: %s", dest.stem, e)
    try:
        from backend.L06_sparse.bm25 import delete as bm25_delete

        bm25_delete(dest.stem)
    except Exception as e:
        log.warning("bm25 delete(%s) failed: %s", dest.stem, e)
    try:
        from backend.L06_sparse.splade import delete as splade_delete

        splade_delete(dest.stem)
    except Exception as e:
        log.warning("splade delete(%s) failed: %s", dest.stem, e)
    store.add_docs(texts, payloads, vectors)
    try:
        from backend.L06_sparse.bm25 import add as bm25_add

        bm25_add(texts, payloads)
    except Exception:
        pass
    try:
        from backend.L06_sparse.splade import add as splade_add

        splade_add(texts, payloads)
    except Exception:
        pass
    try:
        from backend.l05_enrichment.enrich import extract_entities
        from backend.l07_storage.kuzu_min import record_ent

        kuzu_record(dest.stem, len(chunks))
        for ent, label in extract_entities(text):
            record_ent(dest.stem, ent, label)
    except Exception:
        pass
    con = meta_conn(settings.db_path)
    ph = _ph_n(con, 4)
    con.execute(f"""
        INSERT INTO documents(filename, allowed_groups_json, hash, chunks) VALUES ({ph})
        ON CONFLICT (filename) DO UPDATE SET
            allowed_groups_json = EXCLUDED.allowed_groups_json,
            hash = EXCLUDED.hash,
            chunks = EXCLUDED.chunks
        """,
                (f.filename, jdump(groups), h, len(texts)))
    con.commit()
    con.close()
    clear_cache()  # vectors changed — cached answers may cite stale permissions
    return IngestResponse(filename=f.filename, chunks=len(texts), hash=h[:12])


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, user: User = Depends(current_user)):
    try:
        text, cites, contexts, mode, hit, verif = answer(
            req.query, req.top_k, user.groups, req.mode, user.id)
    except Exception as e:
        log.exception("query failed")
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}") from e
    return QueryResponse(answer=text, citations=cites, provider=settings.llm_provider,
                         mode=mode, cache_hit=hit, verification=verif)


@app.get("/documents")
def list_documents(user: User = Depends(current_user)):
    """Docs visible to the caller's groups — same ACL as retrieval (pre-search filter)."""
    con = meta_conn(settings.db_path)
    try:
        rows = con.execute(
            "SELECT filename, allowed_groups_json, hash, chunks FROM documents ORDER BY id DESC"
        ).fetchall()
    finally:
        con.close()
    mine = set(user.groups)
    out = []
    for filename, groups_json, h, chunks in rows:
        groups = jload(groups_json)
        if not mine & set(groups):
            continue
        try:
            size = (Path(settings.upload_dir) / filename).stat().st_size
        except OSError:
            size = None
        out.append({"filename": filename, "chunks": int(chunks or 0),
                    "hash": (h or "")[:12], "allowed_groups": groups, "size_bytes": size})
    return out


@app.delete("/documents/{filename}")
def delete_document(filename: str, user: User = Depends(current_user)):
    """Delete a document everywhere: vectors, BM25, SPLADE, metadata row, source file, answer cache.
    ACL: caller's groups must intersect the doc's groups (same as listing/retrieval)."""
    if Path(filename).name != filename:
        raise HTTPException(400, "invalid filename")
    con = meta_conn(settings.db_path)
    try:
        ph = _ph_n(con, 1)
        rows = con.execute(
            f"SELECT allowed_groups_json FROM documents WHERE filename={ph}", (filename,)
        ).fetchall()
        if not rows or not (set(user.groups) & set(jload(rows[0][0]))):
            raise HTTPException(404, "document not found")
        con.execute(f"DELETE FROM documents WHERE filename={ph}", (filename,))
        con.commit()
    finally:
        con.close()
    stem = Path(filename).stem
    try:
        store.delete_doc(stem)
    except Exception as e:
        log.warning("store.delete_doc(%s) failed: %s", stem, e)
    try:
        from backend.L06_sparse.bm25 import delete as bm25_delete
        bm25_delete(stem)
    except Exception as e:
        log.warning("bm25.delete(%s) failed: %s", stem, e)
    try:
        from backend.L06_sparse.splade import delete as splade_delete
        splade_delete(stem)
    except Exception as e:
        log.warning("splade.delete(%s) failed: %s", stem, e)
    try:
        (Path(settings.upload_dir) / filename).unlink(missing_ok=True)
    except OSError as e:
        log.warning("unlink(%s) failed: %s", filename, e)
    clear_cache()  # cached answers may cite this doc's chunks
    return {"deleted": filename}


@app.get("/conversations")
def list_conversations(user: User = Depends(current_user)):
    """Caller's own chat history, newest first."""
    con = meta_conn(settings.db_path)
    try:
        ph = _ph_n(con, 1)
        rows = con.execute(
            f"SELECT id, query, answer, mode, citations_json, created_at FROM conversations "
            f"WHERE user_id={ph} ORDER BY id DESC LIMIT 100",
            (user.id,),
        ).fetchall()
    finally:
        con.close()
    return [{"id": r[0], "query": r[1], "answer": r[2], "mode": r[3],
             "citations": jload(r[4]), "created_at": str(r[5])} for r in rows]


@app.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, user: User = Depends(current_user)):
    """Delete one of the caller's own conversations (404 if not theirs / missing)."""
    con = meta_conn(settings.db_path)
    try:
        cur = con.execute(
            f"DELETE FROM conversations WHERE id={_ph_n(con, 1)} AND user_id={_ph_n(con, 1)}",
            (conv_id, user.id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "conversation not found")
        con.commit()
    finally:
        con.close()
    return {"deleted": conv_id}


# Serve frontend static files (chat.html, index.html, assets) — same-origin API calls
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

