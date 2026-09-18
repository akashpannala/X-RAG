"""RAG graph — guard → transform → retrieve (ACL) → rerank → assemble → generate.

Quick: raw query, dense-30 → MiniLM → top-5. Deep: multi-query + HyDE +
step-back + decomposition → dense-50 each → RRF fuse → MiniLM → top-10.
Sync invoke, cache wraps outside. Each node appends ms into telemetry.
"""
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.l07_storage import qdrant as store
from backend.l08_freshness.store import meta_conn
from backend.l09_toggle.mode import resolve
from backend.l11_transforms.transforms import decompose, hyde, multi_query, rrf_fuse, step_back
from backend.l13_agents.agents import graph_agent, image_agent, sql_agent, vector_agent
from backend.l14_rerank.cascade import cascade
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
    user_id: int | None
    queries: list[str]
    hits: list[dict]
    prompt: str
    cites: list[str]
    contexts: list[str]
    answer: str
    blocked: str | None
    verification: dict
    telemetry: dict


def guard(s: RAGState) -> dict:
    t0 = time.monotonic()
    reason = screen(s["query"])
    if reason:
        return {"blocked": reason,
                "telemetry": {"guard_ms": (time.monotonic() - t0) * 1000}}
    telemetry = {"guard_ms": (time.monotonic() - t0) * 1000,
                 "n_queries": 1, "n_hits": 0, "rerank_stage": ""}
    return {"mode": resolve(s.get("groups", []), s.get("mode_override")),
            "telemetry": telemetry}


def transform(s: RAGState) -> dict:
    """Deep only: memory rewrite → multi-query + HyDE + step-back + decomposition."""
    t0 = time.monotonic()
    if s.get("blocked") or s["mode"] == "quick":
        return {"queries": [s["query"]],
                "telemetry": {**s.get("telemetry", {}),
                              "n_queries": 1, "transform_ms": (time.monotonic() - t0) * 1000}}
    from backend.l10_memory.memory import rewrite_with_memory

    q = rewrite_with_memory(s["query"], s.get("user_id"))
    queries = [q, *multi_query(q), hyde(q), step_back(q)]
    for step in decompose(q):
        if step != q and step not in queries:
            queries.append(step)
    return {"queries": queries,
            "telemetry": {**s.get("telemetry", {}),
                          "n_queries": len(queries),
                          "transform_ms": (time.monotonic() - t0) * 1000}}


def retrieve(s: RAGState) -> dict:
    """Quick: single dense pass. Deep: per-query dense + vector/graph/SQL agents, RRF-fused."""
    t0 = time.monotonic()
    if s.get("blocked"):
        return {"hits": [], "telemetry": {**s.get("telemetry", {}), "n_hits": 0}}
    n = 30 if s["mode"] == "quick" else 50
    groups = s.get("groups", [])
    if s["mode"] == "quick":
        hits = store.search(s["query"], n, groups_filter(groups))
        return {"hits": hits,
                "telemetry": {**s.get("telemetry", {}), "n_hits": len(hits),
                              "retrieve_ms": (time.monotonic() - t0) * 1000}}
    lists = [store.search(q, n, groups_filter(groups)) for q in s.get("queries", [s["query"]])]
    lists.append(vector_agent(s["query"], groups, n))
    lists.append(graph_agent(s["query"], groups, 10))
    lists.append(sql_agent(s["query"], groups, 5))
    lists.append(image_agent(s["query"], groups, 5))
    try:
        from backend.l06_sparse.bm25 import search as bm25_search

        lists.append(bm25_search(s["query"], 20))
    except Exception:
        pass
    try:
        from backend.l06_sparse.splade import search as splade_search

        lists.append(splade_search(s["query"], 20))
    except Exception:
        pass
    fused = rrf_fuse([l for l in lists if l])[:n]
    return {"hits": fused,
            "telemetry": {**s.get("telemetry", {}), "n_hits": len(fused),
                          "retrieve_ms": (time.monotonic() - t0) * 1000}}


def rerank_step(s: RAGState) -> dict:
    t0 = time.monotonic()
    if s.get("blocked"):
        return {"telemetry": {**s.get("telemetry", {}), "rerank_stage": "skipped",
                              "rerank_ms": (time.monotonic() - t0) * 1000}}
    hits = cascade(s["query"], s.get("hits", []), s["mode"])
    if not confident(hits):
        return {"hits": [], "blocked": "low retrieval confidence — insufficient context",
                "telemetry": {**s.get("telemetry", {}), "rerank_stage": "rejected",
                              "rerank_ms": (time.monotonic() - t0) * 1000}}
    stage = "minilm" if (s["mode"] == "quick" or len(s.get("hits", [])) <= 30) else "bge+rankgpt+mmr"
    return {"hits": hits,
            "telemetry": {**s.get("telemetry", {}), "rerank_stage": stage,
                          "rerank_ms": (time.monotonic() - t0) * 1000}}


