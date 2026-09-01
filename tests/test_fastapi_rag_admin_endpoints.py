from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from ai_actuarial.api.app import create_app
from ai_actuarial.api.routers import rag_admin as rag_admin_router
from ai_actuarial.api.routers import ready_data_publication as ready_publication_router
from ai_actuarial.api.services import rag_admin as rag_admin_service
from ai_actuarial.embedding_service import resolve_server_embedding_identity
from ai_actuarial.rag.kb_index import resolve_kb_bound_chunks
from ai_actuarial.storage import Storage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class _CoreResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, object]:
        return self._payload


class _KBContractTestClient(TestClient):
    """Upgrade legacy KB-create fixtures to select the shared ready profile."""

    def __init__(self, *args: Any, default_chunk_profile_id: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.default_chunk_profile_id = default_chunk_profile_id

    def post(self, url: str, *args: Any, **kwargs: Any):
        payload = kwargs.get("json")
        if (
            url == "/api/rag/knowledge-bases"
            and isinstance(payload, dict)
            and "chunk_profile_id" not in payload
        ):
            kwargs["json"] = {
                **payload,
                "chunk_profile_id": self.default_chunk_profile_id,
            }
        return super().post(url, *args, **kwargs)


def _assert_failed_rollback_preserved_publication(
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    """A rejected rollback updates its audit fields but not publication state."""
    scrubbed_before = json.loads(json.dumps(before))
    scrubbed_after = json.loads(json.dumps(after))
    operation_fields = {
        "latest_operation_kind",
        "latest_operation_state",
        "latest_operation_at",
        "latest_operation_error",
    }

    def scrub_operation_audit(value: object) -> None:
        if isinstance(value, dict):
            for field in operation_fields:
                value.pop(field, None)
            for nested in value.values():
                scrub_operation_audit(nested)
        elif isinstance(value, list):
            for nested in value:
                scrub_operation_audit(nested)

    scrub_operation_audit(scrubbed_before)
    scrub_operation_audit(scrubbed_after)
    assert scrubbed_after == scrubbed_before
    for section_name in ("manifest", "publication_state"):
        section = after[section_name]
        assert isinstance(section, dict)
        assert section["latest_operation_kind"] == "rollback"
        assert section["latest_operation_state"] == "failed"
        assert section["latest_operation_error"] == "ready_data operation failed"


def test_failed_rollback_comparison_ignores_mirrored_operation_audit() -> None:
    before = {
        "kb_id": "kb-test",
        "manifest": {
            "active_publication_id": "arp-active",
            "latest_operation_kind": "publish",
            "latest_operation_state": "succeeded",
            "latest_operation_at": "before",
            "latest_operation_error": "",
            "publication_state": {
                "active_publication_id": "arp-active",
                "latest_operation_kind": "publish",
                "latest_operation_state": "succeeded",
                "latest_operation_at": "before",
                "latest_operation_error": "",
            },
        },
        "publication_state": {
            "active_publication_id": "arp-active",
            "latest_operation_kind": "publish",
            "latest_operation_state": "succeeded",
            "latest_operation_at": "before",
            "latest_operation_error": "",
        },
    }
    after = json.loads(json.dumps(before))
    for section in (
        after["manifest"],
        after["manifest"]["publication_state"],
        after["publication_state"],
    ):
        section.update(
            {
                "latest_operation_kind": "rollback",
                "latest_operation_state": "failed",
                "latest_operation_at": "after",
                "latest_operation_error": "ready_data operation failed",
            }
        )

    _assert_failed_rollback_preserved_publication(before, after)


def _prepare_committed_kb_index(
    db_path: Path,
    kb_id: str,
    *,
    persist_embeddings: bool = False,
) -> dict[str, object]:
    """Upgrade a legacy test KB fixture to the exact #238 index contract."""
    storage = Storage(str(db_path))
    try:
        kb_row = storage._conn.execute(
            """
            SELECT chunk_profile_id, embedding_provider, embedding_model,
                   embedding_dimension, embedding_identity_key, manifest_profile
            FROM rag_knowledge_bases
            WHERE kb_id = ?
            """,
            (kb_id,),
        ).fetchone()
        if not kb_row:
            raise AssertionError(f"test KB not found: {kb_id}")
        member_rows = storage._conn.execute(
            "SELECT file_url FROM rag_kb_files WHERE kb_id = ? ORDER BY file_url",
            (kb_id,),
        ).fetchall()
        if not member_rows:
            raise AssertionError(f"test KB has no members: {kb_id}")

        profile_id = str(kb_row[0] or "").strip()
        if not profile_id:
            existing_binding = storage._conn.execute(
                """
                SELECT fcs.profile_id
                FROM kb_chunk_bindings binding
                JOIN file_chunk_sets fcs ON fcs.chunk_set_id = binding.chunk_set_id
                WHERE binding.kb_id = ? AND fcs.status = 'ready'
                ORDER BY binding.file_url
                LIMIT 1
                """,
                (kb_id,),
            ).fetchone()
            if existing_binding:
                profile_id = str(existing_binding[0] or "")
            else:
                profile_id = str(
                    storage.create_chunk_profile(
                        name="issue-238-api-fixture",
                        chunk_size=256,
                        chunk_overlap=32,
                    )["profile_id"]
                )
            storage._conn.execute(
                "UPDATE rag_knowledge_bases SET chunk_profile_id = ? WHERE kb_id = ?",
                (profile_id, kb_id),
            )
            storage._conn.commit()

        selected_chunk_ids: list[str] = []
        for member_row in member_rows:
            file_url = str(member_row[0])
            ready_set = storage._conn.execute(
                """
                SELECT chunk_set_id
                FROM file_chunk_sets
                WHERE file_url = ? AND profile_id = ? AND status = 'ready'
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (file_url, profile_id),
            ).fetchone()
            if ready_set:
                chunk_set_id = str(ready_set[0])
            else:
                catalog = storage._conn.execute(
                    """
                    SELECT COALESCE(markdown_content, ''), COALESCE(summary, '')
                    FROM catalog_items
                    WHERE file_url = ?
                    """,
                    (file_url,),
                ).fetchone()
                content = str(
                    (catalog[0] if catalog else "") or (catalog[1] if catalog else "") or file_url
                )
                chunk_set = storage.get_or_create_file_chunk_set(
                    file_url=file_url,
                    profile_id=profile_id,
                    markdown_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    status="building",
                )
                storage.replace_global_chunks(
                    chunk_set_id=str(chunk_set["chunk_set_id"]),
                    chunks=[
                        {
                            "chunk_index": 0,
                            "content": content,
                            "token_count": max(1, len(content.split())),
                            "section_hierarchy": "Root",
                        }
                    ],
                    overwrite=True,
                )
                chunk_set_id = str(chunk_set["chunk_set_id"])
            storage.bind_chunk_set_to_kb(
                kb_id=kb_id,
                file_url=file_url,
                chunk_set_id=chunk_set_id,
                bound_by="issue_238_api_fixture",
                binding_mode="pin",
            )
            selected_chunk_ids.extend(
                str(row[0])
                for row in storage._conn.execute(
                    """
                    SELECT chunk_id
                    FROM global_chunks
                    WHERE chunk_set_id = ?
                    ORDER BY chunk_index, chunk_id
                    """,
                    (chunk_set_id,),
                ).fetchall()
            )

        resolved = resolve_kb_bound_chunks(storage, kb_id)
        identity_key = str(kb_row[4] or "")
        provider = str(kb_row[1] or "openai")
        model = str(kb_row[2] or "text-embedding-3-large")
        dimension = int(kb_row[3] or 3072)
        if persist_embeddings:
            identity = resolve_server_embedding_identity(storage, identity_key)
            storage.batch_upsert_chunk_embeddings(
                [
                    {
                        "chunk_id": chunk_id,
                        "vector": [float(index + 1)] * identity.dimension,
                    }
                    for index, chunk_id in enumerate(selected_chunk_ids)
                ],
                identity=identity.as_dict(),
            )

        current = storage._conn.execute(
            """
            SELECT versions.index_version_id, versions.embedding_identity_key,
                   versions.binding_snapshot_fingerprint, versions.chunk_count
            FROM kb_ready_index_state ready
            JOIN kb_index_versions versions
              ON versions.index_version_id = ready.index_version_id
            WHERE ready.kb_id = ? AND versions.status = 'ready'
            """,
            (kb_id,),
        ).fetchone()
        if (
            current
            and str(current[1] or "") == identity_key
            and str(current[2] or "") == resolved["binding_snapshot_fingerprint"]
            and int(current[3] or 0) == len(selected_chunk_ids)
        ):
            item_count = int(
                storage._conn.execute(
                    "SELECT COUNT(*) FROM kb_index_items WHERE index_version_id = ?",
                    (current[0],),
                ).fetchone()[0]
            )
            if item_count == len(selected_chunk_ids):
                return {
                    "index_version_id": str(current[0]),
                    "binding_snapshot_fingerprint": str(current[2]),
                    "chunk_ids": selected_chunk_ids,
                    "status": "ready",
                    "manifest_profile": str(kb_row[5] or "general"),
                }

        created = storage.create_kb_index_version(
            kb_id=kb_id,
            embedding_provider=provider,
            embedding_model=model,
            embedding_dimension=dimension,
            embedding_identity_key=identity_key,
            binding_snapshot_fingerprint=str(resolved["binding_snapshot_fingerprint"]),
            index_type="faiss",
            chunk_count=len(selected_chunk_ids),
            artifact_path=str(db_path.parent / "test-indexes" / kb_id),
            artifact_digest=hashlib.sha256(kb_id.encode("utf-8")).hexdigest(),
            chunk_ids=selected_chunk_ids,
            status="ready",
        )
        return {
            "index_version_id": str(created["index_version_id"]),
            "binding_snapshot_fingerprint": str(resolved["binding_snapshot_fingerprint"]),
            "chunk_ids": selected_chunk_ids,
            "status": "ready",
            "manifest_profile": str(kb_row[5] or "general"),
        }
    finally:
        storage.close()


def _post_ready_build_core(
    client: TestClient,
    url: str,
    *,
    json: dict[str, object] | None = None,
    prepare_index: bool = True,
    publish: bool = True,
) -> _CoreResponse:
    marker = "/api/rag/knowledge-bases/"
    suffix = "/agentic-ready-manifest/build"
    assert url.startswith(marker) and url.endswith(suffix)
    kb_id = url[len(marker) : -len(suffix)]
    db_path = Path(client.app.state.db_path)
    request_payload = dict(json or {})
    if prepare_index:
        prepared = _prepare_committed_kb_index(db_path, kb_id)
        request_payload.setdefault(
            "index_version_id",
            str(prepared["index_version_id"]),
        )
        if "expected_source_snapshot_fingerprint" not in request_payload:
            from ai_actuarial.agentic_rag.ready_data_builder import (
                get_builder_source_fingerprint,
            )

            source = get_builder_source_fingerprint(
                db_path=str(db_path),
                kb_id=kb_id,
                profile=str(
                    request_payload.get("profile") or prepared.get("manifest_profile") or "general"
                ),
                index_version_id=str(request_payload["index_version_id"]),
            )
            request_payload["expected_source_snapshot_fingerprint"] = str(
                source["source_snapshot_fingerprint"]
            )
    try:
        payload = rag_admin_service._build_agentic_ready_manifest_core(
            db_path=str(db_path),
            kb_id=kb_id,
            payload=request_payload,
            publish=publish,
        )
        return _CoreResponse(payload)
    except rag_admin_service.RagAdminError as exc:
        return _CoreResponse({"error": str(exc)}, exc.status_code)


def _wait_for_task(client: TestClient, job_id: str, *, timeout: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with client.app.state.task_lock:
            active = client.app.state.active_tasks_ref.get(job_id)
            if active is not None:
                task = dict(active)
            else:
                task = next(
                    (
                        dict(item)
                        for item in reversed(client.app.state.task_history_ref)
                        if str(item.get("id") or "") == job_id
                    ),
                    {},
                )
        if task and str(task.get("status") or "") in {
            "completed",
            "error",
            "stopped",
        }:
            return task
        time.sleep(0.02)
    raise AssertionError(f"task did not finish: {job_id}")


def _sqlite_file_state(db_path: Path) -> tuple[tuple[bool, int, str], ...]:
    def file_state(candidate: Path) -> tuple[bool, int, str]:
        if not candidate.exists():
            return False, 0, ""
        return True, candidate.stat().st_size, hashlib.sha256(candidate.read_bytes()).hexdigest()

    return tuple(
        file_state(candidate)
        for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
    )


def _record_snapshot_race_publication(
    storage: Storage,
    *,
    kb_id: str,
    label: str,
    output_dir: Path,
) -> dict[str, object]:
    return storage.record_agentic_ready_publication(
        kb_id=kb_id,
        index_version_id=f"idx-{label}",
        source_version_kind="kb_snapshot",
        source_version_id=f"source-{label}",
        profile="general",
        profile_version="1",
        status="validated",
        output_dir=str(output_dir),
        artifact_files=[
            "doc_catalog.jsonl",
            "sections.jsonl",
            "ready_data_manifest.json",
        ],
        doc_count=1,
        section_count=1,
        built_at="2026-08-20T12:00:00+00:00",
        artifact_digest=f"digest-{label}",
        source_db=storage.db_path,
        schema_versions={"ready_data": "1"},
    )


def _public_snapshot_identity(body: dict[str, object]) -> tuple[object, ...]:
    manifest = body["manifest"]
    publication_state = body["publication_state"]
    assert isinstance(manifest, dict)
    assert isinstance(publication_state, dict)
    active = publication_state.get("active_publication")
    assert isinstance(active, dict)
    return (
        publication_state.get("active_publication_id"),
        active.get("publication_id"),
        active.get("authoritative_source_version_id"),
        publication_state.get("current_ready_index_version_id"),
        publication_state.get("automatic_build_enabled"),
        publication_state.get("automatic_publish_enabled"),
        publication_state.get("source_generation"),
        publication_state.get("pending_generation"),
        manifest.get("status"),
        manifest.get("current_ready_index_version_id"),
    )


def _build_public_rollback_pair(
    client: TestClient,
    *,
    db_path: Path,
    kb_id: str,
    file_url: str,
) -> tuple[dict[str, object], dict[str, object]]:
    first_response = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()["candidate_publication"]
    storage = Storage(str(db_path))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                (f"Changed source for {kb_id}", file_url),
            )
            storage.mark_agentic_ready_source_event(
                kb_id=kb_id,
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()
    second_response = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert second_response.status_code == 200, second_response.text
    return first, second_response.json()["candidate_publication"]


def _write_config_files(base_dir: Path) -> tuple[Path, Path, Path, Path]:
    files_dir = base_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / "index.db"
    config_path = base_dir / "sites.yaml"
    categories_path = base_dir / "categories.yaml"

    config = {
        "paths": {
            "db": str(db_path),
            "download_dir": str(files_dir),
            "updates_dir": str(base_dir / "updates"),
            "last_run_new": str(base_dir / "last_run_new.json"),
        },
        "defaults": {
            "user_agent": "test-agent/1.0",
            "max_pages": 10,
            "max_depth": 1,
            "file_exts": [".pdf", ".docx"],
        },
        "sites": [],
        "scheduled_tasks": [],
    }
    categories = {"categories": {"AI": ["artificial intelligence"], "Risk": ["capital"]}}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path, files_dir


def _seed_storage(db_path: Path, files_dir: Path) -> dict[str, object]:
    alpha_path = files_dir / "alpha.pdf"
    alpha_path.write_bytes(PDF_BYTES)
    beta_path = files_dir / "beta.pdf"
    beta_path.write_bytes(PDF_BYTES + b"\n% beta")

    storage = Storage(str(db_path))
    try:
        alpha_url = "https://alpha.example/doc-a.pdf"
        beta_url = "https://beta.example/doc-b.pdf"
        alpha_sha = hashlib.sha256(alpha_path.read_bytes()).hexdigest()
        beta_sha = hashlib.sha256(beta_path.read_bytes()).hexdigest()

        storage.insert_file(
            url=alpha_url,
            sha256=alpha_sha,
            title="Alpha Document",
            source_site="alpha.example",
            source_page_url="https://alpha.example",
            original_filename="doc-a.pdf",
            local_path=str(alpha_path),
            bytes=alpha_path.stat().st_size,
            content_type="application/pdf",
        )
        storage.insert_file(
            url=beta_url,
            sha256=beta_sha,
            title="Beta Document",
            source_site="beta.example",
            source_page_url="https://beta.example",
            original_filename="doc-b.pdf",
            local_path=str(beta_path),
            bytes=beta_path.stat().st_size,
            content_type="application/pdf",
        )

        storage.upsert_catalog_item(
            item={
                "url": alpha_url,
                "sha256": alpha_sha,
                "keywords": ["ai"],
                "summary": "Alpha summary",
                "category": "AI",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.upsert_catalog_item(
            item={
                "url": beta_url,
                "sha256": beta_sha,
                "keywords": ["risk"],
                "summary": "Beta summary",
                "category": "Risk",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(alpha_url, "# Alpha\n\nAlpha markdown.", "manual")
        storage.update_file_markdown(beta_url, "# Beta\n\nBeta markdown.", "manual")
        operator_token = "operator-token"
        storage.upsert_auth_token_by_hash(
            subject="operator-token",
            group_name="operator",
            token_hash=hashlib.sha256(operator_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        admin_token = "admin-token"
        storage.upsert_auth_token_by_hash(
            subject="admin-token",
            group_name="admin",
            token_hash=hashlib.sha256(admin_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        registered_user_id = storage.create_user(
            "registered@example.com",
            "registered-password-hash",
            role="registered",
            display_name="Registered",
        )
        operator_user_id = storage.create_user(
            "operator@example.com",
            "operator-password-hash",
            role="operator",
            display_name="Operator",
        )
        admin_user_id = storage.create_user(
            "admin@example.com",
            "admin-password-hash",
            role="admin",
            display_name="Admin",
        )
    finally:
        storage.close()

    return {
        "alpha_url": alpha_url,
        "beta_url": beta_url,
        "operator_token": operator_token,
        "admin_token": admin_token,
        "registered_user_id": registered_user_id,
        "operator_user_id": operator_user_id,
        "admin_user_id": admin_user_id,
    }


def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, object]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    storage = Storage(str(db_path))
    try:
        default_profile = storage.create_chunk_profile(
            name="issue-238-api-default",
            chunk_size=256,
            chunk_overlap=32,
        )
    finally:
        storage.close()
    default_profile_id = str(default_profile["profile_id"])
    _seed_ready_chunk_set(
        db_path,
        str(seed["alpha_url"]),
        default_profile_id,
        text="Alpha fixture chunk",
    )
    _seed_ready_chunk_set(
        db_path,
        str(seed["beta_url"]),
        default_profile_id,
        text="Beta fixture chunk",
    )
    seed["default_chunk_profile_id"] = default_profile_id
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "fastapi-rag-admin-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = _KBContractTestClient(app, default_chunk_profile_id=default_profile_id)
    client.headers.update({"X-Auth-Token": seed["admin_token"]})
    return client, app, seed


def _make_session_cookie(app, payload: dict[str, object]) -> str:
    serializer = URLSafeSerializer(app.state.fastapi_session_secret, salt="fastapi-session")
    return serializer.dumps(payload)


def _disable_rag_runtime_initialization(monkeypatch, tmp_path: Path) -> None:
    import requests
    import tiktoken

    from ai_actuarial.rag import embeddings, knowledge_base, semantic_chunking

    def fail_runtime_initialization(*_args, **_kwargs):
        raise AssertionError("KB list initialized a RAG runtime dependency")

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "empty-tokenizer-cache"))
    monkeypatch.setattr(knowledge_base, "KnowledgeBaseManager", fail_runtime_initialization)
    monkeypatch.setattr(knowledge_base, "SemanticChunker", fail_runtime_initialization)
    monkeypatch.setattr(knowledge_base, "EmbeddingGenerator", fail_runtime_initialization)
    monkeypatch.setattr(semantic_chunking, "SemanticChunker", fail_runtime_initialization)
    monkeypatch.setattr(embeddings, "EmbeddingGenerator", fail_runtime_initialization)
    monkeypatch.setattr(tiktoken, "get_encoding", fail_runtime_initialization)
    monkeypatch.setattr(tiktoken, "encoding_for_model", fail_runtime_initialization)
    monkeypatch.setattr(requests, "get", fail_runtime_initialization)


def test_rag_index_auth_preserves_tasks_run_permission_boundary(monkeypatch) -> None:
    request = SimpleNamespace(headers={})

    monkeypatch.setattr(
        rag_admin_router,
        "get_auth_context",
        lambda _request: rag_admin_router.AuthContext(
            token={"subject": "catalog-only"},
            permissions=frozenset({"catalog.write"}),
        ),
    )

    assert rag_admin_router.require_rag_write(request).token["subject"] == "catalog-only"
    with pytest.raises(HTTPException) as exc_info:
        rag_admin_router.require_rag_task_run(request)
    assert exc_info.value.status_code == 403


def test_rag_task_auth_preserves_legacy_config_token_fallback(monkeypatch) -> None:
    request = SimpleNamespace(headers={"X-Auth-Token": "legacy-config-token"})
    monkeypatch.setenv("CONFIG_WRITE_AUTH_TOKEN", "legacy-config-token")
    monkeypatch.setattr(
        rag_admin_router,
        "get_auth_context",
        lambda _request: rag_admin_router.AuthContext(token=None, permissions=frozenset()),
    )

    auth = rag_admin_router.require_rag_task_run(request)

    assert auth.token["subject"] == "legacy-config-write-token"
    assert "tasks.run" in auth.permissions


def _seed_ready_chunk_set(
    db_path: Path, file_url: str, profile_id: str, *, text: str = "Chunk"
) -> dict[str, object]:
    storage = Storage(str(db_path))
    try:
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            markdown_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            status="building",
        )
        storage.replace_global_chunks(
            chunk_set_id=chunk_set["chunk_set_id"],
            chunks=[
                {
                    "chunk_index": 0,
                    "content": text,
                    "token_count": 2,
                    "section_hierarchy": "Root",
                }
            ],
            overwrite=True,
        )
        return chunk_set
    finally:
        storage.close()


def test_fastapi_rag_admin_routes_are_listed_in_native_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/chunk/profiles" in body["native_paths"]
    assert "/api/chunk/profiles/{profile_id}" in body["native_paths"]
    assert "/api/rag/knowledge-bases" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/stats" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/publish" in body["native_paths"]
    assert (
        "/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback" in body["native_paths"]
    )
    assert "/api/rag/knowledge-bases/{kb_id}/files" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/files/{file_url:path}" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/categories" in body["native_paths"]
    assert "/api/rag/categories/unmapped" in body["native_paths"]
    assert "/api/rag/categories/stats" in body["native_paths"]
    assert "/api/rag/files/selectable" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/files/pending" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/bindings" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/index" in body["native_paths"]
    assert "/api/chunk-sets/cleanup" in body["native_paths"]


def test_explicit_ready_publish_api_is_thin_exact_adapter(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def publish(*, db_path: str, kb_id: str, payload: dict[str, object]):
        captured.update({"db_path": db_path, "kb_id": kb_id, "payload": payload})
        return {
            "kb_id": kb_id,
            "profile": "general",
            "publication_id": "arp_candidate",
            "publish_status": "published",
            "active_publication_id": "arp_candidate",
        }

    monkeypatch.setattr(ready_publication_router, "publish_ready_data_publication", publish)
    request_payload = {
        "profile": "general",
        "publication_id": "arp_candidate",
        "expected_active_publication_id": None,
    }

    response = client.post(
        "/api/rag/knowledge-bases/kb-publish/agentic-ready-manifest/publish",
        json=request_payload,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "kb_id": "kb-publish",
        "profile": "general",
        "publication_id": "arp_candidate",
        "publish_status": "published",
        "active_publication_id": "arp_candidate",
    }
    assert captured == {
        "db_path": str(tmp_path / "index.db"),
        "kb_id": "kb-publish",
        "payload": request_payload,
    }


def test_fastapi_rag_admin_read_routes_require_task_or_config_permissions(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    client.headers.clear()

    public_kbs = client.get("/api/rag/knowledge-bases")
    assert public_kbs.status_code == 200, public_kbs.text

    for path in (
        "/api/chunk/profiles",
        "/api/rag/categories/unmapped",
        "/api/rag/categories/mapping",
        "/api/rag/files/selectable",
        "/api/rag/knowledge-bases/kb-missing/bindings",
    ):
        response = client.get(path)
        assert response.status_code == 401, path

    category_stats = client.post("/api/rag/categories/stats", json={"categories": ["AI"]})
    assert category_stats.status_code == 401

    pending = client.get("/api/rag/knowledge-bases/kb-missing/files/pending")
    assert pending.status_code == 401

    operator_headers = {"X-Auth-Token": seed["operator_token"]}
    assert client.get(
        "/api/rag/knowledge-bases/kb-missing/files/pending", headers=operator_headers
    ).status_code in {200, 404}
    assert client.get("/api/chunk/profiles", headers=operator_headers).status_code == 200

    admin_headers = {"X-Auth-Token": seed["admin_token"]}
    assert client.get("/api/chunk/profiles", headers=admin_headers).status_code == 200


def test_fastapi_rag_admin_kb_writes_accept_admin_operator_sessions_with_legacy_token_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONFIG_WRITE_AUTH_TOKEN", "legacy-config-token")
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    client.headers.clear()
    app.state.start_background_task = lambda *args, **kwargs: "task-session-rag-index"

    anonymous = client.post(
        "/api/rag/knowledge-bases",
        json={"kb_id": "kb-anonymous-denied", "name": "Anonymous Denied", "kb_mode": "manual"},
    )
    assert anonymous.status_code == 401

    cookie_name = app.state.fastapi_session_cookie_name
    client.cookies.set(
        cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["registered_user_id"]}),
    )
    registered = client.post(
        "/api/rag/knowledge-bases",
        json={"kb_id": "kb-registered-denied", "name": "Registered Denied", "kb_mode": "manual"},
    )
    assert registered.status_code == 403

    client.cookies.clear()
    client.cookies.set(
        cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["operator_user_id"]}),
    )
    operator_create = client.post(
        "/api/rag/knowledge-bases",
        json={"kb_id": "kb-session-operator", "name": "Operator Session KB", "kb_mode": "manual"},
    )
    assert operator_create.status_code == 201, operator_create.text

    operator_add_file = client.post(
        "/api/rag/knowledge-bases/kb-session-operator/files",
        json={"file_urls": [seed["alpha_url"]]},
    )
    assert operator_add_file.status_code == 200, operator_add_file.text

    operator_categories = client.post(
        "/api/rag/knowledge-bases/kb-session-operator/categories",
        json={"categories": ["AI"], "action": "replace"},
    )
    assert operator_categories.status_code == 200, operator_categories.text

    _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-session-operator",
        persist_embeddings=True,
    )

    operator_index = client.post(
        "/api/rag/knowledge-bases/kb-session-operator/index",
        json={"file_urls": [seed["alpha_url"]]},
    )
    assert operator_index.status_code == 202, operator_index.text

    client.cookies.clear()
    client.cookies.set(
        cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]}),
    )
    admin_update = client.put(
        "/api/rag/knowledge-bases/kb-session-operator",
        json={"name": "Admin Updated KB"},
    )
    assert admin_update.status_code == 200, admin_update.text

    admin_delete = client.delete("/api/rag/knowledge-bases/kb-session-operator")
    assert admin_delete.status_code == 200, admin_delete.text


def test_fastapi_rag_admin_kb_writes_preserve_legacy_config_token_access(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CONFIG_WRITE_AUTH_TOKEN", "legacy-config-token")
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    client.headers.clear()

    legacy = client.post(
        "/api/rag/knowledge-bases",
        json={"kb_id": "kb-legacy-token", "name": "Legacy Token KB", "kb_mode": "manual"},
        headers={"X-Auth-Token": "legacy-config-token"},
    )

    assert legacy.status_code == 201, legacy.text

    unrelated_config_write = client.post(
        "/api/config/backend-settings",
        json={"defaults": {"max_pages": 12}},
        headers={"X-Auth-Token": "legacy-config-token"},
    )
    assert unrelated_config_write.status_code == 401


def test_fastapi_rag_admin_categories_mapping_uses_catalog_items_without_legacy_table(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("AI; Risk", seed["alpha_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    response = client.get("/api/rag/categories/mapping")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["categories"] == ["AI", "Risk"]
    assert body["count"] == 2


def test_fastapi_rag_admin_chunk_profiles_and_kb_crud_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "default-profile",
            "chunk_size": 300,
            "chunk_overlap": 50,
            "splitter": "semantic",
            "tokenizer": "cl100k_base",
            "version": "v1",
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    profile = create_profile.json()["profile"]
    profile_id = profile["profile_id"]

    list_profiles = client.get("/api/chunk/profiles")
    assert list_profiles.status_code == 200, list_profiles.text
    assert any(item["profile_id"] == profile_id for item in list_profiles.json()["profiles"])

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-pr4-test",
            "name": "PR4 Test KB",
            "description": "Knowledge base for FastAPI PR4",
            "kb_mode": "manual",
            "chunk_size": 300,
            "chunk_overlap": 50,
            "embedding_model": "text-embedding-3-small",
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    kb = create_kb.json()["knowledge_base"]
    assert kb["kb_id"] == "kb-pr4-test"
    assert kb["embedding_model"] == "text-embedding-3-large"
    assert kb["embedding_provider"] == "openai"

    list_kbs = client.get("/api/rag/knowledge-bases")
    assert list_kbs.status_code == 200, list_kbs.text
    list_body = list_kbs.json()
    assert list_body["current_embeddings"]["stable_credential_id"] == "openai:llm:env"
    listed_kb = next(
        item for item in list_body["knowledge_bases"] if item["kb_id"] == "kb-pr4-test"
    )
    assert listed_kb["current_embeddings"]["provider"] == "openai"
    assert listed_kb["current_embeddings"]["configured"] is True
    assert listed_kb["current_embeddings"]["credential_source"] == "env"
    assert listed_kb["current_embeddings"]["stable_credential_id"] == "openai:llm:env"
    assert listed_kb["current_embeddings"]["credential_error"] is None
    assert listed_kb["embedding_compatible"] is True
    assert listed_kb["availability"] in {"building", "ready"}

    get_kb = client.get("/api/rag/knowledge-bases/kb-pr4-test")
    assert get_kb.status_code == 200, get_kb.text
    detail_body = get_kb.json()["knowledge_base"]
    assert detail_body["name"] == "PR4 Test KB"
    assert detail_body["current_embeddings"]["embedding_fingerprint"].startswith(
        "openai:text-embedding-3-large:"
    )
    assert detail_body["current_embeddings"]["configured"] is True

    update_kb = client.put(
        "/api/rag/knowledge-bases/kb-pr4-test",
        json={"name": "PR4 Test KB Updated", "description": "Updated description"},
    )
    assert update_kb.status_code == 200, update_kb.text
    assert update_kb.json()["knowledge_base"]["name"] == "PR4 Test KB Updated"

    delete_profile = client.delete(f"/api/chunk/profiles/{profile_id}")
    assert delete_profile.status_code == 200, delete_profile.text

    delete_kb = client.delete("/api/rag/knowledge-bases/kb-pr4-test")
    assert delete_kb.status_code == 200, delete_kb.text


def test_fastapi_rag_admin_kb_list_does_not_initialize_rag_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        profile = storage.create_chunk_profile(
            name="offline-profile",
            chunk_size=320,
            chunk_overlap=40,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
        )
        storage._conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            );
            CREATE TABLE rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url)
            );
            """)
        storage._conn.executemany(
            """
            INSERT INTO rag_knowledge_bases (
                kb_id, name, description, kb_mode, chunk_profile_id,
                manifest_profile, embedding_provider, embedding_model,
                embedding_dimension, chunk_size, chunk_overlap, index_type,
                created_at, updated_at, file_count, chunk_count
            ) VALUES (?, ?, ?, ?, ?, 'general', 'openai',
                      'text-embedding-3-large', 3072, 320, 40, 'Flat',
                      ?, ?, 0, 0)
            """,
            (
                (
                    "kb-offline-list",
                    "Offline Actuarial KB",
                    "Offline recovery metadata",
                    "manual",
                    profile["profile_id"],
                    "2026-08-20T13:00:00+00:00",
                    "2026-08-20T13:00:00+00:00",
                ),
                (
                    "kb-category-other",
                    "Other KB",
                    "Must be filtered out",
                    "category",
                    None,
                    "2026-08-20T12:00:00+00:00",
                    "2026-08-20T12:00:00+00:00",
                ),
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)

    from ai_actuarial.api.deps import AuthContext
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    operator_auth = AuthContext(token=None, permissions=frozenset({"tasks.run"}))
    body = rag_admin_service.list_knowledge_bases(
        db_path=str(db_path),
        query={"kb_mode": "manual", "search": "offline"},
        auth=operator_auth,
    )

    assert body["current_embeddings"]["stable_credential_id"] == "openai:llm:env"
    assert [item["kb_id"] for item in body["knowledge_bases"]] == ["kb-offline-list"]
    listed = body["knowledge_bases"][0]
    assert listed["kb_mode"] == "manual"
    assert listed["chunk_profile_id"] == profile["profile_id"]
    assert listed["chunk_profile_name"] == "offline-profile"
    assert listed["embedding_compatible"] is True
    assert listed["availability"] == "building"
    assert listed["usable"] is False
    assert listed["current_embeddings"]["configured"] is True
    assert listed["agentic_ready_manifest"]["status"] == "missing"
    assert listed["agentic_ready_available"] is False
    assert listed["agentic_fallback_mode"] == "standard"


@pytest.mark.parametrize("db_path", (":memory:", ""))
def test_rag_admin_kb_list_supports_connection_local_database(
    tmp_path: Path,
    monkeypatch,
    db_path: str,
) -> None:
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)

    result = rag_admin_service.list_knowledge_bases(db_path=db_path, query={})

    assert result["knowledge_bases"] == []
    current_embeddings = result["current_embeddings"]
    assert current_embeddings["provider"] == "openai"
    assert current_embeddings["model"]
    assert current_embeddings["dimension"] > 0
    assert current_embeddings["stable_credential_id"]
    assert "configured" in current_embeddings


def test_fastapi_rag_admin_kb_list_legacy_metadata_requires_schema_apply_without_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            );
            INSERT INTO rag_knowledge_bases (
                kb_id, name, embedding_model, chunk_size, chunk_overlap,
                index_type, created_at, updated_at
            ) VALUES (
                'kb-legacy-offline', 'Legacy Offline KB',
                'text-embedding-3-large', 800, 100, 'Flat',
                '2026-08-20T11:00:00+00:00', '2026-08-20T11:00:00+00:00'
            );
            """)
        storage._conn.commit()
    finally:
        storage.close()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)
    client.headers.pop("X-Auth-Token", None)
    before_state = _sqlite_file_state(db_path)
    before_schema = sqlite3.connect(str(db_path))
    try:
        before_columns = {
            row[1] for row in before_schema.execute("PRAGMA table_info(rag_knowledge_bases)")
        }
    finally:
        before_schema.close()

    response = client.get("/api/rag/knowledge-bases", params={"search": "legacy"})

    assert response.status_code == 409, response.text
    assert "schema apply" in response.text
    assert _sqlite_file_state(db_path) == before_state

    conn = sqlite3.connect(str(db_path))
    try:
        kb_columns = {row[1] for row in conn.execute("PRAGMA table_info(rag_knowledge_bases)")}
        assert kb_columns == before_columns
        assert not conn.execute(
            "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'rag_kb_files'"
        ).fetchone()
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM rag_knowledge_bases WHERE kb_id = 'kb-legacy-offline'"
            ).fetchone()[0]
            == 1
        )
    finally:
        conn.close()


def test_rag_admin_kb_list_concurrent_legacy_reads_do_not_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor

    from ai_actuarial.api.services import rag_admin as rag_admin_service
    from ai_actuarial.api.services.rag_admin import RagAdminError

    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            );
            INSERT INTO rag_knowledge_bases (
                kb_id, name, embedding_model, chunk_size, chunk_overlap,
                index_type, created_at, updated_at
            ) VALUES (
                'kb-concurrent-legacy', 'Concurrent Legacy KB',
                'text-embedding-3-large', 800, 100, 'Flat',
                '2026-08-20T11:00:00+00:00', '2026-08-20T11:00:00+00:00'
            );
            """)
        storage._conn.commit()
    finally:
        storage.close()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)
    before_state = _sqlite_file_state(db_path)

    def list_legacy_kb() -> int:
        with pytest.raises(RagAdminError) as excinfo:
            rag_admin_service.list_knowledge_bases(
                db_path=str(db_path),
                query={"search": "concurrent"},
            )
        return excinfo.value.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(list_legacy_kb) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]

    assert results == [409, 409]
    assert _sqlite_file_state(db_path) == before_state
    with sqlite3.connect(str(db_path)) as conn:
        assert not conn.execute(
            "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'rag_kb_files'"
        ).fetchone()


