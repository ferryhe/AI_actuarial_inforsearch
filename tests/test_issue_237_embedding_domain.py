from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.storage import Storage


def _downgrade_chunk_tables_to_v7(db_path: Path, *, with_rows: bool) -> dict[str, str]:
    storage = Storage(str(db_path))
    seeded: dict[str, object] | None = None
    try:
        if with_rows:
            seeded = _seed_chunks(storage)
            chunk_id = str(
                storage.list_chunks_for_embedding(
                    [str(seeded["chunk_set"]["chunk_set_id"])]
                )[0]["chunk_id"]
            )
            storage._conn.execute(
                """
                INSERT INTO chunk_embeddings (
                    chunk_id, embedding_identity_key, embedding_provider,
                    embedding_model, dimension, config_fingerprint, vector_json,
                    status, created_at, updated_at
                ) VALUES (?, 'current-key', 'local', 'legacy-model', 3,
                          'current-config', '[1,2,3]', 'ready', 'created', 'updated')
                """,
                (chunk_id,),
            )
            storage._conn.commit()
    finally:
        storage.close()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            """
            CREATE TABLE file_chunk_sets_v7 (
                chunk_set_id TEXT PRIMARY KEY,
                file_url TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                markdown_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(file_url, profile_id, markdown_hash),
                FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                FOREIGN KEY(profile_id) REFERENCES chunk_profiles(profile_id) ON DELETE CASCADE
            );
            INSERT INTO file_chunk_sets_v7
            SELECT chunk_set_id, file_url, profile_id, markdown_hash, status,
                   chunk_count, created_at, updated_at
            FROM file_chunk_sets;
            DROP TABLE file_chunk_sets;
            ALTER TABLE file_chunk_sets_v7 RENAME TO file_chunk_sets;

            CREATE TABLE chunk_embeddings_v7 (
                chunk_id TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                dim INTEGER NOT NULL DEFAULT 0,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, embedding_model),
                FOREIGN KEY(chunk_id) REFERENCES global_chunks(chunk_id) ON DELETE CASCADE
            );
            INSERT INTO chunk_embeddings_v7
            SELECT chunk_id, embedding_model, dimension, vector_json, created_at
            FROM chunk_embeddings;
            DROP TABLE chunk_embeddings;
            ALTER TABLE chunk_embeddings_v7 RENAME TO chunk_embeddings;
            PRAGMA user_version=7;
            """
        )

    return {
        "chunk_set_id": str((seeded or {}).get("chunk_set", {}).get("chunk_set_id", "")),
        "profile_config_hash": str((seeded or {}).get("profile", {}).get("config_hash", "")),
    }


def _seed_chunks(storage: Storage, *, file_url: str = "https://example.test/a.pdf") -> dict[str, object]:
    storage.insert_file(
        file_url,
        "file-hash",
        "A",
        "test",
        None,
        "a.pdf",
        "a.pdf",
        10,
        "application/pdf",
    )
    profile = storage.create_chunk_profile(
        name="issue-237",
        chunk_size=100,
        chunk_overlap=10,
        splitter="semantic",
        tokenizer="cl100k_base",
        version="v1",
    )
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=str(profile["profile_id"]),
        markdown_hash="markdown-v1",
        profile_config_hash=str(profile["config_hash"]),
    )
    storage.replace_global_chunks(
        chunk_set_id=str(chunk_set["chunk_set_id"]),
        chunks=[
            {"chunk_index": 0, "content": "alpha", "token_count": 1},
            {"chunk_index": 1, "content": "beta", "token_count": 1},
            {"chunk_index": 2, "content": "gamma", "token_count": 1},
        ],
    )
    return {"profile": profile, "chunk_set": chunk_set}


