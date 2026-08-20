from __future__ import annotations

import hashlib
import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from ai_actuarial.api.app import create_app
from ai_actuarial.api.routers import rag_admin as rag_admin_router
from ai_actuarial.storage import Storage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


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
    first_response = client.post(
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
    second_response = client.post(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build",
        json={},
    )
    assert second_response.status_code == 200, second_response.text
    return first, second_response.json()["candidate_publication"]


def _assert_publication_slots(
    db_path: Path,
    *,
    kb_id: str,
    active_id: object,
    previous_id: object,
) -> None:
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile="general",
        )
        assert state["active_publication_id"] == active_id
        assert state["previous_publication_id"] == previous_id
    finally:
        storage.close()


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
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "fastapi-rag-admin-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    client.headers.update({"X-Auth-Token": seed["admin_token"]})
    return client, app, seed


def _make_session_cookie(app, payload: dict[str, object]) -> str:
    serializer = URLSafeSerializer(app.state.fastapi_session_secret, salt="fastapi-session")
    return serializer.dumps(payload)


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



def _seed_ready_chunk_set(db_path: Path, file_url: str, profile_id: str, *, text: str = "Chunk") -> dict[str, object]:
    storage = Storage(str(db_path))
    try:
        chunk_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            markdown_hash=f"{file_url}:{profile_id}",
            status="ready",
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



def test_fastapi_rag_admin_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
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
    assert "/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback" in body["native_paths"]
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


def test_fastapi_rag_admin_read_routes_require_task_or_config_permissions(tmp_path: Path, monkeypatch) -> None:
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
    assert client.get("/api/rag/knowledge-bases/kb-missing/files/pending", headers=operator_headers).status_code in {200, 404}
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


def test_fastapi_rag_admin_kb_writes_preserve_legacy_config_token_access(tmp_path: Path, monkeypatch) -> None:
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


def test_fastapi_rag_admin_categories_mapping_uses_catalog_items_without_legacy_table(tmp_path: Path, monkeypatch) -> None:
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
    listed_kb = next(item for item in list_body["knowledge_bases"] if item["kb_id"] == "kb-pr4-test")
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
    assert detail_body["current_embeddings"]["embedding_fingerprint"].startswith("openai:text-embedding-3-large:")
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