def test_rag_admin_kb_list_schema_ready_path_does_not_wait_for_writer(
    tmp_path: Path,
) -> None:
    import sqlite3

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    db_path = tmp_path / "index.db"
    setup = Storage(str(db_path))
    try:
        setup._conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            );
            CREATE TABLE rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url)
            );
            """)
        setup._conn.commit()
    finally:
        setup.close()

    writer = sqlite3.connect(str(db_path))
    writer.execute("BEGIN IMMEDIATE")
    try:
        result = rag_admin_service.list_knowledge_bases(db_path=str(db_path), query={})
        assert writer.in_transaction
    finally:
        writer.rollback()
        writer.close()

    assert result["knowledge_bases"] == []
    assert "configured" in result["current_embeddings"]


def test_rag_admin_kb_list_existing_db_without_kb_table_is_read_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    db_path = tmp_path / "raw-no-kb-table.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE raw_rag_placeholder (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO raw_rag_placeholder (id) VALUES ('keep')")
        conn.commit()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)
    before_state = _sqlite_file_state(db_path)

    result = rag_admin_service.list_knowledge_bases(db_path=str(db_path), query={})

    assert result["knowledge_bases"] == []
    assert "configured" in result["current_embeddings"]
    assert _sqlite_file_state(db_path) == before_state
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM raw_rag_placeholder").fetchone()[0] == 1


def test_rag_admin_kb_list_user_schema_probe_is_read_only_query_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    db_path = tmp_path / "probe-read-only.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE raw_rag_placeholder (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO raw_rag_placeholder (id) VALUES ('keep')")
        conn.commit()

    real_connect = sqlite3.connect
    connect_calls = []
    query_only_statements = []

    class TrackingConnection:
        def __init__(self, conn) -> None:
            self._conn = conn

        def execute(self, statement, *args, **kwargs):
            if str(statement).strip().upper() == "PRAGMA QUERY_ONLY=ON":
                query_only_statements.append(str(statement))
            return self._conn.execute(statement, *args, **kwargs)

        def close(self) -> None:
            self._conn.close()

        def __getattr__(self, name: str):
            return getattr(self._conn, name)

    def tracking_connect(database, *args, **kwargs):
        connect_calls.append((str(database), kwargs.get("uri")))
        return TrackingConnection(real_connect(database, *args, **kwargs))

    monkeypatch.setattr(rag_admin_service.sqlite3, "connect", tracking_connect)

    assert rag_admin_service._kb_list_db_has_user_schema_objects(str(db_path)) is True

    assert connect_calls
    assert connect_calls[0][1] is True
    assert "mode=ro" in connect_calls[0][0]
    assert query_only_statements == ["PRAGMA query_only=ON"]


def test_rag_admin_kb_list_unreadable_sqlite_fails_closed_without_writes(
    tmp_path: Path,
) -> None:
    from ai_actuarial.api.services import rag_admin as rag_admin_service
    from ai_actuarial.api.services.rag_admin import RagAdminError

    db_path = tmp_path / "unreadable.db"
    db_path.write_bytes(b"not a sqlite database")
    before_state = _sqlite_file_state(db_path)

    with pytest.raises(RagAdminError) as excinfo:
        rag_admin_service.list_knowledge_bases(db_path=str(db_path), query={})

    assert excinfo.value.status_code == 409
    assert "schema apply" in excinfo.value.message
    assert _sqlite_file_state(db_path) == before_state


def test_rag_admin_kb_list_reads_raw_rag_only_database_without_core_storage_tables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    db_path = tmp_path / "raw-rag-only.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            );
            INSERT INTO rag_knowledge_bases (
                kb_id, name, description, kb_mode, chunk_profile_id,
                manifest_profile, embedding_provider, embedding_model,
                embedding_dimension, chunk_size, chunk_overlap, index_type,
                created_at, updated_at, file_count, chunk_count, index_dirty_at
            ) VALUES (
                'kb-raw-rag-only', 'Raw RAG Only', 'No core Storage tables',
                'manual', NULL, 'general', 'openai',
                'text-embedding-3-large', 3072, 800, 100, 'Flat',
                '2026-08-20T11:00:00+00:00',
                '2026-08-20T11:00:00+00:00', 0, 0, NULL
            );
            """)
        conn.commit()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)
    before_state = _sqlite_file_state(db_path)

    result = rag_admin_service.list_knowledge_bases(
        db_path=str(db_path),
        query={"search": "raw"},
    )

    assert _sqlite_file_state(db_path) == before_state
    listed = result["knowledge_bases"][0]
    assert listed["kb_id"] == "kb-raw-rag-only"
    assert listed["availability"] == "building"
    assert listed["agentic_ready_manifest"]["status"] == "missing"
    assert listed["agentic_fallback_mode"] == "standard"


def test_rag_admin_kb_list_legacy_optional_table_requires_schema_apply_without_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    from ai_actuarial.api.services import rag_admin as rag_admin_service
    from ai_actuarial.api.services.rag_admin import RagAdminError

    db_path = tmp_path / "raw-rag-legacy-agentic-slot.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            );
            CREATE TABLE agentic_ready_slots (
                kb_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                active_publication_id TEXT,
                previous_publication_id TEXT,
                automatic_build_enabled INTEGER NOT NULL DEFAULT 0,
                automatic_publish_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(kb_id, profile)
            );
            INSERT INTO rag_knowledge_bases (
                kb_id, name, description, kb_mode, chunk_profile_id,
                manifest_profile, embedding_provider, embedding_model,
                embedding_dimension, chunk_size, chunk_overlap, index_type,
                created_at, updated_at, file_count, chunk_count, index_dirty_at
            ) VALUES (
                'kb-legacy-slot', 'Legacy Slot KB', 'Legacy optional table',
                'manual', NULL, 'general', 'openai',
                'text-embedding-3-large', 3072, 800, 100, 'Flat',
                '2026-08-20T11:00:00+00:00',
                '2026-08-20T11:00:00+00:00', 0, 0, NULL
            );
            INSERT INTO agentic_ready_slots (
                kb_id, profile, automatic_build_enabled,
                automatic_publish_enabled, updated_at
            ) VALUES (
                'kb-legacy-slot', 'general', 0, 0,
                '2026-08-20T11:00:00+00:00'
            );
            """)
        conn.commit()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)
    before_state = _sqlite_file_state(db_path)

    with pytest.raises(RagAdminError) as excinfo:
        rag_admin_service.list_knowledge_bases(
            db_path=str(db_path),
            query={"search": "legacy slot"},
        )

    assert excinfo.value.status_code == 409
    assert "schema apply" in excinfo.value.message
    assert _sqlite_file_state(db_path) == before_state
    with sqlite3.connect(str(db_path)) as conn:
        slot_columns = {row[1] for row in conn.execute("PRAGMA table_info(agentic_ready_slots)")}
        assert "publication_revision" not in slot_columns
        assert conn.execute("SELECT COUNT(*) FROM agentic_ready_slots").fetchone()[0] == 1


def test_rag_admin_kb_list_optional_view_requires_schema_apply_without_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import sqlite3

    from ai_actuarial.api.services import rag_admin as rag_admin_service
    from ai_actuarial.api.services.rag_admin import RagAdminError

    db_path = tmp_path / "raw-rag-view-shaped-slot.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            );
            CREATE VIEW agentic_ready_slots AS
            SELECT * FROM missing_slot_source;
            INSERT INTO rag_knowledge_bases (
                kb_id, name, description, kb_mode, chunk_profile_id,
                manifest_profile, embedding_provider, embedding_model,
                embedding_dimension, chunk_size, chunk_overlap, index_type,
                created_at, updated_at, file_count, chunk_count, index_dirty_at
            ) VALUES (
                'kb-view-slot', 'View Slot KB', 'View-shaped optional object',
                'manual', NULL, 'general', 'openai',
                'text-embedding-3-large', 3072, 800, 100, 'Flat',
                '2026-08-20T11:00:00+00:00',
                '2026-08-20T11:00:00+00:00', 0, 0, NULL
            );
            """)
        conn.commit()

    _disable_rag_runtime_initialization(monkeypatch, tmp_path)
    before_state = _sqlite_file_state(db_path)

    with pytest.raises(RagAdminError) as excinfo:
        rag_admin_service.list_knowledge_bases(
            db_path=str(db_path),
            query={"search": "view slot"},
        )

    assert excinfo.value.status_code == 409
    assert "schema apply" in excinfo.value.message
    assert _sqlite_file_state(db_path) == before_state
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT type FROM sqlite_schema WHERE name = 'agentic_ready_slots'"
        ).fetchone()
        assert row[0] == "view"
        assert conn.execute("SELECT COUNT(*) FROM rag_knowledge_bases").fetchone()[0] == 1


def test_fastapi_rag_admin_kb_list_normalizes_legacy_rows_without_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.executescript("""
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT,
                chunk_profile_id TEXT,
                manifest_profile TEXT,
                embedding_provider TEXT,
                embedding_model TEXT NOT NULL,
                embedding_dimension TEXT,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                file_count INTEGER,
                chunk_count INTEGER,
                index_dirty_at TEXT
            );
            CREATE TABLE rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url)
            );
            INSERT INTO rag_knowledge_bases (
                kb_id, name, description, kb_mode, chunk_profile_id,
                manifest_profile, embedding_provider, embedding_model,
                embedding_dimension, chunk_size, chunk_overlap, index_type,
                created_at, updated_at, file_count, chunk_count, index_dirty_at
            ) VALUES (
                'kb-legacy-row', 'Legacy Row KB', 'Legacy row normalization',
                '', NULL, ' Regulation ', ' OpenAI ',
                'text-embedding-3-large', '3072', 800, 100, 'Flat',
                NULL, NULL, 0, 0, NULL
            );
            """)
        storage._conn.commit()
    finally:
        storage.close()

    monkeypatch.setattr(Storage, "_ensure_rag_kb_embedding_columns", lambda _storage: None)
    _disable_rag_runtime_initialization(monkeypatch, tmp_path)

    from ai_actuarial.api.deps import AuthContext
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    operator_auth = AuthContext(token=None, permissions=frozenset({"tasks.run"}))
    body = rag_admin_service.list_knowledge_bases(
        db_path=str(db_path),
        query={"kb_mode": "category", "search": "legacy row"},
        auth=operator_auth,
    )

    listed = body["knowledge_bases"][0]
    assert listed["kb_id"] == "kb-legacy-row"
    assert listed["kb_mode"] == "category"
    assert listed["chunk_profile_id"] == ""
    assert listed["manifest_profile"] == "regulation"
    assert listed["embedding_provider"] == "openai"
    assert listed["embedding_dimension"] == 3072
    assert isinstance(listed["embedding_dimension"], int)
    assert listed["created_at"].endswith("+00:00")
    assert listed["updated_at"].endswith("+00:00")
    assert listed["agentic_ready_manifest"]["status"] == "missing"
    assert listed["agentic_fallback_mode"] == "standard"


