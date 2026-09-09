"""L1 Connector — dispatch by extension. PDF/DOCX/PPTX/CSV/MD/TXT."""
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".pptx", ".csv", ".md", ".txt", ".png", ".jpg", ".jpeg"}

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def check_supported(path: Path) -> None:
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported {path.suffix} — supported: {sorted(SUPPORTED)}")
