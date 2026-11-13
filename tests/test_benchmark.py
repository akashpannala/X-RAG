"""Dev-only benchmark: case loading, aggregation, report, CLI."""
import json

import pytest

from backend.l18_verification import benchmark as bm


def _case(i: int = 1) -> dict:
    return {"id": f"c{i}", "question": f"q{i}?", "expected_output": "e"}


def _record(i: int, passed: bool, latency: float, metrics: dict,
            status: str = "ok", error: str = "") -> dict:
    return {
        "id": f"c{i}",
        "question": f"q{i}?",
        "answer": f"a{i}",
        "contexts": ["ctx"],
        "citations": ["src"],
        "mode": "quick",
        "latency_s": latency,
        "status": status,
        "judge": "judge",
        "metrics": metrics,
        "error": error,
        "passed": passed,
    }


def test_load_cases_from_object(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"name": "demo", "description": "d", "cases": [_case()]}))
    name, description, cases = bm.load_cases(path)
    assert (name, description) == ("demo", "d")
    assert cases[0]["question"] == "q1?"


def test_load_cases_accepts_bare_list(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([_case()]))
    name, description, cases = bm.load_cases(path)
    assert name == "cases" and description == "" and len(cases) == 1


def test_load_cases_rejects_empty_and_missing_question(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": []}))
    with pytest.raises(ValueError):
        bm.load_cases(path)
    path.write_text(json.dumps({"cases": [{"id": "x"}]}))
    with pytest.raises(ValueError):
        bm.load_cases(path)


def test_pass_requires_scores_and_threshold():
    assert bm._pass({"a": {"score": 0.6}, "b": {"score": None}}, 0.6)
    assert not bm._pass({"a": {"score": 0.59}}, 0.6)
    assert not bm._pass({}, 0.6)


def test_summarize_pass_rate_means_p95_and_errors():
    records = [
        _record(1, True, 1.0, {"Faithfulness": {"score": 1.0},
                               "Contextual Recall": {"score": None}}),
        _record(2, False, 2.0, {"Faithfulness": {"score": 0.4},
                                "Contextual Recall": {"score": 0.8}},
                status="error", error="judge failed"),
        _record(3, True, 3.0, {"Faithfulness": {"score": 0.8}}),
    ]
    s = bm.summarize(records, 0.6)
    assert (s["cases"], s["passed"], s["errors"]) == (3, 2, 1)
    assert s["pass_rate"] == 0.667
    assert s["avg_latency_s"] == 2.0
    assert s["p95_latency_s"] == 3.0
    assert s["metric_means"]["Faithfulness"] == 0.733
    assert s["metric_means"]["Contextual Recall"] == 0.8
    assert s["judge"] == "judge"


def test_render_report_headline_rows_and_failure_reason():
    records = [
        _record(1, True, 1.0, {"Faithfulness": {"score": 1.0}}),
        _record(2, False, 2.0, {"Faithfulness": {"score": 0.2}}),
    ]
    summary = bm.summarize(records, 0.6)
    meta = {"name": "demo", "cases_file": "cases.json", "mode": "quick",
            "top_k": 5, "groups": ["hr", "eng"]}
    md = bm.render_report(summary, records, meta)
    assert "Pass rate (accuracy): 50%" in md
    assert "| 1 | c1 | yes | 1.00 s | 1.00 |" in md
    assert "| 2 | c2 | no | 2.00 s | 0.20 |" in md
    assert "below threshold: Faithfulness 0.20" in md
    assert "`cases.json`" in md


def test_render_report_says_none_when_all_pass():
    records = [_record(1, True, 1.0, {"Faithfulness": {"score": 1.0}})]
    meta = {"name": "demo", "cases_file": "cases.json", "mode": "quick",
            "top_k": 5, "groups": ["hr"]}
    md = bm.render_report(bm.summarize(records, 0.6), records, meta)
    assert "## Failures\n\n_None._" in md


def test_run_benchmark_calls_pipeline_and_scores(monkeypatch, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"name": "demo", "cases": [_case(1), _case(2)]}))
    calls, cleared = [], []
    monkeypatch.setattr(bm, "_clear_cache", lambda: cleared.append(1))
    monkeypatch.setattr(
        bm, "_pipeline",
        lambda: lambda q, top_k, groups, mode, user_id: (
            calls.append((q, top_k, groups, mode, user_id))
            or (f"answer {q}", ["src"], ["ctx"], mode, False, {})))
    monkeypatch.setattr(
        bm, "evaluate_case",
        lambda tc, judge_offset=0, metrics_filter=None: {"status": "ok", "judge": "judge",
                    "metrics": {"Faithfulness": {"score": 1.0 if tc["question"] == "q1?" else 0.2}}})

    summary, records, meta = bm.run_benchmark(path, "deep", 7, ["eng"], 0.6)

    assert summary["passed"] == 1 and summary["cases"] == 2
    assert [r["passed"] for r in records] == [True, False]
    assert records[0]["answer"] == "answer q1?"
    assert calls[0] == ("q1?", 7, ["eng"], "deep", None)
    assert meta["mode"] == "deep" and meta["groups"] == ["eng"]
    assert cleared == [1, 1]