def test_chunk_set_identity_includes_actual_profile_contract_and_ready_rows_are_immutable(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        profile = seeded["profile"]
        first = seeded["chunk_set"]
        original = storage._conn.execute(
            "SELECT chunk_id, content, created_at FROM global_chunks WHERE chunk_set_id = ? ORDER BY chunk_index",
            (first["chunk_set_id"],),
        ).fetchall()

        reused = storage.get_or_create_file_chunk_set(
            file_url=str(first["file_url"]),
            profile_id=str(profile["profile_id"]),
            markdown_hash="markdown-v1",
            profile_config_hash=str(profile["config_hash"]),
        )
        no_op = storage.replace_global_chunks(
            chunk_set_id=str(first["chunk_set_id"]),
            chunks=[{"chunk_index": 0, "content": "must-not-overwrite"}],
            overwrite=True,
        )
        changed = storage.get_or_create_file_chunk_set(
            file_url=str(first["file_url"]),
            profile_id=str(profile["profile_id"]),
            markdown_hash="markdown-v1",
            profile_config_hash="different-contract-hash",
        )

        assert reused["chunk_set_id"] == first["chunk_set_id"]
        assert changed["chunk_set_id"] != first["chunk_set_id"]
        assert no_op["replaced"] is False
        assert storage._conn.execute(
            "SELECT chunk_id, content, created_at FROM global_chunks WHERE chunk_set_id = ? ORDER BY chunk_index",
            (first["chunk_set_id"],),
        ).fetchall() == original
    finally:
        storage.close()


def test_chunk_generation_failure_leaves_building_set_and_retry_publishes_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.api.services.files_write import generate_file_chunk_sets
    from ai_actuarial.rag.exceptions import ChunkingException

    db_path = tmp_path / "retry.db"
    file_url = "https://example.test/retry.pdf"
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            file_url,
            "file-hash",
            "Retry",
            "test",
            None,
            "retry.pdf",
            "retry.pdf",
            10,
            "application/pdf",
        )
        storage.update_file_markdown(file_url, "# Retry", "manual")
        profile = storage.create_chunk_profile(
            name="retry-profile",
            chunk_size=100,
            chunk_overlap=10,
        )
    finally:
        storage.close()

    monkeypatch.setattr(
        "ai_actuarial.rag.semantic_chunking.SemanticChunker.chunk_document",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ChunkingException("boom")),
    )
    with pytest.raises(Exception, match="boom"):
        generate_file_chunk_sets(
            db_path=str(db_path),
            file_url=file_url,
            payload={"profile_id": profile["profile_id"]},
        )

    storage = Storage(str(db_path))
    try:
        failed_row = storage._conn.execute(
            "SELECT chunk_set_id, status, chunk_count FROM file_chunk_sets"
        ).fetchone()
        assert failed_row[1:] == ("building", 0)
    finally:
        storage.close()

    monkeypatch.setattr(
        "ai_actuarial.rag.semantic_chunking.SemanticChunker.chunk_document",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                chunk_index=0,
                content="retry chunk",
                token_count=2,
                section_hierarchy="Retry",
            )
        ],
    )
    retried = generate_file_chunk_sets(
        db_path=str(db_path),
        file_url=file_url,
        payload={"profile_id": profile["profile_id"]},
    )

    assert retried["chunk_set_id"] == failed_row[0]
    assert retried["chunk_count"] == 1
    assert retried["reused_existing"] is False
    storage = Storage(str(db_path))
    try:
        ready_row = storage._conn.execute(
            "SELECT status, chunk_count FROM file_chunk_sets WHERE chunk_set_id = ?",
            (failed_row[0],),
        ).fetchone()
        assert ready_row == ("ready", 1)
    finally:
        storage.close()


def test_embedding_identity_excludes_credentials_and_runtime_tuning() -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity

    first = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_batch_size=10,
            api_key="secret-one",
            api_base_url="https://api.example.test/v1?token=secret",
            openai_timeout=10,
        ),
        dimension=3,
    )
    same = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_batch_size=99,
            api_key="secret-two",
            api_base_url="https://API.EXAMPLE.TEST/v1/",
            openai_timeout=999,
        ),
        dimension=3,
    )
    different_dimension = compute_embedding_identity(first.config, dimension=4)
    different_endpoint = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            api_base_url="https://other.example.test/v1",
        ),
        dimension=3,
    )

    assert first.embedding_identity_key == same.embedding_identity_key
    assert first.config_fingerprint == same.config_fingerprint
    assert first.embedding_identity_key != different_dimension.embedding_identity_key
    assert first.embedding_identity_key != different_endpoint.embedding_identity_key
    assert "secret" not in json.dumps(first.as_dict())


