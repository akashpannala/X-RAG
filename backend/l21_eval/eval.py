"""L21: background faithfulness judge (local LLM) + offline RAGAS suite."""
import json
import re

from backend.config import settings
from backend.l08_freshness.store import meta_conn


def judge_score(query: str, answer: str, cites: list[str]) -> float:
    """0..1 faithfulness score. Runs in BackgroundTasks — never blocks queries."""
    from backend.l18_generation.llm import get_llm

    llm = get_llm()
    msg = llm.invoke(
        "Rate how well the ANSWER is supported by the cited context. "
        "Reply with ONLY a number 0.0-1.0.\n"
        f"Question: {query}\nAnswer: {answer}\nCitations: {', '.join(cites)}")
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    m = re.search(r"0?\.\d+|[01](?:\.0)?", text)
    try:
        return max(0.0, min(1.0, float(m.group(0))))
    except Exception:
        return -1.0


def record_score(conv_id: int, score: float) -> None:
    con = meta_conn(settings.sqlite_path)
    try:
        con.execute("UPDATE conversations SET score=? WHERE id=?", (score, conv_id))
        con.commit()
    finally:
        con.close()


def log_conversation(user_id: int, query: str, answer: str, mode: str, contexts: list[str]) -> int:
    con = meta_conn(settings.sqlite_path)
    try:
        cur = con.execute(
            "INSERT INTO conversations(user_id, query, answer, mode, contexts_json)"
            " VALUES (?,?,?,?,?)",
            (user_id, query, answer, mode, json.dumps(contexts[:10])),
        )
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def ragas_offline(limit: int = 20) -> dict:
    """Offline eval: RAGAS suite when importable, else judge-score aggregates.

    ragas 0.4.x is pinned against the sunset langchain-community API and breaks
    on import — the aggregate path reports the same faithfulness signal from
    stored background-judge scores until the lib story stabilizes.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, faithfulness
        from datasets import Dataset
    except Exception as e:
        return _judge_aggregates(limit, fallback=f"ragas lib unavailable: {e}")
    con = meta_conn(settings.sqlite_path)
    try:
        rows = con.execute(
            "SELECT query, answer, contexts_json FROM conversations"
            " WHERE contexts_json IS NOT NULL ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return {"status": "no scored conversations yet"}
    ds = Dataset.from_dict({
        "question": [r[0] for r in rows],
        "answer": [r[1] for r in rows],
        "contexts": [json.loads(r[2]) for r in rows],
    })
    try:
        result = evaluate(ds, metrics=[faithfulness, answer_relevancy])
        return {k: float(v) for k, v in result.scores[0].items()} if hasattr(result, "scores") else dict(result)
    except Exception as e:
        return _judge_aggregates(limit, fallback=f"ragas evaluate failed: {e}")


def _judge_aggregates(limit: int, fallback: str) -> dict:
    import statistics

    con = meta_conn(settings.sqlite_path)
    try:
        rows = con.execute(
            "SELECT mode, score FROM conversations WHERE score IS NOT NULL AND score >= 0"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return {"status": "no judged conversations yet", "fallback": fallback}
    by_mode: dict[str, list[float]] = {}
    for mode, score in rows:
        by_mode.setdefault(mode or "?", []).append(score)
    return {"evaluator": "background-judge aggregates", "fallback": fallback,
            "n": len(rows),
            "mean_faithfulness": round(statistics.fmean(s for _, s in rows), 3),
            "by_mode": {m: round(statistics.fmean(v), 3) for m, v in by_mode.items()}}
