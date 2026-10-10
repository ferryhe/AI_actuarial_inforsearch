from concurrent.futures import ThreadPoolExecutor

import tiktoken

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.rag.semantic_chunking import SemanticChunker
from ai_actuarial.storage import Storage


def _manager(tmp_path):
    storage = Storage(str(tmp_path / "knowledge-base.db"))
    manager = KnowledgeBaseManager(
        storage,
        config=RAGConfig(
            data_dir=str(tmp_path / "rag-data"), max_chunk_tokens=30, min_chunk_tokens=1
        ),
    )
    return storage, manager


def _chunk_values(chunks):
    return [
        (chunk.content, chunk.token_count, chunk.chunk_index, chunk.section_hierarchy)
        for chunk in chunks
    ]


def test_lazy_init_does_not_call_tiktoken_during_manager_construction(tmp_path, monkeypatch):
    calls = []
    original_get_encoding = tiktoken.get_encoding
    original_encoding_for_model = tiktoken.encoding_for_model

    def track_get_encoding(*args, **kwargs):
        calls.append(("get_encoding", args))
        return original_get_encoding(*args, **kwargs)

    def track_encoding_for_model(*args, **kwargs):
        calls.append(("encoding_for_model", args))
        return original_encoding_for_model(*args, **kwargs)

    monkeypatch.setattr(tiktoken, "get_encoding", track_get_encoding)
    monkeypatch.setattr(tiktoken, "encoding_for_model", track_encoding_for_model)
    storage, manager = _manager(tmp_path)
    try:
        assert calls == []
        assert isinstance(manager.chunker, SemanticChunker)
        assert manager.chunker.count_tokens("hi") > 0
        assert calls
    finally:
        storage.close()


def test_chunker_is_cached_and_matches_eager_chunking(tmp_path):
    storage, manager = _manager(tmp_path)
    markdown = (
        "# Introduction\n\nA short actuarial introduction.\n\n## Assumptions\n\nRates are stable."
    )
    eager = SemanticChunker(max_tokens=30, min_tokens=1)
    try:
        assert manager.chunker is manager.chunker
        assert _chunk_values(manager.chunker.chunk_document(markdown)) == _chunk_values(
            eager.chunk_document(markdown)
        )
    finally:
        storage.close()


def test_chunker_first_access_is_thread_safe(tmp_path):
    storage, manager = _manager(tmp_path)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            chunkers = list(pool.map(lambda _: manager.chunker, range(8)))
        assert len({id(chunker) for chunker in chunkers}) == 1
    finally:
        storage.close()