def test_fastapi_rag_admin_agentic_ready_manifest_build_is_kb_scoped(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    alpha_url = seed["alpha_url"]
    beta_url = seed["beta_url"]

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-agentic-manifest",
            "name": "Agentic Manifest KB",
            "kb_mode": "manual",
            "file_urls": [alpha_url],
            "manifest_profile": "general",
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    created_manifest = create_kb.json()["knowledge_base"]["agentic_ready_manifest"]
    assert created_manifest["status"] == "missing"
    assert created_manifest["fallback_mode"] == "standard"
    assert created_manifest["publication_revision"] == 0
    assert create_kb.json()["knowledge_base"]["manifest_profile"] == "general"

    status_before_build = client.get(
        "/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest"
    )
    assert status_before_build.status_code == 200, status_before_build.text
    assert status_before_build.json()["manifest"]["status"] == "missing"
    assert status_before_build.json()["manifest"]["publication_revision"] == 0
    assert status_before_build.json()["publication_state"]["publication_revision"] == 0

    build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    build_body = build.json()
    manifest = build_body["manifest"]
    assert manifest["status"] == "ready", build.text
    assert manifest["usable"] is True
    assert manifest["fallback_mode"] == "agentic"
    assert manifest["doc_count"] == 1
    assert manifest["publication_id"].startswith("arp_")
    assert manifest["index_version_id"].startswith("idxv_")
    assert manifest["source_version_kind"] == "catalog_chunks_snapshot"
    assert manifest["source_version_id"].startswith("rdsnap_")
    assert len(manifest["artifact_digest"]) == 64
    assert manifest["publication_revision"] == 1
    assert build.json()["publication_state"]["publication_revision"] == 1
    assert build.json()["publication_state"]["automatic_publish_enabled"] is False
    safe_snapshot = build_body["ready_data_snapshot"]
    assert safe_snapshot["manifest"]["publication_revision"] == 1
    assert safe_snapshot["publication_state"]["publication_revision"] == 1
    assert safe_snapshot["publication_state"]["active_publication_id"] == manifest["publication_id"]
    assert safe_snapshot["publication_state"]["previous_publication_id"] is None
    assert safe_snapshot["publication_state"]["previous_publication"] is None
    safe_active = safe_snapshot["publication_state"]["active_publication"]
    assert safe_active["publication_id"] == manifest["publication_id"]
    assert safe_active["index_consumed_by_builder"] is True
    serialized_safe_snapshot = json.dumps(safe_snapshot, sort_keys=True)
    for forbidden in (
        "source_db",
        "output_dir",
        "quarantine_dir",
        "claim_token",
        "lease_expires_at",
        "matched_doc_id",
        "matched_file_url",
        "evidence",
    ):
        assert forbidden not in serialized_safe_snapshot
    output_dir = Path(manifest["output_dir"])
    assert output_dir.is_dir()

    catalog_rows = [
        json.loads(line)
        for line in (output_dir / "doc_catalog.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["file_url"] for row in catalog_rows] == [alpha_url]
    assert beta_url not in {row["file_url"] for row in catalog_rows}

    list_kbs = client.get("/api/rag/knowledge-bases")
    assert list_kbs.status_code == 200, list_kbs.text
    listed = next(
        item
        for item in list_kbs.json()["knowledge_bases"]
        if item["kb_id"] == "kb-agentic-manifest"
    )
    assert listed["agentic_ready_manifest"]["status"] == "ready"

    add_beta = client.post(
        "/api/rag/knowledge-bases/kb-agentic-manifest/files",
        json={"file_urls": [beta_url]},
    )
    assert add_beta.status_code == 200, add_beta.text

    stale = client.get("/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest")
    assert stale.status_code == 200, stale.text
    stale_manifest = stale.json()["manifest"]
    assert stale_manifest["status"] == "ready"
    assert stale_manifest["usable"] is True
    assert stale_manifest["fallback_mode"] == "agentic"
    assert stale_manifest["event_generation"] >= 2
    assert stale_manifest["pending_evaluation_generation"] == stale_manifest["event_generation"]
    assert stale_manifest["source_state"]["pending_severity"] == "soft_stale"
    assert stale_manifest["source_state"]["pending_reasons"] == [
        "membership_added",
        "chunk_binding_updated",
    ]


def test_kb_list_and_detail_embed_authoritative_public_ready_data_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-serving-projection"
    kb_name = "Serving Projection KB"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": kb_name,
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    created_manifest = created.json()["knowledge_base"]["agentic_ready_manifest"]
    assert created_manifest["publication_state"]["serving_status"] == "missing"
    assert created_manifest["publication_state"]["serving_usable"] is False

    built = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text
    active_id = built.json()["publication_state"]["active_publication_id"]

    storage = Storage(str(client.app.state.db_path))
    try:
        now = storage._utcnow_iso()
        with storage.transaction(immediate=True):
            storage._conn.execute(
                """
                INSERT INTO agentic_ready_automation (
                    kb_id, profile, automation_state, running_generation,
                    last_attempted_generation, claim_token, claimed_at,
                    lease_expires_at, last_attempt_publication_id,
                    last_success_at, last_error, updated_at
                )
                VALUES (?, 'general', 'failed', NULL, 0, NULL, NULL, NULL,
                        NULL, NULL, ?, ?)
                ON CONFLICT(kb_id, profile) DO UPDATE SET
                    automation_state = 'failed',
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (kb_id, "simulated candidate operation failure", now),
            )
    finally:
        storage.close()

    listed_response = client.get("/api/rag/knowledge-bases")
    detail_response = client.get(f"/api/rag/knowledge-bases/{kb_id}")
    assert listed_response.status_code == 200, listed_response.text
    assert detail_response.status_code == 200, detail_response.text
    listed = next(
        item for item in listed_response.json()["knowledge_bases"] if item["kb_id"] == kb_id
    )
    detail = detail_response.json()["knowledge_base"]

    for payload in (listed, detail):
        assert payload["name"] == kb_name
        manifest = payload["agentic_ready_manifest"]
        state = manifest["publication_state"]
        assert state["active_publication_id"] == active_id
        assert state["active_publication"]["publication_id"] == active_id
        assert state["serving_status"] == "ready"
        assert state["serving_usable"] is True
        assert state["automation_state"] == "failed"
        assert state["last_error"] == "ready_data operation failed"
        assert state["latest_operation_kind"] == "automation"
        assert state["latest_operation_state"] == "failed"
        assert manifest["latest_operation_kind"] == "automation"
        assert manifest["latest_operation_state"] == "failed"
        assert manifest["automation_state"] == "failed"
        assert manifest["last_error"] == "ready_data operation failed"


def test_orphan_pending_is_normalized_across_ready_data_public_projections(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-orphan-pending"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Orphan Pending KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    storage = Storage(str(client.app.state.db_path))
    try:
        before = storage.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile="general",
        )
        now = storage._utcnow_iso()
        with storage.transaction(immediate=True):
            storage._conn.execute(
                """
                INSERT INTO agentic_ready_automation (
                    kb_id, profile, automation_state, running_generation,
                    last_attempted_generation, claim_token, claimed_at,
                    lease_expires_at, last_attempt_publication_id,
                    last_success_at, last_error, updated_at
                )
                VALUES (?, 'general', 'pending', NULL, 0, NULL, NULL, NULL,
                        NULL, NULL, '', ?)
                ON CONFLICT(kb_id, profile) DO UPDATE SET
                    automation_state = 'pending', running_generation = NULL,
                    claim_token = NULL, claimed_at = NULL,
                    lease_expires_at = NULL, updated_at = excluded.updated_at
                """,
                (kb_id, now),
            )
            storage._conn.execute(
                """
                UPDATE agentic_ready_source_state
                SET pending_evaluation_generation = NULL
                WHERE kb_id = ? AND profile = 'general'
                """,
                (kb_id,),
            )
    finally:
        storage.close()

    listed_response = client.get("/api/rag/knowledge-bases")
    detail_response = client.get(f"/api/rag/knowledge-bases/{kb_id}")
    manifest_response = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    assert listed_response.status_code == 200, listed_response.text
    assert detail_response.status_code == 200, detail_response.text
    assert manifest_response.status_code == 200, manifest_response.text
    listed = next(
        item for item in listed_response.json()["knowledge_bases"] if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detail = detail_response.json()["knowledge_base"]["agentic_ready_manifest"]
    dedicated = manifest_response.json()["manifest"]

    for manifest in (listed, detail, dedicated):
        state = manifest["publication_state"]
        assert manifest["status"] == "ready"
        assert manifest["usable"] is True
        assert manifest["automation_state"] == "succeeded"
        assert manifest["pending_generation"] is None
        assert manifest["running_generation"] is None
        assert manifest["latest_operation_state"] == "succeeded"
        assert state["serving_status"] == "ready"
        assert state["serving_usable"] is True
        assert state["automation_state"] == "succeeded"
        assert state["pending_generation"] is None
        assert state["running_generation"] is None
        assert state["latest_operation_state"] == "succeeded"
        assert state["active_publication_id"] == before["active_publication_id"]
        assert state["previous_publication_id"] == before["previous_publication_id"]
        assert state["publication_revision"] == before["publication_revision"]

    storage = Storage(str(client.app.state.db_path))
    try:
        raw_state = storage._conn.execute(
            """
            SELECT automation_state
            FROM agentic_ready_automation
            WHERE kb_id = ? AND profile = 'general'
            """,
            (kb_id,),
        ).fetchone()
        assert raw_state == ("pending",)
    finally:
        storage.close()


@pytest.mark.parametrize("response_path", ("list", "detail"))
def test_kb_embedded_public_projection_uses_one_sqlite_read_snapshot(
    tmp_path: Path,
    monkeypatch,
    response_path: str,
) -> None:
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = f"kb-embedded-read-snapshot-{response_path}"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": f"Embedded read snapshot {response_path}",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first, second = _build_public_rollback_pair(
        client,
        db_path=tmp_path / "index.db",
        kb_id=kb_id,
        file_url=seed["alpha_url"],
    )

    def request_manifest() -> dict[str, object]:
        if response_path == "detail":
            response = client.get(f"/api/rag/knowledge-bases/{kb_id}")
            assert response.status_code == 200, response.text
            return response.json()["knowledge_base"]["agentic_ready_manifest"]
        response = client.get("/api/rag/knowledge-bases")
        assert response.status_code == 200, response.text
        listed = next(item for item in response.json()["knowledge_bases"] if item["kb_id"] == kb_id)
        return listed["agentic_ready_manifest"]

    def snapshot_identity(manifest: dict[str, object]) -> tuple[object, ...]:
        state = manifest["publication_state"]
        assert isinstance(state, dict)
        active = state.get("active_publication")
        previous = state.get("previous_publication")
        return (
            state.get("active_publication_id"),
            active.get("publication_id") if isinstance(active, dict) else None,
            active.get("status") if isinstance(active, dict) else None,
            state.get("previous_publication_id"),
            previous.get("publication_id") if isinstance(previous, dict) else None,
            previous.get("status") if isinstance(previous, dict) else None,
            state.get("serving_status"),
            state.get("serving_usable"),
            manifest.get("status"),
            manifest.get("usable"),
        )

    old_manifest = request_manifest()
    old_identity = snapshot_identity(old_manifest)
    record_read_started = threading.Event()
    mutation_finished = threading.Event()
    mutation_errors: list[BaseException] = []
    storage_type = Storage if response_path == "detail" else rag_admin_service._KBListStorageView
    original_get_publication = storage_type.get_agentic_ready_publication
    active_record_reads = 0
    race_on_record_read = 3 if response_path == "detail" else 1

    def pause_after_slot_read(self, publication_id):
        nonlocal active_record_reads
        if publication_id == second["publication_id"]:
            active_record_reads += 1
        if (
            threading.current_thread().name != "embedded-snapshot-writer"
            and publication_id == second["publication_id"]
            and active_record_reads == race_on_record_read
            and not record_read_started.is_set()
        ):
            assert self._conn.in_transaction
            record_read_started.set()
            if not mutation_finished.wait(10):
                raise RuntimeError("concurrent rollback did not finish")
        return original_get_publication(self, publication_id)

    monkeypatch.setattr(storage_type, "get_agentic_ready_publication", pause_after_slot_read)

    def rollback_publication() -> None:
        writer = Storage(str(tmp_path / "index.db"))
        try:
            if not record_read_started.wait(10):
                raise RuntimeError("reader did not reach publication record lookup")
            result = writer.rollback_agentic_ready_publication(
                kb_id=kb_id,
                profile="general",
                expected_active_publication_id=str(second["publication_id"]),
                expected_previous_publication_id=str(first["publication_id"]),
                validated_previous_publication_id=str(first["publication_id"]),
                validate_previous_publication=lambda _publication: True,
            )
            assert result["cas_won"] is True
        except BaseException as exc:  # pragma: no cover - reported in parent thread
            mutation_errors.append(exc)
        finally:
            writer.close()
            mutation_finished.set()

    writer_thread = threading.Thread(
        target=rollback_publication,
        name="embedded-snapshot-writer",
    )
    writer_thread.start()
    raced_manifest = request_manifest()
    writer_thread.join(timeout=10)
    assert not writer_thread.is_alive()
    assert not mutation_errors
    final_manifest = request_manifest()

    raced_identity = snapshot_identity(raced_manifest)
    final_identity = snapshot_identity(final_manifest)
    assert old_identity != final_identity
    assert raced_identity in {old_identity, final_identity}
    state = raced_manifest["publication_state"]
    assert isinstance(state, dict)
    assert state["active_publication_id"] == state["active_publication"]["publication_id"]
    assert state["active_publication"]["status"] == "active"
    assert state["previous_publication_id"] == state["previous_publication"]["publication_id"]
    assert state["previous_publication"]["status"] == "previous"
    assert state["serving_usable"] is True
    assert state["serving_status"] in {"ready", "stale"}


def test_fastapi_rag_admin_ready_build_launches_real_async_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-ready-async",
            "name": "Ready Async KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    ready_index = _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-ready-async",
    )
    status = client.get("/api/rag/knowledge-bases/kb-ready-async")
    assert status.status_code == 200, status.text
    # Ordinary detail no longer eagerly computes the Ready Data build selector.
    assert (
        status.json()["knowledge_base"]["agentic_ready_manifest"].get("ready_build_input") is None
    )
    fresh = client.get(
        "/api/rag/knowledge-bases/kb-ready-async/agentic-ready-manifest?include_ready_build_input=true"
    )
    assert fresh.status_code == 200, fresh.text
    ready_build_input = fresh.json()["manifest"]["ready_build_input"]
    assert ready_build_input["index_version_id"] == ready_index["index_version_id"]

    launched = client.post(
        "/api/rag/knowledge-bases/kb-ready-async/agentic-ready-manifest/build",
        json=ready_build_input,
    )

    assert launched.status_code == 202, launched.text
    assert str(launched.json()["job_id"]).startswith("task_")
    assert launched.json()["index_version_id"] == ready_index["index_version_id"]
    completed = _wait_for_task(client, str(launched.json()["job_id"]))
    assert completed["status"] == "completed", completed
    assert completed["result"]["index_version_id"] == ready_index["index_version_id"]
    assert completed["result"]["publication_id"] is None
    assert completed["result"]["publish_status"] == "awaiting_publish"

    pending = client.get(
        "/api/rag/knowledge-bases/kb-ready-async/agentic-ready-manifest?include_ready_build_input=true"
    )
    assert pending.status_code == 200, pending.text
    pending_manifest = pending.json()["manifest"]
    candidate_id = pending_manifest["last_attempt_publication_id"]
    assert str(candidate_id).startswith("arp_")
    assert pending_manifest["automation_state"] == "awaiting_publish"
    assert pending_manifest["latest_operation_kind"] == "build"
    assert pending_manifest["latest_operation_state"] == "awaiting_publish"
    assert pending.json()["publication_state"]["latest_operation_kind"] == "build"
    assert pending.json()["publication_state"]["latest_operation_state"] == "awaiting_publish"
    assert pending_manifest["ready_build_input"] == {
        "contract_version": 1,
        "index_version_id": ready_index["index_version_id"],
        "expected_source_snapshot_fingerprint": launched.json()["source_snapshot_fingerprint"],
    }
    pending_listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == "kb-ready-async"
    )["agentic_ready_manifest"]
    pending_detailed = client.get("/api/rag/knowledge-bases/kb-ready-async").json()[
        "knowledge_base"
    ]["agentic_ready_manifest"]
    for projected_manifest in (pending_listed, pending_detailed):
        assert projected_manifest["latest_operation_kind"] == "build"
        assert projected_manifest["latest_operation_state"] == "awaiting_publish"
        assert projected_manifest["publication_state"]["latest_operation_kind"] == "build"
        assert (
            projected_manifest["publication_state"]["latest_operation_state"] == "awaiting_publish"
        )
    assert pending.json()["publication_state"]["automatic_build_enabled"] is False
    assert pending.json()["publication_state"]["automatic_publish_enabled"] is False

    published = client.post(
        "/api/rag/knowledge-bases/kb-ready-async/agentic-ready-manifest/publish",
        json={
            "profile": "general",
            "publication_id": candidate_id,
            "expected_active_publication_id": None,
        },
    )
    assert published.status_code == 200, published.text
    assert published.json()["publication_id"] == candidate_id
    settled = client.get("/api/rag/knowledge-bases/kb-ready-async/agentic-ready-manifest")
    assert settled.status_code == 200, settled.text
    assert settled.json()["manifest"]["automation_state"] == "succeeded"
    assert settled.json()["manifest"]["last_attempt_publication_id"] == candidate_id
    assert settled.json()["publication_state"]["latest_operation_kind"] == "publish"
    assert settled.json()["publication_state"]["latest_operation_state"] == "succeeded"
    assert settled.json()["manifest"]["latest_operation_kind"] == "publish"

    evidence = Storage(str(tmp_path / "index.db"))
    try:
        raw_publication = evidence.get_agentic_ready_publication_state(
            kb_id="kb-ready-async",
            profile="general",
        )
        raw_automation = evidence.get_agentic_ready_automation_state(
            kb_id="kb-ready-async",
            profile="general",
        )
    finally:
        evidence.close()
    active_publication = dict(raw_publication["active_publication"])
    assert raw_automation["automation_state"] == "succeeded"
    assert raw_automation["last_attempt_publication_id"] == candidate_id
    assert datetime.fromisoformat(raw_automation["updated_at"]) >= datetime.fromisoformat(
        active_publication["published_at"]
    )

    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == "kb-ready-async"
    )["agentic_ready_manifest"]
    detailed = client.get("/api/rag/knowledge-bases/kb-ready-async").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    for projected_manifest in (listed, detailed):
        assert projected_manifest["latest_operation_kind"] == "publish"
        assert projected_manifest["latest_operation_state"] == "succeeded"
        assert projected_manifest["publication_state"]["latest_operation_kind"] == "publish"
        assert projected_manifest["publication_state"]["latest_operation_state"] == "succeeded"


def test_up_to_date_automation_settlement_is_not_reported_as_publish(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-up-to-date-operation"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Up-to-date Operation KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text
    active = built.json()["candidate_publication"]
    active_id = str(active["publication_id"])

    claimed_at = datetime(2030, 8, 27, 13, 0, tzinfo=timezone.utc)
    settled_at = claimed_at + timedelta(seconds=1)
    storage = Storage(str(tmp_path / "index.db"))
    try:
        before = storage.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile="general",
        )
        storage.set_agentic_ready_automation(
            kb_id=kb_id,
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=True,
        )
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile="general",
            reason="membership_added",
        )
        claim = storage.claim_next_agentic_ready_automation(
            now=claimed_at,
            claim_token="claim-up-to-date",
        )
        assert claim is not None
        assert claim["mode"] == "build"
        settlement = storage.settle_agentic_ready_automation_up_to_date(
            kb_id=kb_id,
            profile="general",
            generation=int(claim["generation"]),
            claim_token=str(claim["claim_token"]),
            expected_active_publication_id=active_id,
            expected_automatic_build_enabled=True,
            expected_automatic_publish_enabled=True,
            source_version_kind=str(active["source_version_kind"]),
            source_version_id=str(active["source_version_id"]),
            now=settled_at,
        )
        after = storage.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile="general",
        )
        automation = storage.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
        )
    finally:
        storage.close()
    assert settlement["action"] == "up_to_date"
    assert after["active_publication_id"] == before["active_publication_id"] == active_id
    assert after["previous_publication_id"] == before["previous_publication_id"]
    assert after["publication_revision"] == before["publication_revision"]

    status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    assert status.status_code == 200, status.text
    for manifest in (status.json()["manifest"], listed, detailed):
        state = manifest["publication_state"]
        assert state["active_publication_id"] == active_id
        assert state["serving_usable"] is True
        assert state["latest_operation_kind"] == "automation"
        assert state["latest_operation_state"] == "succeeded"
        assert manifest["latest_operation_kind"] == "automation"
        assert manifest["latest_operation_state"] == "succeeded"
    assert automation["automation_state"] == "succeeded"
    assert automation["last_attempt_publication_id"] is None
    assert automation["last_success_at"] == settled_at.isoformat()


@pytest.mark.parametrize("concurrent_mutation", ("publish", "rollback"))
def test_ready_manifest_public_projection_uses_one_sqlite_read_snapshot(
    tmp_path: Path,
    monkeypatch,
    concurrent_mutation: str,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = f"kb-read-snapshot-{concurrent_mutation}"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": f"Read snapshot {concurrent_mutation}",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]

    setup = Storage(str(tmp_path / "index.db"))
    try:
        candidate = _record_snapshot_race_publication(
            setup,
            kb_id=kb_id,
            label=f"{concurrent_mutation}-candidate",
            output_dir=tmp_path / f"{concurrent_mutation}-candidate",
        )
        if concurrent_mutation == "rollback":
            setup.publish_agentic_ready_publication(
                str(candidate["publication_id"]),
                expected_active_publication_id=str(first["publication_id"]),
            )
            expected_response_active = candidate
            expected_final_active_id = str(first["publication_id"])
        else:
            expected_response_active = first
            expected_final_active_id = str(candidate["publication_id"])
    finally:
        setup.close()

    old_response = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    assert old_response.status_code == 200, old_response.text
    old_identity = _public_snapshot_identity(old_response.json())

    record_read_started = threading.Event()
    mutation_finished = threading.Event()
    mutation_errors: list[BaseException] = []
    original_get_publication = Storage.get_agentic_ready_publication

    def pause_after_slot_read(self, publication_id):
        if (
            threading.current_thread().name != "snapshot-writer"
            and publication_id == expected_response_active["publication_id"]
            and not record_read_started.is_set()
        ):
            record_read_started.set()
            if not mutation_finished.wait(10):
                raise RuntimeError("concurrent publication mutation did not finish")
        return original_get_publication(self, publication_id)

    monkeypatch.setattr(Storage, "get_agentic_ready_publication", pause_after_slot_read)

    def mutate_publication() -> None:
        writer = Storage(str(tmp_path / "index.db"))
        try:
            if not record_read_started.wait(10):
                raise RuntimeError("reader did not reach publication record lookup")
            with writer.transaction(immediate=True):
                writer.create_kb_index_version(
                    kb_id=kb_id,
                    embedding_provider="openai",
                    embedding_model="snapshot-race-model",
                    embedding_dimension=8,
                    index_type="faiss",
                    chunk_count=0,
                    status="ready",
                )
                writer.set_agentic_ready_automation(
                    kb_id=kb_id,
                    profile="general",
                    automatic_build_enabled=True,
                    automatic_publish_enabled=True,
                )
                if concurrent_mutation == "rollback":
                    result = writer.rollback_agentic_ready_publication(
                        kb_id=kb_id,
                        profile="general",
                        expected_active_publication_id=str(candidate["publication_id"]),
                        expected_previous_publication_id=str(first["publication_id"]),
                        validated_previous_publication_id=str(first["publication_id"]),
                        validate_previous_publication=lambda _publication: True,
                    )
                else:
                    result = writer.publish_agentic_ready_publication(
                        str(candidate["publication_id"]),
                        expected_active_publication_id=str(first["publication_id"]),
                    )
            assert result["cas_won"] is True
        except BaseException as exc:  # pragma: no cover - reported in parent thread
            mutation_errors.append(exc)
        finally:
            writer.close()
            mutation_finished.set()

    writer_thread = threading.Thread(
        target=mutate_publication,
        name="snapshot-writer",
    )
    writer_thread.start()
    response = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    writer_thread.join(timeout=10)
    assert not writer_thread.is_alive()
    assert not mutation_errors
    assert response.status_code == 200, response.text
    body = response.json()
    public_state = body["publication_state"]
    assert public_state["active_publication_id"] == expected_response_active["publication_id"]
    assert (
        public_state["active_publication"]["publication_id"]
        == expected_response_active["publication_id"]
    )
    assert public_state["active_publication"]["status"] == "active"
    assert (
        public_state["active_publication"]["authoritative_source_version_id"]
        == expected_response_active["source_version_id"]
    )
    assert body["manifest"]["status"] in {"ready", "stale"}
    assert body["manifest"]["usable"] is True

    final_response = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    assert final_response.status_code == 200, final_response.text
    final_body = final_response.json()
    final_identity = _public_snapshot_identity(final_body)
    assert _public_snapshot_identity(body) in {old_identity, final_identity}
    assert _public_snapshot_identity(body) == old_identity
    assert final_identity != old_identity
    assert final_body["publication_state"]["active_publication_id"] == expected_final_active_id


def test_ready_manifest_rollback_success_response_uses_new_read_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-rollback-response-snapshot"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Rollback response snapshot",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed for rollback response snapshot", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id=kb_id,
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()
    second = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        third = _record_snapshot_race_publication(
            storage,
            kb_id=kb_id,
            label="post-rollback-winner",
            output_dir=tmp_path / "post-rollback-winner",
        )
    finally:
        storage.close()

    rollback_completed = threading.Event()
    record_read_started = threading.Event()
    mutation_finished = threading.Event()
    mutation_errors: list[BaseException] = []
    original_rollback = Storage.rollback_agentic_ready_publication
    original_get_publication = Storage.get_agentic_ready_publication

    def rollback_then_arm(self, *args, **kwargs):
        result = original_rollback(self, *args, **kwargs)
        if result.get("cas_won"):
            rollback_completed.set()
        return result

    def pause_response_record_read(self, publication_id):
        if (
            rollback_completed.is_set()
            and threading.current_thread().name != "rollback-response-writer"
            and publication_id == first["publication_id"]
            and not record_read_started.is_set()
        ):
            record_read_started.set()
            if not mutation_finished.wait(10):
                raise RuntimeError("post-rollback publication did not finish")
        return original_get_publication(self, publication_id)

    monkeypatch.setattr(Storage, "rollback_agentic_ready_publication", rollback_then_arm)
    monkeypatch.setattr(Storage, "get_agentic_ready_publication", pause_response_record_read)

    def publish_after_rollback() -> None:
        writer = Storage(str(tmp_path / "index.db"))
        try:
            if not record_read_started.wait(10):
                raise RuntimeError("rollback response did not reach publication lookup")
            result = writer.publish_agentic_ready_publication(
                str(third["publication_id"]),
                expected_active_publication_id=str(first["publication_id"]),
            )
            assert result["cas_won"] is True
        except BaseException as exc:  # pragma: no cover - reported in parent thread
            mutation_errors.append(exc)
        finally:
            writer.close()
            mutation_finished.set()

    writer_thread = threading.Thread(
        target=publish_after_rollback,
        name="rollback-response-writer",
    )
    writer_thread.start()
    response = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    writer_thread.join(timeout=10)
    assert not writer_thread.is_alive()
    assert not mutation_errors
    assert response.status_code == 200, response.text
    public_state = response.json()["publication_state"]
    assert public_state["publication_revision"] == 3
    assert response.json()["manifest"]["publication_revision"] == 3
    assert public_state["active_publication_id"] == first["publication_id"]
    assert public_state["active_publication"]["publication_id"] == first["publication_id"]
    assert public_state["active_publication"]["status"] == "active"
    assert response.json()["manifest"]["status"] in {"ready", "stale"}

    final = Storage(str(tmp_path / "index.db"))
    try:
        final_state = final.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile="general",
        )
        assert final_state["active_publication_id"] == third["publication_id"]
        assert final_state["publication_revision"] == 4
    finally:
        final.close()


def test_ready_manifest_public_projection_and_rollback_are_safe_and_cas_guarded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-publication-controls",
            "name": "Publication Controls KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    ready_index = _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-publication-controls",
    )

    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    first_publication = first_body["candidate_publication"]
    assert first_publication["index_version_id"] == ready_index["index_version_id"]
    first_snapshot = first_body["ready_data_snapshot"]
    assert first_snapshot["manifest"]["publication_revision"] == 1
    assert first_snapshot["publication_state"]["publication_revision"] == 1
    assert (
        first_snapshot["publication_state"]["active_publication_id"]
        == first_publication["publication_id"]
    )
    assert first_snapshot["publication_state"]["previous_publication_id"] is None

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed source for publication controls", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id="kb-publication-controls",
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()

    second = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest/build",
        json={},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    second_publication = second_body["candidate_publication"]
    assert second_publication["publication_id"] != first_publication["publication_id"]
    second_snapshot = second_body["ready_data_snapshot"]
    assert second_snapshot["manifest"]["publication_revision"] == 2
    assert second_snapshot["publication_state"]["publication_revision"] == 2
    assert (
        second_snapshot["publication_state"]["active_publication_id"]
        == second_publication["publication_id"]
    )
    assert (
        second_snapshot["publication_state"]["previous_publication_id"]
        == first_publication["publication_id"]
    )
    assert (
        second_snapshot["publication_state"]["active_publication"]["publication_id"]
        == second_publication["publication_id"]
    )
    assert (
        second_snapshot["publication_state"]["previous_publication"]["publication_id"]
        == first_publication["publication_id"]
    )
    serialized_build_snapshot = json.dumps(second_snapshot, sort_keys=True)
    for forbidden in (
        "source_db",
        "output_dir",
        "quarantine_dir",
        "claim_token",
        "lease_expires_at",
        "query",
        "matched_doc_id",
        "matched_file_url",
        "evidence",
    ):
        assert forbidden not in serialized_build_snapshot

    second_published_at = second_snapshot["publication_state"]["active_publication"]["published_at"]
    automation_failed_at = (
        datetime.fromisoformat(second_published_at) + timedelta(milliseconds=500)
    ).isoformat()
    failed_at = (datetime.fromisoformat(second_published_at) + timedelta(seconds=1)).isoformat()
    rollback_at = (datetime.fromisoformat(second_published_at) + timedelta(seconds=2)).isoformat()
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                """
                INSERT INTO agentic_ready_automation (
                    kb_id, profile, automation_state, running_generation,
                    last_attempted_generation, claim_token, claimed_at,
                    lease_expires_at, last_attempt_publication_id,
                    last_success_at, last_error, updated_at
                )
                VALUES (?, 'general', 'failed', NULL, 0, NULL, NULL, NULL,
                        ?, NULL, ?, ?)
                ON CONFLICT(kb_id, profile) DO UPDATE SET
                    automation_state = 'failed',
                    last_attempt_publication_id = excluded.last_attempt_publication_id,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    "kb-publication-controls",
                    second_publication["publication_id"],
                    "simulated candidate operation failure",
                    automation_failed_at,
                ),
            )
        monkeypatch.setattr(Storage, "_utcnow_iso", staticmethod(lambda: failed_at))
        failed_candidate = storage.record_agentic_ready_publication(
            kb_id="kb-publication-controls",
            index_version_id=ready_index["index_version_id"],
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="source-failed-candidate",
            profile="general",
            profile_version="1",
            status="failed",
            output_dir="",
            artifact_digest="digest-failed-candidate",
            error_message="simulated failed candidate /workspace/private/input.db",
        )
        assert failed_candidate["status"] == "failed"
        assert failed_candidate["published_at"] is None
        assert failed_candidate["updated_at"] == failed_at
    finally:
        storage.close()

    status = client.get("/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest")
    assert status.status_code == 200, status.text
    body = status.json()
    assert (
        body["publication_state"]["active_publication_id"] == second_publication["publication_id"]
    )
    assert (
        body["publication_state"]["previous_publication_id"] == first_publication["publication_id"]
    )
    assert body["publication_state"]["serving_usable"] is True
    assert body["publication_state"]["latest_operation_kind"] == "build"
    assert body["publication_state"]["latest_operation_state"] == "failed"
    assert body["publication_state"]["latest_operation_error"] == "ready_data operation failed"
    assert body["manifest"]["latest_operation_state"] == "failed"
    assert body["manifest"]["latest_operation_error"] == "ready_data operation failed"
    active = body["publication_state"]["active_publication"]
    previous = body["publication_state"]["previous_publication"]
    assert active["authoritative_source_version_kind"] == "catalog_chunks_snapshot"
    assert active["authoritative_source_version_id"] == second_publication["source_version_id"]
    assert active["observed_index_version_id"] == ready_index["index_version_id"]
    assert active["current_ready_index_version_id"] == ready_index["index_version_id"]
    assert active["index_consumed_by_builder"] is True
    assert previous["publication_id"] == first_publication["publication_id"]
    serialized_projection = json.dumps(body["publication_state"], sort_keys=True)
    for forbidden in (
        "source_db",
        "output_dir",
        "quarantine_dir",
        "claim_token",
        "lease_expires_at",
        "query",
        "matched_doc_id",
        "matched_file_url",
    ):
        assert forbidden not in serialized_projection

    rollback_url = (
        "/api/rag/knowledge-bases/kb-publication-controls/" "agentic-ready-manifest/rollback"
    )
    expected_slots = (
        second_publication["publication_id"],
        first_publication["publication_id"],
    )
    for _case, invalid_profile, include_profile in (
        ("missing", None, False),
        ("null", None, True),
        ("empty", "", True),
        ("blank", "   ", True),
        ("non-string", 17, True),
    ):
        invalid_payload = {
            "expected_active_publication_id": expected_slots[0],
            "expected_previous_publication_id": expected_slots[1],
        }
        if include_profile:
            invalid_payload["profile"] = invalid_profile
        invalid = client.post(rollback_url, json=invalid_payload)
        assert invalid.status_code == 400, invalid.text
        unchanged = client.get(
            "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest"
        ).json()["publication_state"]
        assert (
            unchanged["active_publication_id"],
            unchanged["previous_publication_id"],
        ) == expected_slots

    for field_name in (
        "expected_active_publication_id",
        "expected_previous_publication_id",
    ):
        for invalid_value in (None, "", "   ", 17, [], {}):
            invalid_payload = {
                "profile": "general",
                "expected_active_publication_id": expected_slots[0],
                "expected_previous_publication_id": expected_slots[1],
            }
            invalid_payload[field_name] = invalid_value
            invalid = client.post(rollback_url, json=invalid_payload)
            assert invalid.status_code == 400, invalid.text
            unchanged = client.get(
                "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest"
            ).json()["publication_state"]
            assert (
                unchanged["active_publication_id"],
                unchanged["previous_publication_id"],
            ) == expected_slots

    stale = client.post(
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": first_publication["publication_id"],
            "expected_previous_publication_id": second_publication["publication_id"],
        },
    )
    assert stale.status_code == 409, stale.text
    after_failed_rollback = client.get(
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest"
    ).json()
    assert after_failed_rollback["publication_state"]["latest_operation_kind"] == "rollback"
    assert after_failed_rollback["publication_state"]["latest_operation_state"] == "failed"
    assert (
        after_failed_rollback["publication_state"]["latest_operation_error"]
        == "ready_data operation failed"
    )

    monkeypatch.setattr(Storage, "_utcnow_iso", staticmethod(lambda: rollback_at))
    rollback = client.post(
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second_publication["publication_id"],
            "expected_previous_publication_id": first_publication["publication_id"],
        },
    )
    assert rollback.status_code == 200, rollback.text
    rolled = rollback.json()
    assert (
        rolled["publication_state"]["active_publication_id"] == first_publication["publication_id"]
    )
    assert (
        rolled["publication_state"]["previous_publication_id"]
        == second_publication["publication_id"]
    )
    assert rolled["manifest"]["status"] == "stale"
    assert rolled["manifest"]["serving_stale"] is True
    assert rolled["manifest"]["stale_reason"] == "source_version_changed"
    assert rolled["publication_state"]["latest_operation_kind"] == "rollback"
    assert rolled["publication_state"]["latest_operation_state"] == "succeeded"
    assert rolled["publication_state"]["latest_operation_error"] == ""
    assert rolled["publication_state"]["active_publication"]["published_at"] == rollback_at
    assert datetime.fromisoformat(rollback_at) > datetime.fromisoformat(failed_at)
    assert rolled["manifest"]["latest_operation_kind"] == "rollback"
    assert rolled["manifest"]["latest_operation_state"] == "succeeded"
    assert rolled["manifest"]["latest_operation_error"] == ""
    assert rolled["manifest"]["last_error"] == ""

    evidence = Storage(str(tmp_path / "index.db"))
    try:
        raw_rollback = evidence.get_agentic_ready_publication_state(
            kb_id="kb-publication-controls",
            profile="general",
        )
        raw_automation = evidence.get_agentic_ready_automation_state(
            kb_id="kb-publication-controls",
            profile="general",
        )
        raw_manual_operation = evidence.get_agentic_ready_manual_operation(
            kb_id="kb-publication-controls",
            profile="general",
        )
    finally:
        evidence.close()
    active_publication = dict(raw_rollback["active_publication"])
    previous_publication = dict(raw_rollback["previous_publication"])
    assert raw_rollback["updated_at"] == rollback_at
    assert active_publication["published_at"] == rollback_at
    assert active_publication["updated_at"] == rollback_at
    assert previous_publication["updated_at"] == rollback_at
    assert (
        datetime.fromisoformat(active_publication["created_at"])
        < datetime.fromisoformat(previous_publication["published_at"])
        < datetime.fromisoformat(rollback_at)
    )
    assert raw_automation["updated_at"] == automation_failed_at
    assert raw_automation["last_error"] == "simulated candidate operation failure"
    assert raw_manual_operation == {
        "kind": "rollback",
        "state": "succeeded",
        "operation_at": rollback_at,
    }

    listed_after_rollback = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == "kb-publication-controls"
    )["agentic_ready_manifest"]
    detail_after_rollback = client.get("/api/rag/knowledge-bases/kb-publication-controls").json()[
        "knowledge_base"
    ]["agentic_ready_manifest"]
    for projected_manifest in (listed_after_rollback, detail_after_rollback):
        projected_state = projected_manifest["publication_state"]
        assert projected_state["active_publication_id"] == first_publication["publication_id"]
        assert projected_state["previous_publication_id"] == second_publication["publication_id"]
        assert (
            projected_state["active_publication"]["publication_id"]
            == first_publication["publication_id"]
        )
        assert (
            projected_state["previous_publication"]["publication_id"]
            == second_publication["publication_id"]
        )
        assert projected_state["serving_usable"] is True
        assert projected_state["latest_operation_kind"] == "rollback"
        assert projected_state["latest_operation_state"] == "succeeded"
        assert projected_state["latest_operation_error"] == ""
        assert projected_manifest["latest_operation_kind"] == "rollback"
        assert projected_manifest["latest_operation_state"] == "succeeded"
        assert projected_manifest["latest_operation_error"] == ""

    automation_settings_at = (
        datetime.fromisoformat(rollback_at) + timedelta(seconds=1)
    ).isoformat()
    monkeypatch.setattr(
        Storage,
        "_utcnow_iso",
        staticmethod(lambda: automation_settings_at),
    )
    toggled = client.put(
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-automation",
        json={
            "profile": "general",
            "automatic_build_enabled": True,
            "automatic_publish_enabled": False,
        },
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["publication_state"]["updated_at"] == automation_settings_at
    assert (
        toggled.json()["publication_state"]["active_publication_id"]
        == first_publication["publication_id"]
    )
    listed_after_settings = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == "kb-publication-controls"
    )["agentic_ready_manifest"]
    detail_after_settings = client.get("/api/rag/knowledge-bases/kb-publication-controls").json()[
        "knowledge_base"
    ]["agentic_ready_manifest"]
    for projected_manifest in (listed_after_settings, detail_after_settings):
        assert projected_manifest["latest_operation_kind"] == "rollback"
        assert projected_manifest["latest_operation_state"] == "succeeded"
        assert projected_manifest["publication_state"]["latest_operation_kind"] == "rollback"
        assert projected_manifest["publication_state"]["latest_operation_state"] == "succeeded"

    registered = TestClient(app)
    registered.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["registered_user_id"]}),
    )
    forbidden = registered.post(
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": first_publication["publication_id"],
            "expected_previous_publication_id": second_publication["publication_id"],
        },
    )
    assert forbidden.status_code == 403, forbidden.text


