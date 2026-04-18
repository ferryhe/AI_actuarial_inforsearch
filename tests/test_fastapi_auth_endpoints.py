from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TypedDict

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.shared_auth import hash_password
from ai_actuarial.storage import Storage


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class SeedData(TypedDict):
    user_id: int
    admin_token: str


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


def _seed_storage(db_path: Path, files_dir: Path) -> SeedData:
    alpha_path = files_dir / "alpha.pdf"
    alpha_path.write_bytes(PDF_BYTES)

    storage = Storage(str(db_path))
    try:
        alpha_url = "https://alpha.example/doc-a.pdf"
        alpha_sha = hashlib.sha256(alpha_path.read_bytes()).hexdigest()
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
        storage.upsert_catalog_item(
            item={
                "url": alpha_url,
                "sha256": alpha_sha,
                "keywords": ["ai", "solvency"],
                "summary": "Alpha summary",
                "category": "AI",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(alpha_url, "# Alpha\n\nAlpha markdown.", "manual")
        admin_token = "admin-token-123"
        storage.upsert_auth_token_by_hash(
            subject="admin@example.com",
            group_name="admin",
            token_hash=hashlib.sha256(admin_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        user_id = storage.create_user(
            "member@example.com",
            hash_password("password123"),
            role="registered",
            display_name="Member User",
        )
    finally:
        storage.close()

    return {"user_id": user_id, "admin_token": admin_token}


def _build_test_client(tmp_path: Path, monkeypatch, *, require_auth: bool = True) -> tuple[TestClient, object, SeedData]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-auth-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("REQUIRE_AUTH", "1" if require_auth else "0")
    app = create_app()
    client = TestClient(app)
    return client, app, seed


def test_fastapi_auth_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/auth/me" in body["native_paths"]
    assert "/api/auth/tokens" in body["native_paths"]
    assert "/api/auth/tokens/{token_id}/revoke" in body["native_paths"]
    assert "/api/user/me" in body["native_paths"]
    assert "/api/user/profile" in body["native_paths"]
    assert "/api/admin/users" in body["native_paths"]
    assert "/api/admin/users/{user_id}/role" in body["native_paths"]
    assert "/api/admin/users/{user_id}/enable" in body["native_paths"]
    assert "/api/admin/users/{user_id}/disable" in body["native_paths"]
    assert "/api/admin/users/{user_id}/reset-quota" in body["native_paths"]
    assert "/api/admin/users/{user_id}/activity" in body["native_paths"]


def test_auth_me_allows_anonymous_database_and_chat_browse_when_auth_required(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    auth_me = client.get("/api/auth/me")
    assert auth_me.status_code == 200, auth_me.text
    body = auth_me.json()["data"]
    assert body["require_auth"] is True
    assert body["authenticated"] is False
    assert "files.read" in body["permissions"]
    assert "chat.view" in body["permissions"]
    assert "chat.query" in body["permissions"]
    assert "chat.conversations" in body["permissions"]

    files = client.get("/api/files")
    assert files.status_code == 200, files.text

    conv = client.post("/api/chat/conversations", json={"mode": "expert"})
    assert conv.status_code == 201, conv.text


def test_fastapi_auth_register_login_logout_and_profile_flow(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    register = client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "password123",
            "display_name": "New User",
        },
    )
    assert register.status_code == 201, register.text

    auth_me = client.get("/api/auth/me")
    assert auth_me.status_code == 200, auth_me.text
    auth_payload = auth_me.json()["data"]
    assert auth_payload["authenticated"] is True
    assert auth_payload["user"]["email"] == "newuser@example.com"

    user_me = client.get("/api/user/me")
    assert user_me.status_code == 200, user_me.text
    assert user_me.json()["user"]["display_name"] == "New User"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200, logout.text

    logged_out = client.get("/api/auth/me")
    assert logged_out.status_code == 200, logged_out.text
    assert logged_out.json()["data"]["authenticated"] is False

    login = client.post(
        "/api/auth/login",
        json={"email": "newuser@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text

    profile_update = client.patch(
        "/api/user/profile",
        json={"display_name": "Renamed User", "current_password": "password123", "new_password": "password456"},
    )
    assert profile_update.status_code == 200, profile_update.text

    refreshed_user = client.get("/api/user/me")
    assert refreshed_user.status_code == 200, refreshed_user.text
    assert refreshed_user.json()["user"]["display_name"] == "Renamed User"



def test_fastapi_auth_session_persists_with_fastapi_native_session(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    register = client.post(
        "/api/auth/register",
        json={
            "email": "fallback@example.com",
            "password": "password123",
            "display_name": "Fallback User",
        },
    )
    assert register.status_code == 201, register.text

    auth_me = client.get("/api/auth/me")
    assert auth_me.status_code == 200, auth_me.text
    assert auth_me.json()["data"]["authenticated"] is True
    assert auth_me.json()["data"]["user"]["email"] == "fallback@example.com"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200, logout.text
    assert client.get("/api/auth/me").json()["data"]["authenticated"] is False



def test_fastapi_auth_logout_clears_cookie_with_configured_domain(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    app.state.fastapi_session_cookie_domain = "example.com"

    register = client.post(
        "/api/auth/register",
        json={
            "email": "domainlogout@example.com",
            "password": "password123",
            "display_name": "Domain Logout",
        },
    )
    assert register.status_code == 201, register.text

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200, logout.text
    set_cookie = logout.headers.get("set-cookie", "")
    assert "Domain=example.com" in set_cookie
    assert 'session=""' in set_cookie



def test_fastapi_auth_no_flask_runtime_register_login_logout_roundtrip(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    register = client.post(
        "/api/auth/register",
        json={
            "email": "runtime@example.com",
            "password": "password123",
            "display_name": "Runtime User",
        },
    )
    assert register.status_code == 201, register.text
    assert client.get("/api/auth/me").json()["data"]["authenticated"] is True

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200, logout.text
    assert client.get("/api/auth/me").json()["data"]["authenticated"] is False

    login = client.post(
        "/api/auth/login",
        json={"email": "runtime@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    auth_me = client.get("/api/auth/me")
    assert auth_me.status_code == 200, auth_me.text
    assert auth_me.json()["data"]["authenticated"] is True
    assert auth_me.json()["data"]["user"]["email"] == "runtime@example.com"



def test_fastapi_auth_register_and_login_fail_closed_without_session_secret(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    app.state.fastapi_session_secret = ""

    register = client.post(
        "/api/auth/register",
        json={
            "email": "nosecret@example.com",
            "password": "***",
            "display_name": "No Secret",
        },
    )
    assert register.status_code == 503, register.text
    assert register.json()["error"] == "FastAPI session secret is not configured"

    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "***"},
    )
    assert login.status_code == 503, login.text
    assert login.json()["error"] == "FastAPI session secret is not configured"



def test_fastapi_admin_user_and_token_management_surfaces_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['admin_token']}"}

    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200, users.text
    user_rows = users.json()["users"]
    assert all("password_hash" not in row for row in user_rows)

    role = client.post(f"/api/admin/users/{seed['user_id']}/role", json={"role": "premium"}, headers=headers)
    assert role.status_code == 200, role.text
    assert role.json()["role"] == "premium"

    disable = client.post(f"/api/admin/users/{seed['user_id']}/disable", headers=headers)
    assert disable.status_code == 200, disable.text
    assert disable.json()["is_active"] is False

    enable = client.post(f"/api/admin/users/{seed['user_id']}/enable", headers=headers)
    assert enable.status_code == 200, enable.text
    assert enable.json()["is_active"] is True

    reset = client.post(f"/api/admin/users/{seed['user_id']}/reset-quota", headers=headers)
    assert reset.status_code == 200, reset.text

    activity = client.get(f"/api/admin/users/{seed['user_id']}/activity", headers=headers)
    assert activity.status_code == 200, activity.text
    assert "activity" in activity.json()

    token_create = client.post(
        "/api/auth/tokens",
        json={"subject": "reader@example.com", "group_name": "reader"},
        headers=headers,
    )
    assert token_create.status_code == 201, token_create.text
    token_id = token_create.json()["token"]["id"]
    assert token_create.json()["token"]["token"]

    token_list = client.get("/api/auth/tokens", headers=headers)
    assert token_list.status_code == 200, token_list.text
    assert any(item["id"] == token_id for item in token_list.json()["tokens"])

    revoke = client.post(f"/api/auth/tokens/{token_id}/revoke", headers=headers)
    assert revoke.status_code == 200, revoke.text
