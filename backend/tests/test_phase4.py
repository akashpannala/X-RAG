"""Phase 4 (L22 RAGOps) pure-function tests — no models, no network.

MBel: setting toggles must be restored so tests never leak configuration.
"""
import torch

from backend.config import settings
from backend.l22_ragops.queue import _row
from backend.l22_ragops.trace import available


def _restore(**over):
    for k, v in over.items():
        setattr(settings, k, v)


def test_quant_off_is_noop():
    mod = torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.Linear(4, 4))
    before = [type(m).__name__ for m in mod.modules()]
    settings.embed_quant = False
    from backend.l22_ragops.quant import quantize_dynamic_if_enabled
    quantize_dynamic_if_enabled(mod, "transformer", "auto_model")
    after = [type(m).__name__ for m in mod.modules()]
    assert before == after


def test_quant_dynamic_replaces_linears_real():
    settings.embed_quant = True
    try:
        backbone = torch.nn.Module()
        backbone.bert = torch.nn.Sequential(torch.nn.Linear(8, 8), torch.nn.ReLU(),
                                            torch.nn.Linear(8, 8))
        from backend.l22_ragops.quant import quantize_dynamic_if_enabled
        quantize_dynamic_if_enabled(backbone)
        names = [type(m).__module__ for m in backbone.modules()]
        assert any(n.startswith("torch.ao.") for n in names)
    finally:
        _restore(embed_quant=False)


def test_quant_child_fallback_for_sentence_transformer_layout():
    settings.embed_quant = True
    try:
        st = torch.nn.Module()
        st._modules["0"] = torch.nn.Sequential(torch.nn.Linear(8, 8), torch.nn.GELU())
        st._modules["1"] = torch.nn.Identity()
        from backend.l22_ragops.quant import quantize_dynamic_if_enabled
        quantize_dynamic_if_enabled(st)
        kinds = [type(m).__module__ for m in st._modules["0"].modules()]
        assert any(k.startswith("torch.ao.") for k in kinds)
    finally:
        _restore(embed_quant=False)


def test_row_parses_cites():
    row = _row("1-0", {"conv_id": "7", "query": "q", "answer": "a",
                       "cites": '["1", "2"]'})
    assert row["conv_id"] == 7 and row["cites"] == ["1", "2"]


def langfuse_handler_none():
    from backend.l22_ragops import trace
    _e, _p, _s = (settings.langfuse_enabled, settings.langfuse_public_key,
                  settings.langfuse_secret_key)
    settings.langfuse_enabled = False
    settings.langfuse_public_key = ""
    settings.langfuse_secret_key = ""
    try:
        return trace.langfuse_handler() is None and trace.start_query_trace("q") is None
    finally:
        _restore(langfuse_enabled=_e, langfuse_public_key=_p, langfuse_secret_key=_s)


def test_trace_disabled_by_default():
    settings.langfuse_enabled = False
    settings.langfuse_public_key = ""
    settings.langfuse_secret_key = ""
    assert available() is False
    assert langfuse_handler_none()


def test_text_lookup_resolves_exact_then_prefix():
    from backend.l22_ragops.mine import _resolve_gold_texts, _text_lookup
    meta = [
        {"doc": "handbook", "chunk_id": 0,
         "text": "remote work allowed three days weekly."},
        {"doc": "handbook", "chunk_id": 1,
         "text": "kitchen is on floor 2."},
    ]
    lookup = _text_lookup(meta)
    assert lookup["remote work allowed three days weekly."] == ("handbook", 0)
    cites = _resolve_gold_texts(meta, ["remote work allowed three days weekly.", "unknown text"])
    assert cites == [{"doc": "handbook", "chunk_id": 0, "text": "remote work allowed three days weekly."}]