def test_embedding_identity_keeps_semantic_query_but_filters_credentials() -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity

    first = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            api_key="config-secret-a",
            api_base_url=(
                "https://api.example.test/v1?deployment=a&api-version=2025-01-01"
                "&api_key=query-secret-a&token=query-token-a"
            ),
        ),
        dimension=3,
    )
    reordered = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            api_key="config-secret-b",
            api_base_url=(
                "https://API.EXAMPLE.TEST/v1/?token=query-token-b&api_key=query-secret-b"
                "&api-version=2025-01-01&deployment=a"
            ),
        ),
        dimension=3,
    )
    different_deployment = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            api_base_url="https://api.example.test/v1?deployment=b&api-version=2025-01-01",
        ),
        dimension=3,
    )
    different_api_version = compute_embedding_identity(
        RAGConfig(
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            api_base_url="https://api.example.test/v1?deployment=a&api-version=2026-01-01",
        ),
        dimension=3,
    )

    assert first.embedding_identity_key == reordered.embedding_identity_key
    assert first.config_fingerprint == reordered.config_fingerprint
    assert different_deployment.embedding_identity_key != first.embedding_identity_key
    assert different_api_version.embedding_identity_key != first.embedding_identity_key
    safe = json.dumps(first.as_dict(), sort_keys=True)
    for secret in (
        "config-secret-a",
        "query-secret-a",
        "query-token-a",
        "api.example.test/v1?",
    ):
        assert secret not in safe


@pytest.mark.parametrize(
    ("model", "dimension"),
    [
        ("text-embedding-v4", 1024),
        ("qwen3-vl-embedding", 2560),
    ],
)
def test_qwen_embedding_identity_uses_server_default_dimension(
    model: str,
    dimension: int,
) -> None:
    from ai_actuarial.ai_runtime import infer_embedding_dimension
    from ai_actuarial.embedding_service import compute_embedding_identity

    assert infer_embedding_dimension(model) == dimension
    identity = compute_embedding_identity(
        RAGConfig(embedding_provider="qwen", embedding_model=model)
    )
    assert identity.provider == "qwen"
    assert identity.model == model
    assert identity.dimension == dimension


def test_supported_default_embedding_models_have_known_dimensions() -> None:
    from ai_actuarial.ai_runtime import (
        infer_embedding_dimension,
        is_embedding_provider_supported,
    )
    from ai_actuarial.llm_models import DEFAULT_MODELS

    expected_dimensions = {
        ("siliconflow", "Qwen/Qwen3-Embedding-8B"): 4096,
        ("siliconflow", "Qwen/Qwen3-Embedding-4B"): 2560,
        ("siliconflow", "Qwen/Qwen3-Embedding-0.6B"): 1024,
        ("siliconflow", "BAAI/bge-large-en-v1.5"): 1024,
        ("zhipuai", "embedding-3"): 2048,
        ("minimax", "embo-01"): 1536,
    }
    supported_models = {
        (provider, str(model["name"]))
        for provider, models in DEFAULT_MODELS.items()
        if is_embedding_provider_supported(provider)
        for model in models
        if "embeddings" in model.get("types", [])
    }
    dimensions = {
        key: infer_embedding_dimension(key[1]) for key in supported_models
    }

    assert all(
        type(dimension) is int and dimension > 0
        for dimension in dimensions.values()
    ), dimensions
    assert {key: dimensions[key] for key in expected_dimensions} == expected_dimensions


