"""L10 MemoRAG-lite: conversation-aware query rewrite (deep mode).

Recent user queries from SQLite become memory context so follow-ups like
"and the second one?" resolve. Full MemoRAG global-memory pre-training is
Phase 4 hardware territory; this is the online half that matters now.
"""
from backend.l08_freshness.store import meta_conn


def recent_queries(user_id: int, n: int = 5) -> list[str]:
    con = meta_conn("data/meta.db")
    try:
        rows = con.execute(
            "SELECT query FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, n),
        ).fetchall()
        return [r[0] for r in reversed(rows)]
    except Exception:
        return []
    finally:
        con.close()


def rewrite_with_memory(query: str, user_id: int | None) -> str:
    """Resolve follow-ups into standalone queries. No-op without history."""
    if not user_id:
        return query
    hist = recent_queries(user_id)
    if not hist:
        return query
    from backend.l17_generation.llm import get_llm

    try:
        msg = get_llm().invoke(
            "Rewrite the LAST question as standalone, using conversation history. "
            "If already standalone, repeat it unchanged. Reply with ONLY the question.\n"
            f"History:\n" + "\n".join(f"- {h}" for h in hist) + f"\nLast: {query}")
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        return text.strip().splitlines()[0] if text.strip() else query
    except Exception:
        return query
