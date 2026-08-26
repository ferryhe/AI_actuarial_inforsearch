from __future__ import annotations

import hashlib
import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
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
        "system": {
            "file_deletion_enabled": True,
        },
        "sites": [],
        "scheduled_tasks": [],
    }
    categories = {"categories": {"AI": ["artificial intelligence"]}}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path, files_dir



def _seed_storage(db_path: Path, files_dir: Path) -> dict[str, str]:
    alpha_path = files_dir / "alpha.pdf"
    alpha_path.write_bytes(PDF_BYTES)

    storage = Storage(str(db_path))
    try:
        file_url = "https://alpha.example/doc-a.pdf"
        file_sha = hashlib.sha256(PDF_BYTES).hexdigest()
        storage.insert_file(
            url=file_url,
            sha256=file_sha,
            title="Alpha Document",
            source_site="alpha.example",
            source_page_url="https://alpha.example",
            original_filename="doc-a.pdf",
            local_path=str(alpha_path),
            bytes=len(PDF_BYTES),
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            item={
                "url": file_url,
                "sha256": file_sha,
                "keywords": ["ai"],
                "summary": "Alpha summary",
                "category": "AI",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(file_url, "# Alpha\n\nPreview markdown.", "manual")
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
    finally:
        storage.close()

    return {"file_url": "https://alpha.example/doc-a.pdf", "operator_token": operator_token, "admin_token": admin_token}



def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, str]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "fastapi-file-preview-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    return client, app, seed


def _wait_for_task(app: object, task_id: str) -> dict[str, object]:
    runtime = app.state.native_task_runtime
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with runtime.task_lock:
            task = runtime.active_tasks.get(task_id)
            if task is None:
                task = next(
                    (row for row in reversed(runtime.task_history) if row.get("id") == task_id),
                    None,
                )
            if task is not None and task.get("status") in {"completed", "error", "stopped"}:
                return dict(task)
        time.sleep(0.01)
    raise AssertionError(f"task did not finish: {task_id}")



def test_fastapi_file_preview_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/rag/files/preview" in body["native_paths"]
    assert "/api/files/{file_url:path}/chunk-sets" in body["native_paths"]
    assert "/api/files/{file_url:path}/chunk-sets/generate" in body["native_paths"]



def test_fastapi_file_preview_and_chunk_generation_work(tmp_path: Path, monkeypatch) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch)
    file_url = seed["file_url"]
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    before_preview = client.get("/api/rag/files/preview", params={"file_url": file_url}, headers=headers)
    assert before_preview.status_code == 200, before_preview.text
    before_body = before_preview.json()
    assert before_body["file_info"]["url"] == file_url
    assert before_body["markdown"]["content"].startswith("# Alpha")
    assert before_body["chunk_sets"] == []

    list_before = client.get(f"/api/files/{file_url}/chunk-sets", headers=headers)
    assert list_before.status_code == 200, list_before.text
    assert list_before.json()["chunk_sets"] == []

    generate_response = client.post(
        f"/api/files/{file_url}/chunk-sets/generate",
        json={
            "name": "preview-profile",
            "chunk_size": 120,
            "chunk_overlap": 20,
            "splitter": "semantic",
            "tokenizer": "cl100k_base",
            "overwrite_same_profile": True,
        },
        headers=headers,
    )
    assert generate_response.status_code == 202, generate_response.text
    generate_body = generate_response.json()
    assert generate_body["job_id"]
    first_task = _wait_for_task(app, generate_body["job_id"])
    assert first_task["status"] == "completed", first_task
    first_result = first_task["result"]
    assert first_result["contract_version"] == 1
    assert len(first_result["chunk_sets"]) == 1
    assert first_result["chunk_sets"][0]["file_url"] == file_url
    assert first_result["chunk_sets"][0]["reused_existing"] is False

    first_list = client.get(f"/api/files/{file_url}/chunk-sets", headers=headers).json()
    first_preview = client.get(
        "/api/rag/files/preview", params={"file_url": file_url}, headers=headers
    ).json()
    assert len(first_list["chunk_sets"]) == 1
    assert first_preview["active_chunk_set_id"] == first_result["chunk_sets"][0]["chunk_set_id"]
    assert len(first_preview["chunks"]) == first_list["chunk_sets"][0]["chunk_count"] > 0
    first_snapshot = {
        "chunk_set_id": first_list["chunk_sets"][0]["chunk_set_id"],
        "chunk_count": first_list["chunk_sets"][0]["chunk_count"],
        "created_at": first_list["chunk_sets"][0]["created_at"],
        "updated_at": first_list["chunk_sets"][0]["updated_at"],
        "chunks": [
            (row["chunk_id"], row["content"], row["created_at"])
            for row in first_preview["chunks"]
        ],
    }

    identical_response = client.post(
        f"/api/files/{file_url}/chunk-sets/generate",
        json={
            "name": "preview-profile",
            "chunk_size": 120,
            "chunk_overlap": 20,
            "splitter": "semantic",
            "tokenizer": "cl100k_base",
            "overwrite_same_profile": True,
        },
        headers=headers,
    )
    assert identical_response.status_code == 202, identical_response.text
    identical_body = identical_response.json()
    assert identical_body["job_id"]
    second_task = _wait_for_task(app, identical_body["job_id"])
    assert second_task["status"] == "completed", second_task
    second_result = second_task["result"]
    assert second_result["contract_version"] == 1
    assert second_result["chunk_sets"][0]["chunk_set_id"] == first_snapshot["chunk_set_id"]
    assert second_result["chunk_sets"][0]["chunk_count"] == first_snapshot["chunk_count"]
    assert second_result["chunk_sets"][0]["reused_existing"] is True

    second_list = client.get(f"/api/files/{file_url}/chunk-sets", headers=headers).json()
    second_preview = client.get(
        "/api/rag/files/preview", params={"file_url": file_url}, headers=headers
    ).json()
    assert len(second_list["chunk_sets"]) == 1
    assert {
        "chunk_set_id": second_list["chunk_sets"][0]["chunk_set_id"],
        "chunk_count": second_list["chunk_sets"][0]["chunk_count"],
        "created_at": second_list["chunk_sets"][0]["created_at"],
        "updated_at": second_list["chunk_sets"][0]["updated_at"],
        "chunks": [
            (row["chunk_id"], row["content"], row["created_at"])
            for row in second_preview["chunks"]
        ],
    } == first_snapshot


