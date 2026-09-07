"""Backend package init — runs before any model import. Caps CPU threads so
Docling + BGE-M3 + MiniLM + spaCy can coexist on small boxes (7-8GB RAM)."""
import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

try:
    import torch

    torch.set_num_threads(4)
    torch.set_num_interop_threads(2)
except ImportError:
    pass