def test_fastapi_rag_admin_agentic_ready_manifest_build_is_kb_scoped(tmp_path: Path, monkeypatch) -> None:
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

    status_before_build = client.get("/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest")
    assert status_before_build.status_code == 200, status_before_build.text
    assert status_before_build.json()["manifest"]["status"] == "missing"
    assert status_before_build.json()["manifest"]["publication_revision"] == 0
    assert status_before_build.json()["publication_state"]["publication_revision"] == 0

    build = client.post(
        "/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    build_body = build.json()
    manifest = build_body["manifest"]
    assert manifest["status"] == "ready"
    assert manifest["usable"] is True
    assert manifest["fallback_mode"] == "agentic"
    assert manifest["doc_count"] == 1
    assert manifest["publication_id"].startswith("arp_")
    assert manifest["index_version_id"] is None
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
    assert safe_active["index_consumed_by_builder"] is False
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
    listed = next(item for item in list_kbs.json()["knowledge_bases"] if item["kb_id"] == "kb-agentic-manifest")
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
    assert stale_manifest["event_generation"] == 2
    assert stale_manifest["pending_evaluation_generation"] == 2
    assert stale_manifest["source_state"]["pending_severity"] == "soft_stale"
    assert stale_manifest["source_state"]["pending_reasons"] == ["membership_added"]


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
    first = client.post(
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

    old_response = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    )
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
    response = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    )
    writer_thread.join(timeout=10)
    assert not writer_thread.is_alive()
    assert not mutation_errors
    assert response.status_code == 200, response.text
    body = response.json()
    public_state = body["publication_state"]
    assert public_state["active_publication_id"] == expected_response_active["publication_id"]
    assert public_state["active_publication"]["publication_id"] == expected_response_active["publication_id"]
    assert public_state["active_publication"]["status"] == "active"
    assert (
        public_state["active_publication"]["authoritative_source_version_id"]
        == expected_response_active["source_version_id"]
    )
    assert body["manifest"]["status"] in {"ready", "stale"}
    assert body["manifest"]["usable"] is True

    final_response = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    )
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
    first = client.post(
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
    second = client.post(
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

    storage = Storage(str(tmp_path / "index.db"))
    try:
        ready_index = storage.create_kb_index_version(
            kb_id="kb-publication-controls",
            embedding_model="embedding-test",
            index_type="flat",
            chunk_count=0,
        )
    finally:
        storage.close()

    first = client.post(
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
    assert first_snapshot["publication_state"]["active_publication_id"] == first_publication["publication_id"]
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

    second = client.post(
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
    assert second_snapshot["publication_state"]["active_publication_id"] == second_publication["publication_id"]
    assert second_snapshot["publication_state"]["previous_publication_id"] == first_publication["publication_id"]
    assert second_snapshot["publication_state"]["active_publication"]["publication_id"] == second_publication["publication_id"]
    assert second_snapshot["publication_state"]["previous_publication"]["publication_id"] == first_publication["publication_id"]
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

    status = client.get(
        "/api/rag/knowledge-bases/kb-publication-controls/agentic-ready-manifest"
    )
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["publication_state"]["active_publication_id"] == second_publication["publication_id"]
    assert body["publication_state"]["previous_publication_id"] == first_publication["publication_id"]
    active = body["publication_state"]["active_publication"]
    previous = body["publication_state"]["previous_publication"]
    assert active["authoritative_source_version_kind"] == "catalog_chunks_snapshot"
    assert active["authoritative_source_version_id"] == second_publication["source_version_id"]
    assert active["observed_index_version_id"] == ready_index["index_version_id"]
    assert active["current_ready_index_version_id"] == ready_index["index_version_id"]
    assert active["index_consumed_by_builder"] is False
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
        "/api/rag/knowledge-bases/kb-publication-controls/"
        "agentic-ready-manifest/rollback"
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
    assert rolled["publication_state"]["active_publication_id"] == first_publication["publication_id"]
    assert rolled["publication_state"]["previous_publication_id"] == second_publication["publication_id"]
    assert rolled["manifest"]["status"] == "stale"
    assert rolled["manifest"]["serving_stale"] is True
    assert rolled["manifest"]["stale_reason"] == "source_version_changed"

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

    first_a_response = client.post(
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

    second_a_response = client.post(
        "/api/rag/knowledge-bases/kb-rollback-scope-a/agentic-ready-manifest/build",
        json={},
    )
    assert second_a_response.status_code == 200, second_a_response.text
    second_a = second_a_response.json()["candidate_publication"]
    active_b_response = client.post(
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
    first_response = client.post(
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

    second_response = client.post(
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

    projected = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    )
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
    built = client.post(
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

    read_only = TestClient(app)
    read_only.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["registered_user_id"]}),
    )
    for reader in (TestClient(app), read_only):
        response = reader.get(
            "/api/rag/knowledge-bases/kb-public-errors/agentic-ready-manifest"
        )
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
    built = client.post(
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
    monkeypatch.setattr(
        Storage, "get_agentic_ready_publication_state", poisoned_publications
    )
    monkeypatch.setattr(
        Storage, "get_agentic_ready_automation_state", poisoned_automation
    )
    monkeypatch.setattr(
        Storage, "get_agentic_ready_source_state", poisoned_source_state
    )

    read_only = TestClient(app)
    read_only.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["registered_user_id"]}),
    )
    for reader in (TestClient(app), read_only):
        response = reader.get(
            "/api/rag/knowledge-bases/kb-enum-active/agentic-ready-manifest"
        )
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

        legacy = reader.get(
            "/api/rag/knowledge-bases/kb-enum-building/agentic-ready-manifest"
        )
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
    built = client.post(
        "/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest/build",
        json={},
    )
    assert built.status_code == 200, built.text

    original_manifest = Storage.get_agentic_ready_manifest
    original_automation = Storage.get_agentic_ready_automation_state
    simulated = {"manifest_status": None, "automation_state": "running"}

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
        return value

    monkeypatch.setattr(Storage, "get_agentic_ready_manifest", simulated_manifest)
    monkeypatch.setattr(
        Storage, "get_agentic_ready_automation_state", running_automation
    )
    response = client.get(
        "/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manifest"]["status"] == "ready"
    assert body["publication_state"]["serving_status"] == "ready"
    assert body["publication_state"]["automation_state"] == "running"

    simulated.update({"manifest_status": "building", "automation_state": "disabled"})
    legacy_building = client.get(
        "/api/rag/knowledge-bases/kb-ready-running/agentic-ready-manifest"
    )
    assert legacy_building.status_code == 200, legacy_building.text
    legacy_body = legacy_building.json()
    assert legacy_body["manifest"]["status"] == "ready"
    assert legacy_body["publication_state"]["serving_status"] == "ready"
    assert legacy_body["publication_state"]["automation_state"] == "building"


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
    built = client.post(
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
    response = client.get(
        "/api/rag/knowledge-bases/kb-unknown-severity/agentic-ready-manifest"
    )
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
    built = client.post(
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
    response = client.get(
        "/api/rag/knowledge-bases/kb-soft-stale-agentic/agentic-ready-manifest"
    )
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
    built = client.post(
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
    response = client.get(
        "/api/rag/knowledge-bases/kb-corrupt-active-slot/agentic-ready-manifest"
    )
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
    built = client.post(
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
    built = client.post(
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
    built = client.post(
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
    built = client.post(
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
    built = client.post(
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
    first = client.post(
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
    second = client.post(
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
        json.loads(line)
        for line in original_catalog.decode("utf-8").splitlines()
        if line.strip()
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
    before = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    ).json()

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
    assert client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    ).json() == before


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
    before = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    ).json()

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
    assert client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    ).json() == before


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
    (real_dir / "catalog-copy.jsonl").write_bytes(
        (output_dir / "doc_catalog.jsonl").read_bytes()
    )
    (nested_dir / "catalog-copy.jsonl").write_bytes(
        (real_dir / "catalog-copy.jsonl").read_bytes()
    )
    artifact_files = [*list(first["artifact_files"]), nested_artifact]
    recorded_digest = rag_admin_service._ready_data_artifact_digest(
        str(output_dir), artifact_files
    )
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
    before = client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    ).json()

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
    assert client.get(
        f"/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest"
    ).json() == before


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
        lambda path: (
            unsafe_artifact == "doc_catalog.jsonl"
            and Path(path) == catalog_path
        )
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

    first_build = client.post(
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
    failed_build = client.post(
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
    first = client.post(
        "/api/rag/knowledge-bases/kb-dedupe-staging/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_manifest = first.json()["manifest"]
    staging_root = Path(first_manifest["output_dir"]).parent
    staging_dirs_before = sorted(path.name for path in staging_root.iterdir())

    duplicate = client.post(
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
    first = client.post(
        "/api/rag/knowledge-bases/kb-dedupe-gc-guard-loss/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text

    monkeypatch.setattr(
        Storage,
        "mark_agentic_ready_publication_redundant_duplicate",
        lambda _storage, _publication_id, *, expected_active_publication_id: False,
    )
    duplicate = client.post(
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
        recorded_candidate = storage.get_agentic_ready_publication(
            candidate["publication_id"]
        )
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
    first = client.post(
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

    duplicate = client.post(
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
    failed = client.post(
        "/api/rag/knowledge-bases/kb-exception-staging/agentic-ready-manifest/build",
        json={},
    )
    assert failed.status_code == 200, failed.text
    candidate = failed.json()["candidate_publication"]
    assert candidate["status"] == "failed"
    assert candidate["output_dir"] == ""
    assert len(candidate["artifact_digest"]) == 64
    staging_root = tmp_path / "agentic_ready_data" / "kbs" / "kb-exception-staging" / "general" / "1" / "staging"
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
        tmp_path
        / "agentic_ready_data"
        / "kbs"
        / "kb-symlink-staging"
        / "general"
        / "1"
        / "staging"
    )
    staging_root.parent.mkdir(parents=True)
    try:
        staging_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    response = client.post(
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
    response = client.post(
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
    response = client.post(
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
    response = client.post(
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
    response = client.post(
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
    response = client.post(
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

    failed_publish = client.post(
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

    retry = client.post(
        "/api/rag/knowledge-bases/kb-post-record-retry/agentic-ready-manifest/build",
        json={},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    retry_candidate = retry_body["candidate_publication"]
    assert retry_body["validation"]["valid"] is True
    assert retry_candidate["publication_id"] != failed_candidate["publication_id"]
    assert retry_candidate["status"] == "active"
    assert retry_body["publication_state"]["active_publication_id"] == retry_candidate["publication_id"]
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

    first = client.post(
        "/api/rag/knowledge-bases/kb-corrupt-active/agentic-ready-manifest/build",
        json={},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    first_candidate = first_body["candidate_publication"]
    first_output = Path(first_candidate["output_dir"])
    (first_output / "doc_catalog.jsonl").write_text("corrupt\n", encoding="utf-8")

    replacement = client.post(
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
    assert replacement_body["publication_state"]["active_publication_id"] == replacement_candidate["publication_id"]
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
    first = client.post(
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

    second = client.post(
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
        corrupt = storage.get_agentic_ready_publication(
            str(first_candidate["publication_id"])
        )
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
    first = client.post(
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
    second = client.post(
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
        corrupt = storage.get_agentic_ready_publication(
            str(first_candidate["publication_id"])
        )
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
    first = client.post(
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
    second = client.post(
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
    first = client.post(
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
    replacement = client.post(
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
    first = client.post(
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
    replacement = client.post(
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
    response = client.post(
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

    initial_build = client.post(
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

    migrated_build = client.post(
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
    initial = client.post(
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

    blocked = client.post(
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

    storage = Storage(str(tmp_path / "index.db"))
    try:
        ready = storage.create_kb_index_version(
            kb_id="kb-index-source",
            embedding_model="test-model",
            index_type="faiss",
            chunk_count=1,
            status="ready",
            built_at="2026-08-18T10:00:00+00:00",
        )
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

    build = client.post(
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

    build = client.post(
        "/api/rag/knowledge-bases/kb-regulation-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    manifest = build.json()["manifest"]
    assert manifest["profile"] == "regulation"
    assert manifest["status"] == "ready"
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
    storage = Storage(str(tmp_path / "index.db"))
    try:
        storage.update_file_markdown(
            str(seed["alpha_url"]),
            "\n".join(
                [
                    "# Net premium",
                    "Net Premium = PV Benefits / PV Premiums.",
                    "| Term | Description |",
                    "| q_x | mortality rate |",
                    "| v | discount factor |",
                    "The reserve calculation uses mortality rate and discount rate assumptions.",
                ]
            ),
            "manual",
        )
    finally:
        storage.close()

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

    build = client.post(
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

    ready_build = client.post(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={},
    )
    assert ready_build.status_code == 200, ready_build.text
    ready_manifest = ready_build.json()["manifest"]
    assert ready_manifest["status"] == "ready"

    traversal = client.post(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={"output_dir": "../escape"},
    )
    assert traversal.status_code == 400
    assert "output_dir" in traversal.json()["error"]

    after_traversal = client.get("/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest")
    assert after_traversal.status_code == 200, after_traversal.text
    after_traversal_manifest = after_traversal.json()["manifest"]
    assert after_traversal_manifest["status"] == "ready"
    assert after_traversal_manifest["output_dir"] == ready_manifest["output_dir"]

    absolute_outside = client.post(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={"output_dir": str(tmp_path.parent / "outside-agentic-ready-data")},
    )
    assert absolute_outside.status_code == 400
    assert "output_dir" in absolute_outside.json()["error"]

    after_absolute = client.get("/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest")
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
    _seed_ready_chunk_set(db_path, alpha_url, profile_two["profile_id"], text="Unbound profile chunk")

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

    build = client.post(
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

    build = client.post(
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

    status = client.get(
        "/api/rag/knowledge-bases/kb-legacy-invalid-binding/agentic-ready-manifest"
    )
    assert status.status_code == 200, status.text
    assert status.json()["manifest"]["status"] == "ready"


def test_manual_ready_build_clears_captured_hard_generation_after_safe_publish(
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
    first = client.post(
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
    finally:
        storage.close()

    rebuilt = client.post(
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
    first = client.post(
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

    rebuilt = client.post(
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
        assert added_state["event_generation"] == 1
        assert added_state["pending_severity"] == "soft_stale"
        assert added_state["pending_reasons"] == ["membership_added"]
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
        assert removed_state["event_generation"] == 2
        assert removed_state["pending_severity"] == "hard_stale"
        assert removed_state["pending_reasons"] == ["membership_added", "membership_removed"]
        assert removed_state["serving_allowed"] is False
    finally:
        storage.close()


def test_fastapi_rag_admin_kb_add_marks_dirty_and_delete_soft_applies(tmp_path: Path, monkeypatch) -> None:
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
            ("kb-index-dirty:alpha:0", "kb-index-dirty", alpha_url, 0, "Alpha indexed chunk", 3, "Alpha", "hash-alpha", indexed_at),
        )
        storage._conn.execute(
            "UPDATE kb_chunk_bindings SET bound_at = ? WHERE kb_id = ? AND file_url = ?",
            (indexed_at, "kb-index-dirty", alpha_url),
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET chunk_count = ?, updated_at = ? WHERE kb_id = ?",
            (1, indexed_at, "kb-index-dirty"),
        )
        storage._conn.commit()
        storage.create_kb_index_version(
            kb_id="kb-index-dirty",
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
            embedding_dimension=3072,
            index_type="Flat",
            chunk_count=1,
            status="ready",
            built_at=indexed_at,
        )
        storage._conn.execute("UPDATE rag_knowledge_bases SET index_dirty_at = NULL WHERE kb_id = ?", ("kb-index-dirty",))
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

    incremental = client.post(
        "/api/rag/knowledge-bases/kb-index-dirty/index",
        json={"incremental": True},
    )
    assert incremental.status_code == 202, incremental.text
    assert incremental.json()["file_count"] == 1

    storage = Storage(str(tmp_path / "index.db"))
    try:
        beta_indexed_at = "2026-05-24T02:10:00+00:00"
        storage._conn.execute(
            "UPDATE rag_kb_files SET indexed_at = ?, chunk_count = ? WHERE kb_id = ? AND file_url = ?",
            (beta_indexed_at, 1, "kb-index-dirty", beta_url),
        )
        storage._conn.execute(
            "UPDATE catalog_items SET markdown_updated_at = ? WHERE file_url = ?",
            (beta_indexed_at, beta_url),
        )
        storage._conn.commit()
        storage.create_kb_index_version(
            kb_id="kb-index-dirty",
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
            embedding_dimension=3072,
            index_type="Flat",
            chunk_count=2,
            status="ready",
            built_at=beta_indexed_at,
        )
        storage._conn.execute("UPDATE rag_knowledge_bases SET index_dirty_at = NULL WHERE kb_id = ?", ("kb-index-dirty",))
        storage._conn.commit()
    finally:
        storage.close()

    remove_alpha = client.delete(f"/api/rag/knowledge-bases/kb-index-dirty/files/{alpha_url}")
    assert remove_alpha.status_code == 200, remove_alpha.text

    after_delete = client.get("/api/rag/knowledge-bases/kb-index-dirty")
    assert after_delete.status_code == 200, after_delete.text
    assert after_delete.json()["knowledge_base"]["needs_reindex"] is False

    storage = Storage(str(tmp_path / "index.db"))
    try:
        stale_chunks = storage._conn.execute(
            "SELECT COUNT(*) FROM rag_chunks WHERE kb_id = ? AND file_url = ?",
            ("kb-index-dirty", alpha_url),
        ).fetchone()[0]
    finally:
        storage.close()
    assert stale_chunks == 0


def test_fastapi_rag_admin_rejects_incremental_index_after_embedding_change(tmp_path: Path, monkeypatch) -> None:
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

    assert incremental.status_code == 409, incremental.text
    assert "full re-embed" in incremental.text.lower()


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
                {"file_url": alpha_url, "chunk_set_id": "cs_missing", "binding_mode": "follow_latest"}
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

    index = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/index",
        json={"file_urls": [alpha_url]},
    )
    assert index.status_code in {200, 202}, index.text

    cleanup = client.post("/api/chunk-sets/cleanup", json={"dry_run": True})
    assert cleanup.status_code == 200, cleanup.text


def test_fastapi_rag_admin_preserves_zero_chunk_overlap_and_requires_task_bridge(tmp_path: Path, monkeypatch) -> None:
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

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-zero-overlap",
            "name": "KB Zero Overlap",
            "kb_mode": "manual",
            "chunk_size": 256,
            "chunk_overlap": 0,
            "file_urls": [alpha_url],
        },
    )
    assert create_kb.status_code == 201, create_kb.text
    assert create_kb.json()["knowledge_base"]["chunk_overlap"] == 0

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


def test_fastapi_rag_admin_create_kb_uses_existing_chunk_profile_bindings(tmp_path: Path, monkeypatch) -> None:
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
            status="ready",
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
    finally:
        storage.close()

    selectable = client.get("/api/rag/files/selectable", params={"profile_id": profile_id})
    assert selectable.status_code == 200, selectable.text
    selectable_files = selectable.json()["files"]
    assert [item["url"] for item in selectable_files] == [alpha_url]
    assert selectable_files[0]["chunk_set_id"] == chunk_set["chunk_set_id"]
    assert selectable_files[0]["chunk_profile_id"] == profile_id

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
    assert body["chunk_bindings"]["bound"] == 1
    assert body["chunk_bindings"]["skipped_without_chunks"] == 1

    files = client.get("/api/rag/knowledge-bases/kb-existing-chunks/files")
    assert files.status_code == 200, files.text
    assert [item["file_url"] for item in files.json()["files"]] == [alpha_url]

    bindings = client.get("/api/rag/knowledge-bases/kb-existing-chunks/bindings")
    assert bindings.status_code == 200, bindings.text
    binding = bindings.json()["bindings"][0]
    assert binding["file_url"] == alpha_url
    assert binding["chunk_set_id"] == chunk_set["chunk_set_id"]
    assert binding["binding_mode"] == "follow_latest"


def test_fastapi_rag_admin_category_stats_and_kb_profile_metadata(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]

    create_profile = client.post(
        "/api/chunk/profiles",
        json={
            "name": "stats-profile",
            "chunk_size": 256,
            "chunk_overlap": 32,
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
    listed_kb = next(item for item in listed.json()["knowledge_bases"] if item["kb_id"] == "kb-profile-metadata")
    assert listed_kb["chunk_profile_id"] == profile_id
    assert listed_kb["chunk_profile_name"] == "stats-profile"


def test_fastapi_rag_admin_file_management_marks_membership_source_state(tmp_path: Path, monkeypatch) -> None:
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
        assert state["event_generation"] == 1
        assert state["pending_severity"] == "soft_stale"
        assert state["pending_reasons"] == ["membership_added"]
    finally:
        storage.close()


def test_fastapi_rag_admin_category_index_syncs_new_category_files_before_incremental_index(tmp_path: Path, monkeypatch) -> None:
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

    index = client.post(
        "/api/rag/knowledge-bases/kb-category-sync/index",
        json={"incremental": True},
    )
    assert index.status_code == 202, index.text
    assert index.json()["file_count"] == 2
    assert sorted(index.json()["category_sync"]["added_file_urls"]) == [beta_url]
    assert index.json()["chunk_bindings"]["bound"] == 2

    files_after = client.get("/api/rag/knowledge-bases/kb-category-sync/files")
    assert files_after.status_code == 200, files_after.text
    assert sorted(item["file_url"] for item in files_after.json()["files"]) == sorted([alpha_url, beta_url])

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


def test_fastapi_rag_admin_all_mode_adds_all_ready_profile_files(tmp_path: Path, monkeypatch) -> None:
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
    assert sorted(item["file_url"] for item in files.json()["files"]) == sorted([alpha_url, beta_url])


def test_fastapi_rag_admin_chunk_binding_adds_kb_file_membership(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    db_path = tmp_path / "index.db"
    alpha_url = seed["alpha_url"]

    create_profile = client.post("/api/chunk/profiles", json={"name": "bind-profile", "chunk_size": 256, "chunk_overlap": 32})
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

    bind = client.post(
        "/api/rag/knowledge-bases/kb-direct-bind/bindings",
        json={
            "bindings": [
                {
                    "file_url": alpha_url,
                    "chunk_set_id": chunk_set["chunk_set_id"],
                    "binding_mode": "follow_latest",
                }
            ]
        },
    )
    assert bind.status_code == 200, bind.text
    assert bind.json()["created"] == 1

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

    bindings = client.get("/api/rag/knowledge-bases/kb-direct-bind/bindings")
    assert bindings.status_code == 200, bindings.text
    assert bindings.json()["count"] == 0
