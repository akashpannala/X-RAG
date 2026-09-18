"""L1 Connector — dispatch by extension. PDF/DOCX/PPTX/CSV/MD/TXT."""
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".pptx", ".csv", ".md", ".txt", ".png", ".jpg", ".jpeg"}

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def check_supported(path: Path) -> None:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported {ext or '(no extension)'} — supported: {sorted(SUPPORTED)} — convert legacy .doc/.xls/.ppt to .docx/.xlsx via LibreOffice headless if needed")
