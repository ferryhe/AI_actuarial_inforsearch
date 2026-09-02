"""Issue #220 — immutable-stage write-entry guards + runtime fail-closed + versioned record.

Covers the acceptance criteria:

- [ ] 变更切块策略或 embedding 模型/维度时，不带 full_reindex 的保存被拒绝
- [ ] 运行时对不可变配置变更 fail-closed，不静默产出不兼容产物
- [ ] manifest_version / taxonomy 版本变更走迁移契约，可回溯
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

import ai_actuarial.api.services.ops_write as ops_write
import ai_actuarial.api.services.rag_admin as rag_admin
from ai_actuarial.api.services.ops_write import OpsWriteError, update_ai_routing
from ai_actuarial.api.services.rag_admin import RagAdminError, update_chunk_profile
from ai_actuarial.embedding_service import UnsupportedOptionsError
from ai_actuarial.manifest_ingest import ingest_manifest
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime

# ---------------------------------------------------------------------------
# A. embeddings immutable hard intercept (write entry)
# ---------------------------------------------------------------------------


def _patch_routing_io(monkeypatch: pytest.MonkeyPatch, config_data: dict) -> None:
    monkeypatch.setattr(ops_write, "_load_config_data", lambda: config_data)
    monkeypatch.setattr(ops_write, "_write_config_data", lambda data: None)
    monkeypatch.setattr(ops_write, "_notify_site_config_updated", lambda *a, **k: None)
    monkeypatch.setattr(ops_write, "_reload_runtime_caches", lambda: None)
    monkeypatch.setattr(ops_write, "get_ai_routing", lambda **_kw: {})


def _make_kb_in_use(db_path: str, kb_id: str = "kb-1") -> None:
    """Create a KB that holds indexed content (chunk_count > 0) so the
    embeddings in-use guard treats it as invalidated by a config change."""
    storage = Storage(db_path)
    try:
        KnowledgeBaseManager(storage).create_kb(
            kb_id=kb_id,
            name="KB 1",
            kb_mode="manual",
            manifest_profile="general",
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET chunk_count = 1 WHERE kb_id = ?",
            (kb_id,),
        )
        storage._conn.commit()
    finally:
        storage.close()


def test_embeddings_model_change_without_full_reindex_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {
        "ai_config": {"embeddings": {"provider": "openai", "model": "text-embedding-3-large"}}
    }
    _patch_routing_io(monkeypatch, config)
    db_path = str(tmp_path / "index.db")
    _make_kb_in_use(db_path)
    with pytest.raises(OpsWriteError, match="full_reindex"):
        update_ai_routing(
            {
                "bindings": [
                    {
                        "function_name": "embeddings",
                        "provider": "openai",
                        "model": "text-embedding-3-small",
                    }
                ]
            },
            db_path=db_path,
        )


def test_embeddings_provider_change_without_full_reindex_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = {
        "ai_config": {"embeddings": {"provider": "openai", "model": "text-embedding-3-large"}}
    }
    _patch_routing_io(monkeypatch, config)
    db_path = str(tmp_path / "index.db")
    _make_kb_in_use(db_path)
    with pytest.raises(OpsWriteError, match="full_reindex"):
        update_ai_routing(
            {
                "bindings": [
                    {
                        "function_name": "embeddings",
                        "provider": "qwen",
                        "model": "text-embedding-v3",
                    }
                ]
            },
            db_path=db_path,
        )


def test_embeddings_model_change_with_full_reindex_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {
        "ai_config": {"embeddings": {"provider": "openai", "model": "text-embedding-3-large"}}
    }
    _patch_routing_io(monkeypatch, config)
    result = update_ai_routing(
        {
            "full_reindex": True,
            "bindings": [
                {
                    "function_name": "embeddings",
                    "provider": "openai",
                    "model": "text-embedding-3-small",
                }
            ],
        },
        db_path=":memory:",
    )
    assert result["success"] is True
    # Soft info is still returned for the downstream atomic rebuild step.
    assert result["rebuild_required"] is True
    assert result["affected_kb_ids"] == []


def test_embeddings_same_model_knob_update_is_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    config = {
        "ai_config": {"embeddings": {"provider": "openai", "model": "text-embedding-3-large"}}
    }
    _patch_routing_io(monkeypatch, config)
    result = update_ai_routing(
        {
            "bindings": [
                {
                    "function_name": "embeddings",
                    "provider": "openai",
                    "model": "text-embedding-3-large",
                    "batch_size": 64,
                }
            ]
        },
        db_path=":memory:",
    )
    assert result["success"] is True


# ---------------------------------------------------------------------------
# A.1 _has_indexed_knowledge_bases fail-closed semantics (#220 review)
# ---------------------------------------------------------------------------


class _RaisingConnection:
    """Stand-in for ``Storage._conn`` whose ``execute`` raises on demand."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise self._exc


