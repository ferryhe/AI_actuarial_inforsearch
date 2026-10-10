from ai_actuarial.api.deps import AuthContext
from ai_actuarial.api.services import rag_admin as rag_admin_service
from ai_actuarial.api.services.ready_data_publication import publish_ready_data_publication
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage
from tests.test_fastapi_rag_admin_endpoints import _build_test_client


def _disable_tokenizer_initialization(monkeypatch, tmp_path):
    import tiktoken

    from ai_actuarial.rag import embeddings, knowledge_base, semantic_chunking

    def fail(*_args, **_kwargs):
        raise AssertionError("_rag runtime dependency initialized")

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "empty-tokenizer-cache"))
    for target, name in (
        (knowledge_base, "SemanticChunker"),
        (knowledge_base, "EmbeddingGenerator"),
        (semantic_chunking, "SemanticChunker"),
        (embeddings, "EmbeddingGenerator"),
        (tiktoken, "get_encoding"),
        (tiktoken, "encoding_for_model"),
    ):
        monkeypatch.setattr(target, name, fail)


def _kb_db(tmp_path, monkeypatch):
    db_path = tmp_path / "index.db"
    _client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    storage = Storage(str(db_path))
    try:
        KnowledgeBaseManager(storage)
        storage._conn.executescript("""
            INSERT INTO rag_knowledge_bases (
                kb_id, name, description, kb_mode, chunk_profile_id, manifest_profile,
                embedding_provider, embedding_model, embedding_dimension, embedding_identity_key,
                chunk_size, chunk_overlap, index_type, created_at, updated_at, file_count, chunk_count
            ) VALUES (
                'kb-lazy', 'Lazy KB', '', 'manual', '', 'general', 'openai',
                'text-embedding-3-large', 3072, '', 800, 100, 'Flat',
                '2026-10-10T00:00:00+00:00', '2026-10-10T00:00:00+00:00', 0, 0
            );
            """)
        storage._conn.commit()
    finally:
        storage.close()
    _disable_tokenizer_initialization(monkeypatch, tmp_path)
    return str(db_path)


def _admin():
    return AuthContext(
        token={"subject": "admin"}, permissions=frozenset({"catalog.read", "tasks.run"})
    )


def test_fastapi_kb_detail_does_not_initialize_tiktoken(tmp_path, monkeypatch):
    body = rag_admin_service.get_knowledge_base(
        db_path=_kb_db(tmp_path, monkeypatch), kb_id="kb-lazy", auth=_admin()
    )
    assert body["knowledge_base"]["kb_id"] == "kb-lazy"


def test_fastapi_kb_detail_deep_does_not_initialize_tiktoken(tmp_path, monkeypatch):
    body = rag_admin_service.get_knowledge_base(
        db_path=_kb_db(tmp_path, monkeypatch), kb_id="kb-lazy", deep=True, auth=_admin()
    )
    assert body["knowledge_base"]["kb_id"] == "kb-lazy"


def test_fastapi_kb_stats_does_not_initialize_tiktoken(tmp_path, monkeypatch):
    body = rag_admin_service.get_knowledge_base_stats(
        db_path=_kb_db(tmp_path, monkeypatch), kb_id="kb-lazy", auth=_admin()
    )
    assert body["kb_id"] == "kb-lazy"


def test_fastapi_kb_files_does_not_initialize_tiktoken(tmp_path, monkeypatch):
    body = rag_admin_service.list_knowledge_base_files(
        db_path=_kb_db(tmp_path, monkeypatch), kb_id="kb-lazy", query={}, auth=_admin()
    )
    assert body["total"] == 0


def test_fastapi_kb_agentic_manifest_does_not_initialize_tiktoken(tmp_path, monkeypatch):
    body = rag_admin_service.get_agentic_ready_manifest(
        db_path=_kb_db(tmp_path, monkeypatch), kb_id="kb-lazy"
    )
    assert body["kb_id"] == "kb-lazy"


def test_fastapi_kb_ready_data_publication_does_not_initialize_tiktoken(tmp_path, monkeypatch):
    try:
        publish_ready_data_publication(
            db_path=_kb_db(tmp_path, monkeypatch),
            kb_id="kb-lazy",
            payload={
                "profile": "general",
                "publication_id": "missing",
                "expected_active_publication_id": None,
            },
        )
    except rag_admin_service.RagAdminError as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("missing publication unexpectedly published")
