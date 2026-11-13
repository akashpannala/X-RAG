"""DeepEval deep eval — RAG metrics over (question, answer, contexts).

The judge LLM is the configured Groq model through its OpenAI-compatible endpoint,
with an automatic fallback model when the primary judge is rejected. When no judge
is configured the runner degrades to status="unavailable" and never breaks serving.
"""
from backend.config import settings

_GROQ_OPENAI_BASE = "https://api.groq.com/openai/v1"
_FALLBACK_JUDGE_MODEL = "openai/gpt-oss-120b"


def run_eval(test_cases: list[dict] | None = None) -> dict:
    """Deep-eval QA pairs via DeepEval (contextual recall / relevancy / faithfulness)."""
    cases = test_cases or []
    if not cases:
        return {"status": "no-cases", "results": []}
    return _run_deepeval(cases)


def _judge_base_url() -> str:
    url = (settings.llm_base_url or "").strip().rstrip("/")
    if not url:
        return _GROQ_OPENAI_BASE
    if url.endswith("/v1"):
        return url
    if "groq" in url:
        return f"{url}/openai/v1"
    return f"{url}/v1"


def _judges() -> list:
    """Ordered judge models: configured Groq model, then the fallback model."""
    try:
        from deepeval.models import OpenAIModel
    except Exception:
        return []
    if (settings.llm_provider or "").strip().lower() != "groq" or not settings.llm_api_key:
        return []
    base_url = _judge_base_url()
    judges, seen = [], set()
    for model in (settings.llm_model, _FALLBACK_JUDGE_MODEL):
        if not model or model in seen:
            continue
        seen.add(model)
        try:
            judges.append(OpenAIModel(model=model, api_key=settings.llm_api_key, base_url=base_url))
        except Exception:
            continue
    return judges


def _judge_name(judge) -> str:
    try:
        return str(judge.get_model_name())
    except Exception:
        return getattr(judge, "model", None) or type(judge).__name__


def _metrics(judge, case, tc: dict, metrics_filter: list[str] | None = None) -> list:
    """Only metrics whose required inputs are present (avoids empty-input errors).

    ``metrics_filter`` limits which metric classes are instantiated — useful for
    rate-limited judge accounts where running all three metrics burns the TPM
    budget in a single case.
    """
    from deepeval.metrics import ContextualRecallMetric, ContextualRelevancyMetric, FaithfulnessMetric

    _ALL = {
        "Contextual Relevancy": ContextualRelevancyMetric,
        "Faithfulness": FaithfulnessMetric,
        "Contextual Recall": ContextualRecallMetric,
    }
    if metrics_filter:
        _ALL = {k: v for k, v in _ALL.items() if k in metrics_filter}

    metrics = []
    if case.input and case.retrieval_context and "Contextual Relevancy" in _ALL:
        metrics.append(_ALL["Contextual Relevancy"](model=judge))
    if case.actual_output and case.retrieval_context and "Faithfulness" in _ALL:
        metrics.append(_ALL["Faithfulness"](model=judge))
    expected = tc.get("expected_output") or tc.get("expected")
    if expected and case.retrieval_context and "Contextual Recall" in _ALL:
        case.expected_output = expected
        metrics.append(_ALL["Contextual Recall"](model=judge))
    return metrics


def _scores(out) -> tuple[dict, bool]:
    scores, has_score = {}, False
    for tr in getattr(out, "test_results", []) or []:
        for md in getattr(tr, "metrics_data", []) or []:
            score = getattr(md, "score", None)
            has_score = has_score or score is not None
            scores[getattr(md, "name", "metric")] = {
                "score": score,
                "success": getattr(md, "success", None),
                "reason": (getattr(md, "reason", None) or "")[:200],
                "error": getattr(md, "error", None),
            }
    return scores, has_score


def _evaluate_kwargs() -> dict:
    try:
        from deepeval.evaluate.configs import AsyncConfig, DisplayConfig

        # Serialize judge calls (one metric at a time, small throttle) so a
        # rate-limited judge account doesn't burn its per-minute token budget
        # on concurrent metric prompts.
        return {
            "display_config": DisplayConfig(show_indicator=False, print_results=False, inspect_after_run=False),
            "async_config": AsyncConfig(run_async=True, throttle_value=1.5, max_concurrent=1),
        }
    except Exception:
        return {}


def _run_deepeval(cases: list[dict]) -> dict:
    results = [evaluate_case(tc) for tc in cases]
    status = "ok" if results and all(r.get("status") == "ok" for r in results) else "error"
    return {"status": status, "results": results}


def evaluate_case(tc: dict, judge_offset: int = 0,
                  metrics_filter: list[str] | None = None) -> dict:
    """Score one {question, answer, contexts, expected_output?} case.

    Returns the same shape as a result inside run_eval(); shared with the
    dev-only benchmark so both use one judge/metrics path. ``judge_offset``
    rotates which configured judge is tried first so rate-limited accounts
    can burn through separate per-model TPM buckets across cases.
    """
    try:
        from deepeval import evaluate
        from deepeval.test_case import LLMTestCase
    except Exception:
        return {"input": tc.get("question") or "", "status": "unavailable",
                "error": "deepeval is not installed"}
    judges = _judges()
    if not judges:
        return {"input": tc.get("question") or "", "status": "unavailable",
                "error": "no judge LLM configured (set LLM_API_KEY)"}
    if len(judges) > 1 and judge_offset % len(judges):
        judges = judges[judge_offset % len(judges):] + judges[:judge_offset % len(judges)]
    return _eval_case(evaluate, _evaluate_kwargs(), LLMTestCase, tc, judges,
                      metrics_filter)


def _eval_case(evaluate, evaluate_kwargs: dict, llm_test_case, tc: dict, judges: list,
               metrics_filter: list[str] | None = None) -> dict:
    input_text = tc.get("question") or ""
    context = list(tc.get("contexts") or [])
    errors = []
    for judge in judges:
        try:
            case = llm_test_case(
                input=input_text,
                actual_output=tc.get("answer") or "",
                retrieval_context=context,
            )
            metrics = _metrics(judge, case, tc, metrics_filter)
            if not metrics:
                return {"input": input_text, "status": "unavailable", "error": "no applicable metrics"}
            out = evaluate(test_cases=[case], metrics=metrics, **evaluate_kwargs)
            scores, has_score = _scores(out)
            if not has_score:
                errors.append(f"{_judge_name(judge)}: no metric scores returned")
                continue
            return {
                "input": input_text,
                "status": "ok",
                "judge": _judge_name(judge),
                "metrics": scores,
            }
        except Exception as e:
            errors.append(f"{_judge_name(judge)}: {str(e)[:160]}")
    return {"input": input_text, "status": "error", "error": "; ".join(errors)[:400]}