@pytest.mark.parametrize(
    ("failure_case", "expected_status"),
    (("artifact", 422), ("source", 409), ("cas", 409)),
)
def test_failed_explicit_publish_is_latest_operation_without_displacing_active(
    tmp_path: Path,
    monkeypatch,
    failure_case: str,
    expected_status: int,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = f"kb-failed-publish-{failure_case}"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": f"Failed Publish {failure_case}",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    active = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                (f"Publish candidate {failure_case}", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id=kb_id,
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()
    candidate = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
        publish=False,
    ).json()["candidate_publication"]

    if failure_case == "artifact":
        from ai_actuarial.agentic_rag import ready_data_builder

        original_validate = ready_data_builder.validate
        candidate_output = Path(str(candidate["output_dir"])).resolve()

        def invalidate_candidate(output_dir: str) -> dict[str, object]:
            if Path(output_dir).resolve() == candidate_output:
                return {
                    "valid": False,
                    "errors": ["secret artifact /workspace/private/publish.db"],
                    "warnings": [],
                }
            return original_validate(output_dir)

        monkeypatch.setattr(ready_data_builder, "validate", invalidate_candidate)
    elif failure_case == "source":
        storage = Storage(str(tmp_path / "index.db"))
        try:
            with storage.transaction(immediate=True):
                storage._conn.execute(
                    "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                    ("Source changed after candidate", seed["alpha_url"]),
                )
                storage.mark_agentic_ready_source_event(
                    kb_id=kb_id,
                    profile="general",
                    reason="metadata_updated",
                )
        finally:
            storage.close()

    failed = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/publish",
        json={
            "profile": "general",
            "publication_id": candidate["publication_id"],
            "expected_active_publication_id": (
                "arp_stale_active" if failure_case == "cas" else active["publication_id"]
            ),
        },
    )
    assert failed.status_code == expected_status, failed.text

    status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()
    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    for manifest in (status["manifest"], listed, detailed):
        state = manifest["publication_state"]
        assert state["active_publication_id"] == active["publication_id"]
        assert state["serving_usable"] is True
        assert state["latest_operation_kind"] == "publish"
        assert state["latest_operation_state"] == "failed"
        assert state["latest_operation_error"] == "ready_data operation failed"
        assert manifest["latest_operation_kind"] == "publish"
        assert manifest["latest_operation_state"] == "failed"
        assert manifest["latest_operation_error"] == "ready_data operation failed"
        assert "/workspace/private" not in json.dumps(manifest, sort_keys=True)

    evidence = Storage(str(tmp_path / "index.db"))
    try:
        preserved = evidence.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
            include_claim_token=True,
        )
        manual_operation = evidence.get_agentic_ready_manual_operation(
            kb_id=kb_id,
            profile="general",
        )
    finally:
        evidence.close()
    assert preserved["automation_state"] == "awaiting_publish"
    assert preserved["last_attempt_publication_id"] == candidate["publication_id"]
    assert preserved["claim_token"] is None
    assert preserved["claimed_at"] is None
    assert preserved["lease_expires_at"] is None
    assert preserved["last_error"] == ""
    assert manual_operation
    assert manual_operation["kind"] == "publish"
    assert manual_operation["state"] == "failed"

    if failure_case == "cas":
        enabled = client.put(
            f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-automation",
            json={
                "profile": "general",
                "automatic_build_enabled": True,
                "automatic_publish_enabled": True,
            },
        )
        assert enabled.status_code == 200, enabled.text
        from ai_actuarial.api.services.ready_data_automation import (
            run_ready_data_automation_once,
        )

        retried = run_ready_data_automation_once(
            db_path=str(tmp_path / "index.db"),
            heartbeat_interval_seconds=0,
        )
        assert retried["status"] == "published"
        assert retried["candidate_publication"]["publication_id"] == candidate["publication_id"]
        refreshed = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()[
            "publication_state"
        ]
        assert refreshed["latest_operation_kind"] == "publish"
        assert refreshed["latest_operation_state"] == "succeeded"


@pytest.mark.parametrize(
    ("failure_case", "expected_status"),
    (("validation", 422), ("cas", 409)),
)
def test_failed_explicit_rollback_is_latest_operation_without_changing_slots(
    tmp_path: Path,
    monkeypatch,
    failure_case: str,
    expected_status: int,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = f"kb-failed-rollback-{failure_case}"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": f"Failed Rollback {failure_case}",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first, second = _build_public_rollback_pair(
        client,
        db_path=tmp_path / "index.db",
        kb_id=kb_id,
        file_url=seed["alpha_url"],
    )
    if failure_case == "validation":
        from ai_actuarial.agentic_rag import ready_data_builder

        original_validate = ready_data_builder.validate
        previous_output = Path(str(first["output_dir"])).resolve()

        def invalidate_previous(output_dir: str) -> dict[str, object]:
            if Path(output_dir).resolve() == previous_output:
                return {
                    "valid": False,
                    "errors": ["secret rollback /workspace/private/rollback.db"],
                    "warnings": [],
                }
            return original_validate(output_dir)

        monkeypatch.setattr(ready_data_builder, "validate", invalidate_previous)

    failed = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": (
                "arp_stale_active" if failure_case == "cas" else second["publication_id"]
            ),
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert failed.status_code == expected_status, failed.text

    status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()
    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    for manifest in (status["manifest"], listed, detailed):
        state = manifest["publication_state"]
        assert state["active_publication_id"] == second["publication_id"]
        assert state["previous_publication_id"] == first["publication_id"]
        assert state["serving_usable"] is True
        assert state["latest_operation_kind"] == "rollback"
        assert state["latest_operation_state"] == "failed"
        assert state["latest_operation_error"] == "ready_data operation failed"
        assert manifest["latest_operation_kind"] == "rollback"
        assert manifest["latest_operation_state"] == "failed"
        assert manifest["latest_operation_error"] == "ready_data operation failed"
        assert "/workspace/private" not in json.dumps(manifest, sort_keys=True)


def test_older_awaiting_candidate_auto_publish_is_not_inferred_as_rollback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-old-candidate-publish-kind"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Old Candidate Publish Kind",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Second publication source", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id=kb_id,
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()
    second = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile="general",
            reason="metadata_updated",
        )
    finally:
        storage.close()
    awaiting = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
        publish=False,
    ).json()["candidate_publication"]

    evidence = Storage(str(tmp_path / "index.db"))
    try:
        before_rollback = evidence.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
            include_claim_token=True,
        )
    finally:
        evidence.close()
    failed_rollback = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": "arp_stale_active",
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert failed_rollback.status_code == 409, failed_rollback.text
    evidence = Storage(str(tmp_path / "index.db"))
    try:
        after_failed_rollback = evidence.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
            include_claim_token=True,
        )
        failed_rollback_operation = evidence.get_agentic_ready_manual_operation(
            kb_id=kb_id,
            profile="general",
        )
    finally:
        evidence.close()
    for field in (
        "automation_state",
        "running_generation",
        "last_attempted_generation",
        "claim_token",
        "claimed_at",
        "lease_expires_at",
        "last_attempt_publication_id",
        "last_success_at",
        "last_error",
    ):
        assert after_failed_rollback[field] == before_rollback[field]
    assert after_failed_rollback["automation_state"] == "awaiting_publish"
    assert after_failed_rollback["last_attempt_publication_id"] == awaiting["publication_id"]
    assert failed_rollback_operation
    assert failed_rollback_operation["kind"] == "rollback"
    assert failed_rollback_operation["state"] == "failed"

    rollback_at = datetime(2031, 8, 27, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        Storage,
        "_utcnow_iso",
        staticmethod(lambda: rollback_at.isoformat()),
    )
    rolled = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["publication_state"]["latest_operation_kind"] == "rollback"
    assert datetime.fromisoformat(str(awaiting["created_at"])) < rollback_at
    evidence = Storage(str(tmp_path / "index.db"))
    try:
        after_successful_rollback = evidence.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
            include_claim_token=True,
        )
        successful_rollback_operation = evidence.get_agentic_ready_manual_operation(
            kb_id=kb_id,
            profile="general",
        )
    finally:
        evidence.close()
    for field in (
        "automation_state",
        "running_generation",
        "last_attempted_generation",
        "claim_token",
        "claimed_at",
        "lease_expires_at",
        "last_attempt_publication_id",
        "last_success_at",
        "last_error",
    ):
        assert after_successful_rollback[field] == before_rollback[field]
    assert successful_rollback_operation == {
        "kind": "rollback",
        "state": "succeeded",
        "operation_at": rollback_at.isoformat(),
    }
    enabled = client.put(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-automation",
        json={
            "profile": "general",
            "automatic_build_enabled": True,
            "automatic_publish_enabled": True,
        },
    )
    assert enabled.status_code == 200, enabled.text

    automation_at = rollback_at + timedelta(seconds=1)
    publication_at = rollback_at + timedelta(seconds=2)
    monkeypatch.setattr(
        Storage,
        "_utcnow_iso",
        staticmethod(lambda: publication_at.isoformat()),
    )
    from ai_actuarial.api.services.ready_data_automation import (
        run_ready_data_automation_once,
    )

    published = run_ready_data_automation_once(
        db_path=str(tmp_path / "index.db"),
        heartbeat_interval_seconds=0,
        clock=lambda: automation_at,
    )
    assert published["status"] == "published"
    assert published["candidate_publication"]["publication_id"] == awaiting["publication_id"]

    status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()
    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    for manifest in (status["manifest"], listed, detailed):
        state = manifest["publication_state"]
        assert state["active_publication_id"] == awaiting["publication_id"]
        assert state["previous_publication_id"] == first["publication_id"]
        assert state["serving_usable"] is True
        assert state["latest_operation_kind"] == "publish"
        assert state["latest_operation_state"] == "succeeded"
        assert state["latest_operation_error"] == ""
        assert manifest["latest_operation_kind"] == "publish"
        assert manifest["latest_operation_state"] == "succeeded"


def test_failed_build_candidate_is_latest_operation_without_displacing_active(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-failed-build-operation"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Failed Build Operation KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    first = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    active_id = first.json()["candidate_publication"]["publication_id"]
    enabled = client.put(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-automation",
        json={
            "profile": "general",
            "automatic_build_enabled": True,
            "automatic_publish_enabled": True,
        },
    )
    assert enabled.status_code == 200, enabled.text

    from ai_actuarial.agentic_rag import ready_data_builder

    original_validate = ready_data_builder.validate
    failed_at = datetime(2030, 8, 27, 14, 0, tzinfo=timezone.utc)
    retry_at = failed_at + timedelta(seconds=1)

    def fail_candidate_validation(_output_dir: str) -> dict[str, object]:
        return {
            "valid": False,
            "errors": [
                "candidate validation failed at /workspace/private/source.db "
                "claim_token=secret-build-claim"
            ],
            "warnings": [],
        }

    monkeypatch.setattr(ready_data_builder, "validate", fail_candidate_validation)
    monkeypatch.setattr(
        Storage,
        "_utcnow_iso",
        staticmethod(lambda: failed_at.isoformat()),
    )
    failed = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    monkeypatch.setattr(ready_data_builder, "validate", original_validate)
    assert failed.status_code == 200, failed.text
    failed_candidate = failed.json()["candidate_publication"]
    assert failed_candidate["status"] == "failed"
    assert failed_candidate["published_at"] is None
    assert failed_candidate["error_message"]

    status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    assert status.status_code == 200, status.text
    for manifest in (status.json()["manifest"], listed, detailed):
        state = manifest["publication_state"]
        assert state["active_publication_id"] == active_id
        assert state["active_publication"]["status"] == "active"
        assert state["serving_status"] == "ready"
        assert state["serving_usable"] is True
        assert state["latest_operation_kind"] == "build"
        assert state["latest_operation_state"] == "failed"
        assert state["latest_operation_at"] == failed_candidate["updated_at"]
        assert state["latest_operation_error"] == "ready_data operation failed"
        assert manifest["latest_operation_kind"] == "build"
        assert manifest["latest_operation_state"] == "failed"
        assert manifest["latest_operation_error"] == "ready_data operation failed"
        serialized = json.dumps(manifest, sort_keys=True).lower()
        assert "/workspace/private" not in serialized
        assert "secret-build-claim" not in serialized

    monkeypatch.setattr(
        Storage,
        "_utcnow_iso",
        staticmethod(lambda: retry_at.isoformat()),
    )
    retry = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert retry.status_code == 200, retry.text
    retry_candidate = retry.json()["candidate_publication"]
    assert retry_candidate["status"] == "validated"
    assert retry_candidate["published_at"] is None
    assert datetime.fromisoformat(failed_candidate["updated_at"]) < datetime.fromisoformat(
        retry_candidate["updated_at"]
    )
    evidence = Storage(str(tmp_path / "index.db"))
    try:
        retained_retry = evidence.get_agentic_ready_publication(
            str(retry_candidate["publication_id"])
        )
    finally:
        evidence.close()
    assert retained_retry is not None
    assert retained_retry["retention_class"] == "redundant_duplicate"
    assert retained_retry["gc_state"] == "eligible"

    retry_status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    retry_listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    retry_detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    assert retry_status.status_code == 200, retry_status.text
    for manifest in (
        retry.json()["ready_data_snapshot"]["manifest"],
        retry_status.json()["manifest"],
        retry_listed,
        retry_detailed,
    ):
        state = manifest["publication_state"]
        assert state["active_publication_id"] == active_id
        assert state["serving_status"] == "ready"
        assert state["serving_usable"] is True
        assert state["latest_operation_kind"] == "build"
        assert state["latest_operation_state"] == "succeeded"
        assert state["latest_operation_at"] == retry_candidate["updated_at"]
        assert state["latest_operation_error"] == ""
        assert manifest["latest_operation_kind"] == "build"
        assert manifest["latest_operation_state"] == "succeeded"
        assert manifest["latest_operation_error"] == ""


@pytest.mark.parametrize(
    ("phase", "candidate_status", "expected_kind"),
    (
        ("build", "failed", "build"),
        ("publish", "validated", "publish"),
    ),
)
def test_terminal_automation_failure_preserves_candidate_phase_in_public_projection(
    tmp_path: Path,
    monkeypatch,
    phase: str,
    candidate_status: str,
    expected_kind: str,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = f"kb-automatic-{phase}-failure"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": f"Automatic {phase.title()} Failure KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    claimed_at = datetime(2030, 8, 27, 12, 0, tzinfo=timezone.utc)
    candidate_at = claimed_at + timedelta(seconds=1)
    failed_at = claimed_at + timedelta(seconds=2)
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage.set_agentic_ready_automation(
            kb_id=kb_id,
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=True,
        )
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile="general",
            reason="membership_added",
        )
        claim = storage.claim_next_agentic_ready_automation(
            now=claimed_at,
            claim_token=f"claim-{phase}",
        )
        assert claim is not None
        assert claim["mode"] == "build"
        monkeypatch.setattr(
            Storage,
            "_utcnow_iso",
            staticmethod(lambda: candidate_at.isoformat()),
        )
        candidate = storage.record_agentic_ready_publication(
            kb_id=kb_id,
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id=f"source-{phase}-failure",
            profile="general",
            profile_version="1",
            status=candidate_status,
            output_dir=(
                str(tmp_path / f"candidate-{phase}") if candidate_status == "validated" else ""
            ),
            artifact_files=["ready_data_manifest.json"],
            artifact_digest=f"digest-{phase}-failure",
            smoke_result={
                "contract_version": "ready-data-staging-smoke.v1",
                "status": "passed",
            },
            error_message=(
                "simulated automatic build failure at /workspace/private/input.db"
                if candidate_status == "failed"
                else ""
            ),
        )
        finished = storage.finish_agentic_ready_automation_claim(
            kb_id=kb_id,
            profile="general",
            generation=int(claim["generation"]),
            claim_token=str(claim["claim_token"]),
            automation_state="failed",
            publication_id=str(candidate["publication_id"]),
            error_message=(f"simulated automatic {phase} failure at /workspace/private/input.db"),
            now=failed_at,
        )
        assert finished is True
        automation = storage.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
        )
    finally:
        storage.close()
    assert automation["automation_state"] == "failed"
    assert automation["last_attempt_publication_id"] == candidate["publication_id"]
    assert datetime.fromisoformat(candidate["updated_at"]) < datetime.fromisoformat(
        automation["updated_at"]
    )

    status = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    listed = next(
        item
        for item in client.get("/api/rag/knowledge-bases").json()["knowledge_bases"]
        if item["kb_id"] == kb_id
    )["agentic_ready_manifest"]
    detailed = client.get(f"/api/rag/knowledge-bases/{kb_id}").json()["knowledge_base"][
        "agentic_ready_manifest"
    ]
    assert status.status_code == 200, status.text
    for manifest in (status.json()["manifest"], listed, detailed):
        state = manifest["publication_state"]
        assert state["serving_usable"] is False
        assert state["latest_operation_kind"] == expected_kind
        assert state["latest_operation_state"] == "failed"
        assert state["latest_operation_at"] == failed_at.isoformat()
        assert state["latest_operation_error"] == "ready_data operation failed"
        assert manifest["latest_operation_kind"] == expected_kind
        assert manifest["latest_operation_state"] == "failed"
        assert manifest["latest_operation_error"] == "ready_data operation failed"


def test_public_rollback_rejects_active_publication_from_another_kb_atomically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    for kb_id in ("kb-rollback-scope-a", "kb-rollback-scope-b"):
        created = client.post(
            "/api/rag/knowledge-bases",
            json={
                "kb_id": kb_id,
                "name": kb_id,
                "kb_mode": "manual",
                "file_urls": [seed["alpha_url"]],
            },
        )
        assert created.status_code == 201, created.text

    first_a_response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-rollback-scope-a/agentic-ready-manifest/build",
        json={},
    )
    assert first_a_response.status_code == 200, first_a_response.text
    first_a = first_a_response.json()["candidate_publication"]

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed before second scoped rollback build", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id="kb-rollback-scope-a",
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()

    second_a_response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-rollback-scope-a/agentic-ready-manifest/build",
        json={},
    )
    assert second_a_response.status_code == 200, second_a_response.text
    second_a = second_a_response.json()["candidate_publication"]
    active_b_response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-rollback-scope-b/agentic-ready-manifest/build",
        json={},
    )
    assert active_b_response.status_code == 200, active_b_response.text
    active_b = active_b_response.json()["candidate_publication"]

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE agentic_ready_slots SET active_publication_id = ? "
                "WHERE kb_id = ? AND profile = ?",
                (active_b["publication_id"], "kb-rollback-scope-a", "general"),
            )

        def snapshot() -> tuple[object, object, object]:
            slots = storage._conn.execute(
                "SELECT kb_id, profile, active_publication_id, previous_publication_id "
                "FROM agentic_ready_slots "
                "WHERE kb_id IN (?, ?) ORDER BY kb_id, profile",
                ("kb-rollback-scope-a", "kb-rollback-scope-b"),
            ).fetchall()
            publications = storage._conn.execute(
                "SELECT publication_id, kb_id, profile, status FROM agentic_ready_publications "
                "WHERE publication_id IN (?, ?, ?) ORDER BY publication_id",
                (
                    first_a["publication_id"],
                    second_a["publication_id"],
                    active_b["publication_id"],
                ),
            ).fetchall()
            manifests = (
                storage.get_agentic_ready_manifest(
                    kb_id="kb-rollback-scope-a",
                    profile="general",
                ),
                storage.get_agentic_ready_manifest(
                    kb_id="kb-rollback-scope-b",
                    profile="general",
                ),
            )
            return slots, publications, manifests

        before = snapshot()
    finally:
        storage.close()

    response = client.post(
        "/api/rag/knowledge-bases/kb-rollback-scope-a/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": active_b["publication_id"],
            "expected_previous_publication_id": first_a["publication_id"],
        },
    )
    assert response.status_code == 422, response.text

    storage = Storage(str(tmp_path / "index.db"))
    try:
        after_slots = storage._conn.execute(
            "SELECT kb_id, profile, active_publication_id, previous_publication_id "
            "FROM agentic_ready_slots "
            "WHERE kb_id IN (?, ?) ORDER BY kb_id, profile",
            ("kb-rollback-scope-a", "kb-rollback-scope-b"),
        ).fetchall()
        after_publications = storage._conn.execute(
            "SELECT publication_id, kb_id, profile, status FROM agentic_ready_publications "
            "WHERE publication_id IN (?, ?, ?) ORDER BY publication_id",
            (
                first_a["publication_id"],
                second_a["publication_id"],
                active_b["publication_id"],
            ),
        ).fetchall()
        after_manifests = (
            storage.get_agentic_ready_manifest(
                kb_id="kb-rollback-scope-a",
                profile="general",
            ),
            storage.get_agentic_ready_manifest(
                kb_id="kb-rollback-scope-b",
                profile="general",
            ),
        )
        assert (after_slots, after_publications, after_manifests) == before
    finally:
        storage.close()


def test_public_rollback_accepts_canonical_legacy_publication_profiles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from ai_actuarial.api.services import ready_data_publication as publication_service

    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-legacy-publication-profile"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Legacy Publication Profile",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first_response = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()["candidate_publication"]

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed before legacy-profile rollback", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id=kb_id,
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()

    second_response = _post_ready_build_core(
        client,
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()["candidate_publication"]

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE agentic_ready_publications SET profile = ? "
                "WHERE publication_id IN (?, ?)",
                (" General ", first["publication_id"], second["publication_id"]),
            )
    finally:
        storage.close()

    projected = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
    assert projected.status_code == 200, projected.text
    projected_state = projected.json()["publication_state"]
    assert projected_state["active_publication"]["profile"] == "general"
    assert projected_state["previous_publication"]["profile"] == "general"

    validation_calls: list[str] = []
    original_validate = publication_service._validate_recorded_ready_publication

    def observe_validation(publication, **kwargs):
        validation_calls.append(str(publication.get("publication_id")))
        return original_validate(publication, **kwargs)

    monkeypatch.setattr(
        publication_service,
        "_validate_recorded_ready_publication",
        observe_validation,
    )
    rolled = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert rolled.status_code == 200, rolled.text
    assert validation_calls == [first["publication_id"]]
    rolled_state = rolled.json()["publication_state"]
    assert rolled_state["active_publication_id"] == first["publication_id"]
    assert rolled_state["previous_publication_id"] == second["publication_id"]


