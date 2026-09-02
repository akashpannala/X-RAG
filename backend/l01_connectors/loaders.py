"""L1 Connector — dispatch by extension. PDF/DOCX/PPTX/CSV/MD/TXT."""
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".pptx", ".csv", ".md", ".txt"}


def check_supported(path: Path) -> None:
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported {path.suffix} — supported: {sorted(SUPPORTED)}")
