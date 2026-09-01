from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.api.services import rag_admin
from ai_actuarial.embedding_service import EmbeddingIdentity
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage

LARGE_CHUNK_COUNT = 8_704
LARGE_EMBEDDING_DIMENSION = 3_072


def _identity(*, dimension: int) -> EmbeddingIdentity:
    return EmbeddingIdentity(
        embedding_identity_key=f"emb-issue-256-{dimension}",
        provider="local",
        model=f"issue-256-{dimension}",
        dimension=dimension,
        config_fingerprint="issue-256-config",
        config=RAGConfig(
            embedding_provider="local",
            embedding_model=f"issue-256-{dimension}",
            data_dir="unused",
        ),
    )


def _manager(storage: Storage, tmp_path: Path) -> KnowledgeBaseManager:
    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.storage = storage
    manager.config = RAGConfig(
        embedding_provider="local",
        embedding_model="issue-256",
        data_dir=str(tmp_path / "rag"),
    )
    manager.embedding_generator = None
    manager._ensure_rag_tables()
    return manager


def _seed_shared_kbs(
    db_path: Path,
    tmp_path: Path,
    *,
    identity: EmbeddingIdentity,
    kb_ids: tuple[str, ...],
    chunk_count: int,
    embedding_kinds: tuple[str, ...] | None = None,
    create_ready_index: bool = False,
) -> None:
    storage = Storage(str(db_path))
    try:
        manager = _manager(storage, tmp_path)
        file_url = "https://issue-256.test/shared.pdf"
        storage.insert_file(
            url=file_url,
            sha256="issue-256-file",
            title="Issue 256 shared fixture",
            source_site="issue-256.test",
            source_page_url="https://issue-256.test",
            original_filename="shared.pdf",
            local_path=str(tmp_path / "shared.pdf"),
            bytes=128,
            content_type="application/pdf",
        )
        storage.update_file_markdown(file_url, "# Issue 256", "manual")
        profile = storage.create_chunk_profile(
            name=f"issue-256-{chunk_count}",
            chunk_size=128,
            chunk_overlap=16,
        )
        profile_id = str(profile["profile_id"])
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            markdown_hash="issue-256-markdown",
            profile_config_hash=str(profile["config_hash"]),
            status="building",
        )
        storage.replace_global_chunks(
            chunk_set_id=str(chunk_set["chunk_set_id"]),
            chunks=[
                {
                    "chunk_index": index,
                    "content": f"chunk {index}",
                    "token_count": 2,
                    "section_hierarchy": "Issue 256",
                }
                for index in range(chunk_count)
            ],
            overwrite=True,
        )
        chunk_ids = [
            str(row[0])
            for row in storage._conn.execute(
                "SELECT chunk_id FROM global_chunks WHERE chunk_set_id = ? ORDER BY chunk_index",
                (str(chunk_set["chunk_set_id"]),),
            ).fetchall()
        ]
        for kb_id in kb_ids:
            manager.create_kb(
                kb_id=kb_id,
                name=kb_id,
                kb_mode="manual",
                chunk_profile_id=profile_id,
                embedding_provider=identity.provider,
                embedding_model=identity.model,
                embedding_dimension=identity.dimension,
                embedding_identity_key=identity.embedding_identity_key,
            )
            manager.add_files_to_kb(kb_id, [file_url])
            storage.bind_chunk_set_to_kb(
                kb_id=kb_id,
                file_url=file_url,
                chunk_set_id=str(chunk_set["chunk_set_id"]),
                binding_mode="pin",
                bound_by="issue_256_test",
            )

        vector_json = "[" + ",".join("0" for _ in range(identity.dimension)) + "]"
        kinds = embedding_kinds or tuple("ready" for _ in chunk_ids)
        now = storage.now()
        rows = []
        for chunk_id, kind in zip(chunk_ids, kinds, strict=False):
            if kind == "missing":
                continue
            rows.append(
                (
                    chunk_id,
                    identity.embedding_identity_key,
                    identity.provider,
                    identity.model,
                    identity.dimension,
                    identity.config_fingerprint if kind == "ready" else "wrong-config",
                    vector_json,
                    "ready",
                    now,
                    now,
                    now,
                )
            )
        storage._conn.executemany(
            """
            INSERT INTO chunk_embeddings (
                chunk_id, embedding_identity_key, embedding_provider,
                embedding_model, dimension, config_fingerprint, vector_json,
                status, created_at, updated_at, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        storage._conn.commit()

        if create_ready_index:
            storage.create_kb_index_version(
                kb_id=kb_ids[0],
                embedding_provider=identity.provider,
                embedding_model=identity.model,
                embedding_dimension=identity.dimension,
                embedding_identity_key=identity.embedding_identity_key,
                binding_snapshot_fingerprint="bind-issue-256",
                index_type="faiss",
                status="ready",
                artifact_path=str(tmp_path / "index"),
                artifact_digest="issue-256-index",
                chunk_count=len(chunk_ids),
                chunk_ids=chunk_ids,
            )
    finally:
        storage.close()


def _patch_identity(monkeypatch: pytest.MonkeyPatch, identity: EmbeddingIdentity) -> None:
    monkeypatch.setattr(
        rag_admin, "resolve_server_embedding_identity", lambda *_args, **_kwargs: identity
    )
    monkeypatch.setattr(
        rag_admin,
        "_current_embeddings_payload",
        lambda **_kwargs: {
            "provider": identity.provider,
            "model": identity.model,
            "dimension": identity.dimension,
            "embedding_identity_key": identity.embedding_identity_key,
            "configured": True,
        },
    )


def test_kb_list_uses_metadata_coverage_without_deep_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "small.db"
    identity = _identity(dimension=3)
    _seed_shared_kbs(
        db_path,
        tmp_path,
        identity=identity,
        kb_ids=("kb-issue-256",),
        chunk_count=3,
        embedding_kinds=("ready", "wrong-config", "missing"),
        create_ready_index=True,
    )
    _patch_identity(monkeypatch, identity)

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("KB list performed a forbidden deep read")

    monkeypatch.setattr(rag_admin, "resolve_kb_bound_chunks", fail)
    monkeypatch.setattr(rag_admin._KBListStorageView, "read_valid_chunk_embeddings", fail)
    monkeypatch.setattr(
        "ai_actuarial.agentic_rag.ready_data_builder.get_builder_source_fingerprint",
        fail,
    )

    payload = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})

    assert len(payload["knowledge_bases"]) == 1
    kb = payload["knowledge_bases"][0]
    assert kb["index_coverage"] == {
        "bound_file_count": 1,
        "bound_chunk_count": 3,
        "ready_embeddings": 1,
        "missing_embeddings": 2,
        "invalid_bindings": 0,
        "binding_error": "",
    }
    assert kb["agentic_ready_manifest"].get("ready_build_input") is None

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE file_chunk_sets SET status = 'building'")

    invalid_payload = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})
    invalid_coverage = invalid_payload["knowledge_bases"][0]["index_coverage"]
    assert invalid_coverage["ready_embeddings"] == 0
    assert invalid_coverage["invalid_bindings"] == 1


def test_kb_list_rejects_binding_for_non_member_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "mismatched-binding.db"
    identity = _identity(dimension=3)
    _seed_shared_kbs(
        db_path,
        tmp_path,
        identity=identity,
        kb_ids=("kb-issue-256",),
        chunk_count=1,
    )
    _patch_identity(monkeypatch, identity)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE file_chunk_sets SET file_url = ?",
            ("https://issue-256.test/non-member.pdf",),
        )
        conn.execute(
            "UPDATE kb_chunk_bindings SET file_url = ?",
            ("https://issue-256.test/non-member.pdf",),
        )

    coverage = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})["knowledge_bases"][0][
        "index_coverage"
    ]

    assert coverage["invalid_bindings"] == 1
    assert coverage["binding_error"] == "KB chunk binding metadata is invalid"


def test_large_multi_kb_list_is_bounded_and_never_selects_vector_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "large.db"
    identity = _identity(dimension=LARGE_EMBEDDING_DIMENSION)
    _seed_shared_kbs(
        db_path,
        tmp_path,
        identity=identity,
        kb_ids=("kb-large-a", "kb-large-b"),
        chunk_count=LARGE_CHUNK_COUNT,
    )
    _patch_identity(monkeypatch, identity)

    statements: list[str] = []
    original_open = rag_admin._open_kb_list_read_only_connection

    def traced_open(path: str):
        conn = original_open(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(rag_admin, "_open_kb_list_read_only_connection", traced_open)

    started = time.perf_counter()
    cold = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})
    cold_seconds = time.perf_counter() - started
    cold_queries = len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])
    statements.clear()
    started = time.perf_counter()
    warm = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})
    warm_seconds = time.perf_counter() - started
    warm_queries = len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])

    assert len(cold["knowledge_bases"]) == len(warm["knowledge_bases"]) == 2
    for kb in cold["knowledge_bases"]:
        assert kb["index_coverage"]["bound_chunk_count"] == LARGE_CHUNK_COUNT
        assert kb["index_coverage"]["ready_embeddings"] == LARGE_CHUNK_COUNT
        assert kb["index_coverage"]["missing_embeddings"] == 0
    assert all("vector_json" not in sql.lower() for sql in statements)
    assert cold_queries <= 160
    assert warm_queries <= 160
    assert cold_seconds < 1.0
    assert warm_seconds < 0.5
    print(
        "issue256-kb-list-metrics "
        f"rows={LARGE_CHUNK_COUNT} dimension={LARGE_EMBEDDING_DIMENSION} "
        f"cold_queries={cold_queries} warm_queries={warm_queries} "
        f"cold_ms={cold_seconds * 1000:.1f} warm_ms={warm_seconds * 1000:.1f}"
    )


def test_kb_list_select_count_is_invariant_for_multiple_kbs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity(dimension=3)

    def count_selects(db_path: Path, kb_ids: tuple[str, ...]) -> int:
        _seed_shared_kbs(
            db_path,
            tmp_path,
            identity=identity,
            kb_ids=kb_ids,
            chunk_count=1,
            embedding_kinds=("missing",),
        )
        _patch_identity(monkeypatch, identity)
        statements: list[str] = []
        original_open = rag_admin._open_kb_list_read_only_connection

        def traced_open(path: str):
            conn = original_open(path)
            conn.set_trace_callback(statements.append)
            return conn

        monkeypatch.setattr(rag_admin, "_open_kb_list_read_only_connection", traced_open)
        payload = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})
        assert len(payload["knowledge_bases"]) == len(kb_ids)
        return len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])

    one_kb_selects = count_selects(tmp_path / "one-kb.db", ("kb-one",))
    many_kb_selects = count_selects(
        tmp_path / "many-kb.db",
        ("kb-one", "kb-two", "kb-three"),
    )

    assert many_kb_selects == one_kb_selects


def test_kb_list_decodes_only_bounded_publication_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "bounded-publications.db"
    identity = _identity(dimension=3)
    _seed_shared_kbs(
        db_path,
        tmp_path,
        identity=identity,
        kb_ids=("kb-publications",),
        chunk_count=1,
        embedding_kinds=("missing",),
    )
    _patch_identity(monkeypatch, identity)

    storage = Storage(str(db_path))
    try:

        def record(name: str, *, status: str = "validated") -> dict[str, Any]:
            return storage.record_agentic_ready_publication(
                kb_id="kb-publications",
                index_version_id=f"idx-{name}",
                source_version_kind="index",
                source_version_id=f"idx-{name}",
                profile="general",
                profile_version="1",
                status=status,
                output_dir=str(tmp_path / "ready" / name),
                artifact_digest=f"digest-{name}",
                artifact_files=["ready_data_manifest.json"],
                built_at="2026-08-28T12:00:00+00:00",
                source_db=str(db_path),
                schema_versions={"ready_data": "1"},
                error_message=f"{name} failed" if status == "failed" else "",
            )

        previous = record("previous")
        storage.publish_agentic_ready_publication(
            str(previous["publication_id"]),
            expected_active_publication_id=None,
        )
        active = record("active")
        storage.publish_agentic_ready_publication(
            str(active["publication_id"]),
            expected_active_publication_id=str(previous["publication_id"]),
        )
        latest_failed = record("latest-failed", status="failed")
        stale_failed = record("stale-failed", status="failed")
        decode_sentinel = '["issue-256-irrelevant-history-decode-trap"]'
        storage._conn.execute(
            """UPDATE agentic_ready_publications
               SET artifact_files_json = ?, created_at = ?, updated_at = ?
               WHERE publication_id = ?""",
            (
                decode_sentinel,
                "2026-08-27T00:00:00+00:00",
                "2026-08-27T00:00:00+00:00",
                str(stale_failed["publication_id"]),
            ),
        )
        storage._conn.execute(
            """UPDATE agentic_ready_publications
               SET created_at = ?, updated_at = ?
               WHERE publication_id = ?""",
            (
                "2026-08-28T13:00:00+00:00",
                "2026-08-28T13:00:00+00:00",
                str(latest_failed["publication_id"]),
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()

    baseline = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})["knowledge_bases"][0][
        "agentic_ready_manifest"
    ]["publication_state"]

    decoded_publication_ids: list[str] = []
    sentinel_decodes = 0
    original_decode = rag_admin._KBListStorageView._agentic_publication_row_to_dict
    original_json_loads = rag_admin.json.loads

    def track_publication_decode(self: Any, row: Any) -> dict[str, Any]:
        decoded_publication_ids.append(str(row[0]))
        return original_decode(self, row)

    def track_json_loads(value: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal sentinel_decodes
        if value == decode_sentinel:
            sentinel_decodes += 1
        return original_json_loads(value, *args, **kwargs)

    monkeypatch.setattr(
        rag_admin._KBListStorageView,
        "_agentic_publication_row_to_dict",
        track_publication_decode,
    )
    monkeypatch.setattr(rag_admin.json, "loads", track_json_loads)

    payload = rag_admin.list_knowledge_bases(db_path=str(db_path), query={})
    publication_state = payload["knowledge_bases"][0]["agentic_ready_manifest"]["publication_state"]

    assert publication_state == baseline
    assert set(decoded_publication_ids) == {
        str(active["publication_id"]),
        str(previous["publication_id"]),
        str(latest_failed["publication_id"]),
    }
    assert len(decoded_publication_ids) == 3
    assert sentinel_decodes == 0


def _write_api_config(tmp_path: Path, db_path: Path) -> None:
    config_path = tmp_path / "sites.yaml"
    categories_path = tmp_path / "categories.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "db": str(db_path),
                    "download_dir": str(tmp_path / "files"),
                    "updates_dir": str(tmp_path / "updates"),
                    "last_run_new": str(tmp_path / "last-run.json"),
                },
                "defaults": {"file_exts": [".pdf"]},
                "sites": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    categories_path.write_text("categories: {}\n", encoding="utf-8")


def _seed_file_api(db_path: Path, tmp_path: Path) -> str:
    storage = Storage(str(db_path))
    try:
        for suffix in ("large", "adjacent"):
            url = f"https://issue-256.test/{suffix}.pdf"
            storage.insert_file(
                url=url,
                sha256=f"hash-{suffix}",
                title=suffix.title(),
                source_site="issue-256.test",
                source_page_url="https://issue-256.test",
                original_filename=f"{suffix}.pdf",
                local_path=str(tmp_path / f"{suffix}.pdf"),
                bytes=100,
                content_type="application/pdf",
            )
            storage.upsert_catalog_item(
                item={"url": url, "sha256": f"hash-{suffix}", "summary": suffix},
                pipeline_version="v1",
                status="ok",
            )
        large_markdown = "# Large\n\n" + ("markdown body needle\n" * 25_000)
        storage.update_file_markdown(
            "https://issue-256.test/large.pdf",
            large_markdown,
            "manual",
        )
        for role in ("operator", "admin"):
            token = f"{role}-token"
            storage.upsert_auth_token_by_hash(
                subject=token,
                group_name=role,
                token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                is_active=True,
            )
        return large_markdown
    finally:
        storage.close()


def test_file_lists_are_compact_for_public_admin_and_operator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "files.db"
    _write_api_config(tmp_path, db_path)
    large_markdown = _seed_file_api(db_path, tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "sites.yaml"))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(tmp_path / "categories.yaml"))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "issue-256-secret")
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    client = TestClient(create_app())

    statements: list[str] = []
    original_init = Storage.__init__

    def traced_init(self: Storage, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self._conn.set_trace_callback(statements.append)

    monkeypatch.setattr(Storage, "__init__", traced_init)
    responses = {
        "public": client.get("/api/files?query=needle"),
        "operator": client.get(
            "/api/files?query=needle",
            headers={"Authorization": "Bearer operator-token"},
        ),
        "admin": client.get(
            "/api/files?query=needle",
            headers={"Authorization": "Bearer admin-token"},
        ),
    }

    response_bytes: dict[str, int] = {}
    for role, response in responses.items():
        assert response.status_code == 200, (role, response.text)
        files = response.json()["files"]
        assert len(files) == 1
        assert files[0]["has_markdown"] is True
        assert "markdown_content" not in files[0]
        response_bytes[role] = len(response.content)

    adjacent = client.get("/api/files?query=adjacent")
    assert adjacent.status_code == 200
    assert adjacent.json()["files"][0]["has_markdown"] is False
    assert "markdown_content" not in adjacent.json()["files"][0]
    response_bytes["adjacent"] = len(adjacent.content)

    list_selects = [
        sql for sql in statements if "from files f" in sql.lower() and "limit" in sql.lower()
    ]
    assert list_selects
    for sql in list_selects:
        projection = sql.lower().split("from files f", 1)[0]
        assert "c.markdown_content" not in projection
    assert any(
        "c.markdown_content" in sql.lower().split("from files f", 1)[1] for sql in list_selects
    )
    assert max(response_bytes.values()) < 8_192
    assert response_bytes["admin"] < len(large_markdown.encode("utf-8")) // 10
    print(
        "issue256-file-list-bytes "
        + " ".join(f"{key}={value}" for key, value in response_bytes.items())
    )


def test_ordinary_file_list_does_not_materialize_markdown_body(tmp_path: Path) -> None:
    db_path = tmp_path / "ordinary-list.db"
    _seed_file_api(db_path, tmp_path)
    storage = Storage(str(db_path))
    statements: list[str] = []
    try:
        storage._conn.set_trace_callback(statements.append)
        files, total = storage.query_files_with_catalog(limit=10)
        assert total == len(files) == 2
    finally:
        storage.close()

    list_sql = next(
        sql for sql in statements if "from files f" in sql.lower() and "limit" in sql.lower()
    )
    assert "markdown_content" not in list_sql.lower()
    with sqlite3.connect(db_path) as conn:
        plan = conn.execute(f"EXPLAIN QUERY PLAN {list_sql}").fetchall()
    assert not any("AUTOMATIC" in str(row).upper() for row in plan)


def test_database_source_uses_has_markdown_boolean() -> None:
    source = Path("client/src/pages/Database.tsx").read_text(encoding="utf-8")

    assert "has_markdown: boolean;" in source
    assert "markdown_content: string | null;" not in source
    assert "const hasMd = file.has_markdown;" in source


def test_knowledge_build_fetches_fresh_selector_before_posting() -> None:
    source = Path("client/src/pages/Knowledge.tsx").read_text(encoding="utf-8")
    start = source.index("const handleBuildAgenticManifest")
    end = source.index("const toggleKbCategory", start)
    handler = source[start:end]

    manifest_path = "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/agentic-ready-manifest?include_ready_build_input=true`"
    build_path = (
        "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/agentic-ready-manifest/build`"
    )
    assert manifest_path in handler
    assert "await apiGet" in handler
    assert "const readyBuildInput = manifestResponse.manifest?.ready_build_input;" in handler
    assert "kbs.find" not in handler
    assert handler.index(manifest_path) < handler.index(build_path)
    assert "readyBuildInput\n      );" in handler
