from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from ai_actuarial.api.app import create_app
from ai_actuarial.storage import Storage


def _write_config_files(base_dir: Path) -> tuple[Path, Path, Path]:
    db_path = base_dir / "index.db"
    config_path = base_dir / "sites.yaml"
    categories_path = base_dir / "categories.yaml"

    config = {
        "paths": {
            "db": str(db_path),
            "download_dir": str(base_dir / "files"),
            "updates_dir": str(base_dir / "updates"),
            "last_run_new": str(base_dir / "last_run_new.json"),
        },
        "defaults": {
            "user_agent": "test-agent/1.0",
            "max_pages": 10,
            "max_depth": 1,
            "file_exts": [".pdf"],
        },
        "sites": [],
    }
    categories = {
        "categories": {
            "AI": ["artificial intelligence"],
            "Pricing": ["premium"],
            "Reserve": ["reserve"],
        }
    }

    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path


def _seed_storage(db_path: Path) -> dict[str, object]:
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url="https://alpha.example/doc-a.pdf",
            sha256="hash-alpha",
            title="Alpha Document",
            source_site="alpha.example",
            source_page_url="https://alpha.example",
            original_filename="doc-a.pdf",
            local_path="/tmp/doc-a.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://alpha.example/doc-a.pdf",
                "sha256": "hash-alpha",
                "keywords": ["ai"],
                "summary": "Alpha summary",
                "category": "AI; Risk",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(
            "https://alpha.example/doc-a.pdf",
            "# Alpha Document\n\nMarkdown content for alpha.",
            "manual",
        )

        storage.insert_file(
            url="https://beta.example/doc-b.docx",
            sha256="hash-beta",
            title="Beta Document",
            source_site="beta.example",
            source_page_url="https://beta.example",
            original_filename="doc-b.docx",
            local_path="/tmp/doc-b.docx",
            bytes=2048,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://beta.example/doc-b.docx",
                "sha256": "hash-beta",
                "keywords": ["pricing"],
                "summary": "Beta summary",
                "category": "Pricing",
            },
            pipeline_version="v1",
            status="ok",
        )

        storage.insert_file(
            url="https://gamma.example/doc-c.pdf",
            sha256="hash-gamma",
            title="Gamma Deleted",
            source_site="gamma.example",
            source_page_url="https://gamma.example",
            original_filename="doc-c.pdf",
            local_path="/tmp/doc-c.pdf",
            bytes=512,
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://gamma.example/doc-c.pdf",
                "sha256": "hash-gamma",
                "keywords": ["archived"],
                "summary": "Gamma summary",
                "category": "Archive",
            },
            pipeline_version="v1",
            status="ok",
        )
        deleted_at = datetime.now(timezone.utc).isoformat()
        storage.mark_file_deleted("https://gamma.example/doc-c.pdf", deleted_at)
        storage.clear_local_path("https://gamma.example/doc-c.pdf")

        user_id = storage.create_user(
            "reader@example.com",
            "test-password-hash",
            role="registered",
            display_name="Reader",
        )
        token_plain = "reader-token"
        storage.upsert_auth_token_by_hash(
            subject="reader-token",
            group_name="reader",
            token_hash=hashlib.sha256(token_plain.encode("utf-8")).hexdigest(),
            is_active=True,
        )

        storage._conn.execute(
            "UPDATE files SET last_seen = ? WHERE url = ?",
            ("2026-03-08T10:00:00+00:00", "https://alpha.example/doc-a.pdf"),
        )
        storage._conn.execute(
            "UPDATE files SET last_seen = ? WHERE url = ?",
            ("2026-03-09T10:00:00+00:00", "https://beta.example/doc-b.docx"),
        )
        storage._conn.execute(
            "UPDATE files SET last_seen = ? WHERE url = ?",
            ("2026-03-07T10:00:00+00:00", "https://gamma.example/doc-c.pdf"),
        )
        storage._conn.commit()
    finally:
        storage.close()

    return {"user_id": user_id, "token_plain": token_plain}


def _build_test_client(tmp_path: Path, monkeypatch, *, require_auth: bool) -> tuple[TestClient, object, dict[str, object]]:
    db_path, config_path, categories_path = _write_config_files(tmp_path)
    seed = _seed_storage(db_path)

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-read-test-secret")
    if require_auth:
        monkeypatch.setenv("REQUIRE_AUTH", "true")
    else:
        monkeypatch.delenv("REQUIRE_AUTH", raising=False)

    app = create_app()
    client = TestClient(app)
    return client, app, seed


def _make_session_cookie(app, payload: dict[str, object]) -> str:
    serializer = URLSafeSerializer(app.state.fastapi_session_secret, salt="fastapi-session")
    return serializer.dumps(payload)


