from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

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
    legacy_app = app.state.legacy_flask_app
    serializer = legacy_app.session_interface.get_signing_serializer(legacy_app)
    assert serializer is not None
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
    assert "/api/categories" in body["native_paths"]
    assert "/api/files" in body["native_paths"]


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


def test_fastapi_native_read_routes_require_bearer_auth(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    unauthorized = client.get("/api/stats")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/api/files",
        headers={"Authorization": f"Bearer {seed['token_plain']}"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["total"] == 2


def test_fastapi_native_read_routes_accept_flask_session_cookie(tmp_path: Path, monkeypatch) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    cookie_name = app.state.legacy_flask_app.config.get("SESSION_COOKIE_NAME", "session")
    session_cookie = _make_session_cookie(app, {"email_user_id": seed["user_id"]})
    client.cookies.set(cookie_name, session_cookie)

    response = client.get("/api/categories?mode=used")
    assert response.status_code == 200
    assert response.json()["categories"] == ["AI", "Archive", "Pricing", "Risk"]
