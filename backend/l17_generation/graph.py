"""RAG graph — guard → transform → retrieve (ACL) → rerank → assemble → generate.

Quick: raw query, dense-30 → MiniLM → top-5. Deep: multi-query + HyDE +
step-back + decomposition → dense-50 each → RRF fuse → MiniLM → top-10.
Sync invoke, cache wraps outside.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend import l07_storage as store
from backend.l08_freshness.store import meta_conn, jdump
from backend.config import settings
from backend.l09_toggle.mode import resolve
from backend.l11_transforms.transforms import decompose, hyde, multi_query, rrf_fuse, step_back
from backend.l12_agents.agents import graph_agent, image_agent, sql_agent, vector_agent
from backend.l13_rerank.cascade import cascade
from backend.l14_security.acl import groups_filter
from backend.l14_security.injection import confident, screen
from backend.l16_assembly.prompt import assemble
from backend.l17_generation.llm import get_llm
from backend.l19_cache import cache as qcache


class RAGState(TypedDict, total=False):
    query: str
    top_k: int
    groups: list[str]
    mode: str
    mode_override: str | None
    user_id: int | None
    queries: list[str]
    hits: list[dict]
    prompt: str
    cites: list[str]
    contexts: list[str]
    answer: str
    blocked: str | None
    verification: dict


def guard(s: RAGState) -> dict:
    reason = screen(s["query"])
    if reason:
        return {"blocked": reason}
    return {"mode": resolve(s.get("groups", []), s.get("mode_override"))}


def transform(s: RAGState) -> dict:
    """Deep only: memory rewrite → multi-query + HyDE + step-back + decomposition."""
    if s.get("blocked") or s["mode"] == "quick":
        return {"queries": [s["query"]]}
    from backend.l10_memory.memory import rewrite_with_memory

    q = rewrite_with_memory(s["query"], s.get("user_id"))
    queries = [q, *multi_query(q), hyde(q), step_back(q)]
    for step in decompose(q):
        if step != q and step not in queries:
            queries.append(step)
    return {"queries": queries}


def retrieve(s: RAGState) -> dict:
    """Quick: single dense pass. Deep: per-query dense + vector/graph/SQL agents, RRF-fused."""
    if s.get("blocked"):
        return {"hits": []}
    n = 30 if s["mode"] == "quick" else 50
    groups = s.get("groups", [])
    if s["mode"] == "quick":
        return {"hits": store.search(s["query"], n, groups_filter(groups))}
    lists = [store.search(q, n, groups_filter(groups)) for q in s.get("queries", [s["query"]])]
    lists.append(vector_agent(s["query"], groups, n))
    lists.append(graph_agent(s["query"], groups, 10))
    lists.append(sql_agent(s["query"], groups, 5))
    lists.append(image_agent(s["query"], groups, 5))
    try:
        from backend.L06_sparse.bm25 import search as bm25_search

        lists.append(bm25_search(s["query"], 20, groups))
    except Exception:
        pass
    try:
        from backend.L06_sparse.splade import search as splade_search

        lists.append(splade_search(s["query"], 20, groups))
    except Exception:
        pass
    return {"hits": rrf_fuse([l for l in lists if l])[:n]}


def rerank_step(s: RAGState) -> dict:
    if s.get("blocked"):
        return {}
    hits = cascade(s["query"], s.get("hits", []), s["mode"])
    if not confident(hits):
        return {"hits": [], "blocked": "low retrieval confidence — insufficient context"}
    return {"hits": hits}


def assemble_step(s: RAGState) -> dict:
    if s.get("blocked"):
        return {"prompt": "", "cites": [], "contexts": []}
    hits = s.get("hits", [])
    cites = []
    for h in hits:  # full provenance even when contexts get compressed
        tag = f"[{h.get('doc', '?')}#{h.get('chunk_id', 0)}]"
        if tag not in cites:
            cites.append(tag)
    if s.get("mode") == "deep" and hits:
        from backend.l15_compression.compress import compress_hits

        hits = compress_hits(s["query"], hits, budget_chars=5500)
    prompt, _ = assemble(s["query"], hits)
    return {"prompt": prompt, "cites": cites,
            "contexts": [h["text"] for h in hits]}


def generate(s: RAGState) -> dict:
    """Self-RAG-lite (deep): draft → critique uncited claims → single revision."""
    if s.get("blocked"):
        return {"answer": f"I can't answer that: {s['blocked']}."}
    llm = get_llm()
    msg = llm.invoke(s["prompt"])
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    if s.get("mode") == "deep" and s.get("cites"):
        crit = llm.invoke(
            "Review this answer against its required citation format [doc#chunk]. "
            "If any factual sentence lacks a citation, reply REVISE: followed by "
            "the corrected answer; else reply OK.\nAnswer:\n" + text)
        ctext = crit.content if isinstance(crit.content, str) else str(crit.content)
        if ctext.strip().upper().startswith("REVISE:"):
            text = ctext.strip()[len("REVISE:"):].strip() or text
    return {"answer": text}


def verify_step(s: RAGState) -> dict:
    """Deep only: HHEM sentence labels over the final answer."""
    if s.get("blocked") or s.get("mode") != "deep":
        return {"verification": {"labels": [], "supported_ratio": -1.0}}
    from backend.l18_verification.verify import verify

    return {"verification": verify(s.get("answer", ""), s.get("contexts", []))}


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        g = StateGraph(RAGState)
        g.add_node("guard", guard)
        g.add_node("transform", transform)
        g.add_node("retrieve", retrieve)
        g.add_node("rerank", rerank_step)
        g.add_node("assemble", assemble_step)
        g.add_node("generate", generate)
        g.add_node("verify", verify_step)
        for a, b in [(START, "guard"), ("guard", "transform"), ("transform", "retrieve"),
                     ("retrieve", "rerank"), ("rerank", "assemble"),
                     ("assemble", "generate"), ("generate", "verify"), ("verify", END)]:
            g.add_edge(a, b)
        _graph = g.compile()
    return _graph


def answer(query: str, top_k: int = 5, groups: list[str] | None = None,
           mode_override: str | None = None, user_id: int | None = None,
           _retried: bool = False) -> tuple[str, list[str], list[str], str, bool, dict]:
    """Returns (answer, cites, contexts, mode, cache_hit, verification).

    CRAG loop: a confidence refusal in deep mode retries once with a
    step-back (broader) query before giving up. ACL is never relaxed.
    """
    groups = groups or []
    mode = resolve(groups, mode_override)
    hit = qcache.lookup(query, mode, groups)
    if hit is not None:
        return hit[0], hit[1], [], mode, True, {"labels": [], "supported_ratio": -1.0}
    state = {"query": query, "top_k": top_k, "groups": groups,
             "mode_override": mode_override, "user_id": user_id}
    try:
        out = get_graph().invoke(state)
    except Exception:
        out = get_graph().invoke(state)
    if (out.get("blocked", "").startswith("low retrieval confidence")
            and mode == "deep" and not _retried):
        retry_q = step_back(query)
        if retry_q != query:
            return answer(retry_q, top_k, groups, mode_override, user_id, True)
    text, cites = out.get("answer", ""), out.get("cites", [])
    if not out.get("blocked"):
        qcache.store(query, out.get("mode", mode), groups, text, cites)
        if user_id:
            try:
                con = meta_conn(settings.db_path)
                con.execute(
                    "INSERT INTO conversations(user_id, query, answer, mode, score, contexts_json) VALUES (?,?,?,?,?,?)",
                    (user_id, query, text, out.get("mode", mode), 0.0, jdump(out.get("contexts", []))))
                con.commit()
                con.close()
            except Exception:
                pass
    return (text, cites, out.get("contexts", []), out.get("mode", mode), False,
            out.get("verification", {"labels": [], "supported_ratio": -1.0}))