def test_embedding_coverage_exposes_server_owned_qwen_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.api.services.ops_read import get_embedding_coverage

    db_path = tmp_path / "qwen-coverage.db"
    storage = Storage(str(db_path))
    try:
        seeded = _seed_chunks(storage)
        chunk_set_id = str(seeded["chunk_set"]["chunk_set_id"])
    finally:
        storage.close()

    monkeypatch.setattr(
        RAGConfig,
        "from_config",
        classmethod(
            lambda cls, *, storage=None: cls(
                embedding_provider="qwen",
                embedding_model="qwen3-vl-embedding",
            )
        ),
    )

    coverage = get_embedding_coverage(
        db_path=str(db_path),
        chunk_set_ids=[chunk_set_id],
        file_urls=[],
        profile_id=None,
        embedding_identity_key=None,
    )

    assert coverage["provider"] == "qwen"
    assert coverage["model"] == "qwen3-vl-embedding"
    assert coverage["dimension"] == 2560
    assert coverage["expected_count"] == 3
    assert coverage["missing"] == 3


class _FakeGenerator:
    def __init__(self, batches: list[list[list[float]]]) -> None:
        self._batches = list(batches)
        self.calls: list[list[str]] = []

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return self._batches.pop(0)


def test_ensure_embeddings_reuses_valid_rows_and_repairs_only_one_invalid_row(tmp_path: Path) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity, ensure_chunk_embeddings

    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        chunk_set_id = str(seeded["chunk_set"]["chunk_set_id"])
        chunks = storage.list_chunks_for_embedding([chunk_set_id])
        identity = compute_embedding_identity(
            RAGConfig(
                embedding_provider="local",
                embedding_model="test-model",
                embedding_cache_enabled=False,
            ),
            dimension=3,
        )
        first_generator = _FakeGenerator(
            [[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]]
        )
        first = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=first_generator,
            batch_size=10,
        )
        second_generator = _FakeGenerator([])
        second = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=second_generator,
            batch_size=10,
        )
        broken_chunk_id = str(chunks[1]["chunk_id"])
        storage._conn.execute(
            "UPDATE chunk_embeddings SET vector_json = ? WHERE chunk_id = ? AND embedding_identity_key = ?",
            (json.dumps([[1.0, 2.0, 3.0]]), broken_chunk_id, identity.embedding_identity_key),
        )
        storage._conn.commit()
        repair_generator = _FakeGenerator([[[0.25, 0.5, 0.75]]])
        repaired = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=repair_generator,
            batch_size=10,
        )

        assert first.generated == 3
        assert second.reused == 3
        assert second_generator.calls == []
        assert repaired.invalid_regenerated == 1
        assert repair_generator.calls == [["beta"]]
        assert storage.embedding_coverage(
            chunk_set_ids=[chunk_set_id], identity=identity.as_dict()
        )["ready_count"] == 3
    finally:
        storage.close()


def test_ensure_embeddings_persists_completed_batch_then_stops_before_next_batch(
    tmp_path: Path,
) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity, ensure_chunk_embeddings

    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        chunks = storage.list_chunks_for_embedding(
            [str(seeded["chunk_set"]["chunk_set_id"])]
        )
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="test-model"),
            dimension=3,
        )
        stopped = False

        class StopAfterFirst:
            calls: list[list[str]] = []

            def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
                nonlocal stopped
                self.calls.append(texts)
                stopped = True
                return [[1.0, 0.0, 0.0]]

        generator = StopAfterFirst()
        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=generator,
            batch_size=1,
            stop_check=lambda: stopped,
        )

        assert generator.calls == [["alpha"]]
        assert result.stopped is True
        assert result.generated == 1
        assert result.ready_count == 1
        assert result.persisted_record_count == 1
    finally:
        storage.close()


def test_ensure_embeddings_rechecks_stop_after_only_persisted_batch(
    tmp_path: Path,
) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity, ensure_chunk_embeddings

    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        chunks = storage.list_chunks_for_embedding(
            [str(seeded["chunk_set"]["chunk_set_id"])]
        )[:1]
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="test-model"),
            dimension=3,
        )
        stopped = False

        class StopDuringOnlyBatch:
            def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
                nonlocal stopped
                assert texts == ["alpha"]
                stopped = True
                return [[1.0, 0.0, 0.0]]

        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=StopDuringOnlyBatch(),
            batch_size=1,
            stop_check=lambda: stopped,
        )

        assert result.stopped is True
        assert result.generated == 1
        assert result.ready_count == 1
        assert result.persisted_record_count == 1
    finally:
        storage.close()