class _FakeStorage:
    def __init__(self, db_path: str) -> None:
        self._conn = _RaisingConnection(self._execute_exc)

    def close(self) -> None:
        pass


def _patch_storage_raise(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    _FakeStorage._execute_exc = exc
    monkeypatch.setattr(ops_write, "Storage", _FakeStorage)


def test_has_indexed_knowledge_bases_fails_closed_on_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_storage_raise(monkeypatch, RuntimeError("database is locked"))
    # A transient/unknown failure must NOT be treated as "nothing indexed".
    assert ops_write._has_indexed_knowledge_bases(":memory:") is True


def test_has_indexed_knowledge_bases_fails_closed_on_operational_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_storage_raise(monkeypatch, sqlite3.OperationalError("database is locked"))
    assert ops_write._has_indexed_knowledge_bases(":memory:") is True


def test_has_indexed_knowledge_bases_allows_missing_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_storage_raise(
        monkeypatch, sqlite3.OperationalError("no such table: rag_knowledge_bases")
    )
    # A fresh/empty DB (no such table) is the one safe fail-open case.
    assert ops_write._has_indexed_knowledge_bases(":memory:") is False


# ---------------------------------------------------------------------------
# B. chunk profile immutable intercept (write entry)
# ---------------------------------------------------------------------------


def _make_profile_in_use(storage: Storage, profile_id: str) -> None:
    storage.upsert_file(
        url="https://example.com/doc.md",
        sha256="deadbeef",
        title=None,
        source_site="",
        source_page_url=None,
        original_filename=None,
        local_path="",
        bytes_size=None,
        content_type=None,
        last_modified=None,
        etag=None,
        published_time=None,
    )
    storage.get_or_create_file_chunk_set(
        file_url="https://example.com/doc.md",
        profile_id=profile_id,
        markdown_hash="hash",
    )
    storage._conn.execute(
        "UPDATE file_chunk_sets SET chunk_count = 1 WHERE profile_id = ?", (profile_id,)
    )
    storage._conn.commit()


def _make_profile(db_path: str, *, chunk_size: int = 800, chunk_overlap: int = 100) -> dict:
    storage = Storage(db_path)
    try:
        return storage.create_chunk_profile(
            name="profile-a",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
            metadata={},
        )
    finally:
        storage.close()


def test_chunk_profile_immutable_change_in_use_requires_full_reindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag_admin, "_require_config_write_token", lambda *a, **k: None)
    db_path = str(tmp_path / "index.db")
    profile = _make_profile(db_path)
    storage = Storage(db_path)
    try:
        _make_profile_in_use(storage, profile["profile_id"])
    finally:
        storage.close()

    with pytest.raises(RagAdminError, match="full_reindex"):
        update_chunk_profile(
            db_path=db_path,
            profile_id=profile["profile_id"],
            payload={"chunk_size": 300},
            headers={},
        )


def test_chunk_profile_immutable_change_in_use_rejected_even_with_legacy_full_reindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag_admin, "_require_config_write_token", lambda *a, **k: None)
    db_path = str(tmp_path / "index.db")
    profile = _make_profile(db_path)
    storage = Storage(db_path)
    try:
        _make_profile_in_use(storage, profile["profile_id"])
    finally:
        storage.close()

    with pytest.raises(RagAdminError, match="create a new profile"):
        update_chunk_profile(
            db_path=db_path,
            profile_id=profile["profile_id"],
            payload={"chunk_size": 300, "full_reindex": True},
            headers={},
        )

    storage = Storage(db_path)
    try:
        unchanged = storage.get_chunk_profile(profile["profile_id"])
    finally:
        storage.close()
    assert unchanged["chunk_size"] == profile["chunk_size"]
    assert unchanged["config_hash"] == profile["config_hash"]


