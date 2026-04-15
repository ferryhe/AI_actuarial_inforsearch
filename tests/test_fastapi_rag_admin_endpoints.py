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
        "sites": [],
        "scheduled_tasks": [],
    }
    categories = {"categories": {"AI": ["artificial intelligence"], "Risk": ["capital"]}}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path, files_dir



def _seed_storage(db_path: Path, files_dir: Path) -> dict[str, str]:
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
    finally:
        storage.close()

    return {"alpha_url": alpha_url, "beta_url": beta_url}



def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, str]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-rag-admin-test-secret")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    return client, app, seed



def test_fastapi_rag_admin_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/chunk/profiles" in body["native_paths"]
    assert "/api/chunk/profiles/{profile_id}" in body["native_paths"]
    assert "/api/rag/knowledge-bases" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/stats" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/files" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/files/{file_url:path}" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/categories" in body["native_paths"]
    assert "/api/rag/categories/unmapped" in body["native_paths"]
    assert "/api/rag/files/selectable" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/files/pending" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/bindings" in body["native_paths"]
    assert "/api/rag/knowledge-bases/{kb_id}/index" in body["native_paths"]
    assert "/api/chunk-sets/cleanup" in body["native_paths"]



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

    list_kbs = client.get("/api/rag/knowledge-bases")
    assert list_kbs.status_code == 200, list_kbs.text
    assert any(item["kb_id"] == "kb-pr4-test" for item in list_kbs.json()["knowledge_bases"])

    get_kb = client.get("/api/rag/knowledge-bases/kb-pr4-test")
    assert get_kb.status_code == 200, get_kb.text
    assert get_kb.json()["knowledge_base"]["name"] == "PR4 Test KB"

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

    index = client.post(
        "/api/rag/knowledge-bases/kb-detail-test/index",
        json={"file_urls": [alpha_url]},
    )
    assert index.status_code in {200, 202}, index.text

    cleanup = client.post("/api/chunk-sets/cleanup", json={"dry_run": True})
    assert cleanup.status_code == 200, cleanup.text
