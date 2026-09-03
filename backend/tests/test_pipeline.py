from backend.l04_chunking.splitter import chunk
from backend.l17_assembly.prompt import assemble


def test_chunk_and_assemble():
    chunks = chunk("hello world " * 500 + "\n```code block```\n" + "tail " * 100)
    assert chunks and all(len(c) <= 2100 for c in chunks)
    prompt, cites = assemble("hi?", [{"doc": "d", "chunk_id": 0, "text": chunks[0][:500]}])
    assert "[d#0]" in prompt and cites == ["[d#0]"]


def test_llm_factory_no_network():
    from langchain_core.language_models.chat_models import BaseChatModel

    from backend.l18_generation.llm import get_llm

    assert isinstance(get_llm(), BaseChatModel)