def test_run_benchmark_counts_pipeline_failure(monkeypatch, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([_case(1)]))

    def boom(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(bm, "_clear_cache", lambda: None)
    monkeypatch.setattr(bm, "_pipeline", lambda: boom)
    monkeypatch.setattr(bm, "evaluate_case",
                        lambda tc, judge_offset=0, metrics_filter=None: pytest.fail("evaluate_case should not run"))

    summary, records, _meta = bm.run_benchmark(path)
    assert summary["passed"] == 0 and summary["errors"] == 1
    assert "RuntimeError: provider down" in records[0]["error"]


def test_cache_hit_retries_after_clearing(monkeypatch, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([_case(1)]))
    cleared, hits = [], iter([True, False])
    monkeypatch.setattr(bm, "_clear_cache", lambda: cleared.append(1))
    monkeypatch.setattr(
        bm, "_pipeline",
        lambda: lambda *args: ("a", [], ["ctx"], "quick", next(hits), {}))
    monkeypatch.setattr(bm, "evaluate_case",
                        lambda tc, judge_offset=0, metrics_filter=None: {"status": "ok", "judge": "j",
                                    "metrics": {"Faithfulness": {"score": 1.0}}})
    bm.run_benchmark(path)
    assert len(cleared) == 2


def test_main_writes_markdown_and_json(monkeypatch, tmp_path):
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([_case(1)]))
    out, json_out = tmp_path / "evaluation.md", tmp_path / "evaluation.json"
    monkeypatch.setattr(bm, "_clear_cache", lambda: None)
    monkeypatch.setattr(bm, "_pipeline",
                        lambda: lambda *args: ("a", [], ["ctx"], "quick", False, {}))
    monkeypatch.setattr(bm, "evaluate_case",
                        lambda tc, judge_offset=0, metrics_filter=None: {"status": "ok", "judge": "j",
                                    "metrics": {"Faithfulness": {"score": 1.0}}})

    rc = bm.main(["--cases", str(cases), "--out", str(out),
                  "--json-out", str(json_out), "--groups", "eng"])

    assert rc == 0
    assert "Pass rate (accuracy): 100%" in out.read_text()
    data = json.loads(json_out.read_text())
    assert data["summary"]["cases"] == 1
    assert data["cases"][0]["id"] == "c1"
    assert data["meta"]["groups"] == ["eng"]


def test_main_missing_cases_file_returns_2(tmp_path, capsys):
    rc = bm.main(["--cases", str(tmp_path / "nope.json"),
                  "--out", str(tmp_path / "o.md"),
                  "--json-out", str(tmp_path / "o.json")])
    assert rc == 2
    assert "benchmark:" in capsys.readouterr().err
