from __future__ import annotations

import hashlib
import json
import shutil
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
    assert create_kb.json()["knowledge_base"]["manifest_profile"] == "general"

    status_before_build = client.get("/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest")
    assert status_before_build.status_code == 200, status_before_build.text
    assert status_before_build.json()["manifest"]["status"] == "missing"

    build = client.post(
        "/api/rag/knowledge-bases/kb-agentic-manifest/agentic-ready-manifest/build",
        json={},
    )
    assert build.status_code == 200, build.text
    manifest = build.json()["manifest"]
    assert manifest["status"] == "ready"
    assert manifest["usable"] is True
    assert manifest["fallback_mode"] == "agentic"
    assert manifest["doc_count"] == 1
    assert manifest["publication_id"].startswith("arp_")
    assert manifest["index_version_id"] is None
    assert manifest["source_version_kind"] == "catalog_chunks_snapshot"
    assert manifest["source_version_id"].startswith("rdsnap_")
    assert len(manifest["artifact_digest"]) == 64
    assert build.json()["publication_state"]["automatic_publish_enabled"] is False
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
    assert stale_manifest["status"] == "stale"
    assert stale_manifest["usable"] is False
    assert stale_manifest["fallback_mode"] == "standard"
    assert stale_manifest["stale_reason"]


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
        assert "invalid json" in corrupt_after["error_message"].lower()
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
    assert candidate["index_version_id"] is None


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


def test_fastapi_rag_admin_agentic_manifest_stale_uses_bound_chunks_and_catalog_metadata(
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
    assert stale.json()["manifest"]["status"] == "stale"


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

    storage = Storage(str(tmp_path / "index.db"))
    try:
        first_mark = storage.mark_agentic_ready_source_event(
            kb_id="kb-manual-generation-race",
            profile="general",
            reason="membership_removed",
        )
        assert first_mark["event_generation"] == 1
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
    assert manifest["event_generation"] == 2
    assert manifest["pending_evaluation_generation"] == 2
    assert manifest["stale_severity"] == "hard_stale"
    assert manifest["usable"] is False


def test_fastapi_rag_admin_kb_file_membership_routes_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
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

    remove_file = client.delete(f"/api/rag/knowledge-bases/kb-files-test/files/{alpha_url}")
    assert remove_file.status_code == 200, remove_file.text

    files_after_remove = client.get("/api/rag/knowledge-bases/kb-files-test/files")
    assert files_after_remove.status_code == 200, files_after_remove.text
    assert not any(item["file_url"] == alpha_url for item in files_after_remove.json()["files"])


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

    files = client.get("/api/rag/knowledge-bases/kb-direct-bind/files")
    assert files.status_code == 200, files.text
    assert [item["file_url"] for item in files.json()["files"]] == [alpha_url]
    assert files.json()["files"][0]["chunk_set_id"] == chunk_set["chunk_set_id"]
