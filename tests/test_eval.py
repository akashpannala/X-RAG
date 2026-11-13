"""DeepEval deep eval — judge wiring + graceful degradation."""
from types import SimpleNamespace

from backend.config import settings
from backend.l18_verification import eval as xeval


def test_run_eval_no_cases():
    assert xeval.run_eval([])["status"] == "no-cases"


def test_run_eval_delegates_to_deep_eval_runner(monkeypatch):
    monkeypatch.setattr(xeval, "_run_deepeval", lambda cases: {"status": "ok", "results": cases})
    out = xeval.run_eval([{"question": "q", "answer": "a", "contexts": ["c"]}])
    assert out["status"] == "ok"


def test_judge_base_url_defaults_to_groq_openai_compat(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert xeval._judge_base_url() == "https://api.groq.com/openai/v1"


def test_judge_base_url_appends_openai_v1_to_groq_root(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://api.groq.com")
    assert xeval._judge_base_url() == "https://api.groq.com/openai/v1"


def test_judges_empty_without_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert xeval._judges() == []


def test_judges_use_configured_model_then_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "openai/gpt-oss-20b")
    monkeypatch.setattr(settings, "llm_base_url", "")
    judges = xeval._judges()
    assert len(judges) == 2
    assert judges[0].get_model_name() == "openai/gpt-oss-20b"
    assert judges[1].get_model_name() == xeval._FALLBACK_JUDGE_MODEL


def test_scores_extracts_metric_data_and_flags_missing_scores():
    out = SimpleNamespace(
        test_results=[
            SimpleNamespace(
                metrics_data=[
                    SimpleNamespace(name="Contextual Relevancy", score=0.8, success=True, reason="ok", error=None),
                    SimpleNamespace(name="Faithfulness", score=None, success=None, reason=None, error="judge failed"),
                ]
            )
        ]
    )
    scores, has_score = xeval._scores(out)
    assert scores["Contextual Relevancy"]["score"] == 0.8
    assert scores["Faithfulness"]["error"] == "judge failed"
    assert has_score is True


def test_scores_without_scores_is_not_ok():
    out = SimpleNamespace(test_results=[SimpleNamespace(metrics_data=[SimpleNamespace(name="Faithfulness", score=None)])])
    _scores, has_score = xeval._scores(out)
    assert has_score is False
