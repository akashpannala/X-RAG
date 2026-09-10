"""L22 RAGOps: durable async eval via Redis Streams.

Producer (api /query) XADDs a job; the worker consumes it in a consumer
group with XAUTOCLAIM crash-recovery and a DLQ. If Redis is unreachable we
fall back to in-process BackgroundTasks so queries never block or lose the
judge on outage — the stdlib path that Redis replaces.
"""
import json
import time

from backend.config import settings

STREAM = "rag:eval"
GROUP = "workers"
DLQ = "rag:eval:dlq"


def _client():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)


def enqueue(conv_id: int, query: str, answer: str, cites: list[str]) -> bool:
    """XADD one judge job. Returns True if queued, False on any failure."""
    try:
        r = _client()
        r.xadd(STREAM, {"conv_id": conv_id, "query": query,
                        "answer": answer, "cites": json.dumps(cites)},
               maxlen=1000, approximate=True)
        r.close()
        return True
    except Exception:
        return False


def _ensure_group() -> None:
    """Create the consumer group (idempotent, MKSTREAM)."""
    r = _client()
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception:
        pass  # BUSYGROUP or redis down
    finally:
        r.close()


def pending_read(count: int = 50) -> list[dict]:
    """Read the stream without a consumer group — used for tests/backfill."""
    r = _client()
    try:
        raw = r.xrange(STREAM, count=count)
    finally:
        r.close()
    return [_row(mid, fields) for mid, fields in raw]


def _row(mid: str, fields: dict) -> dict:
    return {"id": mid, "conv_id": int(fields["conv_id"]),
            "query": fields["query"], "answer": fields["answer"],
            "cites": json.loads(fields["cites"])}


def process_job(row: dict) -> tuple[str, float]:
    """Run the judge for one row and persist the score. Returns (status, score)."""
    from backend.l21_eval.eval import judge_score, record_score

    score = judge_score(row["query"], row["answer"], row["cites"])
    record_score(row["conv_id"], score)
    return ("ok", score)


def ack(mid: str) -> None:
    r = _client()
    try:
        r.xack(STREAM, GROUP, mid)
    except Exception:
        pass
    finally:
        r.close()


def dead_letter(row: dict, error: str) -> None:
    r = _client()
    try:
        r.xadd(DLQ, {"job_id": row["id"], "error": str(error)[:500]})
    except Exception:
        pass
    finally:
        r.close()


def reclaim(max_ms: int = 60000) -> int:
    """XAUTOCLAIM jobs stuck in pending (worker died mid-process). Returns count."""
    r = _client()
    _ensure_group()
    total = 0
    try:
        claims, _ = r.xautoclaim(STREAM, GROUP, "reclaimer", min_idle_time=max_ms,
                                 count=50, start_id="0-0")
        for mid, fields in claims or []:
            row = _row(mid, fields)
            try:
                process_job(row)
                ack(mid)
                total += 1
            except Exception as e:
                dead_letter(row, e)
                r.xack(STREAM, GROUP, mid)
    except Exception:
        pass
    finally:
        r.close()
    return total