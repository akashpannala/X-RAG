"""L2-basic: Docling local only. Lazy import so API boots without it."""
from pathlib import Path


def parse(path: Path) -> str:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as e:
        raise RuntimeError("docling not installed — uv pip install docling") from e
    return DocumentConverter().convert(str(path)).document.export_to_markdown()