def test_chunk_profile_immutable_change_not_in_use_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag_admin, "_require_config_write_token", lambda *a, **k: None)
    db_path = str(tmp_path / "index.db")
    profile = _make_profile(db_path)  # never bound to any chunk data

    result = update_chunk_profile(
        db_path=db_path,
        profile_id=profile["profile_id"],
        payload={"chunk_size": 300},
        headers={},
    )
    assert result["profile"]["chunk_size"] == 300


def test_chunk_profile_name_change_is_always_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag_admin, "_require_config_write_token", lambda *a, **k: None)
    db_path = str(tmp_path / "index.db")
    profile = _make_profile(db_path)
    storage = Storage(db_path)
    try:
        _make_profile_in_use(storage, profile["profile_id"])
    finally:
        storage.close()

    result = update_chunk_profile(
        db_path=db_path,
        profile_id=profile["profile_id"],
        payload={"name": "renamed-profile"},
        headers={},
    )
    assert result["profile"]["name"] == "renamed-profile"


def test_chunk_profile_update_resulting_in_duplicate_config_hash_is_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rag_admin, "_require_config_write_token", lambda *a, **k: None)
    db_path = str(tmp_path / "index.db")
    profile = _make_profile(db_path, chunk_size=800)
    storage = Storage(db_path)
    try:
        # A second profile already holds the exact config the update would
        # collapse into (chunk_size=300 + same splitter/tokenizer/version/
        # metadata) -> config_hash UNIQUE collision.
        storage.create_chunk_profile(
            name="profile-b",
            chunk_size=300,
            chunk_overlap=100,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
            metadata={},
        )
    finally:
        storage.close()

    with pytest.raises(RagAdminError, match="already exists") as excinfo:
        update_chunk_profile(
            db_path=db_path,
            profile_id=profile["profile_id"],
            payload={"chunk_size": 300},
            headers={},
        )
    assert excinfo.value.status_code == 409


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("chunk_size", "300.5"),
        ("chunk_size", ""),
        ("chunk_size", None),
        ("chunk_size", True),
        ("chunk_size", 300.5),
        ("chunk_overlap", "100.5"),
        ("chunk_overlap", None),
    ],
)
def test_chunk_profile_update_rejects_non_integer_immutable_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    bad_value: Any,
) -> None:
    monkeypatch.setattr(rag_admin, "_require_config_write_token", lambda *a, **k: None)
    db_path = str(tmp_path / "index.db")
    profile = _make_profile(db_path)
    with pytest.raises(RagAdminError, match=f"{field} must be an integer") as excinfo:
        update_chunk_profile(
            db_path=db_path,
            profile_id=profile["profile_id"],
            payload={field: bad_value},
            headers={},
        )
    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# C. runtime fail-closed (chunk side; embeddings side already covered by
#    rag/indexing._ensure_incremental_embedding_compatible)
# ---------------------------------------------------------------------------


def test_kb_committed_chunk_profiles_returns_bound_profiles(tmp_path: Path) -> None:
    db_path = str(tmp_path / "index.db")
    storage = Storage(db_path)
    try:
        profile = storage.create_chunk_profile(
            name="p1",
            chunk_size=800,
            chunk_overlap=100,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
            metadata={},
        )
        storage.upsert_file(
            url="https://example.com/doc.md",
            sha256="deadbeef",
            title=None,
            source_site="",
            source_page_url=None,
            original_filename=None,
            local_path="",
            bytes_size=None,
            content_type=None,
            last_modified=None,
            etag=None,
            published_time=None,
        )
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url="https://example.com/doc.md",
            profile_id=profile["profile_id"],
            markdown_hash="hash",
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET chunk_count = 1 WHERE profile_id = ?",
            (profile["profile_id"],),
        )
        storage._conn.execute(
            "INSERT INTO kb_chunk_bindings (kb_id, file_url, chunk_set_id, bound_at) VALUES (?, ?, ?, ?)",
            ("kb-1", "https://example.com/doc.md", chunk_set["chunk_set_id"], "t"),
        )
        storage._conn.commit()

        committed = storage.kb_committed_chunk_profiles("kb-1")
        assert len(committed) == 1
        assert committed[0]["chunk_size"] == 800
        assert committed[0]["chunk_overlap"] == 100
    finally:
        storage.close()


