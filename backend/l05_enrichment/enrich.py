"""L5 Enrichment — RAPTOR-lite summaries + hypothetical questions + NER to Kuzu.

Rides get_llm() (Groq dev / Ollama prod). Summaries and HyQs become extra
retrievable points; entities land in Kuzu for Phase 3 graph agents.
"""
import logging
import re

_logger = logging.getLogger(__name__)

_Q = re.compile(r"^(?:Q\d+[:.]?|\d+[).:-]?)\s*")


def _strip_numbering(s: str) -> str:
    return _Q.sub("", s).strip()


from backend.l17_generation.llm import get_llm


def summarize_cluster(texts: list[str]) -> str:
    # ponytail: sequential invokes; batch with asyncio.gather if enrich latency matters on local Ollama
    if len(texts) > 4:
        _logger.debug("summarize_cluster got %d texts > width 4 — check caller", len(texts))
    llm = get_llm()
    joined = "\n---\n".join(t[:1500] for t in texts)[:6000]
    if len(joined) == 6000:
        _logger.debug("summarize_cluster hit 6000-char cap — later chunks truncated")
    msg = llm.invoke(f"Summarize these document chunks in 5 sentences or less:\n{joined}")
    return msg.content if isinstance(msg.content, str) else str(msg.content)


def raptor_parents(chunks: list[str], width: int = 4) -> list[str]:
    """One summary per sequential window — parents of the chunk leaves."""
    # ponytail: one level only (lite); recurse parents->grandparents to root if cross-section summaries needed
    return [summarize_cluster(chunks[i:i + width]) for i in range(0, len(chunks), width)]


def hypothetical_questions(doc: str, sample: str, n: int = 3) -> list[str]:
    # ponytail: sequential; batch if enrich latency matters
    llm = get_llm()
    msg = llm.invoke(
        f"Write {n} distinct questions a reader would ask that this document answers.\n"
        f"Document '{doc}' excerpt:\n{sample[:3000]}\nQuestions (one per line, no numbering):")
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    return [_strip_numbering(l) for l in text.splitlines() if l.strip()][:n]


def extract_entities(text: str) -> list[tuple[str, str]]:
    """Prefer the small spaCy model (~12MB RAM); lg vectors cost ~1GB."""
    try:
        import spacy

        nlp = None
        for model in ("en_core_web_sm", "en_core_web_lg"):
            try:
                nlp = spacy.load(model)
                if model == "en_core_web_lg":
                    _logger.warning("using en_core_web_lg (1GB) — prefer en_core_web_sm for 12MB box")
                break
            except OSError:
                _logger.info("spacy %s not found, trying next", model)
                continue
        if nlp is None:
            _logger.warning("no spacy model found — NER skipped, Kuzu will stay empty; pip install en_core_web_sm")
            return []
        doc = nlp(text[:20000])
        return [(e.text[:80], e.label_) for e in doc.ents]
    except Exception as e:
        _logger.warning("NER failed: %s", e)
        return []