def test_fastapi_stats_and_categories_are_native(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json() == {
        "total_files": 2,
        "cataloged_files": 2,
        "total_sources": 3,
        "active_tasks": 0,
    }

    categories = client.get("/api/categories")
    assert categories.status_code == 200
    assert categories.json()["categories"] == ["AI", "Pricing", "Reserve"]

    used_categories = client.get("/api/categories?mode=used")
    assert used_categories.status_code == 200
    assert used_categories.json()["categories"] == ["AI", "Archive", "Pricing", "Risk"]

    migration = client.get("/api/migration/status")
    body = migration.json()
    assert "/api/stats" in body["native_paths"]
    assert "/api/sources" in body["native_paths"]
    assert "/api/categories" in body["native_paths"]
    assert "/api/files" in body["native_paths"]
    assert "/api/files/detail" in body["native_paths"]
    assert "/api/files/{file_url:path}/markdown" in body["native_paths"]


def test_fastapi_files_supports_filters_sorting_and_deleted(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)

    response = client.get("/api/files?limit=10&order_by=title&order_dir=asc")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert [item["title"] for item in body["files"]] == ["Alpha Document", "Beta Document"]

    filtered = client.get("/api/files?category=AI")
    assert filtered.status_code == 200
    filtered_body = filtered.json()
    assert filtered_body["total"] == 1
    assert filtered_body["files"][0]["title"] == "Alpha Document"
    assert filtered_body["files"][0]["category"] == "AI; Risk"

    deleted = client.get("/api/files?include_deleted=true&order_by=title&order_dir=asc")
    assert deleted.status_code == 200
    deleted_body = deleted.json()
    assert deleted_body["total"] == 3
    assert [item["title"] for item in deleted_body["files"]] == [
        "Alpha Document",
        "Beta Document",
        "Gamma Deleted",
    ]


def test_fastapi_native_read_routes_keep_public_reads_available_under_require_auth(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    public_stats = client.get("/api/stats")
    assert public_stats.status_code == 200

    public_files = client.get("/api/files")
    assert public_files.status_code == 200
    assert public_files.json()["total"] == 2

    authorized = client.get(
        "/api/files",
        headers={"Authorization": f"Bearer {seed['token_plain']}"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["total"] == 2


def test_fastapi_sources_file_detail_and_markdown_match_legacy_contract(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    assert sources.json() == {
        "sources": ["alpha.example", "beta.example", "gamma.example"],
    }

    detail = client.get("/api/files/detail?url=https%3A%2F%2Falpha.example%2Fdoc-a.pdf")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["file"]["url"] == "https://alpha.example/doc-a.pdf"
    assert detail_body["file"]["title"] == "Alpha Document"
    assert detail_body["file"]["markdown_source"] == "manual"

    missing_param = client.get("/api/files/detail")
    assert missing_param.status_code == 400
    assert missing_param.json() == {"error": "url parameter is required"}

    missing_file = client.get("/api/files/detail?url=https%3A%2F%2Fmissing.example%2Fdoc.pdf")
    assert missing_file.status_code == 404
    assert missing_file.json() == {"error": "File not found"}

    markdown = client.get(f"/api/files/{quote('https://alpha.example/doc-a.pdf', safe='')}/markdown")
    assert markdown.status_code == 200
    assert markdown.json()["success"] is True
    assert markdown.json()["markdown"]["markdown_content"] == "# Alpha Document\n\nMarkdown content for alpha."
    assert markdown.json()["markdown"]["markdown_source"] == "manual"

    unknown_markdown = client.get(f"/api/files/{quote('https://missing.example/doc.pdf', safe='')}/markdown")
    assert unknown_markdown.status_code == 200
    assert unknown_markdown.json() == {"success": True, "markdown": None}


def test_fastapi_markdown_route_preserves_percent_encoded_file_urls(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)

    storage = Storage(str(app.state.db_path))
    try:
        encoded_url = "https://encoded.example/doc%20space.pdf"
        storage.insert_file(
            url=encoded_url,
            sha256="hash-encoded",
            title="Encoded Document",
            source_site="encoded.example",
            source_page_url="https://encoded.example",
            original_filename="doc%20space.pdf",
            local_path="/tmp/doc%20space.pdf",
            bytes=333,
            content_type="application/pdf",
        )
        storage.update_file_markdown(
            encoded_url,
            "# Encoded Document\n\nStored under a percent-encoded URL.",
            "manual",
        )
    finally:
        storage.close()

    response = client.get(f"/api/files/{quote(encoded_url, safe='')}/markdown")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["markdown"]["markdown_content"] == "# Encoded Document\n\nStored under a percent-encoded URL."


def test_fastapi_native_read_routes_accept_fastapi_session_cookie(tmp_path: Path, monkeypatch) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    cookie_name = app.state.fastapi_session_cookie_name
    session_cookie = _make_session_cookie(app, {"email_user_id": seed["user_id"]})
    client.cookies.set(cookie_name, session_cookie)

    response = client.get("/api/categories?mode=used")
    assert response.status_code == 200
    assert response.json()["categories"] == ["AI", "Archive", "Pricing", "Risk"]

    sources = client.get("/api/sources")
    assert sources.status_code == 200
    assert sources.json()["sources"] == ["alpha.example", "beta.example", "gamma.example"]

    detail = client.get("/api/files/detail?url=https%3A%2F%2Falpha.example%2Fdoc-a.pdf")
    assert detail.status_code == 200
    assert detail.json()["file"]["title"] == "Alpha Document"

    markdown = client.get(f"/api/files/{quote('https://alpha.example/doc-a.pdf', safe='')}/markdown")
    assert markdown.status_code == 200
    assert markdown.json()["markdown"]["markdown_source"] == "manual"