def _stub_storage(committed: list[dict]) -> object:
    class _Stub:
        def kb_committed_chunk_profiles(self, kb_id: str) -> list[dict]:
            return committed

    return _Stub()


def test_runtime_chunk_fail_closed_on_profile_mismatch() -> None:
    runtime = NativeTaskRuntime()
    storage = _stub_storage(
        [
            {
                "chunk_size": 800,
                "chunk_overlap": 100,
                "splitter": "semantic",
                "tokenizer": "cl100k_base",
            }
        ]
    )
    with pytest.raises(RuntimeError, match="full_reindex"):
        runtime._ensure_chunk_config_compatible(
            storage,
            "kb-1",
            chunk_size=300,
            chunk_overlap=50,
            splitter="semantic",
            tokenizer="cl100k_base",
        )


def test_runtime_chunk_fail_closed_passes_on_matching_profile() -> None:
    runtime = NativeTaskRuntime()
    storage = _stub_storage(
        [
            {
                "chunk_size": 800,
                "chunk_overlap": 100,
                "splitter": "semantic",
                "tokenizer": "cl100k_base",
            }
        ]
    )
    # Should not raise.
    runtime._ensure_chunk_config_compatible(
        storage,
        "kb-1",
        chunk_size=800,
        chunk_overlap=100,
        splitter="semantic",
        tokenizer="cl100k_base",
    )


def test_runtime_chunk_fail_closed_passes_without_committed_chunks() -> None:
    runtime = NativeTaskRuntime()
    storage = _stub_storage([])
    runtime._ensure_chunk_config_compatible(
        storage,
        "kb-1",
        chunk_size=300,
        chunk_overlap=50,
        splitter="semantic",
        tokenizer="cl100k_base",
    )


def test_runtime_chunk_generation_rejects_legacy_kb_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Removed KB options must be rejected before chunk generation runs, even
    # when the saved data already has committed chunks.
    db_path = str(tmp_path / "index.db")
    file_url = "https://example.com/wired.md"
    storage = Storage(db_path)
    try:
        KnowledgeBaseManager(storage).create_kb(
            kb_id="kb-1",
            name="KB 1",
            kb_mode="manual",
            manifest_profile="general",
        )
        storage.insert_file(
            url=file_url,
            sha256="sha-wired",
            title="Wired",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="wired.md",
            local_path=str(tmp_path / "wired.md"),
            bytes=12,
            content_type="text/markdown",
        )
        storage.upsert_catalog_item(
            item={
                "url": file_url,
                "sha256": "sha-wired",
                "keywords": ["wired"],
                "summary": "Wired",
                "category": "Docs",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(file_url, "# Wired", "manual")
        profile = storage.create_chunk_profile(
            name="committed-profile",
            chunk_size=800,
            chunk_overlap=100,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
            metadata={},
        )
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=profile["profile_id"],
            markdown_hash="wired-hash",
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET chunk_count = 1 WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        )
        storage._conn.execute(
            "INSERT INTO kb_chunk_bindings (kb_id, file_url, chunk_set_id, bound_at) VALUES (?, ?, ?, ?)",
            ("kb-1", file_url, chunk_set["chunk_set_id"], "t"),
        )
        storage._conn.commit()
    finally:
        storage.close()

    storage = Storage(db_path)
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        lambda **kwargs: {"chunk_set_id": "cs-wired", "chunk_count": 1, "reused_existing": False},
    )
    try:
        with pytest.raises(UnsupportedOptionsError, match="unsupported_option: kb_id"):
            runtime._run_chunk_generation(
                "task-wired",
                storage,
                db_path,
                {"kb_id": "kb-1", "chunk_size": 300, "chunk_overlap": 50},
            )
    finally:
        storage.close()


