"""L2-full: OCR fallback via RapidOCR (installed with Docling).

Docling handles born-digital PDFs; scanned pages / raw images go here.
Qwen2-VL-2B chart understanding stays gated on Phase-4 hardware.
"""
from pathlib import Path


_engine = None  # ponytail: singleton; reload per-process if you run multi-worker uvicorn


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:
            raise RuntimeError("rapidocr not installed") from e
        _engine = RapidOCR()
    return _engine


def ocr_image(path: Path) -> str:
    # ponytail: lossy text only (line[1]); keep line[0] box + line[2] conf when table-aware chunking needed
    result, _ = _get_engine()(str(path))
    if not result:
        return ""
    return "\n".join(line[1] if isinstance(line, (list, tuple)) else str(line) for line in result)