def test_ready_manifest_public_projection_fail_closes_sensitive_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-public-errors",
            "name": "Public Errors KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-public-errors/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    sensitive = (
        "/workspace/private/a.txt /srv/ready-data/b.txt "
        r"\\fileserver\Ready Data\c.txt C:\Project\Ready Data\d.txt "
        "C:/Project/Ready Data/e.txt claim_token=claim-secret "
        "lease_token=lease-secret output_dir=/workspace/private/output "
        "Traceback (most recent call last): internal-stack"
    )
    storage = Storage(str(tmp_path / "index.db"))
    try:
        now = storage._utcnow_iso()
        with storage.transaction(immediate=True):
            storage._conn.execute(
                """
                UPDATE agentic_ready_manifests
                SET status = 'failed', error_message = ?, updated_at = ?
                WHERE kb_id = ? AND profile = 'general'
                """,
                (sensitive, now, "kb-public-errors"),
            )
            storage._conn.execute(
                """
                UPDATE agentic_ready_source_state
                SET event_generation = event_generation + 1,
                    pending_evaluation_generation = event_generation + 1,
                    pending_severity = 'hard_stale',
                    pending_reasons_json = ?, updated_at = ?
                WHERE kb_id = ? AND profile = 'general'
                """,
                (json.dumps(["chunk_content_updated", sensitive]), now, "kb-public-errors"),
            )
            storage._conn.execute(
                """
                INSERT INTO agentic_ready_automation (
                    kb_id, profile, automation_state, running_generation,
                    last_attempted_generation, claim_token, claimed_at,
                    lease_expires_at, last_attempt_publication_id,
                    last_success_at, last_error, updated_at
                )
                VALUES (?, 'general', 'failed', NULL, 0, NULL, NULL, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(kb_id, profile) DO UPDATE SET
                    automation_state = 'failed', last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                ("kb-public-errors", sensitive, now),
            )
    finally:
        storage.close()

    response = client.get("/api/rag/knowledge-bases/kb-public-errors/agentic-ready-manifest")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["error_message"] == "ready_data operation failed"
    assert body["manifest"]["stale_reason"] == "ready_data operation failed"
    assert body["publication_state"]["last_error"] == "ready_data operation failed"
    assert body["publication_state"]["stale_reasons"] == [
        "chunk_content_updated",
        "ready_data_source_changed",
    ]
    serialized = json.dumps(body, sort_keys=True).lower()
    for forbidden in (
        "/workspace/",
        "/srv/",
        "fileserver",
        "c:\\project",
        "c:/project",
        "a.txt",
        "b.txt",
        "c.txt",
        "d.txt",
        "e.txt",
        "claim-secret",
        "lease-secret",
        "output_dir=",
        "internal-stack",
    ):
        assert forbidden not in serialized


def test_ready_manifest_public_projection_canonicalizes_all_public_state_enums(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    for kb_id in ("kb-enum-active", "kb-enum-building"):
        created = client.post(
            "/api/rag/knowledge-bases",
            json={
                "kb_id": kb_id,
                "name": kb_id,
                "kb_mode": "manual",
                "file_urls": [seed["alpha_url"]],
            },
        )
        assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-enum-active/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_manifest = Storage.get_agentic_ready_manifest
    original_publications = Storage.get_agentic_ready_publication_state
    original_automation = Storage.get_agentic_ready_automation_state
    original_source_state = Storage.get_agentic_ready_source_state
    injected = {
        "manifest": r"C:\private\status secret.txt",
        "fallback": r"\\server\ready data\fallback secret.txt",
        "publication": "output_dir=/srv/private/publication-secret",
        "smoke": "/workspace/private/smoke-secret.txt",
        "automation": "claim_token=automation-secret",
        "source_state": "lease_token=source-secret",
        "severity": r"C:/Project/Ready Data/severity-secret.txt",
        "profile": r"C:\private\profile-secret.txt",
        "source_kind": "output_dir=/srv/private/source-kind-secret",
    }

    def poisoned_manifest(self, *, kb_id, profile):
        value = original_manifest(self, kb_id=kb_id, profile=profile)
        if kb_id == "kb-enum-building":
            return {
                "kb_id": kb_id,
                "profile": profile,
                "profile_version": "1",
                "status": "building",
                "fallback_mode": "standard",
            }
        if kb_id != "kb-enum-active" or not value:
            return value
        value = dict(value)
        value["status"] = injected["manifest"]
        value["fallback_mode"] = injected["fallback"]
        value["profile"] = injected["profile"]
        value["source_version_kind"] = injected["source_kind"]
        return value

    def poisoned_publications(self, *, kb_id, profile):
        value = dict(original_publications(self, kb_id=kb_id, profile=profile))
        if kb_id != "kb-enum-active":
            return value
        active = dict(value["active_publication"])
        active["status"] = injected["publication"]
        active["source_version_kind"] = injected["source_kind"]
        active["smoke_result"] = {
            "status": injected["smoke"],
            "checked_at": "2026-08-19T12:00:00+00:00",
        }
        value["active_publication"] = active
        return value

    def poisoned_automation(self, *, kb_id, profile):
        value = dict(original_automation(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-enum-active":
            value["automation_state"] = injected["automation"]
        return value

    def poisoned_source_state(self, *, kb_id, profile):
        value = dict(original_source_state(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-enum-active":
            value.update(
                {
                    "state": injected["source_state"],
                    "pending_severity": injected["severity"],
                    "evaluated_severity": injected["severity"],
                    "stale_severity": injected["severity"],
                    "evaluated_source_version_kind": injected["source_kind"],
                    "active_source_version_kind": injected["source_kind"],
                }
            )
        return value

    monkeypatch.setattr(Storage, "get_agentic_ready_manifest", poisoned_manifest)
    monkeypatch.setattr(Storage, "get_agentic_ready_publication_state", poisoned_publications)
    monkeypatch.setattr(Storage, "get_agentic_ready_automation_state", poisoned_automation)
    monkeypatch.setattr(Storage, "get_agentic_ready_source_state", poisoned_source_state)

    response = client.get("/api/rag/knowledge-bases/kb-enum-active/agentic-ready-manifest")
    assert response.status_code == 200, response.text
    body = response.json()
    manifest = body["manifest"]
    state = body["publication_state"]
    assert manifest["status"] in {"missing", "ready", "stale", "failed", "unavailable"}
    assert manifest["profile"] == "general"
    assert manifest["fallback_mode"] == "standard"
    assert state["serving_status"] in {"missing", "ready", "stale", "failed", "unavailable"}
    assert state["automation_state"] in {
        "idle",
        "pending",
        "running",
        "building",
        "awaiting_publish",
        "awaiting_manual_confirmation",
        "succeeded",
        "failed",
    }
    assert state["active_publication"]["status"] in {
        "failed",
        "validated",
        "active",
        "previous",
    }
    assert state["active_publication"]["profile"] == "general"
    assert state["active_publication"]["authoritative_source_version_kind"] == "unknown"
    assert state["smoke_status"] in {"not_run", "skipped_empty", "failed", "passed"}
    assert state["active_publication"]["smoke_status"] in {
        "not_run",
        "skipped_empty",
        "failed",
        "passed",
    }
    source_state = manifest["source_state"]
    assert source_state["state"] in {
        "legacy_fallback",
        "pending_evaluation",
        "stale",
        "legacy_hard_gate",
        "fresh",
    }
    for severity_name in (
        "pending_severity",
        "evaluated_severity",
        "stale_severity",
    ):
        assert source_state[severity_name] in {"none", "soft_stale", "hard_stale"}
    assert source_state["evaluated_source_version_kind"] == "unknown"
    assert source_state["active_source_version_kind"] == "unknown"
    assert manifest["source_version_kind"] == "unknown"
    serialized = json.dumps(body, sort_keys=True)
    for raw_value in injected.values():
        assert raw_value not in serialized

    legacy = client.get("/api/rag/knowledge-bases/kb-enum-building/agentic-ready-manifest")
    assert legacy.status_code == 200, legacy.text
    legacy_body = legacy.json()
    assert legacy_body["manifest"]["status"] == "missing"
    assert legacy_body["publication_state"]["serving_status"] == "missing"
    assert legacy_body["publication_state"]["automation_state"] == "building"


def test_ready_manifest_public_projection_keeps_active_ready_while_automation_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-ready-running",
            "name": "Ready While Running",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_manifest = Storage.get_agentic_ready_manifest
    original_automation = Storage.get_agentic_ready_automation_state
    simulated = {
        "manifest_status": None,
        "automation_state": "running",
        "last_error": None,
    }

    def simulated_manifest(self, *, kb_id, profile):
        value = original_manifest(self, kb_id=kb_id, profile=profile)
        if kb_id == "kb-ready-running" and value and simulated["manifest_status"]:
            value = dict(value)
            value["status"] = simulated["manifest_status"]
        return value

    def running_automation(self, *, kb_id, profile):
        value = dict(original_automation(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-ready-running":
            value["automation_state"] = simulated["automation_state"]
            if simulated["last_error"] is not None:
                value["last_error"] = simulated["last_error"]
        return value

    monkeypatch.setattr(Storage, "get_agentic_ready_manifest", simulated_manifest)
    monkeypatch.setattr(Storage, "get_agentic_ready_automation_state", running_automation)
    response = client.get("/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["status"] == "ready"
    assert body["publication_state"]["serving_status"] == "ready"
    assert body["publication_state"]["automation_state"] == "running"
    assert body["publication_state"]["latest_operation_kind"] == "build"
    assert body["publication_state"]["latest_operation_state"] == "running"

    simulated.update(
        {
            "automation_state": "awaiting_publish",
            "last_error": "empty ready_data requires manual publish confirmation",
        }
    )
    awaiting_manual = client.get("/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest")
    assert awaiting_manual.status_code == 200, awaiting_manual.text
    awaiting_state = awaiting_manual.json()["publication_state"]
    assert awaiting_state["automation_state"] == "awaiting_manual_confirmation"
    assert awaiting_state["latest_operation_kind"] == "build"
    assert awaiting_state["latest_operation_state"] == "awaiting_manual_confirmation"

    simulated.update(
        {
            "manifest_status": "building",
            "automation_state": "disabled",
            "last_error": None,
        }
    )
    legacy_building = client.get("/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest")
    assert legacy_building.status_code == 200, legacy_building.text
    legacy_body = legacy_building.json()
    assert legacy_body["manifest"]["status"] == "ready"
    assert legacy_body["publication_state"]["serving_status"] == "ready"
    assert legacy_body["publication_state"]["automation_state"] == "building"
    assert legacy_body["publication_state"]["latest_operation_kind"] == "build"
    assert legacy_body["publication_state"]["latest_operation_state"] == "building"


@pytest.mark.parametrize(
    "severity_field",
    ("pending_severity", "evaluated_severity", "stale_severity"),
)
def test_ready_manifest_public_projection_fail_closes_unknown_source_severity(
    tmp_path: Path,
    monkeypatch,
    severity_field: str,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-unknown-severity",
            "name": "Unknown Severity",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-unknown-severity/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_source_state = Storage.get_agentic_ready_source_state
    injected = r"C:\private\unknown-severity.txt"

    def unknown_source_severity(self, *, kb_id, profile):
        value = dict(original_source_state(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-unknown-severity":
            value[severity_field] = injected
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_source_state",
        unknown_source_severity,
    )
    response = client.get("/api/rag/knowledge-bases/kb-unknown-severity/agentic-ready-manifest")
    assert response.status_code == 200, response.text
    body = response.json()
    manifest = body["manifest"]
    state = body["publication_state"]
    assert manifest["status"] == "stale"
    assert manifest["usable"] is False
    assert manifest["serving_stale"] is True
    assert manifest["stale_severity"] == "hard_stale"
    assert manifest["fallback_mode"] == "standard"
    assert state["serving_status"] == "stale"
    assert state["serving_usable"] is False
    assert state["serving_stale"] is True
    assert state["stale_severity"] == "hard_stale"
    assert state["stale_reasons"] == ["ready_data_source_changed"]
    public_source_state = manifest["source_state"]
    assert public_source_state[severity_field] == "hard_stale"
    assert public_source_state["stale_severity"] == "hard_stale"
    assert public_source_state["stale_reasons"] == ["ready_data_source_changed"]
    assert public_source_state["serving_stale"] is True
    assert public_source_state["serving_allowed"] is False
    assert injected not in json.dumps(body, sort_keys=True)


def test_ready_manifest_public_projection_preserves_soft_stale_agentic_serving(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-soft-stale-agentic",
            "name": "Soft Stale Agentic",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-soft-stale-agentic/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_source_state = Storage.get_agentic_ready_source_state

    def soft_stale_source_state(self, *, kb_id, profile):
        value = dict(original_source_state(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-soft-stale-agentic":
            value.update(
                {
                    "stale_confirmed": True,
                    "stale_severity": "soft_stale",
                    "stale_reasons": ["membership_added"],
                    "serving_stale": True,
                    "serving_allowed": True,
                }
            )
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_source_state",
        soft_stale_source_state,
    )
    response = client.get("/api/rag/knowledge-bases/kb-soft-stale-agentic/agentic-ready-manifest")
    assert response.status_code == 200, response.text
    body = response.json()
    manifest = body["manifest"]
    state = body["publication_state"]
    assert manifest["status"] == "stale"
    assert manifest["usable"] is True
    assert manifest["fallback_mode"] == "agentic"
    assert manifest["source_state"]["serving_stale"] is True
    assert manifest["source_state"]["serving_allowed"] is True
    assert state["serving_status"] == "stale"
    assert state["serving_usable"] is True


@pytest.mark.parametrize(
    "active_record_state",
    ("missing", "failed", "validated", "wrong_scope"),
)
def test_ready_manifest_public_projection_fail_closes_corrupt_active_slot(
    tmp_path: Path,
    monkeypatch,
    active_record_state: str,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-corrupt-active-slot",
            "name": "Corrupt Active Slot",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-active-slot/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_publications = Storage.get_agentic_ready_publication_state

    def corrupt_active_slot(self, *, kb_id, profile):
        value = dict(original_publications(self, kb_id=kb_id, profile=profile))
        if kb_id != "kb-corrupt-active-slot":
            return value
        value["active_publication_id"] = "pub-corrupt-active"
        if active_record_state == "missing":
            value["active_publication"] = None
        else:
            active = dict(value["active_publication"])
            active["publication_id"] = "pub-corrupt-active"
            if active_record_state == "wrong_scope":
                active["kb_id"] = "kb-other-scope"
            else:
                active["status"] = active_record_state
            value["active_publication"] = active
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_publication_state",
        corrupt_active_slot,
    )
    response = client.get("/api/rag/knowledge-bases/kb-corrupt-active-slot/agentic-ready-manifest")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["status"] == "unavailable"
    assert body["manifest"]["usable"] is False
    assert body["publication_state"]["serving_status"] == "unavailable"
    assert body["publication_state"]["serving_usable"] is False
    if active_record_state == "wrong_scope":
        assert body["publication_state"]["active_publication"] is None


@pytest.mark.parametrize(
    "stored_profile",
    (
        pytest.param("regulation", id="other-known-profile"),
        pytest.param("future-profile", id="unknown-profile"),
        pytest.param("", id="empty-profile"),
        pytest.param("   ", id="blank-profile"),
        pytest.param(None, id="null-profile"),
        pytest.param(17, id="number-profile"),
        pytest.param([], id="list-profile"),
        pytest.param({}, id="object-profile"),
    ),
)
def test_ready_manifest_public_projection_rejects_invalid_active_profile_scope(
    tmp_path: Path,
    monkeypatch,
    stored_profile: object,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-invalid-active-profile",
            "name": "Invalid Active Profile",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-invalid-active-profile/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_publications = Storage.get_agentic_ready_publication_state

    def invalid_active_profile(self, *, kb_id, profile):
        value = dict(original_publications(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-invalid-active-profile":
            active = dict(value["active_publication"])
            active["profile"] = stored_profile
            value["active_publication"] = active
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_publication_state",
        invalid_active_profile,
    )
    response = client.get(
        "/api/rag/knowledge-bases/kb-invalid-active-profile/agentic-ready-manifest"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["publication_state"]["active_publication"] is None
    assert body["publication_state"]["serving_status"] == "unavailable"
    assert body["publication_state"]["serving_usable"] is False
    assert body["manifest"]["status"] == "unavailable"
    assert body["manifest"]["usable"] is False


@pytest.mark.parametrize(
    "stored_profile",
    (
        pytest.param("regulation", id="other-known-profile"),
        pytest.param("future-profile", id="unknown-profile"),
        pytest.param("", id="empty-profile"),
        pytest.param("   ", id="blank-profile"),
        pytest.param(None, id="null-profile"),
        pytest.param(17, id="number-profile"),
        pytest.param([], id="list-profile"),
        pytest.param({}, id="object-profile"),
    ),
)
def test_ready_manifest_public_projection_rejects_invalid_previous_profile_scope(
    tmp_path: Path,
    monkeypatch,
    stored_profile: object,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-invalid-previous-profile",
            "name": "Invalid Previous Profile",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-invalid-previous-profile/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_publications = Storage.get_agentic_ready_publication_state

    def invalid_previous_profile(self, *, kb_id, profile):
        value = dict(original_publications(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-invalid-previous-profile":
            previous = dict(value["active_publication"])
            previous.update(
                {
                    "publication_id": "pub-invalid-previous-profile",
                    "profile": stored_profile,
                    "status": "previous",
                }
            )
            value["previous_publication_id"] = previous["publication_id"]
            value["previous_publication"] = previous
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_publication_state",
        invalid_previous_profile,
    )
    response = client.get(
        "/api/rag/knowledge-bases/kb-invalid-previous-profile/agentic-ready-manifest"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["publication_state"]["active_publication"]["profile"] == "general"
    assert body["publication_state"]["serving_status"] == "ready"
    assert body["publication_state"]["serving_usable"] is True
    assert body["publication_state"]["previous_publication"] is None


@pytest.mark.parametrize(
    "stored_status",
    (
        pytest.param("failed", id="failed"),
        pytest.param("validated", id="validated"),
        pytest.param("active", id="active"),
        pytest.param("future-status", id="unknown"),
        pytest.param(None, id="null"),
    ),
)
def test_ready_manifest_public_projection_only_exposes_previous_status(
    tmp_path: Path,
    monkeypatch,
    stored_status: object,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-invalid-previous-status",
            "name": "Invalid Previous Status",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-invalid-previous-status/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_publications = Storage.get_agentic_ready_publication_state

    def invalid_previous_status(self, *, kb_id, profile):
        value = dict(original_publications(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-invalid-previous-status":
            previous = dict(value["active_publication"])
            previous.update(
                {
                    "publication_id": "pub-invalid-previous-status",
                    "status": stored_status,
                }
            )
            value["previous_publication_id"] = previous["publication_id"]
            value["previous_publication"] = previous
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_publication_state",
        invalid_previous_status,
    )
    response = client.get(
        "/api/rag/knowledge-bases/kb-invalid-previous-status/agentic-ready-manifest"
    )
    assert response.status_code == 200, response.text
    state = response.json()["publication_state"]
    assert state["active_publication"]["status"] == "active"
    assert state["previous_publication_id"] == "pub-invalid-previous-status"
    assert state["previous_publication"] is None


def test_ready_manifest_public_projection_accepts_exact_publication_profile_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-valid-publication-profile",
            "name": "Valid Publication Profile",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-valid-publication-profile/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text
    body = client.get(
        "/api/rag/knowledge-bases/kb-valid-publication-profile/agentic-ready-manifest"
    ).json()
    assert body["publication_state"]["active_publication"]["profile"] == "general"
    assert body["publication_state"]["serving_status"] == "ready"
    assert body["publication_state"]["serving_usable"] is True


def test_ready_manifest_public_projection_preserves_legacy_ready_without_active_slot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-legacy-no-active-slot",
            "name": "Legacy No Active Slot",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    built = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-legacy-no-active-slot/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_publications = Storage.get_agentic_ready_publication_state

    def legacy_without_slot(self, *, kb_id, profile):
        value = dict(original_publications(self, kb_id=kb_id, profile=profile))
        if kb_id == "kb-legacy-no-active-slot":
            value["active_publication_id"] = None
            value["active_publication"] = None
        return value

    monkeypatch.setattr(
        Storage,
        "get_agentic_ready_publication_state",
        legacy_without_slot,
    )
    response = client.get(
        "/api/rag/knowledge-bases/kb-legacy-no-active-slot/agentic-ready-manifest"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["status"] == "ready"
    assert body["manifest"]["usable"] is True
    assert body["publication_state"]["serving_status"] == "ready"
    assert body["publication_state"]["serving_usable"] is True


def test_ready_manifest_rollback_rejects_corrupt_previous_without_changing_slots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-public-rollback-corrupt",
            "name": "Public Rollback Corrupt KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-public-rollback-corrupt/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed before corrupt rollback", seed["alpha_url"]),
            )
            storage.mark_agentic_ready_source_event(
                kb_id="kb-public-rollback-corrupt",
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()
    second = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-public-rollback-corrupt/agentic-ready-manifest/build",
        json={},
    ).json()["candidate_publication"]
    catalog_path = Path(first["output_dir"]) / "doc_catalog.jsonl"
    original_catalog = catalog_path.read_bytes()
    catalog_path.write_text(
        "corrupt previous\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/rag/knowledge-bases/kb-public-rollback-corrupt/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert response.status_code == 422, response.text
    catalog_path.write_bytes(original_catalog)
    storage = Storage(str(tmp_path / "index.db"))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-public-rollback-corrupt",
            profile="general",
        )
        assert state["active_publication_id"] == second["publication_id"]
        assert state["previous_publication_id"] == first["publication_id"]
    finally:
        storage.close()

    catalog_rows = [
        json.loads(line) for line in original_catalog.decode("utf-8").splitlines() if line.strip()
    ]
    catalog_rows[0]["title"] = "Structurally valid but digest changed"
    catalog_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in catalog_rows) + "\n",
        encoding="utf-8",
    )
    digest_mismatch = client.post(
        "/api/rag/knowledge-bases/kb-public-rollback-corrupt/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert digest_mismatch.status_code == 422, digest_mismatch.text
    catalog_path.write_bytes(original_catalog)

    storage = Storage(str(tmp_path / "index.db"))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-public-rollback-corrupt",
            profile="general",
        )
        assert state["active_publication_id"] == second["publication_id"]
        assert state["previous_publication_id"] == first["publication_id"]
        outside = tmp_path / "outside-ready-data"
        outside.mkdir()
        storage._conn.execute(
            "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
            (str(outside), first["publication_id"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    escaped = client.post(
        "/api/rag/knowledge-bases/kb-public-rollback-corrupt/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert escaped.status_code == 422, escaped.text

    storage = Storage(str(tmp_path / "index.db"))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-public-rollback-corrupt",
            profile="general",
        )
        assert state["active_publication_id"] == second["publication_id"]
        assert state["previous_publication_id"] == first["publication_id"]
        storage._conn.execute(
            "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
            (first["output_dir"], first["publication_id"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_link_check = rag_admin_service._is_link_or_reparse
    previous_path = Path(first["output_dir"]).resolve()
    monkeypatch.setattr(
        rag_admin_service,
        "_is_link_or_reparse",
        lambda path: Path(path).resolve() == previous_path or original_link_check(path),
    )
    reparse = client.post(
        "/api/rag/knowledge-bases/kb-public-rollback-corrupt/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert reparse.status_code == 422, reparse.text
    storage = Storage(str(tmp_path / "index.db"))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-public-rollback-corrupt",
            profile="general",
        )
        assert state["active_publication_id"] == second["publication_id"]
        assert state["previous_publication_id"] == first["publication_id"]
    finally:
        storage.close()


def test_public_rollback_rejects_linked_allowed_root_before_structure_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-public-rollback-linked-root"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Linked Root Rollback KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first, second = _build_public_rollback_pair(
        client,
        db_path=tmp_path / "index.db",
        kb_id=kb_id,
        file_url=str(seed["alpha_url"]),
    )
    before = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()

    ready_root = tmp_path / "agentic_ready_data"
    external_root = tmp_path / "external-ready-data-root"
    ready_root.rename(external_root)
    try:
        ready_root.symlink_to(external_root, target_is_directory=True)
    except OSError as exc:
        external_root.rename(ready_root)
        pytest.skip(f"directory symlink unavailable: {exc}")

    from ai_actuarial.agentic_rag import ready_data_builder

    validator_calls = 0

    original_validator = ready_data_builder.validate

    def count_only(output_dir: str) -> dict[str, object]:
        nonlocal validator_calls
        validator_calls += 1
        return original_validator(output_dir)

    monkeypatch.setattr(ready_data_builder, "validate", count_only)
    response = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert response.status_code == 422, response.text
    assert validator_calls == 0
    after = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()
    _assert_failed_rollback_preserved_publication(before, after)


@pytest.mark.parametrize("artifact_name", ["ready_data_manifest.json", "doc_catalog.jsonl"])
def test_public_rollback_rejects_linked_artifact_before_structure_validation(
    tmp_path: Path,
    monkeypatch,
    artifact_name: str,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = f"kb-public-rollback-linked-{artifact_name.split('.')[0]}"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Linked Artifact Rollback KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first, second = _build_public_rollback_pair(
        client,
        db_path=tmp_path / "index.db",
        kb_id=kb_id,
        file_url=str(seed["alpha_url"]),
    )
    before = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()

    artifact_path = Path(str(first["output_dir"])) / artifact_name
    external = tmp_path / "linked-artifacts" / artifact_name
    external.parent.mkdir()
    external.write_bytes(artifact_path.read_bytes())
    artifact_path.unlink()
    try:
        artifact_path.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"file symlink unavailable: {exc}")

    from ai_actuarial.agentic_rag import ready_data_builder

    original_validator = ready_data_builder.validate
    validator_calls = 0

    def count_only(output_dir: str) -> dict[str, object]:
        nonlocal validator_calls
        validator_calls += 1
        return original_validator(output_dir)

    monkeypatch.setattr(ready_data_builder, "validate", count_only)
    response = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert response.status_code == 422, response.text
    assert validator_calls == 0
    after = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()
    _assert_failed_rollback_preserved_publication(before, after)


def test_public_rollback_rejects_nested_artifact_ancestor_link_atomically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    kb_id = "kb-public-rollback-linked-artifact-parent"
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": kb_id,
            "name": "Linked Artifact Parent Rollback KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first, second = _build_public_rollback_pair(
        client,
        db_path=tmp_path / "index.db",
        kb_id=kb_id,
        file_url=str(seed["alpha_url"]),
    )

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    output_dir = Path(str(first["output_dir"]))
    real_dir = output_dir / "real"
    nested_dir = output_dir / "nested"
    real_dir.mkdir()
    nested_dir.mkdir()
    nested_artifact = "nested/catalog-copy.jsonl"
    (real_dir / "catalog-copy.jsonl").write_bytes((output_dir / "doc_catalog.jsonl").read_bytes())
    (nested_dir / "catalog-copy.jsonl").write_bytes((real_dir / "catalog-copy.jsonl").read_bytes())
    artifact_files = [*list(first["artifact_files"]), nested_artifact]
    recorded_digest = rag_admin_service._ready_data_artifact_digest(str(output_dir), artifact_files)
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage._conn.execute(
            """
            UPDATE agentic_ready_publications
            SET artifact_files_json = ?, artifact_digest = ?
            WHERE publication_id = ?
            """,
            (json.dumps(artifact_files), recorded_digest, first["publication_id"]),
        )
        storage._conn.commit()
    finally:
        storage.close()
    shutil.rmtree(nested_dir)
    try:
        nested_dir.symlink_to(real_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    before = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()

    from ai_actuarial.agentic_rag import ready_data_builder

    original_validator = ready_data_builder.validate
    validator_calls = 0

    def count_only(output_path: str) -> dict[str, object]:
        nonlocal validator_calls
        validator_calls += 1
        return original_validator(output_path)

    monkeypatch.setattr(ready_data_builder, "validate", count_only)
    response = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback",
        json={
            "profile": "general",
            "expected_active_publication_id": second["publication_id"],
            "expected_previous_publication_id": first["publication_id"],
        },
    )
    assert response.status_code == 422, response.text
    assert validator_calls == 0
    after = client.get(f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest").json()
    _assert_failed_rollback_preserved_publication(before, after)


@pytest.mark.parametrize(
    "unsafe_artifact",
    ["doc_catalog.jsonl", "../outside.jsonl", "", "C:/outside.jsonl"],
)
def test_recorded_publication_preflight_precedes_structure_validation(
    tmp_path: Path,
    monkeypatch,
    unsafe_artifact: str,
) -> None:
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    allowed_root = tmp_path / "agentic_ready_data"
    output_dir = allowed_root / "kbs" / "kb-preflight" / "general" / "1"
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "ready_data_manifest.json"
    catalog_path = output_dir / "doc_catalog.jsonl"
    manifest_path.write_text("{}", encoding="utf-8")
    catalog_path.write_text("{}\n", encoding="utf-8")
    artifact_files = ["ready_data_manifest.json", unsafe_artifact]
    recorded_digest = "not-used-before-preflight"
    validator_calls = 0

    def validator(_output_dir: str) -> dict[str, object]:
        nonlocal validator_calls
        validator_calls += 1
        return {"valid": True, "errors": [], "warnings": []}

    original_link_check = rag_admin_service._is_link_or_reparse
    monkeypatch.setattr(
        rag_admin_service,
        "_is_link_or_reparse",
        lambda path: (unsafe_artifact == "doc_catalog.jsonl" and Path(path) == catalog_path)
        or original_link_check(path),
    )
    result = rag_admin_service._validate_recorded_ready_publication(
        {
            "output_dir": str(output_dir),
            "artifact_files": artifact_files,
            "artifact_digest": recorded_digest,
        },
        validator=validator,
        allowed_output_root=str(allowed_root),
    )
    assert result["valid"] is False
    assert validator_calls == 0


def test_fastapi_rag_admin_failed_ready_build_keeps_serving_publication(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-failed-staging",
            "name": "Failed Staging KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    first_build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-failed-staging/agentic-ready-manifest/build",
        json={},
    )
    assert first_build.status_code == 200, first_build.text
    first_manifest = first_build.json()["manifest"]
    serving_manifest_path = Path(first_manifest["output_dir"]) / "ready_data_manifest.json"
    serving_bytes = serving_manifest_path.read_bytes()
    staging_root = Path(first_manifest["output_dir"]).parent
    staging_dirs_before = sorted(path.name for path in staging_root.iterdir())

    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
            ("Changed candidate summary", seed["alpha_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    from ai_actuarial.agentic_rag import ready_data_builder

    monkeypatch.setattr(
        ready_data_builder,
        "validate",
        lambda _output_dir: {
            "valid": False,
            "errors": ["synthetic validation failure"],
            "warnings": [],
        },
    )
    failed_build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-failed-staging/agentic-ready-manifest/build",
        json={},
    )
    assert failed_build.status_code == 200, failed_build.text
    body = failed_build.json()
    assert body["validation"]["valid"] is False
    assert body["candidate_publication"]["status"] == "failed"
    assert body["candidate_publication"]["output_dir"] == ""
    assert body["manifest"]["publication_id"] == first_manifest["publication_id"]
    assert body["manifest"]["status"] == "ready"
    assert body["publication_state"]["active_publication_id"] == first_manifest["publication_id"]
    assert serving_manifest_path.read_bytes() == serving_bytes
    assert sorted(path.name for path in staging_root.iterdir()) == staging_dirs_before


def test_fastapi_rag_admin_idempotent_ready_build_retains_validated_duplicate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-dedupe-staging",
            "name": "Dedupe Staging KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-staging/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_manifest = first.json()["manifest"]
    staging_root = Path(first_manifest["output_dir"]).parent
    staging_dirs_before = sorted(path.name for path in staging_root.iterdir())

    duplicate = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-staging/agentic-ready-manifest/build",
        json={},
    )
    assert duplicate.status_code == 200, duplicate.text
    body = duplicate.json()
    candidate = body["candidate_publication"]
    assert candidate["publication_id"] != first_manifest["publication_id"]
    assert candidate["status"] == "validated"
    assert Path(candidate["output_dir"]).is_dir()
    assert body["publication_state"]["active_publication_id"] == first_manifest["publication_id"]
    assert body["publication_state"]["idempotent"] is True
    assert body["publication_state"]["duplicate_retained"] is True
    assert body["publication_state"]["duplicate_gc_deferred"] is True
    assert body["publication_state"]["duplicate_gc_marked"] is True
    storage = Storage(str(tmp_path / "index.db"))
    try:
        recorded_candidate = storage.get_agentic_ready_publication(candidate["publication_id"])
        assert recorded_candidate is not None
        assert recorded_candidate["retention_class"] == "redundant_duplicate"
        assert recorded_candidate["gc_state"] == "eligible"
        assert recorded_candidate["gc_marked_at"]
    finally:
        storage.close()
    assert sorted(path.name for path in staging_root.iterdir()) == sorted(
        [*staging_dirs_before, Path(candidate["output_dir"]).name]
    )


def test_fastapi_rag_admin_duplicate_keeps_deferred_compatibility_when_gc_mark_loses_guard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-dedupe-gc-guard-loss",
            "name": "Dedupe GC Guard Loss KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-gc-guard-loss/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text

    monkeypatch.setattr(
        Storage,
        "mark_agentic_ready_publication_redundant_duplicate",
        lambda _storage, _publication_id, *, expected_active_publication_id: False,
    )
    duplicate = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-gc-guard-loss/agentic-ready-manifest/build",
        json={},
    )

    assert duplicate.status_code == 200, duplicate.text
    body = duplicate.json()
    candidate = body["candidate_publication"]
    state = body["publication_state"]
    assert candidate["status"] == "validated"
    assert Path(candidate["output_dir"]).is_dir()
    assert state["duplicate_retained"] is True
    assert state["duplicate_gc_deferred"] is True
    assert state["duplicate_gc_marked"] is False
    storage = Storage(str(tmp_path / "index.db"))
    try:
        recorded_candidate = storage.get_agentic_ready_publication(candidate["publication_id"])
        assert recorded_candidate is not None
        assert recorded_candidate["retention_class"] == ""
        assert recorded_candidate["gc_state"] == ""
    finally:
        storage.close()


def test_fastapi_rag_admin_duplicate_reports_concurrent_active_cas_loss(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-dedupe-cas-loss",
            "name": "Dedupe CAS Loss KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-cas-loss/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_candidate = first.json()["candidate_publication"]

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_validate = rag_admin_service._validate_recorded_ready_publication
    concurrent: dict[str, object] = {}

    def publish_different_identity_after_validation(publication, **kwargs):
        result = original_validate(publication, **kwargs)
        if not concurrent and publication["publication_id"] == first_candidate["publication_id"]:
            storage = Storage(str(tmp_path / "index.db"))
            try:
                winner_output_dir = Path(str(publication["output_dir"])).with_name(
                    f'{Path(str(publication["output_dir"])).name}-concurrent'
                )
                shutil.copytree(str(publication["output_dir"]), winner_output_dir)
                winner = storage.record_agentic_ready_publication(
                    kb_id=str(publication["kb_id"]),
                    index_version_id=publication["index_version_id"],
                    source_version_kind=str(publication["source_version_kind"]),
                    source_version_id=f'{publication["source_version_id"]}:concurrent',
                    profile=str(publication["profile"]),
                    profile_version=str(publication["profile_version"]),
                    status="validated",
                    output_dir=str(winner_output_dir),
                    artifact_files=list(publication["artifact_files"]),
                    doc_count=int(publication["doc_count"]),
                    section_count=int(publication["section_count"]),
                    built_at=publication["built_at"],
                    artifact_digest=str(publication["artifact_digest"]),
                    source_db=str(publication["source_db"]),
                    schema_versions=dict(publication["schema_versions"]),
                    error_message="",
                )
                concurrent["publication_id"] = winner["publication_id"]
                winner_state = storage.publish_agentic_ready_publication(
                    str(winner["publication_id"]),
                    expected_active_publication_id=str(publication["publication_id"]),
                )
                assert winner_state["cas_won"] is True
            finally:
                storage.close()
        return result

    monkeypatch.setattr(
        rag_admin_service,
        "_validate_recorded_ready_publication",
        publish_different_identity_after_validation,
    )

    duplicate = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-cas-loss/agentic-ready-manifest/build",
        json={},
    )
    assert duplicate.status_code == 200, duplicate.text
    body = duplicate.json()
    candidate = body["candidate_publication"]
    state = body["publication_state"]
    assert candidate["publication_id"] not in {
        first_candidate["publication_id"],
        concurrent["publication_id"],
    }
    assert candidate["status"] == "validated"
    assert Path(candidate["output_dir"]).is_dir()
    assert state["active_publication_id"] == concurrent["publication_id"]
    assert state["idempotent"] is False
    assert state["cas_won"] is False
    assert state["cas_lost"] is True


def test_fastapi_rag_admin_exception_build_cleans_partial_staging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-exception-staging",
            "name": "Exception Staging KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.agentic_rag import ready_data_builder

    def partial_failure(*, output_dir: str, **_kwargs):
        candidate = Path(output_dir)
        candidate.mkdir(parents=True)
        (candidate / "partial.jsonl").write_text('{"partial":true}\n', encoding="utf-8")
        raise RuntimeError("synthetic builder failure")

    monkeypatch.setattr(ready_data_builder, "build_l0", partial_failure)
    failed = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-exception-staging/agentic-ready-manifest/build",
        json={},
    )
    assert failed.status_code == 200, failed.text
    candidate = failed.json()["candidate_publication"]
    assert candidate["status"] == "failed"
    assert candidate["output_dir"] == ""
    assert len(candidate["artifact_digest"]) == 64
    staging_root = (
        tmp_path
        / "agentic_ready_data"
        / "kbs"
        / "kb-exception-staging"
        / "general"
        / "1"
        / "staging"
    )
    assert not staging_root.exists() or list(staging_root.iterdir()) == []


def test_fastapi_rag_admin_rejects_symlink_staging_root_without_touching_outside(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-symlink-staging",
            "name": "Symlink Staging KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    outside = tmp_path / "outside-staging"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    staging_root = (
        tmp_path / "agentic_ready_data" / "kbs" / "kb-symlink-staging" / "general" / "1" / "staging"
    )
    staging_root.parent.mkdir(parents=True)
    try:
        staging_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-symlink-staging/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 400, response.text
    assert "staging" in response.json()["error"].lower()
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert outside.is_dir()


def test_fastapi_rag_admin_cleanup_warning_does_not_mask_builder_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-cleanup-warning",
            "name": "Cleanup Warning KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.agentic_rag import ready_data_builder
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    def build_failure(**_kwargs):
        raise RuntimeError("original builder failure")

    def cleanup_failure(*_args, **_kwargs):
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(ready_data_builder, "build_l0", build_failure)
    monkeypatch.setattr(rag_admin_service, "_remove_unreferenced_staging_dir", cleanup_failure)
    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-cleanup-warning/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 200, response.text
    validation = response.json()["validation"]
    assert validation["errors"] == ["original builder failure"]
    assert validation["warnings"] == ["staging cleanup failed: synthetic cleanup failure"]
    assert response.json()["candidate_publication"]["error_message"] == "original builder failure"


def test_fastapi_rag_admin_rejects_builder_returning_a_different_staging_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-unexpected-build-path",
            "name": "Unexpected Build Path KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.agentic_rag import ready_data_builder

    original_build = ready_data_builder.build_l0

    def build_with_wrong_returned_path(**kwargs):
        manifest = original_build(**kwargs)
        manifest["output_dir"] = str(Path(kwargs["output_dir"]).with_name("other-candidate"))
        return manifest

    monkeypatch.setattr(ready_data_builder, "build_l0", build_with_wrong_returned_path)
    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-unexpected-build-path/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validation"]["valid"] is False
    assert body["validation"]["errors"] == [
        "ready_data builder returned an unexpected staging output path"
    ]
    assert body["publication_state"]["active_publication_id"] is None
    assert body["publication_state"]["previous_publication_id"] is None
    assert body["candidate_publication"]["status"] == "failed"
    staging_roots = list((tmp_path / "agentic_ready_data").rglob("staging"))
    assert len(staging_roots) == 1
    assert list(staging_roots[0].iterdir()) == []


def test_fastapi_rag_admin_rechecks_staging_root_immediately_before_publish(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outside = tmp_path / "outside-publish"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-publish-root-swap",
            "name": "Publish Root Swap KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_digest = rag_admin_service._ready_data_artifact_digest

    def digest_then_swap_root(output_dir: str, artifact_files: list[str]) -> str:
        digest = original_digest(output_dir, artifact_files)
        staging_root = Path(output_dir).parent
        held_root = staging_root.with_name("staging-held")
        staging_root.rename(held_root)
        staging_root.symlink_to(outside, target_is_directory=True)
        return digest

    monkeypatch.setattr(rag_admin_service, "_ready_data_artifact_digest", digest_then_swap_root)
    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-publish-root-swap/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validation"]["valid"] is False
    assert "link or reparse" in body["validation"]["errors"][0]
    assert body["publication_state"]["active_publication_id"] is None
    assert body["publication_state"]["previous_publication_id"] is None
    assert body["candidate_publication"]["status"] == "failed"
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert outside.is_dir()


def test_fastapi_rag_admin_rechecks_generated_candidate_before_publish(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-publish-recheck",
            "name": "Publish Recheck KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_verify = rag_admin_service._verified_staging_candidate
    verified_paths: list[str] = []

    def fail_second_verification(**kwargs):
        verified_paths.append(str(kwargs["output_dir"]))
        if len(verified_paths) == 2:
            raise ValueError("synthetic staging root replacement")
        return original_verify(**kwargs)

    monkeypatch.setattr(
        rag_admin_service,
        "_verified_staging_candidate",
        fail_second_verification,
    )
    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-publish-recheck/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert verified_paths[:2] == [verified_paths[0], verified_paths[0]]
    assert body["validation"]["valid"] is False
    assert body["validation"]["errors"] == ["synthetic staging root replacement"]
    assert body["publication_state"]["active_publication_id"] is None
    assert body["publication_state"]["previous_publication_id"] is None
    assert body["candidate_publication"]["status"] == "failed"


def test_fastapi_rag_admin_rechecks_candidate_after_publication_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-post-record-recheck",
            "name": "Post Record Recheck KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_record = Storage.record_agentic_ready_publication
    original_verify = rag_admin_service._verified_staging_candidate
    state = {"validated_recorded": False, "post_record_check_failed": False}

    def record_then_arm(self, **kwargs):
        publication = original_record(self, **kwargs)
        if kwargs["status"] == "validated":
            state["validated_recorded"] = True
        return publication

    def fail_once_after_record(**kwargs):
        if state["validated_recorded"] and not state["post_record_check_failed"]:
            state["post_record_check_failed"] = True
            raise ValueError("synthetic post-record staging replacement")
        return original_verify(**kwargs)

    monkeypatch.setattr(Storage, "record_agentic_ready_publication", record_then_arm)
    monkeypatch.setattr(
        rag_admin_service,
        "_verified_staging_candidate",
        fail_once_after_record,
    )
    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-post-record-recheck/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert state == {"validated_recorded": True, "post_record_check_failed": True}
    assert body["validation"]["valid"] is False
    assert body["validation"]["errors"] == ["synthetic post-record staging replacement"]
    assert body["publication_state"]["active_publication_id"] is None
    assert body["publication_state"]["previous_publication_id"] is None
    assert body["candidate_publication"]["status"] in {"validated", "failed"}


def test_fastapi_rag_admin_post_record_gate_failure_can_retry_with_new_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-post-record-retry",
            "name": "Post Record Retry KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_record = Storage.record_agentic_ready_publication
    original_verify = rag_admin_service._verified_staging_candidate
    state = {"validated_recorded": False, "post_record_check_failed": False}

    def record_then_arm(self, **kwargs):
        publication = original_record(self, **kwargs)
        if kwargs["status"] == "validated":
            state["validated_recorded"] = True
        return publication

    def fail_once_after_record(**kwargs):
        if state["validated_recorded"] and not state["post_record_check_failed"]:
            state["post_record_check_failed"] = True
            raise ValueError("synthetic post-record staging replacement")
        return original_verify(**kwargs)

    monkeypatch.setattr(Storage, "record_agentic_ready_publication", record_then_arm)
    monkeypatch.setattr(
        rag_admin_service,
        "_verified_staging_candidate",
        fail_once_after_record,
    )

    failed_publish = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-post-record-retry/agentic-ready-manifest/build",
        json={},
    )
    assert failed_publish.status_code == 200, failed_publish.text
    failed_body = failed_publish.json()
    failed_candidate = failed_body["candidate_publication"]
    assert failed_body["validation"]["valid"] is False
    assert failed_candidate["status"] == "validated"
    assert Path(failed_candidate["output_dir"]).is_dir()
    assert failed_body["publication_state"]["active_publication_id"] is None

    retry = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-post-record-retry/agentic-ready-manifest/build",
        json={},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    retry_candidate = retry_body["candidate_publication"]
    assert retry_body["validation"]["valid"] is True
    assert retry_candidate["publication_id"] != failed_candidate["publication_id"]
    assert retry_candidate["status"] == "active"
    assert (
        retry_body["publication_state"]["active_publication_id"]
        == retry_candidate["publication_id"]
    )
    assert retry_body["publication_state"]["previous_publication_id"] is None


def test_fastapi_rag_admin_replaces_corrupt_active_with_fresh_duplicate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-corrupt-active",
            "name": "Corrupt Active KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-active/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    first_candidate = first_body["candidate_publication"]
    first_output = Path(first_candidate["output_dir"])
    (first_output / "doc_catalog.jsonl").write_text("corrupt\n", encoding="utf-8")

    replacement = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-active/agentic-ready-manifest/build",
        json={},
    )
    assert replacement.status_code == 200, replacement.text
    replacement_body = replacement.json()
    replacement_candidate = replacement_body["candidate_publication"]
    assert replacement_body["validation"]["valid"] is True
    assert replacement_candidate["publication_id"] != first_candidate["publication_id"]
    assert replacement_candidate["status"] == "active"
    assert Path(replacement_candidate["output_dir"]) != first_output
    assert (
        replacement_body["publication_state"]["active_publication_id"]
        == replacement_candidate["publication_id"]
    )
    assert replacement_body["publication_state"]["previous_publication_id"] is None
    storage = Storage(str(tmp_path / "index.db"))
    try:
        corrupt_after = storage.get_agentic_ready_publication(
            str(first_candidate["publication_id"])
        )
        assert corrupt_after is not None
        assert corrupt_after["status"] == "failed"
        assert "artifact digest does not match" in corrupt_after["error_message"].lower()
    finally:
        storage.close()


def test_fastapi_rag_admin_excludes_corrupt_different_identity_from_previous(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-corrupt-previous",
            "name": "Corrupt Previous KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-previous/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_candidate = first.json()["candidate_publication"]
    (Path(first_candidate["output_dir"]) / "doc_catalog.jsonl").write_text(
        "corrupt\n",
        encoding="utf-8",
    )
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction():
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed source identity", seed["alpha_url"]),
            )
    finally:
        storage.close()

    second = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-previous/agentic-ready-manifest/build",
        json={},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    replacement = body["candidate_publication"]
    assert replacement["source_version_id"] != first_candidate["source_version_id"]
    assert replacement["status"] == "active"
    assert body["publication_state"]["previous_publication_id"] is None

    storage = Storage(str(tmp_path / "index.db"))
    try:
        corrupt = storage.get_agentic_ready_publication(str(first_candidate["publication_id"]))
        assert corrupt is not None
        assert corrupt["status"] == "failed"
        with pytest.raises(
            ValueError,
            match="no previous validated ready-data publication",
        ):
            storage.rollback_agentic_ready_publication(
                kb_id="kb-corrupt-previous",
                profile="general",
                expected_active_publication_id=str(replacement["publication_id"]),
                expected_previous_publication_id=str(first_candidate["publication_id"]),
                validated_previous_publication_id=str(first_candidate["publication_id"]),
            )
    finally:
        storage.close()


def test_fastapi_rag_admin_revalidates_different_identity_active_before_previous(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-different-identity-recheck",
            "name": "Different Identity Recheck KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-different-identity-recheck/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_candidate = first.json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction():
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed source for guarded recheck", seed["alpha_url"]),
            )
    finally:
        storage.close()

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_validate = rag_admin_service._validate_recorded_ready_publication
    validations = 0

    def validate_then_corrupt(publication, **kwargs):
        nonlocal validations
        result = original_validate(publication, **kwargs)
        if publication["publication_id"] == first_candidate["publication_id"]:
            validations += 1
            if validations == 1:
                assert result["valid"] is True
                (Path(publication["output_dir"]) / "doc_catalog.jsonl").write_text(
                    "corrupt after different-identity validation\n",
                    encoding="utf-8",
                )
        return result

    monkeypatch.setattr(
        rag_admin_service,
        "_validate_recorded_ready_publication",
        validate_then_corrupt,
    )
    second = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-different-identity-recheck/agentic-ready-manifest/build",
        json={},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    replacement = body["candidate_publication"]
    assert validations >= 2
    assert replacement["source_version_id"] != first_candidate["source_version_id"]
    assert replacement["status"] == "active"
    assert body["publication_state"]["previous_publication_id"] is None

    storage = Storage(str(tmp_path / "index.db"))
    try:
        corrupt = storage.get_agentic_ready_publication(str(first_candidate["publication_id"]))
        assert corrupt is not None and corrupt["status"] == "failed"
    finally:
        storage.close()


def test_internal_ready_publication_rollback_rejects_corrupt_previous(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-corrupt-rollback",
            "name": "Corrupt Rollback KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-rollback/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_candidate = first.json()["candidate_publication"]
    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction():
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed source for rollback", seed["alpha_url"]),
            )
    finally:
        storage.close()
    second = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-rollback/agentic-ready-manifest/build",
        json={},
    )
    assert second.status_code == 200, second.text
    second_candidate = second.json()["candidate_publication"]
    (Path(first_candidate["output_dir"]) / "doc_catalog.jsonl").write_text(
        "corrupt previous\n",
        encoding="utf-8",
    )

    from ai_actuarial.agentic_rag import ready_data_builder
    from ai_actuarial.api.services import rag_admin as rag_admin_service

    storage = Storage(str(tmp_path / "index.db"))
    try:
        before = storage.get_agentic_ready_publication_state(
            kb_id="kb-corrupt-rollback",
            profile="general",
        )
        with pytest.raises(ValueError, match="previous ready_data validation failed"):
            rag_admin_service._rollback_agentic_ready_publication(
                storage,
                kb_id="kb-corrupt-rollback",
                profile="general",
                validator=ready_data_builder.validate,
                allowed_output_root=str(tmp_path / "agentic_ready_data"),
            )
        after = storage.get_agentic_ready_publication_state(
            kb_id="kb-corrupt-rollback",
            profile="general",
        )
        serving = storage.get_agentic_ready_manifest(
            kb_id="kb-corrupt-rollback",
            profile="general",
        )
        assert after["active_publication_id"] == before["active_publication_id"]
        assert after["previous_publication_id"] == before["previous_publication_id"]
        assert after["active_publication_id"] == second_candidate["publication_id"]
        assert after["previous_publication_id"] == first_candidate["publication_id"]
        assert serving is not None
        assert serving["publication_id"] == second_candidate["publication_id"]
    finally:
        storage.close()


def test_fastapi_rag_admin_revalidates_active_after_dedupe_decision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-dedupe-post-validation-corruption",
            "name": "Dedupe Post-validation Corruption KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-post-validation-corruption/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_candidate = first.json()["candidate_publication"]

    from ai_actuarial.api.services import rag_admin as rag_admin_service

    original_validate = rag_admin_service._validate_recorded_ready_publication
    validations = 0

    def validate_then_corrupt(publication, **kwargs):
        nonlocal validations
        result = original_validate(publication, **kwargs)
        if publication["publication_id"] == first_candidate["publication_id"]:
            validations += 1
            if validations == 1:
                assert result["valid"] is True
                (Path(publication["output_dir"]) / "doc_catalog.jsonl").write_text(
                    "corrupt after validation\n",
                    encoding="utf-8",
                )
        return result

    monkeypatch.setattr(
        rag_admin_service,
        "_validate_recorded_ready_publication",
        validate_then_corrupt,
    )
    replacement = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-dedupe-post-validation-corruption/agentic-ready-manifest/build",
        json={},
    )
    assert replacement.status_code == 200, replacement.text
    body = replacement.json()
    candidate = body["candidate_publication"]
    assert validations >= 2
    assert candidate["publication_id"] != first_candidate["publication_id"]
    assert candidate["status"] == "active"
    assert Path(candidate["output_dir"]).is_dir()
    assert body["publication_state"]["active_publication_id"] == candidate["publication_id"]
    assert body["publication_state"]["previous_publication_id"] is None


def test_fastapi_rag_admin_corrupt_replacement_cas_loss_is_not_reported_as_replaced(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-corrupt-cas-loss",
            "name": "Corrupt CAS Loss KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-cas-loss/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_candidate = first.json()["candidate_publication"]
    (Path(first_candidate["output_dir"]) / "doc_catalog.jsonl").write_text(
        "corrupt\n",
        encoding="utf-8",
    )

    original_publish = Storage.publish_agentic_ready_publication
    concurrent: dict[str, object] = {}

    def publish_concurrent_replacement(
        self: Storage,
        publication_id: str,
        *,
        expected_active_publication_id: str | None,
        preserve_expected_active_as_previous: bool = True,
        invalidated_expected_active_error: str = "",
    ) -> dict[str, object]:
        if not concurrent:
            candidate = self.get_agentic_ready_publication(publication_id)
            assert candidate is not None
            winner_output_dir = Path(str(candidate["output_dir"])).with_name(
                f'{Path(str(candidate["output_dir"])).name}-concurrent'
            )
            shutil.copytree(str(candidate["output_dir"]), winner_output_dir)
            winner = self.record_agentic_ready_publication(
                kb_id=str(candidate["kb_id"]),
                index_version_id=candidate["index_version_id"],
                source_version_kind=str(candidate["source_version_kind"]),
                source_version_id=f'{candidate["source_version_id"]}:concurrent',
                profile=str(candidate["profile"]),
                profile_version=str(candidate["profile_version"]),
                status="validated",
                output_dir=str(winner_output_dir),
                artifact_files=list(candidate["artifact_files"]),
                doc_count=int(candidate["doc_count"]),
                section_count=int(candidate["section_count"]),
                built_at=candidate["built_at"],
                artifact_digest=str(candidate["artifact_digest"]),
                source_db=str(candidate["source_db"]),
                schema_versions=dict(candidate["schema_versions"]),
                error_message="",
            )
            concurrent["publication_id"] = winner["publication_id"]
            winner_state = original_publish(
                self,
                str(winner["publication_id"]),
                expected_active_publication_id=expected_active_publication_id,
                preserve_expected_active_as_previous=False,
                invalidated_expected_active_error="concurrent invalid active replacement",
            )
            assert winner_state["cas_won"] is True
        return original_publish(
            self,
            publication_id,
            expected_active_publication_id=expected_active_publication_id,
            preserve_expected_active_as_previous=preserve_expected_active_as_previous,
            invalidated_expected_active_error=invalidated_expected_active_error,
        )

    monkeypatch.setattr(
        Storage,
        "publish_agentic_ready_publication",
        publish_concurrent_replacement,
    )
    replacement = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-corrupt-cas-loss/agentic-ready-manifest/build",
        json={},
    )
    assert replacement.status_code == 200, replacement.text
    body = replacement.json()
    candidate = body["candidate_publication"]
    warnings = body["validation"]["warnings"]
    assert candidate["status"] == "validated"
    assert Path(candidate["output_dir"]).is_dir()
    assert body["publication_state"]["active_publication_id"] == concurrent["publication_id"]
    assert body["publication_state"]["cas_won"] is False
    assert not any("replaced invalid active" in warning for warning in warnings)
    assert any("lost publication CAS" in warning for warning in warnings)


def test_fastapi_rag_admin_rejects_real_staging_swap_after_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    outside = tmp_path / "outside-post-record"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    probe = tmp_path / "post-record-symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
        probe.unlink()
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-real-post-record-swap",
            "name": "Real Post Record Swap KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    original_record = Storage.record_agentic_ready_publication
    swapped = False

    def record_then_swap_root(self, **kwargs):
        nonlocal swapped
        publication = original_record(self, **kwargs)
        if kwargs["status"] == "validated" and not swapped:
            staging_root = Path(kwargs["output_dir"]).parent
            staging_root.rename(staging_root.with_name("staging-held-post-record"))
            staging_root.symlink_to(outside, target_is_directory=True)
            swapped = True
        return publication

    monkeypatch.setattr(Storage, "record_agentic_ready_publication", record_then_swap_root)
    response = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-real-post-record-swap/agentic-ready-manifest/build",
        json={},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert swapped is True
    assert body["validation"]["valid"] is False
    assert "link or reparse" in body["validation"]["errors"][0]
    assert body["publication_state"]["active_publication_id"] is None
    assert body["publication_state"]["previous_publication_id"] is None
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert outside.is_dir()


def test_fastapi_rag_admin_first_publication_preserves_legacy_ready_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-legacy-ready",
            "name": "Legacy Ready KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    initial_build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-legacy-ready/agentic-ready-manifest/build",
        json={},
    )
    assert initial_build.status_code == 200, initial_build.text
    legacy_manifest = initial_build.json()["manifest"]
    legacy_output_dir = legacy_manifest["output_dir"]
    legacy_artifact_digest = legacy_manifest["artifact_digest"]

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction():
            storage._conn.execute(
                "DELETE FROM agentic_ready_slots WHERE kb_id = ?",
                ("kb-legacy-ready",),
            )
            storage._conn.execute(
                "DELETE FROM agentic_ready_publications WHERE kb_id = ?",
                ("kb-legacy-ready",),
            )
            storage._conn.execute(
                """
                UPDATE agentic_ready_manifests
                SET publication_id = NULL, index_version_id = NULL,
                    source_version_kind = NULL, source_version_id = NULL,
                    artifact_digest = NULL
                WHERE kb_id = ? AND profile = 'general'
                """,
                ("kb-legacy-ready",),
            )
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed after the legacy ready-data build", seed["alpha_url"]),
            )
    finally:
        storage.close()

    migrated_build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-legacy-ready/agentic-ready-manifest/build",
        json={},
    )
    assert migrated_build.status_code == 200, migrated_build.text
    state = migrated_build.json()["publication_state"]
    assert state["previous_publication_id"]
    previous = state["previous_publication"]
    assert previous["status"] == "previous"
    assert previous["output_dir"] == legacy_output_dir
    assert previous["artifact_digest"] == legacy_artifact_digest
    assert previous["source_version_kind"] == "legacy_ready_data"
    assert previous["source_version_id"] == f"artifact:{legacy_artifact_digest}"


def test_fastapi_rag_admin_invalid_legacy_manifest_is_not_registered_as_previous(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-invalid-legacy",
            "name": "Invalid Legacy KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    initial = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-invalid-legacy/agentic-ready-manifest/build",
        json={},
    )
    assert initial.status_code == 200, initial.text
    legacy_manifest = initial.json()["manifest"]
    legacy_output_dir = Path(legacy_manifest["output_dir"])

    storage = Storage(str(tmp_path / "index.db"))
    try:
        with storage.transaction():
            storage._conn.execute(
                "DELETE FROM agentic_ready_slots WHERE kb_id = ?",
                ("kb-invalid-legacy",),
            )
            storage._conn.execute(
                "DELETE FROM agentic_ready_publications WHERE kb_id = ?",
                ("kb-invalid-legacy",),
            )
            storage._conn.execute(
                """
                UPDATE agentic_ready_manifests
                SET publication_id = NULL, index_version_id = NULL,
                    source_version_kind = NULL, source_version_id = NULL,
                    artifact_digest = NULL
                WHERE kb_id = ? AND profile = 'general'
                """,
                ("kb-invalid-legacy",),
            )
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("Changed after invalid legacy build", seed["alpha_url"]),
            )
    finally:
        storage.close()
    (legacy_output_dir / "doc_catalog.jsonl").write_text("not-json\n", encoding="utf-8")

    blocked = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-invalid-legacy/agentic-ready-manifest/build",
        json={},
    )
    assert blocked.status_code == 200, blocked.text
    body = blocked.json()
    assert body["validation"]["valid"] is False
    assert "legacy ready_data validation failed" in body["validation"]["errors"][0]
    assert body["publication_state"]["active_publication_id"] is None
    assert body["publication_state"]["previous_publication_id"] is None
    assert body["manifest"]["publication_id"] == ""
    assert Path(body["manifest"]["output_dir"]) == legacy_output_dir
    assert legacy_output_dir.exists()


def test_fastapi_rag_admin_ready_build_uses_builder_input_snapshot_not_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-index-source",
            "name": "Indexed Source KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    ready = _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-index-source",
    )
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage._conn.execute(
            """
            INSERT INTO kb_index_versions (
                index_version_id, kb_id, embedding_model, index_type, status,
                chunk_count, built_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "idx-newer-error",
                "kb-index-source",
                "test-model",
                "faiss",
                "error",
                0,
                "2026-08-18T11:00:00+00:00",
                "2026-08-18T11:00:00+00:00",
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()

    build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-index-source/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    candidate = build.json()["candidate_publication"]
    assert ready["status"] == "ready"
    assert candidate["source_version_kind"] == "catalog_chunks_snapshot"
    assert candidate["source_version_id"].startswith("rdsnap_")
    assert candidate["index_version_id"] == ready["index_version_id"]


def test_fastapi_rag_admin_agentic_ready_manifest_builds_regulation_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-regulation-manifest",
            "name": "Regulation Manifest KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
            "manifest_profile": "regulation",
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-regulation-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    manifest = build.json()["manifest"]
    assert manifest["profile"] == "regulation"
    assert manifest["status"] == "ready", build.text
    assert manifest["usable"] is True
    assert manifest["fallback_mode"] == "agentic"
    output_dir = Path(manifest["output_dir"])
    assert (output_dir / "title_aliases.jsonl").is_file()
    assert (output_dir / "sections_structured.jsonl").is_file()
    assert (output_dir / "relations_graph.json").is_file()


def test_fastapi_rag_admin_agentic_ready_manifest_builds_formula_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    formula_source = "\n".join(
        [
            "# Net premium",
            "Net Premium = PV Benefits / PV Premiums.",
            "| Term | Description |",
            "| q_x | mortality rate |",
            "| v | discount factor |",
            "The reserve calculation uses mortality rate and discount rate assumptions.",
        ]
    )
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage.update_file_markdown(
            str(seed["alpha_url"]),
            formula_source,
            "manual",
        )
    finally:
        storage.close()
    _seed_ready_chunk_set(
        tmp_path / "index.db",
        str(seed["alpha_url"]),
        str(seed["default_chunk_profile_id"]),
        text=formula_source,
    )

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-formula-manifest",
            "name": "Formula Manifest KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
            "manifest_profile": "formula",
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-formula-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    manifest = build.json()["manifest"]
    assert manifest["profile"] == "formula"
    assert manifest["status"] == "ready"
    assert manifest["usable"] is True
    assert manifest["fallback_mode"] == "agentic"
    output_dir = Path(manifest["output_dir"])
    assert (output_dir / "formula_cards.jsonl").is_file()
    assert (output_dir / "tables_structured.jsonl").is_file()
    assert (output_dir / "calculation_terms.jsonl").is_file()
    formula_cards = [
        json.loads(line)
        for line in (output_dir / "formula_cards.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert formula_cards[0]["formula_text"] == "Net Premium = PV Benefits / PV Premiums."


def test_fastapi_rag_admin_agentic_manifest_rejects_output_dir_escape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-output-dir-guard",
            "name": "Output Dir Guard KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    ready_build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={},
    )
    assert ready_build.status_code == 200, ready_build.text
    ready_manifest = ready_build.json()["manifest"]
    assert ready_manifest["status"] == "ready"

    traversal = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={"output_dir": "../escape"},
    )
    assert traversal.status_code == 400
    assert "output_dir" in traversal.json()["error"]

    after_traversal = client.get(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest"
    )
    assert after_traversal.status_code == 200, after_traversal.text
    after_traversal_manifest = after_traversal.json()["manifest"]
    assert after_traversal_manifest["status"] == "ready"
    assert after_traversal_manifest["output_dir"] == ready_manifest["output_dir"]

    absolute_outside = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={"output_dir": str(tmp_path.parent / "outside-agentic-ready-data")},
    )
    assert absolute_outside.status_code == 400
    assert "output_dir" in absolute_outside.json()["error"]

    after_absolute = client.get(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest"
    )
    assert after_absolute.status_code == 200, after_absolute.text
    after_absolute_manifest = after_absolute.json()["manifest"]
    assert after_absolute_manifest["status"] == "ready"
    assert after_absolute_manifest["output_dir"] == ready_manifest["output_dir"]


def test_fastapi_rag_admin_legacy_manifest_stale_uses_bound_chunks_and_catalog_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]

    storage = Storage(str(db_path))
    try:
        profile_one = storage.create_chunk_profile(
            name="agentic-bound-profile",
            chunk_size=300,
            chunk_overlap=50,
        )
        profile_two = storage.create_chunk_profile(
            name="agentic-unbound-profile",
            chunk_size=301,
            chunk_overlap=51,
        )
    finally:
        storage.close()
    _seed_ready_chunk_set(db_path, alpha_url, profile_one["profile_id"], text="Bound profile chunk")
    _seed_ready_chunk_set(
        db_path, alpha_url, profile_two["profile_id"], text="Unbound profile chunk"
    )

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-bound-manifest",
            "name": "Bound Manifest KB",
            "kb_mode": "manual",
            "file_urls": [alpha_url],
            "chunk_profile_id": profile_one["profile_id"],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-bound-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    manifest = build.json()["manifest"]
    assert manifest["status"] == "ready"
    section_text = (Path(manifest["output_dir"]) / "sections.jsonl").read_text(encoding="utf-8")
    assert "Bound profile chunk" in section_text
    assert "Unbound profile chunk" not in section_text

    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "DELETE FROM agentic_ready_source_state WHERE kb_id = ?",
            ("kb-bound-manifest",),
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET updated_at = ? WHERE profile_id = ?",
            ("2099-01-01T00:00:00+00:00", profile_two["profile_id"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    still_ready = client.get("/api/rag/knowledge-bases/kb-bound-manifest/agentic-ready-manifest")
    assert still_ready.status_code == 200, still_ready.text
    assert still_ready.json()["manifest"]["status"] == "ready"

    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET summary = ?, updated_at = ? WHERE file_url = ?",
            ("Updated summary", "2099-01-02T00:00:00+00:00", alpha_url),
        )
        storage._conn.commit()
    finally:
        storage.close()

    stale = client.get("/api/rag/knowledge-bases/kb-bound-manifest/agentic-ready-manifest")
    assert stale.status_code == 200, stale.text
    stale_body = stale.json()
    assert stale_body["manifest"]["status"] == "stale"
    assert stale_body["publication_state"]["serving_stale"] is True
    assert stale_body["publication_state"]["stale_severity"] == "soft_stale"
    assert stale_body["publication_state"]["stale_reasons"] == [
        "KB source files changed after the ready_data manifest was built"
    ]


@pytest.mark.parametrize("invalid_binding_kind", ["orphan", "catalog_not_ok"])
def test_fastapi_rag_admin_legacy_manifest_ignores_binding_outside_builder_input(
    tmp_path: Path,
    monkeypatch,
    invalid_binding_kind: str,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = str(seed["alpha_url"])
    beta_url = str(seed["beta_url"])

    storage = Storage(str(db_path))
    try:
        profile = storage.create_chunk_profile(
            name=f"legacy-invalid-binding-{invalid_binding_kind}",
            chunk_size=300,
            chunk_overlap=50,
        )
    finally:
        storage.close()
    _seed_ready_chunk_set(db_path, alpha_url, profile["profile_id"], text="Alpha fallback chunk")
    invalid_chunk_set = _seed_ready_chunk_set(
        db_path,
        beta_url,
        profile["profile_id"],
        text="Ignored binding chunk",
    )

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-legacy-invalid-binding",
            "name": "Legacy Invalid Binding KB",
            "kb_mode": "manual",
            "file_urls": [alpha_url],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    build = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-legacy-invalid-binding/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    assert build.json()["manifest"]["status"] == "ready"

    storage = Storage(str(db_path))
    try:
        if invalid_binding_kind == "catalog_not_ok":
            storage._conn.execute(
                """
                INSERT INTO rag_kb_files(kb_id, file_url, added_at)
                VALUES (?, ?, ?)
                """,
                (
                    "kb-legacy-invalid-binding",
                    beta_url,
                    "2000-01-01T00:00:00+00:00",
                ),
            )
            storage._conn.execute(
                "UPDATE catalog_items SET status = ?, updated_at = ? WHERE file_url = ?",
                ("error", "2000-01-01T00:00:00+00:00", beta_url),
            )
            storage._conn.commit()
        storage.bind_chunk_set_to_kb(
            kb_id="kb-legacy-invalid-binding",
            file_url=beta_url,
            chunk_set_id=str(invalid_chunk_set["chunk_set_id"]),
            bound_by="historical-test",
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET updated_at = ? WHERE chunk_set_id = ?",
            ("2099-01-01T00:00:00+00:00", invalid_chunk_set["chunk_set_id"]),
        )
        storage._conn.execute(
            "DELETE FROM agentic_ready_source_state WHERE kb_id = ?",
            ("kb-legacy-invalid-binding",),
        )
        storage._conn.commit()
    finally:
        storage.close()

    status = client.get("/api/rag/knowledge-bases/kb-legacy-invalid-binding/agentic-ready-manifest")
    assert status.status_code == 200, status.text
    assert status.json()["manifest"]["status"] == "ready"


def test_manual_ready_build_settles_orphan_pending_without_overriding_latest_operation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-manual-generation",
            "name": "Manual generation KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-manual-generation/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text

    storage = Storage(str(tmp_path / "index.db"))
    try:
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-manual-generation",
            profile="general",
            reason="membership_removed",
        )
        assert marked["serving_allowed"] is False
        with storage.transaction(immediate=True):
            storage._conn.execute(
                """
                INSERT INTO agentic_ready_automation (
                    kb_id, profile, automation_state, running_generation,
                    last_attempted_generation, claim_token, claimed_at,
                    lease_expires_at, last_attempt_publication_id,
                    last_success_at, last_error, updated_at
                )
                VALUES (?, 'general', 'pending', NULL, 0, NULL, NULL, NULL,
                        NULL, NULL, '', ?)
                """,
                ("kb-manual-generation", "2000-01-01T00:00:00+00:00"),
            )
        pending = storage.get_agentic_ready_automation_state(
            kb_id="kb-manual-generation",
            profile="general",
        )
        assert pending["automation_state"] == "pending"
        assert pending["pending_evaluation_generation"] == marked["event_generation"]
    finally:
        storage.close()

    rebuilt = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-manual-generation/agentic-ready-manifest/build",
        json={},
    )

    assert rebuilt.status_code == 200, rebuilt.text
    manifest = rebuilt.json()["manifest"]
    assert rebuilt.json()["validation"]["valid"] is True
    assert manifest["pending_evaluation_generation"] is None
    assert manifest["stale_severity"] == "none"
    assert manifest["serving_stale"] is False
    assert manifest["usable"] is True
    from ai_actuarial.api.services.ready_data_publication import _latest_build_attempt

    storage = Storage(str(tmp_path / "index.db"))
    try:
        latest_build_attempt = _latest_build_attempt(
            storage,
            kb_id="kb-manual-generation",
            profile="general",
        )
        automation = storage.get_agentic_ready_automation_state(
            kb_id="kb-manual-generation",
            profile="general",
        )
    finally:
        storage.close()
    assert latest_build_attempt is not None
    assert automation["automation_state"] == "succeeded"
    assert automation["pending_evaluation_generation"] is None
    projected = client.get("/api/rag/knowledge-bases/kb-manual-generation/agentic-ready-manifest")
    assert projected.status_code == 200, projected.text
    publication_state = projected.json()["publication_state"]
    assert publication_state["latest_operation_kind"] == "build"
    assert publication_state["latest_operation_state"] == "succeeded"
    assert publication_state["latest_operation_at"] == latest_build_attempt["updated_at"]


