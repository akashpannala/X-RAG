"""L4-basic: fenced table/code blocks stay whole, rest via LC splitter."""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

FENCED = re.compile(r"```.*?```", re.S)
_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)


def chunk(text: str) -> list[str]:
    parts, last = [], 0
    for m in FENCED.finditer(text):
        if m.start() > last:
            parts.append(text[last:m.start()])
        parts.append(m.group(0))
        last = m.end()
    parts.append(text[last:])
    out: list[str] = []
    for p in parts:
        if not p.strip():
            continue
        if p.lstrip().startswith("```"):  # ponytail: fenced stays whole even >2000 for table/code integrity
            out.append(p)
        else:
            out.extend(_splitter.split_text(p))
    return out
