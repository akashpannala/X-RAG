"""L17: 6k-char budget + [doc#chunk] citations."""

BUDGET_CHARS = 6000


def assemble(query: str, hits: list[dict]) -> tuple[str, list[str]]:
    budget, parts, cites, used = BUDGET_CHARS, [], [], 0
    for h in hits:
        tag = f"[{h['doc']}#{h['chunk_id']}]"
        block = f"{tag} {h['text']}\n"
        # partial-fit: if a whole block won't fit but some of it will, truncate it
        if used + len(block) > budget:
            remaining = budget - used
            if remaining > 200:  # worth including a partial block
                cut = block[:remaining].rsplit(" ", 1)[0]
                parts.append(cut + "\n")
                used += len(cut) + 1
                if tag not in cites:
                    cites.append(tag)
            break
        parts.append(block)
        used += len(block)
        if tag not in cites:
            cites.append(tag)
    context = "".join(parts) if parts else "(no retrieved context)"
    return (f"Answer ONLY from the context below. Cite every fact as [doc#chunk].\n"
            f"Context:\n{context}\nQuestion: {query}\nAnswer:"), cites
