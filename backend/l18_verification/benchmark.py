"""Dev-only answer-quality benchmark.

Runs the real pipeline over a bundled question set, scores every answer with
DeepEval (same judge path as eval.py), and writes a headline scorecard plus raw
results into data/. This is not a service and has no HTTP route: run it by hand
when a model, prompt, or corpus change needs a before/after number.

    python -m backend.l18_verification.benchmark \
        --cases backend/l18_verification/benchmark_cases.json \
        --out data/evaluation.md --json-out data/evaluation.json

Latency is the in-process answer() call (retrieval + generation); the answer
cache is cleared first and judge calls are not timed.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.l18_verification.eval import evaluate_case

DEFAULT_CASES = Path(__file__).with_name("benchmark_cases.json")
DEFAULT_OUT = Path("data/evaluation.md")
DEFAULT_JSON_OUT = Path("data/evaluation.json")
DEFAULT_THRESHOLD = 0.6
DEFAULT_GROUPS = "hr,eng,public"

_SHORT = {
    "Contextual Relevancy": "Relevancy",
    "Contextual Recall": "Recall",
    "Faithfulness": "Faithfulness",
}

# Groq rate-limit signals; the shared org TPM bucket resets ~1 minute.
_RATE_LIMIT_MARKERS = ("429", "ratelimit", "rate limit", "rate_limit_exceeded",
                       "tokens per minute")


def _is_rate_limit(err_text: str) -> bool:
    low = err_text.lower()
    return "429" in low or any(m in low for m in _RATE_LIMIT_MARKERS)


def load_cases(path: Path) -> tuple[str, str, list[dict]]:
    """Read a list or an object with {name, description, cases}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        name, description, cases = Path(path).stem, "", data
    elif isinstance(data, dict):
        name = data.get("name") or Path(path).stem
        description = data.get("description") or ""
        cases = data.get("cases") or []
    else:
        raise ValueError("cases file must be a JSON list or an object with 'cases'")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases file has no cases")
    for i, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not str(case.get("question") or "").strip():
            raise ValueError(f"case {i} is missing 'question'")
    return name, description, cases


def _pipeline():
    from backend.l17_generation.graph import answer

    return answer


def _clear_cache() -> None:
    from backend.l19_cache.cache import clear

    clear()


def _pass(metrics: dict, threshold: float) -> bool:
    scores = [m.get("score") for m in metrics.values() if m.get("score") is not None]
    return bool(scores) and all(float(s) >= threshold for s in scores)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[min(idx, len(ordered) - 1)]


def run_case(case: dict, index: int, answer_fn, mode: str, top_k: int,
             groups: list[str], threshold: float,
             judge_offset: int = 0,
             metrics_filter: list[str] | None = None) -> dict:
    question = case["question"]
    started = time.perf_counter()
    pipeline_error, text, cites, contexts = "", "", [], []
    snap_text, snap_contexts = "", []
    try:
        text, cites, contexts, _, cache_hit, _ = answer_fn(
            question, top_k, groups, mode, None)
        # Snapshot before the judge runs — DeepEval mutates the retrieval
        # context list in place, which would otherwise wipe the record.
        snap_text = str(text)
        snap_contexts = list(contexts)
        if cache_hit:
            _clear_cache()
            started = time.perf_counter()
            text, cites, contexts, _, _, _ = answer_fn(
                question, top_k, groups, mode, None)
            snap_text = str(text)
            snap_contexts = list(contexts)
        latency = time.perf_counter() - started
    except Exception as e:
        latency = time.perf_counter() - started
        pipeline_error = f"{type(e).__name__}: {e}"[:300]

    if pipeline_error:
        result = {"status": "error", "error": pipeline_error, "metrics": {}}
    else:
        result = None
        for attempt in range(3):
            try:
                result = evaluate_case({
                    "question": question,
                    "answer": snap_text,
                    "contexts": list(snap_contexts),
                    "expected_output": case.get("expected_output") or "",
                }, judge_offset=judge_offset, metrics_filter=metrics_filter)
            except Exception as e:
                result = {"status": "error",
                          "error": f"{type(e).__name__}: {e}"[:300],
                          "metrics": {}}
            if result.get("status") == "ok":
                break
            err_text = str(result.get("error") or "")
            if attempt < 2 and _is_rate_limit(err_text):
                time.sleep(15 * (attempt + 1))
            else:
                break

    metrics = result.get("metrics") or {}
    passed = result.get("status") == "ok" and _pass(metrics, threshold)
    return {
        "id": case.get("id") or f"case-{index}",
        "question": question,
        "answer": snap_text,
        "contexts": [c[:1000] for c in snap_contexts],
        "citations": cites,
        "mode": mode,
        "latency_s": round(latency, 2),
        "status": result.get("status", "error"),
        "judge": result.get("judge", ""),
        "metrics": metrics,
        "error": result.get("error", ""),
        "passed": passed,
    }