def assemble_step(s: RAGState) -> dict:
    t0 = time.monotonic()
    if s.get("blocked"):
        return {"prompt": "", "cites": [], "contexts": [],
                "telemetry": {**s.get("telemetry", {}),
                              "assemble_ms": (time.monotonic() - t0) * 1000}}
    hits = s.get("hits", [])
    cites = []
    for h in hits:  # full provenance even when contexts get compressed
        tag = f"[{h.get('doc', '?')}#{h.get('chunk_id', 0)}]"
        if tag not in cites:
            cites.append(tag)
    if s.get("mode") == "deep" and hits:
        from backend.l16_compression.compress import compress

        ctx = compress(s["query"], [h["text"] for h in hits], budget_chars=5500)
        hits = [{**hits[0], "text": c} for c in ctx] if ctx else hits
    prompt, _ = assemble(s["query"], hits)
    return {"prompt": prompt, "cites": cites,
            "contexts": [h["text"] for h in hits],
            "telemetry": {**s.get("telemetry", {}),
                          "assemble_ms": (time.monotonic() - t0) * 1000}}


def generate(s: RAGState) -> dict:
    """Self-RAG-lite (deep): draft → critique uncited claims → single revision."""
    t0 = time.monotonic()
    if s.get("blocked"):
        return {"answer": f"I can't answer that: {s['blocked']}.",
                "telemetry": {**s.get("telemetry", {}),
                              "generate_ms": (time.monotonic() - t0) * 1000}}
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
    return {"answer": text,
            "telemetry": {**s.get("telemetry", {}),
                          "generate_ms": (time.monotonic() - t0) * 1000}}


def verify_step(s: RAGState) -> dict:
    """Deep only: HHEM sentence labels over the final answer."""
    t0 = time.monotonic()
    if s.get("blocked") or s.get("mode") != "deep":
        return {"verification": {"labels": [], "supported_ratio": -1.0},
                "telemetry": {**s.get("telemetry", {}),
                              "verify_ms": (time.monotonic() - t0) * 1000}}
    from backend.l19_verification.verify import verify

    v = verify(s.get("answer", ""), s.get("contexts", []))
    return {"verification": v,
            "telemetry": {**s.get("telemetry", {}),
                          "verify_ms": (time.monotonic() - t0) * 1000,
                          "supported_ratio": float(v.get("supported_ratio", -1.0))}}


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
    t_start = time.monotonic()
    hit = qcache.lookup(query, mode, groups)
    if hit is not None:
        _record_telemetry(query, user_id, mode, True, t_start, {}, 0, -1.0)
        return hit[0], hit[1], [], mode, True, {"labels": [], "supported_ratio": -1.0}
    state = {"query": query, "top_k": top_k, "groups": groups,
             "mode_override": mode_override, "user_id": user_id,
             "telemetry": {}}
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
    telemetry = out.get("telemetry", {})
    _record_telemetry(query, user_id, out.get("mode", mode), False, t_start,
                      telemetry, int(telemetry.get("n_hits", 0)),
                      float(out.get("verification", {}).get("supported_ratio", -1.0)))
    if not out.get("blocked"):
        qcache.store(query, out.get("mode", mode), groups, text, cites)
    return (text, cites, out.get("contexts", []), out.get("mode", mode), False,
            out.get("verification", {"labels": [], "supported_ratio": -1.0}))


def _record_telemetry(query: str, user_id: int, mode: str, cache_hit: bool,
                      t_start: float, telemetry: dict, n_hits: int,
                      supported_ratio: float) -> None:
    """Best-effort ops row in query_telemetry. Never raises."""
    try:
        latency_ms = (time.monotonic() - t_start) * 1000
        con = meta_conn(settings.sqlite_path)
        try:
            con.execute(
                "INSERT INTO query_telemetry(user_id, mode, cache_hit, latency_ms, n_queries,"
                " n_hits, rerank_stage, supported_ratio, provider) VALUES (?,?,?,?,?,?,?,?,?)",
                (user_id, mode, int(cache_hit), latency_ms,
                 int(telemetry.get("n_queries", 1)), n_hits,
                 str(telemetry.get("rerank_stage", "")), supported_ratio,
                 settings.llm_provider))
            con.commit()
        finally:
            con.close()
    except Exception:
        pass
