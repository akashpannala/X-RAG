"""RAG graph — linear retrieve → assemble → generate (LangGraph).

Single path today, sync invoke, zero added latency. Phase 3 adds parallel
agent branches + rerank nodes here without touching the API.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.l17_assembly.prompt import assemble
from backend.l18_generation.llm import get_llm
from backend.l07_storage import qdrant as store


class RAGState(TypedDict, total=False):
    query: str
    top_k: int
    hits: list[dict]
    prompt: str
    cites: list[str]
    answer: str


def retrieve(s: RAGState) -> dict:
    return {"hits": store.search(s["query"], s.get("top_k", 5))}


def assemble_step(s: RAGState) -> dict:
    prompt, cites = assemble(s["query"], s.get("hits", []))
    return {"prompt": prompt, "cites": cites}


def generate(s: RAGState) -> dict:
    msg = get_llm().invoke(s["prompt"])
    return {"answer": msg.content if isinstance(msg.content, str) else str(msg.content)}


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        g = StateGraph(RAGState)
        g.add_node("retrieve", retrieve)
        g.add_node("assemble", assemble_step)
        g.add_node("generate", generate)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "assemble")
        g.add_edge("assemble", "generate")
        g.add_edge("generate", END)
        _graph = g.compile()
    return _graph


def answer(query: str, top_k: int = 5) -> tuple[str, list[str]]:
    out = get_graph().invoke({"query": query, "top_k": top_k})
    return out.get("answer", ""), out.get("cites", [])
