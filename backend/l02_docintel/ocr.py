"""L2-full: OCR fallback via RapidOCR (installed with Docling).

Docling handles born-digital PDFs; scanned pages / raw images go here.
Qwen2-VL-2B chart understanding stays gated on Phase-4 hardware.
"""
from pathlib import Path


def ocr_image(path: Path) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        raise RuntimeError("rapidocr not installed") from e
    engine = RapidOCR()
    result, _ = engine(str(path))
    if not result:
        return ""
    return "\n".join(line[1] if isinstance(line, (list, tuple)) else str(line) for line in result)
