"""L22 worker: consumes the eval stream in a consumer group.

   .venv/bin/python -m backend.l22_ragops.worker        # long-running
   .venv/bin/python -m backend.l22_ragops.worker --once # drain + exit (CI)
Runs the background faithfulness judge out-of-process so a crash, restart
or long Groq call never blocks/wins the API process.
"""
import sys
import time

from backend.l22_ragops import queue


def run_once() -> int:
    queue._ensure_group()
    r = queue._client()
    kind = "--once" in sys.argv
    processed = 0

    def execute(mid: str, fields: dict) -> None:
        nonlocal processed
        row = queue._row(mid, fields)
        try:
            status, score = queue.process_job(row)
            queue.ack(mid)
            processed += 1
            print(f"judged {row['conv_id']}: {status} {score:.2f}", flush=True)
        except Exception as e:
            print(f"dead-letter {row['conv_id']}: {e}", flush=True)
            queue.dead_letter(row, e)
            queue.ack(mid)

    # 1) Reclaim this worker's own leftover pending (crash recovery), then any
    #    other consumer's stale pending that passed the idle threshold.
    if kind:
        pending = r.xpending_range(
            queue.STREAM, queue.GROUP, min="-", max="+", count=100) or []
        for p in pending:
            claimed = r.xclaim(queue.STREAM, queue.GROUP, "worker", 0, [p["message_id"]])
            for cmid, cfields in claimed:
                execute(cmid, cfields)
        queue.reclaim()
    while True:
        try:
            resp = r.xreadgroup(queue.GROUP, "worker",
                                {queue.STREAM: ">"}, count=10, block=2000)
        except Exception:
            return processed  # redis down — exit cleanly
        for _, rows in resp or []:
            for mid, fields in rows:
                execute(mid, fields)
        if kind and not (resp or []):
            return processed
        if kind:
            time.sleep(0.05)
        else:
            time.sleep(0.1)


if __name__ == "__main__":
    processed = run_once()
    print(f"worker drained: {processed} jobs", flush=True)