def test_provider_count_mismatch_fails_whole_batch_without_persisting(
    tmp_path: Path,
) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity, ensure_chunk_embeddings

    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        chunks = storage.list_chunks_for_embedding(
            [str(seeded["chunk_set"]["chunk_set_id"])]
        )[:2]
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="test-model"),
            dimension=3,
        )
        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=_FakeGenerator([[[1.0, 0.0, 0.0]]]),
            batch_size=2,
        )

        assert result.failed == 2
        assert {error["code"] for error in result.errors} == {"provider_count_mismatch"}
        assert storage._conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0
    finally:
        storage.close()


def test_concurrent_embedding_upserts_keep_one_identity_row(tmp_path: Path) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity

    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        seeded = _seed_chunks(storage)
        chunk_id = str(
            storage.list_chunks_for_embedding(
                [str(seeded["chunk_set"]["chunk_set_id"])]
            )[0]["chunk_id"]
        )
    finally:
        storage.close()
    identity = compute_embedding_identity(
        RAGConfig(embedding_provider="local", embedding_model="test-model"),
        dimension=3,
    )

    def upsert(_: int) -> None:
        worker = Storage(str(db_path))
        try:
            worker.batch_upsert_chunk_embeddings(
                [{"chunk_id": chunk_id, "vector": [1.0, 2.0, 3.0]}],
                identity=identity.as_dict(),
            )
        finally:
            worker.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(upsert, range(8)))

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*) FROM chunk_embeddings
            WHERE chunk_id = ? AND embedding_identity_key = ?
            """,
            (chunk_id, identity.embedding_identity_key),
        ).fetchone()[0] == 1


def test_openai_provider_response_order_is_validated() -> None:
    from ai_actuarial.rag.embeddings import EmbeddingGenerator
    from ai_actuarial.rag.exceptions import EmbeddingException

    class Item:
        def __init__(self, index: int) -> None:
            self.index = index
            self.embedding = [1.0, 2.0, 3.0]

    class Embeddings:
        def create(self, **_kwargs: object) -> object:
            return type("Response", (), {"data": [Item(1), Item(0)]})()

    generator = object.__new__(EmbeddingGenerator)
    generator.config = RAGConfig(
        embedding_provider="openai",
        embedding_model="test-model",
        openai_max_retries=1,
    )
    generator.openai_client = type("Client", (), {"embeddings": Embeddings()})()

    with pytest.raises(EmbeddingException, match="provider_item_order_mismatch"):
        generator._generate_openai_batch_with_retry(["first", "second"])


@pytest.mark.parametrize(
    "items",
    [
        [SimpleNamespace(embedding=[1.0]), SimpleNamespace(index=1, embedding=[2.0])],
        [SimpleNamespace(index="0", embedding=[1.0]), SimpleNamespace(index=1, embedding=[2.0])],
        [SimpleNamespace(index=False, embedding=[1.0]), SimpleNamespace(index=1, embedding=[2.0])],
        [SimpleNamespace(index=0, embedding=[1.0]), SimpleNamespace(index=0, embedding=[2.0])],
        [SimpleNamespace(index=1, embedding=[1.0]), SimpleNamespace(index=0, embedding=[2.0])],
    ],
    ids=["missing", "string", "bool", "duplicate", "mismatch"],
)
def test_openai_provider_requires_explicit_exact_integer_indices(items: list[SimpleNamespace]) -> None:
    from ai_actuarial.rag.embeddings import EmbeddingGenerator

    generator = EmbeddingGenerator.__new__(EmbeddingGenerator)
    generator.config = SimpleNamespace(
        embedding_model="test-model",
        openai_max_retries=1,
    )
    generator.openai_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(data=items))
    )

    with pytest.raises(Exception, match="provider_item_order_mismatch"):
        generator._generate_openai_batch_with_retry(["a", "b"])


def test_ready_zero_chunk_set_is_immutable_in_storage(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "ready-zero.db"))
    try:
        storage.insert_file(
            "https://example.test/zero.pdf", "hash", "Zero", "test", None,
            "zero.pdf", "zero.pdf", 1, "application/pdf",
        )
        profile = storage.create_chunk_profile(name="zero", chunk_size=100, chunk_overlap=10)
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url="https://example.test/zero.pdf",
            profile_id=str(profile["profile_id"]),
            markdown_hash="markdown-hash",
            profile_config_hash=str(profile["config_hash"]),
            status="ready",
        )
        before = storage._conn.execute(
            "SELECT status, chunk_count, updated_at FROM file_chunk_sets WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        ).fetchone()

        with pytest.raises(ValueError, match="ready chunk set"):
            storage.replace_global_chunks(
                chunk_set_id=str(chunk_set["chunk_set_id"]),
                chunks=[{"chunk_index": 0, "content": "must not write", "token_count": 3}],
            )

        after = storage._conn.execute(
            "SELECT status, chunk_count, updated_at FROM file_chunk_sets WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        ).fetchone()
        assert after == before == ("ready", 0, chunk_set["updated_at"])
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM global_chunks WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        ).fetchone()[0] == 0
    finally:
        storage.close()


def test_ready_zero_chunk_set_is_not_repaired_by_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.api.services.files_write import generate_file_chunk_sets

    db_path = tmp_path / "ready-zero-service.db"
    file_url = "https://example.test/zero.pdf"
    markdown = "# Zero"
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            file_url, "hash", "Zero", "test", None,
            "zero.pdf", "zero.pdf", 1, "application/pdf",
        )
        storage.update_file_markdown(file_url, markdown, "manual")
        profile = storage.create_chunk_profile(name="zero", chunk_size=100, chunk_overlap=10)
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=str(profile["profile_id"]),
            markdown_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            profile_config_hash=str(profile["config_hash"]),
            status="ready",
        )
        before = (chunk_set["status"], chunk_set["chunk_count"], chunk_set["updated_at"])
    finally:
        storage.close()

    monkeypatch.setattr(
        "ai_actuarial.rag.semantic_chunking.SemanticChunker.chunk_document",
        lambda *_args, **_kwargs: pytest.fail("ready/0 must fail before chunking"),
    )
    with pytest.raises(Exception, match="ready chunk set"):
        generate_file_chunk_sets(
            db_path=str(db_path),
            file_url=file_url,
            payload={"profile_id": profile["profile_id"]},
        )

    storage = Storage(str(db_path))
    try:
        after = storage._conn.execute(
            "SELECT status, chunk_count, updated_at FROM file_chunk_sets WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        ).fetchone()
        assert after == before
        assert storage._conn.execute("SELECT COUNT(*) FROM global_chunks").fetchone()[0] == 0
    finally:
        storage.close()


@pytest.mark.parametrize(
    "bad_vector",
    [
        [[1.0, 2.0, 3.0]],
        [1.0, "bad", 3.0],
        [1.0, math.nan, 3.0],
        [1.0, math.inf, 3.0],
        [1.0, 2.0],
    ],
)
def test_provider_invalid_item_is_not_persisted_and_error_is_sanitized(
    tmp_path: Path, bad_vector: list[object]
) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity, ensure_chunk_embeddings

    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        chunks = storage.list_chunks_for_embedding([str(seeded["chunk_set"]["chunk_set_id"])])[:1]
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="secret-text-model"),
            dimension=3,
        )
        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=_FakeGenerator([[bad_vector]]),
            batch_size=1,
        )

        assert result.failed == 1
        assert result.errors == [
            {
                "chunk_id": chunks[0]["chunk_id"],
                "provider": "local",
                "model": "secret-text-model",
                "dimension": 3,
                "code": "invalid_embedding_vector",
            }
        ]
        assert storage._conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0
        assert "alpha" not in json.dumps(result.as_dict())
        assert "[1.0" not in json.dumps(result.as_dict())
    finally:
        storage.close()


def test_oversized_vector_json_is_rejected_before_json_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_actuarial.embedding_service import compute_embedding_identity

    storage = Storage(str(tmp_path / "index.db"))
    try:
        seeded = _seed_chunks(storage)
        chunk_set_id = str(seeded["chunk_set"]["chunk_set_id"])
        chunk_id = str(storage.list_chunks_for_embedding([chunk_set_id])[0]["chunk_id"])
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="test-model"), dimension=3
        )
        storage._conn.execute(
            """
            INSERT INTO chunk_embeddings(
                chunk_id, embedding_identity_key, embedding_provider, embedding_model,
                dimension, config_fingerprint, vector_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', 'now', 'now')
            """,
            (
                chunk_id,
                identity.embedding_identity_key,
                identity.provider,
                identity.model,
                identity.dimension,
                identity.config_fingerprint,
                "[" + ("0," * 1_100_000) + "0]",
            ),
        )
        storage._conn.commit()
        real_conn = storage._conn

        class CursorProbe:
            def __init__(self, cursor: sqlite3.Cursor) -> None:
                self._cursor = cursor

            def fetchall(self) -> list[tuple[object, ...]]:
                rows = self._cursor.fetchall()
                assert rows[0][5] is None
                assert int(rows[0][6]) > 2_000_000
                return rows

        class ConnectionProbe:
            def execute(self, statement: str, params: tuple[object, ...]) -> CursorProbe:
                assert "CASE" in statement
                assert "length(CAST(vector_json AS BLOB))" in statement
                return CursorProbe(real_conn.execute(statement, params))

        storage._conn = ConnectionProbe()  # type: ignore[assignment]
        monkeypatch.setattr(json, "loads", lambda _value: (_ for _ in ()).throw(AssertionError("parsed")))

        try:
            result = storage.read_valid_chunk_embeddings(
                [chunk_id], identity=identity.as_dict()
            )
        finally:
            storage._conn = real_conn

        assert result["valid"] == {}
        assert result["invalid_chunk_ids"] == [chunk_id]
    finally:
        storage.close()


@pytest.mark.parametrize("with_rows", [False, True])
def test_v7_embedding_schema_migrates_empty_and_nonempty_tables_without_reusing_legacy_rows(
    tmp_path: Path, with_rows: bool
) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_status

    db_path = tmp_path / "legacy-v7.db"
    expected = _downgrade_chunk_tables_to_v7(db_path, with_rows=with_rows)

    before = schema_status(db_path)
    assert before["state"] == "needs_migration"
    migrated = apply_schema(db_path)

    assert migrated["state"] == "current"
    assert migrated["applied_migrations"] == [
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
    ]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        embedding_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(chunk_embeddings)")
        }
        assert {"embedding_identity_key", "embedding_provider", "dimension", "status"}.issubset(
            embedding_columns
        )
        if with_rows:
            chunk_set = conn.execute(
                "SELECT chunk_set_id, profile_config_hash, chunk_count FROM file_chunk_sets"
            ).fetchone()
            assert chunk_set == (
                expected["chunk_set_id"],
                expected["profile_config_hash"],
                3,
            )
            legacy = conn.execute(
                """
                SELECT embedding_identity_key, embedding_provider, embedding_model,
                       dimension, vector_json, status, failure_reason
                FROM chunk_embeddings
                """
            ).fetchone()
            assert legacy[0].startswith("legacy:")
            assert legacy[1:] == (
                "legacy",
                "legacy-model",
                3,
                "[1,2,3]",
                "legacy_unusable",
                "legacy_identity_unavailable",
            )
        else:
            assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0


def test_v7_embedding_schema_rejects_missing_prerequisite_column(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_status, SchemaMigrationError

    db_path = tmp_path / "broken-v7.db"
    _downgrade_chunk_tables_to_v7(db_path, with_rows=False)
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE chunk_embeddings DROP COLUMN vector_json")

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    with pytest.raises(SchemaMigrationError, match="not safe to migrate"):
        apply_schema(db_path)