def summarize(records: list[dict], threshold: float) -> dict:
    n = len(records)
    passed = sum(1 for r in records if r["passed"])
    latencies = [r["latency_s"] for r in records]
    by_metric = defaultdict(list)
    for r in records:
        for name, metric in (r.get("metrics") or {}).items():
            if metric.get("score") is not None:
                by_metric[name].append(float(metric["score"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": n,
        "passed": passed,
        "pass_rate": round(passed / n, 3) if n else 0.0,
        "avg_latency_s": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        "p95_latency_s": round(_p95(latencies), 2),
        "metric_means": {name: round(statistics.fmean(vals), 3)
                         for name, vals in sorted(by_metric.items())},
        "errors": sum(1 for r in records if r.get("status") != "ok"),
        "threshold": threshold,
        "judge": next((r.get("judge") for r in records if r.get("judge")), ""),
    }


def run_benchmark(cases_path: Path = DEFAULT_CASES, mode: str = "quick",
                  top_k: int = 5, groups: list[str] | None = None,
                  threshold: float = DEFAULT_THRESHOLD,
                  limit: int | None = None,
                  delay: float = 0.0,
                  metrics_filter: list[str] | None = None,
                  on_case=None) -> tuple[dict, list[dict], dict]:
    name, description, cases = load_cases(cases_path)
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError("no cases to run")
    groups = groups or ["hr", "eng", "public"]
    meta = {
        "name": name,
        "description": description,
        "cases_file": str(cases_path),
        "mode": mode,
        "top_k": top_k,
        "groups": groups,
        "threshold": threshold,
        "metrics": metrics_filter or ["Contextual Relevancy", "Faithfulness", "Contextual Recall"],
    }
    answer_fn = _pipeline()
    records = []
    for i, case in enumerate(cases, 1):
        # fresh retrieval per case: the semantic answer cache would otherwise
        # short-circuit similar questions with empty contexts
        _clear_cache()
        records.append(run_case(case, i, answer_fn, mode, top_k, groups,
                                threshold, judge_offset=i % 2,
                                metrics_filter=metrics_filter))
        if on_case:
            on_case(records.copy(), summarize(records, threshold), meta)
        if i < len(cases) and delay > 0:
            time.sleep(delay)
    meta = {
        "name": name,
        "description": description,
        "cases_file": str(cases_path),
        "mode": mode,
        "top_k": top_k,
        "groups": groups,
        "threshold": threshold,
    }
    return summarize(records, threshold), records, meta


def _md(text: object, limit: int = 80) -> str:
    flat = " ".join(str(text or "").split()).replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _score(value) -> str:
    return "—" if value is None else f"{float(value):.2f}"


def render_report(summary: dict, records: list[dict], meta: dict) -> str:
    metric_names = list(summary["metric_means"].keys())
    lines = [
        "# Answer quality benchmark",
        "",
        "Dev-only scorecard generated by `python -m backend.l18_verification.benchmark`.",
        "It runs the real pipeline, clears the answer cache first, and judges every answer",
        "with DeepEval. Judge calls are not included in latency.",
        "",
        f"**Pass rate (accuracy): {summary['pass_rate']:.0%}** "
        f"({summary['passed']}/{summary['cases']} cases) · "
        f"**avg latency: {summary['avg_latency_s']:.2f} s** · "
        f"**p95: {summary['p95_latency_s']:.2f} s**",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Generated | {summary['generated_at']} |",
        f"| Case set | {_md(meta['name'], 120)} |",
        f"| Mode / top_k | {meta['mode']} / {meta['top_k']} |",
        f"| Groups | {', '.join(meta['groups'])} |",
        f"| Pass threshold | {summary['threshold']:.2f} (all metrics) |",
        f"| Judge | {_md(summary['judge'] or 'n/a', 120)} |",
        f"| Pipeline errors | {summary['errors']} |",
    ]
    for name, mean in summary["metric_means"].items():
        lines.append(f"| {name} (mean) | {mean:.2f} |")

    header = ["#", "Case", "Pass", "Latency"] + [_SHORT.get(n, n) for n in metric_names]
    lines += ["", "## Per case", "",
              "| " + " | ".join(header) + " |",
              "|" + "|".join(["---"] * len(header)) + "|"]
    for i, r in enumerate(records, 1):
        cells = [str(i), _md(r["id"], 40), "yes" if r["passed"] else "no",
                 f"{r['latency_s']:.2f} s"]
        cells += [_score((r.get("metrics") or {}).get(n, {}).get("score"))
                  for n in metric_names]
        lines.append("| " + " | ".join(cells) + " |")

    failures = [r for r in records if not r["passed"]]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("_None._")
    for r in failures:
        lines.append(f"- **{_md(r['id'], 40)}** — {_md(r['question'], 160)}")
        if r.get("status") != "ok":
            lines.append(f"  - {r['status']}: {_md(r.get('error') or 'unknown error', 240)}")
        else:
            low = [f"{name} {_score(m.get('score'))}"
                   for name, m in (r.get("metrics") or {}).items()
                   if m.get("score") is None or float(m["score"]) < summary["threshold"]]
            lines.append(f"  - below threshold: {', '.join(low) or 'no scores'}")
        if r.get("error"):
            lines.append(f"  - error: {_md(r['error'], 240)}")
        if r.get("answer"):
            lines.append(f"  - answer: {_md(r['answer'], 240)}")

    lines += [
        "",
        "---",
        "",
        f"Cases and expected answers: `{meta['cases_file']}`. Raw results: "
        "`data/evaluation.json`. Re-run after any model, prompt, or corpus change.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the dev-only answer-quality benchmark and write a scorecard.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--groups", default=DEFAULT_GROUPS,
                        help="comma-separated retrieval groups")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="minimum score for every metric (default 0.6)")
    parser.add_argument("--limit", type=int, default=None,
                        help="run only the first N cases")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="seconds to sleep between cases (spreads rate-limited judge calls)")
    parser.add_argument("--metrics", default="Faithfulness,Contextual Relevancy,Contextual Recall",
                        help="comma-separated metric names to run (default all three)")
    args = parser.parse_args(argv)

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    metrics_filter = [m.strip() for m in args.metrics.split(",") if m.strip()]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)

    def _persist(summary_: dict, records_: list[dict], meta_: dict) -> None:
        args.out.write_text(render_report(summary_, records_, meta_), encoding="utf-8")
        args.json_out.write_text(
            json.dumps({"summary": summary_, "meta": meta_, "cases": records_},
                       indent=2, ensure_ascii=False),
            encoding="utf-8")

    try:
        def on_case(records_: list[dict], summary_: dict, meta_: dict) -> None:
            _persist(summary_, records_, meta_)

        summary, records, meta = run_benchmark(
            args.cases, args.mode, args.top_k, groups, args.threshold,
            args.limit, args.delay, metrics_filter, on_case)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"benchmark: {e}", file=sys.stderr)
        return 2

    _persist(summary, records, meta)

    print(f"pass rate {summary['pass_rate']:.0%} "
          f"({summary['passed']}/{summary['cases']}) · "
          f"avg {summary['avg_latency_s']:.2f}s · p95 {summary['p95_latency_s']:.2f}s")
    print(f"wrote {args.out} and {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
