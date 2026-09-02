"""L3 Cleaning — MinHash near-dedup + Presidio PII redact (both local)."""
import re

try:
    from datasketch import MinHash
except ImportError:
    MinHash = None  # type: ignore


def dedup_texts(texts: list[str], threshold: float = 0.85) -> list[str]:
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


def redact(text: str) -> tuple[str, int]:
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        red, n = re.subn(r"[\w.-]+@[\w.-]+\.\w+", "[REDACTED_EMAIL]", text)
        return red, n
    res = AnalyzerEngine().analyze(text=text, language="en")
    if not res:
        return text, 0
    return AnonymizerEngine().anonymize(text=text, analyzer_results=res).text, len(res)