def _seed_kb_with_committed_chunk(
    db_path: str, tmp_path: Path, *, file_url: str, kb_id: str = "kb-1"
) -> None:
    """Seed a KB with a committed chunk profile at (800, 100) so the runtime
    fail-closed guard sees incompatible committed chunk data."""
    storage = Storage(db_path)
    try:
        KnowledgeBaseManager(storage).create_kb(
            kb_id=kb_id,
            name="KB 1",
            kb_mode="manual",
            manifest_profile="general",
        )
        storage.insert_file(
            url=file_url,
            sha256="sha-wired",
            title="Wired",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="wired.md",
            local_path=str(tmp_path / "wired.md"),
            bytes=12,
            content_type="text/markdown",
        )
        storage.upsert_catalog_item(
            item={
                "url": file_url,
                "sha256": "sha-wired",
                "keywords": ["wired"],
                "summary": "Wired",
                "category": "Docs",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(file_url, "# Wired", "manual")
        profile = storage.create_chunk_profile(
            name="committed-profile",
            chunk_size=800,
            chunk_overlap=100,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
            metadata={},
        )
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=profile["profile_id"],
            markdown_hash="wired-hash",
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET chunk_count = 1 WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        )
        storage._conn.execute(
            "INSERT INTO kb_chunk_bindings (kb_id, file_url, chunk_set_id, bound_at) VALUES (?, ?, ?, ?)",
            (kb_id, file_url, chunk_set["chunk_set_id"], "t"),
        )
        storage._conn.commit()
    finally:
        storage.close()


def test_runtime_chunk_generation_rejects_legacy_full_reindex_and_kb_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Issue #237 removes KB binding/reindex from chunk generation entirely.
    db_path = str(tmp_path / "index.db")
    file_url = "https://example.com/wired.md"
    _seed_kb_with_committed_chunk(db_path, tmp_path, file_url=file_url)

    storage = Storage(db_path)
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        lambda **kwargs: {"chunk_count": 1, "reused_existing": False},
    )
    try:
        with pytest.raises(
            UnsupportedOptionsError,
            match="unsupported_option: full_reindex, kb_id",
        ):
            runtime._run_chunk_generation(
                "task-wired",
                storage,
                db_path,
                {"kb_id": "kb-1", "chunk_size": 300, "chunk_overlap": 50, "full_reindex": True},
            )
    finally:
        storage.close()


def test_runtime_chunk_generation_overwrite_noop_does_not_allow_legacy_kb_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # overwrite_same_profile remains a no-op compatibility signal, but it does
    # not make the removed KB option valid.
    db_path = str(tmp_path / "index.db")
    file_url = "https://example.com/wired.md"
    _seed_kb_with_committed_chunk(db_path, tmp_path, file_url=file_url)

    storage = Storage(db_path)
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        lambda **kwargs: {"chunk_count": 1, "reused_existing": False},
    )
    try:
        with pytest.raises(UnsupportedOptionsError, match="unsupported_option: kb_id"):
            runtime._run_chunk_generation(
                "task-wired",
                storage,
                db_path,
                {
                    "kb_id": "kb-1",
                    "chunk_size": 300,
                    "chunk_overlap": 50,
                    "overwrite_same_profile": True,
                },
            )
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# D. manifest schema version traceability
# ---------------------------------------------------------------------------


def test_manifest_schema_version_is_recorded_and_traceable(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        for suffix in ("1", "2"):
            ingest_manifest(
                storage,
                {
                    "manifest_id": f"m{suffix}",
                    "schema_version": "web-listening-manifest.v1",
                    "run": {"run_id": f"run-{suffix}"},
                    "source": {
                        "source_id": f"source-{suffix}",
                        "site_name": f"Source {suffix}",
                        "site_url": f"https://source-{suffix}.example/",
                    },
                    "downloaded_assets": [],
                },
            )
        rows = storage._conn.execute(
            "SELECT manifest_id, schema_version FROM manifest_raw ORDER BY manifest_id"
        ).fetchall()
        versions = {row[0]: row[1] for row in rows}
        assert versions == {
            "m1": "web-listening-manifest.v1",
            "m2": "web-listening-manifest.v1",
        }
    finally:
        storage.close()
