"""L3 Cleaning — MinHash near-dedup + Presidio PII redact (both local)."""
import logging
import re

_logger = logging.getLogger(__name__)

try:
    from datasketch import MinHash
except ImportError:
    MinHash = None  # type: ignore

_analyzer = None  # ponytail: singleton; per-process on multi-worker
_anonymizer = None


def dedup_texts(texts: list[str], threshold: float = 0.85) -> list[str]:  # ponytail: 0.85 lexical Jaccard (~15% word change); lower to 0.70 if paraphrase dup slips through
    if MinHash is None:
        raise RuntimeError("datasketch not installed")
    kept, hashes = [], []
    for t in texts:
        h = MinHash(num_perm=128)
        for w in set(t.lower().split()):
            h.update(w.encode())
        if all(h.jaccard(o) < threshold for o in hashes):
            kept.append(t)
            hashes.append(h)
    return kept


def clean(texts: list[str]) -> list[str]:
    """Batch entry: dedup first, then redact kept docs. Dedup before redact keeps Jaccard stable."""
    redacted: list[str] = []
    for t in dedup_texts(texts):
        red, _ = redact(t)
        redacted.append(red)
    return redacted


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine

        _analyzer = AnalyzerEngine()
    return _analyzer


def _get_anonymizer():
    global _anonymizer
    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine

        _anonymizer = AnonymizerEngine()
    return _anonymizer


def redact(text: str) -> tuple[str, int]:
    try:
        analyzer = _get_analyzer()
        res = analyzer.analyze(text=text, language="en")
        if not res:
            return text, 0
        return _get_anonymizer().anonymize(text=text, analyzer_results=res).text, len(res)
    except ImportError as e:
        _logger.warning("presidio not installed — PII redact degraded to email-only regex: %s", e)
    except Exception as e:
        _logger.warning("presidio analyze failed — falling back to email regex: %s", e)
    red, n = re.subn(r"[\w.-]+@[\w.-]+\.\w+", "[REDACTED_EMAIL]", text)
    return red, n
