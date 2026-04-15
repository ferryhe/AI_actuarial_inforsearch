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
    export_dir = base_dir / "updates"
    export_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "paths": {
            "db": str(db_path),
            "download_dir": str(files_dir),
            "updates_dir": str(export_dir),
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
    beta_path = files_dir / "beta.docx"
    beta_path.write_text("beta docx content", encoding="utf-8")

    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url="https://alpha.example/doc-a.pdf",
            sha256=hashlib.sha256(PDF_BYTES).hexdigest(),
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
                "url": "https://alpha.example/doc-a.pdf",
                "sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
                "keywords": ["ai"],
                "summary": "Alpha summary",
                "category": "AI",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(
            "https://alpha.example/doc-a.pdf",
            "# Alpha\n\nOriginal markdown.",
            "manual",
        )

        storage.insert_file(
            url="https://beta.example/doc-b.docx",
            sha256=hashlib.sha256(beta_path.read_bytes()).hexdigest(),
            title="Beta Document",
            source_site="beta.example",
            source_page_url="https://beta.example",
            original_filename="doc-b.docx",
            local_path=str(beta_path),
            bytes=beta_path.stat().st_size,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://beta.example/doc-b.docx",
                "sha256": hashlib.sha256(beta_path.read_bytes()).hexdigest(),
                "keywords": ["pricing"],
                "summary": "Beta summary",
                "category": "Pricing",
            },
            pipeline_version="v1",
            status="ok",
        )
    finally:
        storage.close()

    return {
        "alpha_url": "https://alpha.example/doc-a.pdf",
        "beta_url": "https://beta.example/doc-b.docx",
        "alpha_path": str(alpha_path),
    }



def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, str]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-file-mutations-test-secret")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    return client, app, seed



def test_fastapi_file_mutation_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/files/update" in body["native_paths"]
    assert "/api/files/delete" in body["native_paths"]
    assert "/api/files/{file_url:path}/markdown" in body["native_paths"]
    assert "/api/download" in body["native_paths"]
    assert "/api/export" in body["native_paths"]



def test_fastapi_file_mutations_download_and_export_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)

    update_response = client.post(
        "/api/files/update",
        json={
            "url": seed["alpha_url"],
            "title": "Alpha Document Updated",
            "category": "AI; Preview",
            "summary": "Updated summary",
            "keywords": ["ai", "preview"],
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["file"]["title"] == "Alpha Document Updated"

    markdown_response = client.post(
        f"/api/files/{seed['alpha_url']}/markdown",
        json={"markdown_content": "# Updated\n\nFastAPI markdown.", "markdown_source": "manual"},
    )
    assert markdown_response.status_code == 200, markdown_response.text
    assert markdown_response.json()["markdown"]["markdown_content"].startswith("# Updated")

    download_response = client.get("/api/download", params={"url": seed["alpha_url"]})
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == PDF_BYTES

    export_response = client.get("/api/export", params={"format": "csv"})
    assert export_response.status_code == 200, export_response.text
    assert "attachment; filename=catalog_export.csv" in export_response.headers.get("content-disposition", "")
    assert "Alpha Document Updated" in export_response.content.decode("utf-8-sig")

    delete_response = client.post("/api/files/delete", json={"url": seed["beta_url"], "confirm": "DELETE"})
    assert delete_response.status_code == 200, delete_response.text

    files_after_delete = client.get("/api/files?include_deleted=true")
    deleted = next(item for item in files_after_delete.json()["files"] if item["url"] == seed["beta_url"])
    assert deleted["deleted_at"]
