from __future__ import annotations

import hashlib
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
    finally:
        storage.close()

    return {"file_url": "https://alpha.example/doc-a.pdf"}



def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, str]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-file-preview-test-secret")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    return client, app, seed



def test_fastapi_file_preview_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/rag/files/preview" in body["native_paths"]
    assert "/api/files/{file_url:path}/chunk-sets" in body["native_paths"]
    assert "/api/files/{file_url:path}/chunk-sets/generate" in body["native_paths"]



def test_fastapi_file_preview_and_chunk_generation_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    file_url = seed["file_url"]

    before_preview = client.get("/api/rag/files/preview", params={"file_url": file_url})
    assert before_preview.status_code == 200, before_preview.text
    before_body = before_preview.json()
    assert before_body["file_info"]["url"] == file_url
    assert before_body["markdown"]["content"].startswith("# Alpha")
    assert before_body["chunk_sets"] == []

    list_before = client.get(f"/api/files/{file_url}/chunk-sets")
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
    )
    assert generate_response.status_code in {200, 201}, generate_response.text
    generate_body = generate_response.json()
    assert generate_body["chunk_set_id"]
    assert generate_body["chunk_count"] >= 1

    list_after = client.get(f"/api/files/{file_url}/chunk-sets")
    assert list_after.status_code == 200, list_after.text
    list_body = list_after.json()
    assert list_body["count"] >= 1

    preview_after = client.get("/api/rag/files/preview", params={"file_url": file_url})
    assert preview_after.status_code == 200, preview_after.text
    preview_body = preview_after.json()
    assert preview_body["active_chunk_set_id"] == generate_body["chunk_set_id"]
    assert len(preview_body["chunks"]) >= 1


def test_fastapi_chunk_generation_requires_config_write_token_when_configured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_WRITE_AUTH_TOKEN", "secret-token")
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)
    file_url = seed["file_url"]

    payload = {
        "name": "preview-profile",
        "chunk_size": 120,
        "chunk_overlap": 20,
        "splitter": "semantic",
        "tokenizer": "cl100k_base",
        "overwrite_same_profile": True,
    }

    forbidden = client.post(f"/api/files/{file_url}/chunk-sets/generate", json=payload)
    assert forbidden.status_code == 403, forbidden.text

    allowed = client.post(
        f"/api/files/{file_url}/chunk-sets/generate",
        json=payload,
        headers={"X-Auth-Token": "secret-token"},
    )
    assert allowed.status_code in {200, 201}, allowed.text
