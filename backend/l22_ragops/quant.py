"""L22: shared INT8 dynamic quantization seam.

quantize_dynamic_if_enabled() applies torch.ao.quantization.quantize_dynamic
to the transformer backbone of a loaded model when EMBED_QUANT=true, and only
once per model instance. Pure no-op otherwise / when torch is unavailable.

Target backbones (by attribute, tried in order):
  transformer   -> SentenceTransformer / HF embeddings backbones (BGE-M3)
  auto_model    -> CrossEncoder backbones (MiniLM / BGE-reranker)
"""
from backend.config import settings

_quantized_ids = set()


def quantize_dynamic_if_enabled(model, *attrs):
    """Quantize in place if enabled and this instance wasn't touched yet."""
    if not settings.embed_quant or model is None:
        return model
    if id(model) in _quantized_ids:
        return model
    try:
        import torch

        attrs = attrs or ("transformer", "auto_model", "bert", "roberta",
                          "distilbert", "electra", "encoder")
        backbone = None
        for attr in attrs:
            backbone = getattr(model, attr, None)
            if isinstance(backbone, torch.nn.Module) and len(list(backbone.modules())) > 3:
                break
        if backbone is None:
            best, best_n = None, 1
            for _, child in list(model.named_children()):
                n = len(list(child.modules()))
                if n > best_n:
                    best, best_n = child, n
            backbone = best
        if backbone is not None:
            torch.ao.quantization.quantize_dynamic(
                backbone, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
            _quantized_ids.add(id(model))
    except Exception:
        pass
    return model