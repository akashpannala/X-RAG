"""RAG graph — guard → retrieve (ACL) → rerank → assemble → generate.

Quick: dense-30 → MiniLM → top-5. Deep: dense-50 → MiniLM → top-10
(Phase 3 adds cascade + verification). Sync invoke, cache wraps outside.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.l07_storage import qdrant as store
from backend.l09_toggle.mode import resolve
from backend.l14_rerank.minilm import rerank
from backend.l15_security.acl import groups_filter
from backend.l15_security.injection import confident, screen
from backend.l17_assembly.prompt import assemble
from backend.l18_generation.llm import get_llm
from backend.l20_cache import cache as qcache


class RAGState(TypedDict, total=False):
    query: str
    top_k: int
    groups: list[str]
    mode: str
    mode_override: str | None
    hits: list[dict]
    prompt: str
    cites: list[str]
    contexts: list[str]
    answer: str
    blocked: str | None


def guard(s: RAGState) -> dict:
    reason = screen(s["query"])
    if reason:
        return {"blocked": reason}
    return {"mode": resolve(s.get("groups", []), s.get("mode_override"))}


def retrieve(s: RAGState) -> dict:
    if s.get("blocked"):
        return {"hits": []}
    n = 30 if s["mode"] == "quick" else 50
    return {"hits": store.search(s["query"], n, groups_filter(s.get("groups", [])))}


def rerank_step(s: RAGState) -> dict:
    if s.get("blocked"):
        return {}
    n = 5 if s["mode"] == "quick" else 10
    hits = rerank(s["query"], s.get("hits", []), n)
    if not confident(hits):
        return {"hits": [], "blocked": "low retrieval confidence — insufficient context"}
    return {"hits": hits}


def assemble_step(s: RAGState) -> dict:
    if s.get("blocked"):
        return {"prompt": "", "cites": [], "contexts": []}
    prompt, cites = assemble(s["query"], s.get("hits", []))
    return {"prompt": prompt, "cites": cites,
            "contexts": [h["text"] for h in s.get("hits", [])]}


def generate(s: RAGState) -> dict:
    if s.get("blocked"):
        return {"answer": f"I can't answer that: {s['blocked']}."}
    msg = get_llm().invoke(s["prompt"])
    return {"answer": msg.content if isinstance(msg.content, str) else str(msg.content)}


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        g = StateGraph(RAGState)
        g.add_node("guard", guard)
        g.add_node("retrieve", retrieve)
        g.add_node("rerank", rerank_step)
        g.add_node("assemble", assemble_step)
        g.add_node("generate", generate)
        for a, b in [(START, "guard"), ("guard", "retrieve"), ("retrieve", "rerank"),
                     ("rerank", "assemble"), ("assemble", "generate"), ("generate", END)]:
            g.add_edge(a, b)
        _graph = g.compile()
    return _graph


def answer(query: str, top_k: int = 5, groups: list[str] | None = None,
           mode_override: str | None = None) -> tuple[str, list[str], list[str], str, bool]:
    """Returns (answer, cites, contexts, mode, cache_hit)."""
    groups = groups or []
    mode = resolve(groups, mode_override)
    hit = qcache.lookup(query, mode, groups)
    if hit is not None:
        return hit[0], hit[1], [], mode, True
    out = get_graph().invoke(
        {"query": query, "top_k": top_k, "groups": groups, "mode_override": mode_override})
    text, cites = out.get("answer", ""), out.get("cites", [])
    if not out.get("blocked"):
        qcache.store(query, out.get("mode", mode), groups, text, cites)
    return text, cites, out.get("contexts", []), out.get("mode", mode), False
