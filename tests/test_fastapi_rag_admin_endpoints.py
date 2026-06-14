from __future__ import annotations

import hashlib
import json
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


def test_fastapi_rag_admin_agentic_ready_manifest_records_unsupported_profile_failure(
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
    assert manifest["status"] == "failed"
    assert manifest["usable"] is False
    assert manifest["fallback_mode"] == "standard"
    assert "not implemented" in manifest["error_message"]


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

    traversal = client.post(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={"output_dir": "../escape"},
    )
    assert traversal.status_code == 400
    assert "output_dir" in traversal.json()["error"]

    absolute_outside = client.post(
        "/api/rag/knowledge-bases/kb-output-dir-guard/agentic-ready-manifest/build",
        json={"output_dir": str(tmp_path.parent / "outside-agentic-ready-data")},
    )
    assert absolute_outside.status_code == 400
    assert "output_dir" in absolute_outside.json()["error"]


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