def test_fastapi_file_chunk_generation_rejects_removed_kb_binding_options(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    file_url = seed["file_url"]
    headers = {"Authorization": f"Bearer {seed['admin_token']}"}

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={
            "kb_id": "kb-file-bind",
            "name": "File Bind KB",
            "kb_mode": "manual",
            "chunk_size": 120,
            "chunk_overlap": 20,
        },
        headers=headers,
    )
    assert create_kb.status_code == 201, create_kb.text

    generate_response = client.post(
        f"/api/files/{file_url}/chunk-sets/generate",
        json={
            "name": "file-bind-profile",
            "chunk_size": 120,
            "chunk_overlap": 20,
            "splitter": "semantic",
            "tokenizer": "cl100k_base",
            "overwrite_same_profile": True,
            "kb_id": "kb-file-bind",
            "binding_mode": "follow_latest",
        },
        headers=headers,
    )
    assert generate_response.status_code == 400, generate_response.text
    generate_body = generate_response.json()
    assert generate_body["code"] == "unsupported_option"
    assert generate_body["unsupported_options"] == ["binding_mode", "kb_id"]
    assert "KB Binding" in generate_body["guidance"]

    bindings = client.get("/api/rag/knowledge-bases/kb-file-bind/bindings", headers=headers)
    assert bindings.status_code == 200, bindings.text
    assert bindings.json()["bindings"] == []


def test_fastapi_chunk_generation_uses_tasks_run_auth_when_legacy_token_is_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONFIG_WRITE_AUTH_TOKEN", "secret-token")
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    file_url = seed["file_url"]
    auth_headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    payload = {
        "name": "preview-profile",
        "chunk_size": 120,
        "chunk_overlap": 20,
        "splitter": "semantic",
        "tokenizer": "cl100k_base",
        "overwrite_same_profile": True,
    }

    allowed = client.post(
        f"/api/files/{file_url}/chunk-sets/generate",
        json=payload,
        headers=auth_headers,
    )
    assert allowed.status_code == 202, allowed.text
    assert allowed.json()["job_id"]
