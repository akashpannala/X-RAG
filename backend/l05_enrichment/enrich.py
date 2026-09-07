"""L5 Enrichment — RAPTOR-lite summaries + hypothetical questions + NER to Kuzu.

Rides get_llm() (Groq dev / Ollama prod). Summaries and HyQs become extra
retrievable points; entities land in Kuzu for Phase 3 graph agents.
"""
from backend.l18_generation.llm import get_llm


def summarize_cluster(texts: list[str]) -> str:
    llm = get_llm()
    joined = "\n---\n".join(t[:1500] for t in texts)[:6000]
    msg = llm.invoke(f"Summarize these document chunks in 5 sentences or less:\n{joined}")
    return msg.content if isinstance(msg.content, str) else str(msg.content)


def raptor_parents(chunks: list[str], width: int = 4) -> list[str]:
    """One summary per sequential window — parents of the chunk leaves."""
    return [summarize_cluster(chunks[i:i + width]) for i in range(0, len(chunks), width)]


def hypothetical_questions(doc: str, sample: str, n: int = 3) -> list[str]:
    llm = get_llm()
    msg = llm.invoke(
        f"Write {n} distinct questions a reader would ask that this document answers.\n"
        f"Document '{doc}' excerpt:\n{sample[:3000]}\nQuestions (one per line, no numbering):")
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    return [l.strip().lstrip("1234567890.-) ") for l in text.splitlines() if l.strip()][:n]


def extract_entities(text: str) -> list[tuple[str, str]]:
    """Prefer the small spaCy model (~12MB RAM); lg vectors cost ~1GB."""
    try:
        import spacy

        for model in ("en_core_web_sm", "en_core_web_lg"):
            try:
                nlp = spacy.load(model)
                break
            except OSError:
                continue
        else:
            return []
        doc = nlp(text[:20000])
        return [(e.text[:80], e.label_) for e in doc.ents]
    except Exception:
        return []
