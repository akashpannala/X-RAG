"""L22: per-query telemetry table + Prometheus metrics.

Every /query writes one row (node timings, hit counts, stage used) so you can
slice quality by mode/user/week. /metrics serves Prometheus text for a scraper
(or dashboard). Metrics are additive — never imported eagerly by graph.py.
"""
import time

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client.registry import REGISTRY

from backend.config import settings
from backend.l08_freshness.store import meta_conn

QUERY_SECONDS = Histogram(
    "rag_query_seconds", "Wall time per query", ["mode"],
    buckets=(0.5, 1, 2, 4, 8, 16, 32, 64))
CACHE_HITS = Counter("rag_cache_hits_total", "Answer-cache hits")
RETRIEVAL_MISSES = Counter("rag_retrieval_misses_total",
                           "Queries that produced no retrieval hits", ["mode"])
WORKER_JOBS = Counter("rag_worker_jobs_total", "Judge jobs processed by L22 worker")
CACHE_ROWS = Gauge("rag_cache_rows", "Rows in answer_cache")


def observe_cache(n: int) -> None:
    try:
        CACHE_ROWS.set(n)
    except Exception:
        pass


def _inc_metric(m, *args) -> None:
    try:
        m(*args).inc()
    except Exception:
        pass


def _observe_hist(h, *args) -> None:
    try:
        h(*args).observe
    except Exception:
        pass


def record(query: str, user_id: int, mode: str, cache_hit: bool, latency_ms: float,
           n_queries: int, n_hits: int, rerank_stage: str, supported_ratio: float,
           provider: str) -> None:
    _inc_metric(CACHE_HITS) if cache_hit else None
    if not cache_hit:
        try:
            QUERY_SECONDS.labels(mode=mode).observe(latency_ms / 1000.0)
        except Exception:
            pass
        if n_hits == 0:
            _inc_metric(RETRIEVAL_MISSES, mode)
    try:
        con = meta_conn(settings.sqlite_path)
        con.execute(
            "INSERT INTO query_telemetry(user_id, mode, cache_hit, latency_ms, n_queries,"
            " n_hits, rerank_stage, supported_ratio, provider) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, mode, int(cache_hit), latency_ms, n_queries, n_hits,
             rerank_stage, supported_ratio, provider))
        con.commit()
    except Exception:
        pass
    finally:
        try:
            con.close()
        except Exception:
            pass


def dump() -> str:
    from io import StringIO

    buf = StringIO()
    REGISTRY.write_to_string(buf)
    return buf.getvalue()


def cache_rows() -> int:
    try:
        con = meta_conn(settings.sqlite_path)
        n = con.execute("SELECT COUNT(*) FROM answer_cache").fetchone()[0]
        con.close()
        return int(n)
    except Exception:
        return 0