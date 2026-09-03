"""L17: 6k-char budget + [doc#chunk] citations."""

BUDGET_CHARS = 6000


def assemble(query: str, hits: list[dict]) -> tuple[str, list[str]]:
    budget, parts, cites = BUDGET_CHARS, [], []
    for h in hits:
        tag = f"[{h['doc']}#{h['chunk_id']}]"
        block = f"{tag} {h['text']}\n"
        if len("".join(parts)) + len(block) > budget:
            break
        parts.append(block)
        if tag not in cites:
            cites.append(tag)
    context = "".join(parts) if parts else "(no retrieved context)"
    return (f"Answer ONLY from the context below. Cite every fact as [doc#chunk].\n"
            f"Context:\n{context}\nQuestion: {query}\nAnswer:"), cites