def test_manual_ready_build_does_not_clear_generation_created_during_build(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-manual-generation-race",
            "name": "Manual generation race KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text
    first = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-manual-generation-race/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    initial_generation = int(first.json()["manifest"]["event_generation"])

    storage = Storage(str(tmp_path / "index.db"))
    try:
        first_mark = storage.mark_agentic_ready_source_event(
            kb_id="kb-manual-generation-race",
            profile="general",
            reason="membership_removed",
        )
        assert first_mark["event_generation"] == initial_generation + 1
    finally:
        storage.close()

    from ai_actuarial.agentic_rag import ready_data_builder

    original_build = ready_data_builder.build_l0

    def build_then_mark_new_generation(*args, **kwargs):
        result = original_build(*args, **kwargs)
        concurrent = Storage(str(tmp_path / "index.db"))
        try:
            concurrent.mark_agentic_ready_source_event(
                kb_id="kb-manual-generation-race",
                profile="general",
                reason="source_deleted",
            )
        finally:
            concurrent.close()
        return result

    monkeypatch.setattr(ready_data_builder, "build_l0", build_then_mark_new_generation)

    rebuilt = _post_ready_build_core(
        client,
        "/api/rag/knowledge-bases/kb-manual-generation-race/agentic-ready-manifest/build",
        json={},
    )

    assert rebuilt.status_code == 200, rebuilt.text
    manifest = rebuilt.json()["manifest"]
    assert rebuilt.json()["validation"]["valid"] is True
    expected_generation = int(first_mark["event_generation"]) + 1
    assert manifest["event_generation"] == expected_generation
    assert manifest["pending_evaluation_generation"] == expected_generation
    assert manifest["stale_severity"] == "hard_stale"
    assert manifest["usable"] is False


def test_fastapi_rag_admin_kb_file_membership_routes_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-files-test",
            "name": "KB Files Test",
            "kb_mode": "manual",
            "chunk_size": 300,
            "chunk_overlap": 50,
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    add_files = client.post(
        "/api/rag/knowledge-bases/kb-files-test/files",
        json={"file_urls": [alpha_url]},
    )
    assert add_files.status_code == 200, add_files.text
    assert add_files.json()["added_count"] == 1

    files_after_add = client.get("/api/rag/knowledge-bases/kb-files-test/files")
    assert files_after_add.status_code == 200, files_after_add.text
    assert any(item["file_url"] == alpha_url for item in files_after_add.json()["files"])

    storage = Storage(str(db_path))
    try:
        added_state = storage.get_agentic_ready_source_state(
            kb_id="kb-files-test",
            profile="general",
        )
        assert added_state["event_generation"] == 2
        assert added_state["pending_severity"] == "hard_stale"
        assert added_state["pending_reasons"] == [
            "membership_added",
            "access_scope_restricted",
        ]
    finally:
        storage.close()

    remove_file = client.delete(f"/api/rag/knowledge-bases/kb-files-test/files/{alpha_url}")
    assert remove_file.status_code == 200, remove_file.text

    files_after_remove = client.get("/api/rag/knowledge-bases/kb-files-test/files")
    assert files_after_remove.status_code == 200, files_after_remove.text
    assert not any(item["file_url"] == alpha_url for item in files_after_remove.json()["files"])

    storage = Storage(str(db_path))
    try:
        removed_state = storage.get_agentic_ready_source_state(
            kb_id="kb-files-test",
            profile="general",
        )
        assert removed_state["event_generation"] == 3
        assert removed_state["pending_severity"] == "hard_stale"
        assert removed_state["pending_reasons"] == [
            "membership_added",
            "access_scope_restricted",
            "membership_removed",
        ]
        assert removed_state["serving_allowed"] is False
    finally:
        storage.close()


def test_fastapi_rag_admin_kb_add_marks_dirty_and_delete_soft_applies(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    alpha_url = seed["alpha_url"]
    beta_url = seed["beta_url"]

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-index-dirty",
            "name": "Index Dirty KB",
            "kb_mode": "manual",
            "file_urls": [alpha_url],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-index-dirty",
        persist_embeddings=True,
    )
    storage = Storage(str(tmp_path / "index.db"))
    try:
        indexed_at = "2026-05-24T02:00:00+00:00"
        storage._conn.execute(
            "UPDATE rag_kb_files SET indexed_at = ?, chunk_count = ? WHERE kb_id = ? AND file_url = ?",
            (indexed_at, 1, "kb-index-dirty", alpha_url),
        )
        storage._conn.execute(
            "UPDATE catalog_items SET markdown_updated_at = ? WHERE file_url = ?",
            (indexed_at, alpha_url),
        )
        storage._conn.execute(
            """
            INSERT INTO rag_chunks (chunk_id, kb_id, file_url, chunk_index, content, token_count, section_hierarchy, embedding_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "kb-index-dirty:alpha:0",
                "kb-index-dirty",
                alpha_url,
                0,
                "Alpha indexed chunk",
                3,
                "Alpha",
                "hash-alpha",
                indexed_at,
            ),
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET chunk_count = ?, index_dirty_at = NULL WHERE kb_id = ?",
            (1, "kb-index-dirty"),
        )
        storage._conn.commit()
    finally:
        storage.close()

    initial_detail = client.get("/api/rag/knowledge-bases/kb-index-dirty")
    assert initial_detail.status_code == 200, initial_detail.text
    assert initial_detail.json()["knowledge_base"]["needs_reindex"] is False

    add_beta = client.post(
        "/api/rag/knowledge-bases/kb-index-dirty/files",
        json={"file_urls": [beta_url]},
    )
    assert add_beta.status_code == 200, add_beta.text

    after_add = client.get("/api/rag/knowledge-bases/kb-index-dirty")
    assert after_add.status_code == 200, after_add.text
    assert after_add.json()["knowledge_base"]["needs_reindex"] is True

    _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-index-dirty",
        persist_embeddings=True,
    )

    incremental = client.post(
        "/api/rag/knowledge-bases/kb-index-dirty/index",
        json={"incremental": True},
    )
    assert incremental.status_code == 202, incremental.text
    assert incremental.json()["file_count"] == 2
    completed = _wait_for_task(client, str(incremental.json()["job_id"]))
    assert completed["status"] == "completed", completed

    remove_alpha = client.delete(f"/api/rag/knowledge-bases/kb-index-dirty/files/{alpha_url}")
    assert remove_alpha.status_code == 200, remove_alpha.text

    after_delete = client.get("/api/rag/knowledge-bases/kb-index-dirty")
    assert after_delete.status_code == 200, after_delete.text
    assert after_delete.json()["knowledge_base"]["needs_reindex"] is True

    storage = Storage(str(tmp_path / "index.db"))
    try:
        stale_chunks = storage._conn.execute(
            "SELECT COUNT(*) FROM rag_chunks WHERE kb_id = ? AND file_url = ?",
            ("kb-index-dirty", alpha_url),
        ).fetchone()[0]
    finally:
        storage.close()
    assert stale_chunks == 1


@pytest.mark.parametrize(
    ("kb_mode", "selector"),
    [
        ("manual", {"file_urls": ["alpha"]}),
        ("category", {"categories": ["AI"]}),
        ("all", {}),
    ],
)
def test_kb_create_preflight_missing_chunks_leaves_no_partial_kb(
    tmp_path: Path,
    monkeypatch,
    kb_mode: str,
    selector: dict[str, object],
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": f"missing-{kb_mode}", "chunk_size": 333, "chunk_overlap": 17},
    )
    assert profile.status_code == 201, profile.text
    selector_payload = dict(selector)
    if selector_payload.get("file_urls") == ["alpha"]:
        selector_payload["file_urls"] = [seed["alpha_url"]]

    response = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": f"kb-preflight-{kb_mode}",
            "name": f"Preflight {kb_mode}",
            "kb_mode": kb_mode,
            "chunk_profile_id": profile.json()["profile"]["profile_id"],
            **selector_payload,
        },
    )

    assert response.status_code == 400, response.text
    assert "missing_chunk:" in response.json()["error"]
    assert "Chunk & Embedding" in response.json()["error"]
    missing = client.get(f"/api/rag/knowledge-bases/kb-preflight-{kb_mode}")
    assert missing.status_code == 404


def test_manual_add_preflight_missing_chunk_leaves_membership_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "missing-manual-add", "chunk_size": 334, "chunk_overlap": 18},
    )
    profile_id = profile.json()["profile"]["profile_id"]
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-preflight-manual-add",
            "name": "Preflight Manual Add",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        "/api/rag/knowledge-bases/kb-preflight-manual-add/files",
        json={"file_urls": [seed["alpha_url"]]},
    )

    assert response.status_code == 400, response.text
    assert "missing_chunk:" in response.json()["error"]
    files = client.get("/api/rag/knowledge-bases/kb-preflight-manual-add/files")
    assert files.json()["files"] == []


def test_category_replace_preflight_preserves_existing_mapping_membership_and_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "category-replace-preflight", "chunk_size": 335, "chunk_overlap": 19},
    )
    profile_id = profile.json()["profile"]["profile_id"]
    alpha_set = _seed_ready_chunk_set(
        db_path, seed["alpha_url"], profile_id, text="Existing AI chunk"
    )
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("Risk", seed["beta_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-category-preflight",
            "name": "Category Preflight",
            "kb_mode": "category",
            "chunk_profile_id": profile_id,
            "categories": ["AI"],
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        "/api/rag/knowledge-bases/kb-category-preflight/categories",
        json={"action": "replace", "categories": ["Risk"]},
    )

    assert response.status_code == 400, response.text
    assert "missing_chunk:" in response.json()["error"]
    assert client.get("/api/rag/knowledge-bases/kb-category-preflight/categories").json()[
        "categories"
    ] == ["AI"]
    files = client.get("/api/rag/knowledge-bases/kb-category-preflight/files")
    assert [row["file_url"] for row in files.json()["files"]] == [seed["alpha_url"]]
    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT chunk_set_id FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-category-preflight",),
            ).fetchone()[0]
            == alpha_set["chunk_set_id"]
        )
    finally:
        storage.close()


def test_profile_update_preflight_preserves_old_profile_and_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    old_profile = client.post(
        "/api/chunk/profiles",
        json={"name": "old-profile", "chunk_size": 256, "chunk_overlap": 32},
    ).json()["profile"]
    new_profile = client.post(
        "/api/chunk/profiles",
        json={"name": "new-profile", "chunk_size": 512, "chunk_overlap": 32},
    ).json()["profile"]
    old_set = _seed_ready_chunk_set(
        db_path, seed["alpha_url"], old_profile["profile_id"], text="Old profile chunk"
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-profile-preflight",
            "name": "Profile Preflight",
            "kb_mode": "manual",
            "chunk_profile_id": old_profile["profile_id"],
            "file_urls": [seed["alpha_url"]],
        },
    )
    assert created.status_code == 201, created.text

    response = client.put(
        "/api/rag/knowledge-bases/kb-profile-preflight",
        json={"chunk_profile_id": new_profile["profile_id"]},
    )

    assert response.status_code == 400, response.text
    assert "missing_chunk:" in response.json()["error"]
    current = client.get("/api/rag/knowledge-bases/kb-profile-preflight")
    assert current.json()["knowledge_base"]["chunk_profile_id"] == old_profile["profile_id"]
    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT chunk_set_id FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-profile-preflight",),
            ).fetchone()[0]
            == old_set["chunk_set_id"]
        )
    finally:
        storage.close()


def test_fastapi_rag_admin_rebuilds_complete_index_after_embedding_change(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    alpha_url = seed["alpha_url"]

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-embedding-change",
            "name": "Embedding Change KB",
            "kb_mode": "manual",
            "file_urls": [alpha_url],
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-embedding-change",
        persist_embeddings=True,
    )

    storage = Storage(str(tmp_path / "index.db"))
    try:
        old_built_at = "2026-05-24T02:00:00+00:00"
        storage._conn.execute(
            "UPDATE rag_kb_files SET indexed_at = ?, chunk_count = ? WHERE kb_id = ? AND file_url = ?",
            (old_built_at, 1, "kb-embedding-change", alpha_url),
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET chunk_count = ?, updated_at = ? WHERE kb_id = ?",
            (1, old_built_at, "kb-embedding-change"),
        )
        storage._conn.commit()
        storage.create_kb_index_version(
            kb_id="kb-embedding-change",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
            index_type="Flat",
            chunk_count=1,
            status="ready",
            built_at=old_built_at,
        )
    finally:
        storage.close()

    incremental = client.post(
        "/api/rag/knowledge-bases/kb-embedding-change/index",
        json={"incremental": True},
    )

    assert incremental.status_code == 202, incremental.text
    assert (
        incremental.json()["embedding_identity_key"]
        == create_kb.json()["knowledge_base"]["embedding_identity_key"]
    )


def test_fastapi_rag_admin_kb_detail_surfaces_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    alpha_url = seed["alpha_url"]

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-detail-test",
            "name": "Detail Test KB",
            "kb_mode": "manual",
            "chunk_size": 300,
            "chunk_overlap": 50,
            "embedding_model": "text-embedding-3-small",
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    stats = client.get("/api/rag/knowledge-bases/kb-detail-test/stats")
    assert stats.status_code == 200, stats.text

    files = client.get("/api/rag/knowledge-bases/kb-detail-test/files")
    assert files.status_code == 200, files.text

    categories = client.get("/api/rag/knowledge-bases/kb-detail-test/categories")
    assert categories.status_code == 200, categories.text

    unmapped = client.get("/api/rag/categories/unmapped")
    assert unmapped.status_code == 200, unmapped.text

    selectable = client.get("/api/rag/files/selectable")
    assert selectable.status_code == 200, selectable.text
    assert any(item["url"] == alpha_url for item in selectable.json()["files"])

    pending = client.get("/api/rag/knowledge-bases/kb-detail-test/files/pending")
    assert pending.status_code == 200, pending.text

    bind = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/bindings",
        json={
            "bindings": [
                {
                    "file_url": alpha_url,
                    "chunk_set_id": "cs_missing",
                    "binding_mode": "follow_latest",
                }
            ]
        },
    )
    assert bind.status_code in {200, 400, 404}, bind.text

    set_categories = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/categories",
        json={"categories": ["AI"]},
    )
    assert set_categories.status_code == 200, set_categories.text

    remove_categories = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/categories",
        json={"categories": ["AI"], "action": "remove"},
    )
    assert remove_categories.status_code == 200, remove_categories.text
    categories_after_remove = client.get("/api/rag/knowledge-bases/kb-detail-test/categories")
    assert categories_after_remove.status_code == 200, categories_after_remove.text
    assert "AI" not in categories_after_remove.json()["categories"]

    replace_categories = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/categories",
        json={"categories": ["Risk"], "action": "replace"},
    )
    assert replace_categories.status_code == 200, replace_categories.text
    categories_after_replace = client.get("/api/rag/knowledge-bases/kb-detail-test/categories")
    assert categories_after_replace.status_code == 200, categories_after_replace.text
    assert categories_after_replace.json()["categories"] == ["Risk"]

    add_alpha = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/files",
        json={"file_urls": [alpha_url]},
    )
    assert add_alpha.status_code == 200, add_alpha.text
    _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-detail-test",
        persist_embeddings=True,
    )

    index = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/index",
        json={},
    )
    assert index.status_code in {200, 202}, index.text

    cleanup = client.post("/api/chunk-sets/cleanup", json={"dry_run": True})
    assert cleanup.status_code == 200, cleanup.text


def test_fastapi_rag_admin_preserves_zero_chunk_overlap_and_requires_task_bridge(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    alpha_url = seed["alpha_url"]

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "zero-overlap-profile",
            "chunk_size": 256,
            "chunk_overlap": 0,
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    assert create_profile.json()["profile"]["chunk_overlap"] == 0
    profile_id = create_profile.json()["profile"]["profile_id"]
    _seed_ready_chunk_set(tmp_path / "index.db", alpha_url, profile_id, text="Zero overlap chunk")

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-zero-overlap",
            "name": "KB Zero Overlap",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
            "chunk_size": 256,
            "chunk_overlap": 0,
            "file_urls": [alpha_url],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    assert create_kb.json()["knowledge_base"]["chunk_overlap"] == 0

    _prepare_committed_kb_index(
        tmp_path / "index.db",
        "kb-zero-overlap",
        persist_embeddings=True,
    )

    index = client.post(
        "/api/rag/knowledge-bases/kb-zero-overlap/index",
        json={"force_reindex": True},
    )

    assert index.status_code == 202, index.text
    assert index.json()["kb_id"] == "kb-zero-overlap"
    assert str(index.json()["job_id"]).startswith("task_")
    assert "category_sync" not in index.json()
    assert "all_sync" not in index.json()
    assert "chunk_bindings" not in index.json()


def test_fastapi_rag_admin_create_kb_uses_existing_chunk_profile_bindings(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    alpha_url = seed["alpha_url"]
    beta_url = seed["beta_url"]

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "kb-create-profile",
            "chunk_size": 300,
            "chunk_overlap": 50,
            "splitter": "semantic",
            "tokenizer": "cl100k_base",
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    profile_id = create_profile.json()["profile"]["profile_id"]

    storage = Storage(str(tmp_path / "index.db"))
    try:
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=alpha_url,
            profile_id=profile_id,
            markdown_hash="alpha-markdown-hash",
            status="building",
        )
        storage.replace_global_chunks(
            chunk_set_id=chunk_set["chunk_set_id"],
            chunks=[
                {
                    "chunk_index": 0,
                    "content": "Alpha chunk",
                    "token_count": 2,
                    "section_hierarchy": "Alpha",
                }
            ],
            overwrite=True,
        )
        beta_chunk_set = storage.get_or_create_file_chunk_set(
            file_url=beta_url,
            profile_id=profile_id,
            markdown_hash="beta-markdown-hash",
            status="building",
        )
        storage.replace_global_chunks(
            chunk_set_id=beta_chunk_set["chunk_set_id"],
            chunks=[
                {
                    "chunk_index": 0,
                    "content": "Beta chunk",
                    "token_count": 2,
                    "section_hierarchy": "Beta",
                }
            ],
            overwrite=True,
        )
    finally:
        storage.close()

    selectable = client.get("/api/rag/files/selectable", params={"profile_id": profile_id})
    assert selectable.status_code == 200, selectable.text
    selectable_files = selectable.json()["files"]
    selectable_by_url = {item["url"]: item for item in selectable_files}
    assert set(selectable_by_url) == {alpha_url, beta_url}
    assert selectable_by_url[alpha_url]["chunk_set_id"] == chunk_set["chunk_set_id"]
    assert selectable_by_url[alpha_url]["chunk_profile_id"] == profile_id

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-existing-chunks",
            "name": "Existing Chunks KB",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
            "file_urls": [alpha_url, beta_url],
            "chunk_size": 9999,
            "chunk_overlap": 888,
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    body = create_kb.json()
    assert body["knowledge_base"]["chunk_size"] == 300
    assert body["knowledge_base"]["chunk_overlap"] == 50
    assert body["chunk_bindings"]["bound"] == 2
    assert body["chunk_bindings"]["skipped_without_chunks"] == 0

    files = client.get("/api/rag/knowledge-bases/kb-existing-chunks/files")
    assert files.status_code == 200, files.text
    assert [item["file_url"] for item in files.json()["files"]] == [
        alpha_url,
        beta_url,
    ]

    bindings = client.get("/api/rag/knowledge-bases/kb-existing-chunks/bindings")
    assert bindings.status_code == 200, bindings.text
    assert bindings.json()["binding"]["bound_file_count"] == 2
    assert bindings.json()["binding"]["bound_chunk_count"] == 2


def test_fastapi_rag_admin_category_stats_and_kb_profile_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "stats-profile",
            "chunk_size": 321,
            "chunk_overlap": 31,
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    profile_id = create_profile.json()["profile"]["profile_id"]
    _seed_ready_chunk_set(db_path, alpha_url, profile_id, text="Alpha ready chunk")

    stats = client.post(
        "/api/rag/categories/stats",
        json={"categories": ["AI", "Risk"], "profile_id": profile_id},
    )
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["totals"]["total_files"] == 2
    assert body["totals"]["markdown_files"] == 2
    assert body["totals"]["ready_chunk_files"] == 1
    by_name = {item["name"]: item for item in body["categories"]}
    assert by_name["AI"]["ready_chunk_files"] == 1
    assert by_name["Risk"]["ready_chunk_files"] == 0

    too_many = client.post(
        "/api/rag/categories/stats",
        json={"categories": [f"Category {idx}" for idx in range(101)], "profile_id": profile_id},
    )
    assert too_many.status_code == 400, too_many.text
    assert "at most 100" in too_many.json()["error"]

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-profile-metadata",
            "name": "Profile Metadata KB",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
            "file_urls": [alpha_url],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    created = create_kb.json()["knowledge_base"]
    assert created["chunk_profile_id"] == profile_id
    assert created["chunk_profile_name"] == "stats-profile"

    detail = client.get("/api/rag/knowledge-bases/kb-profile-metadata")
    assert detail.status_code == 200, detail.text
    assert detail.json()["knowledge_base"]["chunk_profile_id"] == profile_id
    assert detail.json()["knowledge_base"]["chunk_profile_name"] == "stats-profile"

    listed = client.get("/api/rag/knowledge-bases")
    assert listed.status_code == 200, listed.text
    listed_kb = next(
        item for item in listed.json()["knowledge_bases"] if item["kb_id"] == "kb-profile-metadata"
    )
    assert listed_kb["chunk_profile_id"] == profile_id
    assert listed_kb["chunk_profile_name"] == "stats-profile"


def test_fastapi_rag_admin_file_management_marks_membership_source_state(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"

    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-membership-api",
            "name": "Membership API KB",
            "kb_mode": "manual",
            "file_urls": [seed["alpha_url"], seed["beta_url"]],
        },
    )
    assert created.status_code == 201, created.text

    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_source_state(
            kb_id="kb-membership-api",
            profile="general",
        )
        assert state["event_generation"] == 3
        assert state["pending_severity"] == "hard_stale"
        assert state["pending_reasons"] == [
            "membership_added",
            "access_scope_restricted",
            "chunk_binding_updated",
        ]
    finally:
        storage.close()


def test_fastapi_rag_admin_category_update_syncs_new_files_before_index(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]
    beta_url = seed["beta_url"]

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "category-sync-profile",
            "chunk_size": 256,
            "chunk_overlap": 32,
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    profile_id = create_profile.json()["profile"]["profile_id"]
    _seed_ready_chunk_set(db_path, alpha_url, profile_id, text="Initial alpha chunk")

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-category-sync",
            "name": "Category Sync KB",
            "kb_mode": "category",
            "chunk_profile_id": profile_id,
            "categories": ["AI"],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    files_before = client.get("/api/rag/knowledge-bases/kb-category-sync/files")
    assert files_before.status_code == 200, files_before.text
    assert [item["file_url"] for item in files_before.json()["files"]] == [alpha_url]

    beta_sha = hashlib.sha256((PDF_BYTES + b"\n% beta")).hexdigest()
    storage = Storage(str(db_path))
    try:
        storage.upsert_catalog_item(
            item={
                "url": beta_url,
                "sha256": beta_sha,
                "keywords": ["ai"],
                "summary": "Beta moved into AI",
                "category": "AI",
            },
            pipeline_version="v2",
            status="ok",
        )
        _seed_ready_chunk_set(db_path, beta_url, profile_id, text="New beta AI chunk")
    finally:
        storage.close()

    category_update = client.post(
        "/api/rag/knowledge-bases/kb-category-sync/categories",
        json={
            "action": "replace",
            "categories": ["AI"],
            "chunk_profile_id": profile_id,
        },
    )
    assert category_update.status_code == 200, category_update.text
    assert sorted(category_update.json()["category_sync"]["added_file_urls"]) == [beta_url]
    assert category_update.json()["chunk_bindings"]["bound"] == 2

    index = client.post(
        "/api/rag/knowledge-bases/kb-category-sync/index",
        json={"incremental": True},
    )
    assert index.status_code == 202, index.text
    assert index.json()["file_count"] == 2

    files_after = client.get("/api/rag/knowledge-bases/kb-category-sync/files")
    assert files_after.status_code == 200, files_after.text
    assert sorted(item["file_url"] for item in files_after.json()["files"]) == sorted(
        [alpha_url, beta_url]
    )

    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_source_state(
            kb_id="kb-category-sync",
            profile="general",
        )
        assert state["event_generation"] == 4
        assert state["pending_severity"] == "hard_stale"
        assert state["pending_reasons"] == [
            "membership_added",
            "access_scope_restricted",
            "chunk_binding_updated",
        ]
    finally:
        storage.close()


def test_fastapi_rag_admin_removing_last_category_reconciles_files_and_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "remove-last-profile", "chunk_size": 256, "chunk_overlap": 32},
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["profile"]["profile_id"]
    _seed_ready_chunk_set(
        db_path,
        seed["alpha_url"],
        profile_id,
        text="Remove last category chunk",
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-remove-last-category",
            "name": "Remove Last Category",
            "kb_mode": "category",
            "chunk_profile_id": profile_id,
            "categories": ["AI"],
        },
    )
    assert created.status_code == 201, created.text

    removed = client.post(
        "/api/rag/knowledge-bases/kb-remove-last-category/categories",
        json={"action": "remove", "categories": ["AI"]},
    )

    assert removed.status_code == 200, removed.text
    assert removed.json()["categories"] == []
    assert removed.json()["category_sync"]["removed_file_urls"] == [seed["alpha_url"]]
    files = client.get("/api/rag/knowledge-bases/kb-remove-last-category/files")
    assert files.status_code == 200, files.text
    assert files.json()["files"] == []
    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-remove-last-category",),
            ).fetchone()[0]
            == 0
        )
    finally:
        storage.close()


def test_fastapi_rag_admin_category_remove_preserves_files_selected_by_remaining_mapping(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "remove-overlap-profile", "chunk_size": 256, "chunk_overlap": 32},
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["profile"]["profile_id"]
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("AI; Risk", seed["beta_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()
    alpha_set = _seed_ready_chunk_set(db_path, seed["alpha_url"], profile_id, text="AI-only chunk")
    beta_set = _seed_ready_chunk_set(
        db_path, seed["beta_url"], profile_id, text="AI and Risk chunk"
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-remove-overlap-category",
            "name": "Remove Overlap Category",
            "kb_mode": "category",
            "chunk_profile_id": profile_id,
            "categories": ["AI", "Risk"],
        },
    )
    assert created.status_code == 201, created.text

    removed = client.post(
        "/api/rag/knowledge-bases/kb-remove-overlap-category/categories",
        json={"action": "remove", "categories": ["AI"]},
    )

    assert removed.status_code == 200, removed.text
    assert removed.json()["categories"] == ["Risk"]
    assert removed.json()["category_sync"]["removed_file_urls"] == [seed["alpha_url"]]
    files = client.get("/api/rag/knowledge-bases/kb-remove-overlap-category/files")
    assert files.status_code == 200, files.text
    assert [item["file_url"] for item in files.json()["files"]] == [seed["beta_url"]]
    storage = Storage(str(db_path))
    try:
        rows = storage._conn.execute(
            "SELECT file_url, chunk_set_id FROM kb_chunk_bindings WHERE kb_id = ?",
            ("kb-remove-overlap-category",),
        ).fetchall()
        assert [(row[0], row[1]) for row in rows] == [(seed["beta_url"], beta_set["chunk_set_id"])]
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM global_chunks WHERE chunk_set_id = ?",
                (alpha_set["chunk_set_id"],),
            ).fetchone()[0]
            == 1
        )
    finally:
        storage.close()


def test_fastapi_rag_admin_category_remove_missing_new_remaining_chunk_rolls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "remove-rollback-profile", "chunk_size": 333, "chunk_overlap": 33},
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["profile"]["profile_id"]
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("Finance", seed["beta_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()
    alpha_set = _seed_ready_chunk_set(
        db_path, seed["alpha_url"], profile_id, text="Original AI chunk"
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-remove-category-rollback",
            "name": "Remove Category Rollback",
            "kb_mode": "category",
            "chunk_profile_id": profile_id,
            "categories": ["AI", "Risk"],
        },
    )
    assert created.status_code == 201, created.text

    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("Risk", seed["beta_url"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    removed = client.post(
        "/api/rag/knowledge-bases/kb-remove-category-rollback/categories",
        json={"action": "remove", "categories": ["AI"]},
    )

    assert removed.status_code == 400, removed.text
    assert removed.json()["error"].startswith("missing_chunk:")
    categories = client.get("/api/rag/knowledge-bases/kb-remove-category-rollback/categories")
    assert categories.status_code == 200, categories.text
    assert categories.json()["categories"] == ["AI", "Risk"]
    files = client.get("/api/rag/knowledge-bases/kb-remove-category-rollback/files")
    assert files.status_code == 200, files.text
    assert [item["file_url"] for item in files.json()["files"]] == [seed["alpha_url"]]
    storage = Storage(str(db_path))
    try:
        rows = storage._conn.execute(
            "SELECT file_url, chunk_set_id FROM kb_chunk_bindings WHERE kb_id = ?",
            ("kb-remove-category-rollback",),
        ).fetchall()
        assert [(row[0], row[1]) for row in rows] == [
            (seed["alpha_url"], alpha_set["chunk_set_id"])
        ]
    finally:
        storage.close()


def test_fastapi_rag_admin_all_mode_adds_all_ready_profile_files(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]
    beta_url = seed["beta_url"]

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "all-mode-profile",
            "chunk_size": 256,
            "chunk_overlap": 32,
        },
    )
    assert create_profile.status_code == 201, create_profile.text
    profile_id = create_profile.json()["profile"]["profile_id"]
    _seed_ready_chunk_set(db_path, alpha_url, profile_id, text="Alpha all chunk")
    _seed_ready_chunk_set(db_path, beta_url, profile_id, text="Beta all chunk")

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-all-mode",
            "name": "All Mode KB",
            "kb_mode": "all",
            "chunk_profile_id": profile_id,
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    body = create_kb.json()
    assert body["all_sync"]["added_count"] == 2
    assert sorted(body["all_sync"]["file_urls"]) == sorted([alpha_url, beta_url])
    assert body["chunk_bindings"]["bound"] == 2

    files = client.get("/api/rag/knowledge-bases/kb-all-mode/files")
    assert files.status_code == 200, files.text
    assert sorted(item["file_url"] for item in files.json()["files"]) == sorted(
        [alpha_url, beta_url]
    )


def test_fastapi_rag_admin_chunk_binding_adds_kb_file_membership(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]

    create_profile = client.post(
        "/api/chunk/profiles", json={"name": "bind-profile", "chunk_size": 256, "chunk_overlap": 32}
    )
    assert create_profile.status_code == 201, create_profile.text
    profile_id = create_profile.json()["profile"]["profile_id"]
    chunk_set = _seed_ready_chunk_set(db_path, alpha_url, profile_id, text="Bindable alpha chunk")

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-direct-bind",
            "name": "Direct Bind KB",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
        },
    )
    assert create_kb.status_code == 201, create_kb.text

    binding_payload = {
        "bindings": [
            {
                "file_url": alpha_url,
                "chunk_set_id": chunk_set["chunk_set_id"],
                "binding_mode": "follow_latest",
            }
        ]
    }
    bind = client.post(
        "/api/rag/knowledge-bases/kb-direct-bind/bindings",
        json=binding_payload,
    )
    assert bind.status_code == 200, bind.text
    assert bind.json()["created"] == 1
    assert bind.json()["binding"] == {
        "contract_version": 1,
        "kb_id": "kb-direct-bind",
        "binding_snapshot_fingerprint": bind.json()["binding"]["binding_snapshot_fingerprint"],
        "bound_file_count": 1,
        "bound_chunk_set_count": 1,
        "bound_chunk_count": 1,
    }
    repeated = client.post(
        "/api/rag/knowledge-bases/kb-direct-bind/bindings",
        json=binding_payload,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] == 0
    assert repeated.json()["existing"] == 1
    assert repeated.json()["binding"] == bind.json()["binding"]

    bindings = client.get("/api/rag/knowledge-bases/kb-direct-bind/bindings")
    assert bindings.status_code == 200, bindings.text
    assert bindings.json()["binding"] == bind.json()["binding"]
    assert "content" not in json.dumps(bindings.json())
    assert "vector" not in json.dumps(bindings.json())

    storage = Storage(str(db_path))
    try:
        source_state = storage.get_agentic_ready_source_state(
            kb_id="kb-direct-bind",
            profile="general",
        )
    finally:
        storage.close()
    assert source_state["event_generation"] == 2
    assert source_state["pending_severity"] == "hard_stale"
    assert source_state["pending_reasons"] == [
        "membership_added",
        "access_scope_restricted",
    ]

    files = client.get("/api/rag/knowledge-bases/kb-direct-bind/files")
    assert files.status_code == 200, files.text
    assert [item["file_url"] for item in files.json()["files"]] == [alpha_url]
    assert files.json()["files"][0]["chunk_set_id"] == chunk_set["chunk_set_id"]

    removed = client.delete(f"/api/rag/knowledge-bases/kb-direct-bind/files/{alpha_url}")
    assert removed.status_code == 200, removed.text

    invalid_bindings = client.get("/api/rag/knowledge-bases/kb-direct-bind/bindings")
    assert invalid_bindings.status_code == 400, invalid_bindings.text
    assert "invalid_selector:" in invalid_bindings.json()["error"]


def test_fastapi_rag_admin_binding_batch_rolls_back_when_later_item_is_invalid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "atomic-bind-profile", "chunk_size": 256, "chunk_overlap": 32},
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["profile"]["profile_id"]
    valid_set = _seed_ready_chunk_set(
        db_path,
        seed["alpha_url"],
        profile_id,
        text="Atomic valid chunk",
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-atomic-invalid",
            "name": "Atomic Invalid",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        "/api/rag/knowledge-bases/kb-atomic-invalid/bindings",
        json={
            "bindings": [
                {
                    "file_url": seed["alpha_url"],
                    "chunk_set_id": valid_set["chunk_set_id"],
                    "binding_mode": "pin",
                },
                {
                    "file_url": seed["beta_url"],
                    "chunk_set_id": "missing-chunk-set",
                    "binding_mode": "pin",
                },
            ]
        },
    )

    assert response.status_code == 404, response.text
    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?",
                ("kb-atomic-invalid",),
            ).fetchone()[0]
            == 0
        )
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-atomic-invalid",),
            ).fetchone()[0]
            == 0
        )
    finally:
        storage.close()


def test_fastapi_rag_admin_binding_batch_rejects_wrong_profile_without_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    selected = client.post(
        "/api/chunk/profiles",
        json={"name": "selected-profile", "chunk_size": 256, "chunk_overlap": 32},
    )
    wrong = client.post(
        "/api/chunk/profiles",
        json={"name": "wrong-profile", "chunk_size": 512, "chunk_overlap": 32},
    )
    assert selected.status_code == wrong.status_code == 201
    wrong_set = _seed_ready_chunk_set(
        db_path,
        seed["alpha_url"],
        wrong.json()["profile"]["profile_id"],
        text="Wrong profile chunk",
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-atomic-profile",
            "name": "Atomic Profile",
            "kb_mode": "manual",
            "chunk_profile_id": selected.json()["profile"]["profile_id"],
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        "/api/rag/knowledge-bases/kb-atomic-profile/bindings",
        json={
            "file_url": seed["alpha_url"],
            "chunk_set_id": wrong_set["chunk_set_id"],
            "binding_mode": "pin",
        },
    )

    assert response.status_code == 400, response.text
    assert "wrong chunk profile" in response.json()["error"]
    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?",
                ("kb-atomic-profile",),
            ).fetchone()[0]
            == 0
        )
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-atomic-profile",),
            ).fetchone()[0]
            == 0
        )
    finally:
        storage.close()


def test_rag_admin_binding_batch_rolls_back_database_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    profile = client.post(
        "/api/chunk/profiles",
        json={"name": "db-rollback-profile", "chunk_size": 256, "chunk_overlap": 32},
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["profile"]["profile_id"]
    alpha_set = _seed_ready_chunk_set(
        db_path, seed["alpha_url"], profile_id, text="Alpha rollback chunk"
    )
    beta_set = _seed_ready_chunk_set(
        db_path, seed["beta_url"], profile_id, text="Beta rollback chunk"
    )
    created = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-atomic-db",
            "name": "Atomic DB",
            "kb_mode": "manual",
            "chunk_profile_id": profile_id,
        },
    )
    assert created.status_code == 201, created.text
    initial = client.post(
        "/api/rag/knowledge-bases/kb-atomic-db/bindings",
        json={
            "file_url": seed["alpha_url"],
            "chunk_set_id": alpha_set["chunk_set_id"],
            "binding_mode": "pin",
        },
    )
    assert initial.status_code == 200, initial.text
    storage = Storage(str(db_path))
    try:
        replacement_set = storage.get_or_create_file_chunk_set(
            file_url=seed["alpha_url"],
            profile_id=profile_id,
            markdown_hash="atomic-db-replacement",
            status="building",
        )
        storage.replace_global_chunks(
            chunk_set_id=str(replacement_set["chunk_set_id"]),
            chunks=[
                {
                    "chunk_index": 0,
                    "content": "Replacement rollback chunk",
                    "token_count": 3,
                    "section_hierarchy": "Root",
                }
            ],
        )
    finally:
        storage.close()

    original_bind = Storage.bind_chunk_set_to_kb
    bind_calls = 0

    def fail_second_bind(self: Storage, **kwargs):
        nonlocal bind_calls
        bind_calls += 1
        result = original_bind(self, **kwargs)
        if bind_calls == 2:
            raise RuntimeError("synthetic binding database failure")
        return result

    monkeypatch.setattr(Storage, "bind_chunk_set_to_kb", fail_second_bind)
    with pytest.raises(RuntimeError, match="synthetic binding database failure"):
        rag_admin_service.bind_chunk_sets(
            db_path=str(db_path),
            kb_id="kb-atomic-db",
            payload={
                "bindings": [
                    {
                        "file_url": seed["alpha_url"],
                        "chunk_set_id": replacement_set["chunk_set_id"],
                        "binding_mode": "pin",
                    },
                    {
                        "file_url": seed["beta_url"],
                        "chunk_set_id": beta_set["chunk_set_id"],
                        "binding_mode": "pin",
                    },
                ]
            },
            headers={},
        )

    storage = Storage(str(db_path))
    try:
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?",
                ("kb-atomic-db",),
            ).fetchone()[0]
            == 1
        )
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-atomic-db",),
            ).fetchone()[0]
            == 1
        )
        assert (
            storage._conn.execute(
                "SELECT chunk_set_id FROM kb_chunk_bindings WHERE kb_id = ?",
                ("kb-atomic-db",),
            ).fetchone()[0]
            == alpha_set["chunk_set_id"]
        )
    finally:
        storage.close()
