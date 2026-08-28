from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from itsdangerous import URLSafeSerializer

from ai_actuarial.shared_auth import hash_token
from ai_actuarial.storage import Storage
from tests.test_fastapi_chat_endpoints import (
    _build_test_client as _build_chat_test_client,
    _install_guest_chat_fakes,
)
from tests.test_fastapi_ops_read_endpoints import (
    _build_test_client,
    _make_session_cookie,
    _patch_available_models,
)


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_TSX = ROOT / "client" / "src" / "pages" / "Settings.tsx"
MARKDOWN_TAB_TSX = ROOT / "client" / "src" / "pages" / "settings" / "MarkdownConversionTab.tsx"
LOGIN_TSX = ROOT / "client" / "src" / "pages" / "Login.tsx"
SETTINGS_ERRORS_TS = ROOT / "client" / "src" / "lib" / "settings-errors.ts"
API_TS = ROOT / "client" / "src" / "lib" / "api.ts"
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


def _run_tsx(script: str) -> dict[str, object]:
    wrapped = f"(async () => {{ {script} }})().catch((error) => {{ console.error(error); process.exit(1); }});".replace(
        "\n", " "
    )
    result = subprocess.run(
        [NPM_COMMAND, "exec", "--", "tsx", "-e", wrapped],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _assert_mutation_uses_settings_error_formatter(source: str, marker: str) -> None:
    start = source.index(marker)
    catch = source.index("catch", start)
    assert catch - start < 1800, marker
    error_call = source.index("formatSettingsMutationError(error, t,", catch)
    assert error_call - catch < 500, marker


def _seeded_token_id(app, presented_token: object) -> int:
    storage = Storage(app.state.db_path)
    try:
        token = storage.get_auth_token_by_hash(hash_token(str(presented_token)))
    finally:
        storage.close()
    assert token is not None
    return int(token["id"])


def test_admin_email_session_remains_authoritative_for_settings_write_and_readback(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    markdown_config_path = tmp_path / "markdown_conversion.yaml"
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(markdown_config_path))
    monkeypatch.delenv("CONFIG_WRITE_AUTH_TOKEN", raising=False)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    client.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]}),
    )
    stale_reader_header = {"X-Auth-Token": str(seed["reader_token"])}

    before = client.get("/api/auth/me", headers=stale_reader_header)
    assert before.status_code == 200
    before_auth = before.json()["data"]
    assert before_auth["user"]["id"] == seed["admin_user_id"]
    assert before_auth["user"]["role"] == "admin"
    assert "config.write" in before_auth["permissions"]

    update = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown", "limits": {"default_scan_count": 29}},
        headers=stale_reader_header,
    )
    assert update.status_code == 200, update.text

    read_back = client.get("/api/config/markdown-conversion", headers=stale_reader_header)
    after = client.get("/api/auth/me", headers=stale_reader_header)
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["config"]["default_tool"] == "markitdown"
    assert read_back.json()["config"]["limits"]["default_scan_count"] == 29
    assert after.json()["data"]["user"] == before_auth["user"]
    assert after.json()["data"]["permissions"] == before_auth["permissions"]


def test_invalid_present_session_does_not_fall_back_to_reader_header(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    client.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]}),
    )
    before = client.get("/api/auth/me")
    assert before.json()["data"]["user"]["id"] == seed["admin_user_id"]
    assert before.json()["data"]["user"]["role"] == "admin"
    app.state.fastapi_session_secret = "rotated-issue-249-test-secret"

    response = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={"X-Auth-Token": str(seed["reader_token"])},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_invalid_session_identity_does_not_fall_back_to_reader_header(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    client.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": 999_999}),
    )

    response = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={"X-Auth-Token": str(seed["reader_token"])},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_duplicate_session_cookies_choose_valid_admin_identity(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    valid_admin = _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]})
    cookie_name = app.state.fastapi_session_cookie_name

    response = client.get(
        "/api/auth/me",
        headers={
            "Cookie": f"{cookie_name}={valid_admin}; {cookie_name}=stale-invalid-session",
            "X-Auth-Token": str(seed["reader_token"]),
        },
    )

    assert response.status_code == 200
    auth = response.json()["data"]
    assert auth["user"]["id"] == seed["admin_user_id"]
    assert auth["user"]["role"] == "admin"
    assert "config.write" in auth["permissions"]


def test_duplicate_token_mode_reader_session_cannot_downgrade_email_admin(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(tmp_path / "markdown_conversion.yaml"))
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    cookie_name = app.state.fastapi_session_cookie_name
    token_login = client.post("/api/auth/login", json={"token": seed["reader_token"]})
    assert token_login.status_code == 200
    reader_session = client.cookies.get(cookie_name)
    assert reader_session
    client.cookies.clear()
    admin_session = _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]})

    for cookie_header in (
        f"{cookie_name}={admin_session}; {cookie_name}={reader_session}",
        f"{cookie_name}={reader_session}; {cookie_name}={admin_session}",
    ):
        response = client.get("/api/auth/me", headers={"Cookie": cookie_header})
        auth = response.json()["data"]
        assert auth["user"]["id"] == seed["admin_user_id"]
        assert auth["user"]["role"] == "admin"
        assert "config.write" in auth["permissions"]

        update = client.post(
            "/api/config/markdown-conversion",
            json={"default_tool": "markitdown"},
            headers={"Cookie": cookie_header},
        )
        assert update.status_code == 200, update.text


@pytest.mark.parametrize("email_first", [True, False])
@pytest.mark.parametrize("with_admin_header", [False, True])
def test_non_admin_email_and_active_admin_token_session_fail_closed(
    tmp_path: Path, monkeypatch, email_first: bool, with_admin_header: bool
) -> None:
    _patch_available_models(monkeypatch)
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(tmp_path / "markdown_conversion.yaml"))
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    storage = Storage(app.state.db_path)
    try:
        registered_user_id = storage.create_user(
            "cross-mode-registered@example.com",
            "not-a-real-password-hash",
            role="registered",
            display_name="Cross-mode Registered",
        )
    finally:
        storage.close()

    cookie_name = app.state.fastapi_session_cookie_name
    email_session = _make_session_cookie(app, {"email_user_id": registered_user_id})
    admin_token_session = _make_session_cookie(
        app, {"auth_token_id": _seeded_token_id(app, seed["admin_token"])}
    )
    ordered_sessions = (
        (email_session, admin_token_session)
        if email_first
        else (admin_token_session, email_session)
    )
    headers = {"Cookie": f"{cookie_name}={ordered_sessions[0]}; {cookie_name}={ordered_sessions[1]}"}
    if with_admin_header:
        headers["X-Auth-Token"] = str(seed["admin_token"])

    auth_me = client.get("/api/auth/me", headers=headers)
    assert auth_me.status_code == 200
    assert auth_me.json()["data"]["authenticated"] is False

    update = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers=headers,
    )
    assert update.status_code == 401
    assert update.json()["detail"] == "Unauthorized"


@pytest.mark.parametrize("reader_first", [True, False])
@pytest.mark.parametrize("with_admin_header", [False, True])
def test_different_active_token_sessions_fail_closed_in_both_cookie_orders(
    tmp_path: Path, monkeypatch, reader_first: bool, with_admin_header: bool
) -> None:
    _patch_available_models(monkeypatch)
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(tmp_path / "markdown_conversion.yaml"))
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    cookie_name = app.state.fastapi_session_cookie_name
    reader_session = _make_session_cookie(
        app, {"auth_token_id": _seeded_token_id(app, seed["reader_token"])}
    )
    admin_session = _make_session_cookie(
        app, {"auth_token_id": _seeded_token_id(app, seed["admin_token"])}
    )
    ordered_sessions = (reader_session, admin_session) if reader_first else (admin_session, reader_session)
    headers = {"Cookie": f"{cookie_name}={ordered_sessions[0]}; {cookie_name}={ordered_sessions[1]}"}
    if with_admin_header:
        headers["X-Auth-Token"] = str(seed["admin_token"])

    auth_me = client.get("/api/auth/me", headers=headers)
    assert auth_me.status_code == 200
    assert auth_me.json()["data"]["authenticated"] is False

    update = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers=headers,
    )
    assert update.status_code == 401
    assert update.json()["detail"] == "Unauthorized"


def test_duplicate_same_active_token_session_keeps_admin_identity(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(tmp_path / "markdown_conversion.yaml"))
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    cookie_name = app.state.fastapi_session_cookie_name
    admin_session = _make_session_cookie(
        app, {"auth_token_id": _seeded_token_id(app, seed["admin_token"])}
    )
    headers = {"Cookie": f"{cookie_name}={admin_session}; {cookie_name}={admin_session}"}

    auth_me = client.get("/api/auth/me", headers=headers)
    assert auth_me.status_code == 200
    auth = auth_me.json()["data"]
    assert auth["user"]["role"] == "admin"
    assert "config.write" in auth["permissions"]

    update = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers=headers,
    )
    assert update.status_code == 200, update.text


@pytest.mark.parametrize("stale_kind", ["inactive", "expired", "missing", "invalid"])
def test_unusable_token_session_does_not_mask_unique_active_admin_in_either_order(
    tmp_path: Path, monkeypatch, stale_kind: str
) -> None:
    _patch_available_models(monkeypatch)
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(tmp_path / "markdown_conversion.yaml"))
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    storage = Storage(app.state.db_path)
    try:
        if stale_kind == "inactive":
            stale_id: object = storage.upsert_auth_token_by_hash(
                subject="inactive-token",
                group_name="reader",
                token_hash=hash_token("issue-249-inactive-token"),
                is_active=False,
            )
        elif stale_kind == "expired":
            stale_id = storage.create_auth_token(
                subject="expired-token",
                group_name="reader",
                token_hash=hash_token("issue-249-expired-token"),
                expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            )
        elif stale_kind == "missing":
            stale_id = 999_999
        else:
            stale_id = "not-a-token-id"
    finally:
        storage.close()

    cookie_name = app.state.fastapi_session_cookie_name
    stale_session = _make_session_cookie(app, {"auth_token_id": stale_id})
    admin_session = _make_session_cookie(
        app, {"auth_token_id": _seeded_token_id(app, seed["admin_token"])}
    )

    for ordered_sessions in ((stale_session, admin_session), (admin_session, stale_session)):
        headers = {
            "Cookie": f"{cookie_name}={ordered_sessions[0]}; {cookie_name}={ordered_sessions[1]}"
        }
        auth_me = client.get("/api/auth/me", headers=headers)
        assert auth_me.status_code == 200
        auth = auth_me.json()["data"]
        assert auth["user"]["role"] == "admin"
        assert "config.write" in auth["permissions"]

        update = client.post(
            "/api/config/markdown-conversion",
            json={"default_tool": "markitdown"},
            headers=headers,
        )
        assert update.status_code == 200, update.text


def test_different_active_email_sessions_fail_closed_in_both_cookie_orders(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    storage = Storage(app.state.db_path)
    try:
        registered_user_id = storage.create_user(
            "ambiguous-registered@example.com",
            "not-a-real-password-hash",
            role="registered",
            display_name="Ambiguous Registered",
        )
    finally:
        storage.close()
    cookie_name = app.state.fastapi_session_cookie_name
    registered_session = _make_session_cookie(app, {"email_user_id": registered_user_id})
    admin_session = _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]})

    for cookie_header in (
        f"{cookie_name}={registered_session}; {cookie_name}={admin_session}",
        f"{cookie_name}={admin_session}; {cookie_name}={registered_session}",
    ):
        auth_me = client.get("/api/auth/me", headers={"Cookie": cookie_header})
        assert auth_me.status_code == 200
        assert auth_me.json()["data"]["authenticated"] is False

        update = client.post(
            "/api/config/markdown-conversion",
            json={"default_tool": "markitdown"},
            headers={"Cookie": cookie_header},
        )
        assert update.status_code == 401
        assert update.json()["detail"] == "Unauthorized"


def test_duplicate_same_email_and_invalid_or_disabled_identity_keep_valid_admin(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    storage = Storage(app.state.db_path)
    try:
        disabled_user_id = storage.create_user(
            "disabled-duplicate@example.com",
            "not-a-real-password-hash",
            role="registered",
            display_name="Disabled Duplicate",
        )
        storage.update_user_active(disabled_user_id, False)
    finally:
        storage.close()
    cookie_name = app.state.fastapi_session_cookie_name
    admin_session = _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]})
    disabled_session = _make_session_cookie(app, {"email_user_id": disabled_user_id})
    missing_session = _make_session_cookie(app, {"email_user_id": 999_999})

    for cookie_header in (
        f"{cookie_name}={admin_session}; {cookie_name}={admin_session}",
        (
            f"{cookie_name}=invalid-signed-session; {cookie_name}={disabled_session}; "
            f"{cookie_name}={missing_session}; {cookie_name}={admin_session}"
        ),
        (
            f"{cookie_name}={admin_session}; {cookie_name}={missing_session}; "
            f"{cookie_name}={disabled_session}; {cookie_name}=invalid-signed-session"
        ),
    ):
        response = client.get("/api/auth/me", headers={"Cookie": cookie_header})
        assert response.status_code == 200
        auth = response.json()["data"]
        assert auth["user"]["id"] == seed["admin_user_id"]
        assert auth["user"]["role"] == "admin"
        assert "config.write" in auth["permissions"]


def test_non_admin_settings_write_remains_forbidden(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    for token in (seed["reader_token"], seed["operator_token"]):
        response = client.post(
            "/api/config/markdown-conversion",
            json={"default_tool": "markitdown"},
            headers={"X-Auth-Token": str(token)},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    storage = Storage(app.state.db_path)
    try:
        registered_user_id = storage.create_user(
            "registered-settings@example.com",
            "not-a-real-password-hash",
            role="registered",
            display_name="Registered Settings User",
        )
    finally:
        storage.close()
    client.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": registered_user_id}),
    )
    registered = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
    )
    assert registered.status_code == 403
    assert registered.json()["detail"] == "Forbidden"


def test_email_session_with_stale_header_still_requires_csrf(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    app.state.enable_csrf = True
    client.cookies.set(
        app.state.fastapi_session_cookie_name,
        _make_session_cookie(app, {"email_user_id": seed["admin_user_id"]}),
    )
    stale_reader_header = {"X-Auth-Token": str(seed["reader_token"])}

    rejected = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers=stale_reader_header,
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "CSRF token missing or invalid"

    csrf_seed = client.get("/api/auth/me", headers=stale_reader_header)
    csrf_token = csrf_seed.cookies.get("csrf_token")
    accepted = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={**stale_reader_header, "X-CSRF-Token": str(csrf_token)},
    )
    assert accepted.status_code == 200, accepted.text


def test_valid_guest_session_with_explicit_admin_token_keeps_token_csrf_exemption(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    app.state.enable_csrf = True
    guest_session = _make_session_cookie(app, {"guest_chat_user_id": "guest:issue249"})

    response = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={
            "Cookie": f"{app.state.fastapi_session_cookie_name}={guest_session}",
            "X-Auth-Token": str(seed["admin_token"]),
        },
    )

    assert response.status_code == 200, response.text


def test_invalid_session_with_explicit_token_is_not_csrf_exempt_or_authenticated(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    app.state.enable_csrf = True
    cookie_name = app.state.fastapi_session_cookie_name
    invalid_cookie_header = f"{cookie_name}=invalid-signed-session"
    admin_header = {"X-Auth-Token": str(seed["admin_token"])}

    rejected = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={**admin_header, "Cookie": invalid_cookie_header},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "CSRF token missing or invalid"

    csrf_seed = client.get(
        "/api/auth/me",
        headers={**admin_header, "Cookie": invalid_cookie_header},
    )
    assert csrf_seed.json()["data"]["authenticated"] is False
    csrf_token = csrf_seed.cookies.get("csrf_token")
    authenticated = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={
            **admin_header,
            "Cookie": f"{invalid_cookie_header}; csrf_token={csrf_token}",
            "X-CSRF-Token": str(csrf_token),
        },
    )
    assert authenticated.status_code == 401
    assert authenticated.json()["detail"] == "Unauthorized"


def test_public_chat_query_creates_and_restores_guest_without_default_auth_header(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, _seed = _build_chat_test_client(tmp_path, monkeypatch)
    client.headers.pop("X-Auth-Token", None)
    client.cookies.clear()

    import ai_actuarial.api.services.chat as chat_service

    resolve_chat_user = chat_service._resolve_chat_user
    _install_guest_chat_fakes(monkeypatch)
    monkeypatch.setattr(chat_service, "_resolve_chat_user", resolve_chat_user)
    first_query = client.post(
        "/api/chat/query",
        json={"message": "capital", "kb_ids": ["chat-kb-b"], "mode": "expert"},
    )
    assert first_query.status_code == 200, first_query.text
    assert first_query.json()["data"]["conversation_id"] == "conv_guest_query"
    cookie_name = app.state.fastapi_session_cookie_name
    first_cookie = client.cookies.get(cookie_name)
    assert first_cookie
    serializer = URLSafeSerializer(
        app.state.fastapi_session_secret,
        salt="fastapi-session",
    )
    first_guest_id = serializer.loads(first_cookie)["guest_chat_user_id"]

    second_query = client.post(
        "/api/chat/query",
        json={"message": "capital again", "kb_ids": ["chat-kb-b"], "mode": "expert"},
    )
    assert second_query.status_code == 200, second_query.text
    restored_cookie = client.cookies.get(cookie_name)
    assert restored_cookie
    assert serializer.loads(restored_cookie)["guest_chat_user_id"] == first_guest_id


def test_markdown_writer_permission_error_returns_safe_json_detail(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    import ai_actuarial.api.services.ops_write as ops_write_service

    def deny_write(_config):
        raise PermissionError("C:/sensitive/config/markdown_conversion.yaml")

    monkeypatch.setattr(ops_write_service, "write_markdown_conversion_config", deny_write)
    response = client.post(
        "/api/config/markdown-conversion",
        json={"default_tool": "markitdown"},
        headers={"X-Auth-Token": str(seed["admin_token"])},
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"error": "Unable to write Markdown conversion configuration"}
    assert "sensitive" not in response.text


def test_login_storage_transitions_remove_stale_auth_material() -> None:
    login_source = LOGIN_TSX.read_text(encoding="utf-8")
    email_handler = login_source.split("async function handleEmailSubmit", 1)[1].split(
        "async function handleTokenSubmit", 1
    )[0]
    assert email_handler.index('setStoredAuthToken("", true)') < email_handler.index(
        'apiPost("/api/auth/login"'
    )

    script = f"""
      const values = new Map();
      class Storage {{
        getItem(key) {{ return values.get(this.prefix + key) ?? null; }}
        setItem(key, value) {{ values.set(this.prefix + key, String(value)); }}
        removeItem(key) {{ values.delete(this.prefix + key); }}
        constructor(prefix) {{ this.prefix = prefix; }}
      }}
      globalThis.window = {{
        sessionStorage: new Storage("session:"),
        localStorage: new Storage("local:"),
      }};
      const apiModule = await import({json.dumps(API_TS.as_uri())});
      const api = apiModule.default ?? apiModule;
      window.sessionStorage.setItem("api_write_auth_token", "stale-session");
      window.localStorage.setItem("api_write_auth_token", "stale-persistent");
      api.setStoredAuthToken("", true);
      const email = {{
        session: window.sessionStorage.getItem("api_write_auth_token"),
        local: window.localStorage.getItem("api_write_auth_token"),
      }};
      window.localStorage.setItem("api_write_auth_token", "older-persistent");
      api.setStoredAuthToken("current-session-token", false);
      const token = {{
        session: window.sessionStorage.getItem("api_write_auth_token"),
        local: window.localStorage.getItem("api_write_auth_token"),
        resolved: api.getStoredAuthToken(),
      }};
      console.log(JSON.stringify({{ email, token }}));
    """

    result = _run_tsx(script)
    assert result == {
        "email": {"session": None, "local": None},
        "token": {"session": "current-session-token", "local": None, "resolved": "current-session-token"},
    }


def test_settings_error_formatter_preserves_status_classification_and_safe_detail() -> None:
    script = f"""
      const apiModule = await import({json.dumps(API_TS.as_uri())});
      const errorsModule = await import({json.dumps(SETTINGS_ERRORS_TS.as_uri())});
      const {{ ApiError }} = apiModule.default ?? apiModule;
      const {{ formatSettingsMutationError }} = errorsModule.default ?? errorsModule;
      const t = (key) => key;
      const result = {{
        permission: formatSettingsMutationError(new ApiError("Forbidden", 403, "Forbidden"), t, "fallback"),
        csrf: formatSettingsMutationError(new ApiError("CSRF token missing or invalid", 403, "CSRF token missing or invalid"), t, "fallback"),
        validation: formatSettingsMutationError(new ApiError("validation", 422, [{{ loc: ["body", "value"], msg: "required" }}]), t, "fallback"),
        write: formatSettingsMutationError(new ApiError("write", 500, "Unable to write configuration"), t, "fallback"),
        providerDelete: formatSettingsMutationError(new ApiError("not found", 404, "Provider not found"), t, "settings.provider_delete_error"),
        tokenRevoke: formatSettingsMutationError(new ApiError("not found", 404, "Token not found"), t, "settings.token_revoke_error"),
        rateLimit: formatSettingsMutationError(new ApiError("limited", 429, "Too many requests"), t, "settings.provider_save_error"),
        other: formatSettingsMutationError(new ApiError("conflict", 409, "Configuration changed"), t, "settings.models_save_error"),
        fallback: formatSettingsMutationError(new Error("network"), t, "fallback"),
      }};
      console.log(JSON.stringify(result));
    """

    result = _run_tsx(script)
    assert result["permission"] == "settings.error_permission: Forbidden"
    assert result["csrf"] == "settings.error_csrf: CSRF token missing or invalid"
    assert result["validation"].startswith("settings.error_validation: ")
    assert '"msg":"required"' in str(result["validation"])
    assert result["write"] == "settings.error_config_write: Unable to write configuration"
    assert result["providerDelete"] == "settings.provider_delete_error: Provider not found"
    assert result["tokenRevoke"] == "settings.token_revoke_error: Token not found"
    assert result["rateLimit"] == "settings.provider_save_error: Too many requests"
    assert result["other"] == "settings.models_save_error: Configuration changed"
    assert result["fallback"] == "fallback"


def test_api_client_and_formatter_surface_safe_markdown_write_detail() -> None:
    script = f"""
      class Storage {{ getItem() {{ return null; }} setItem() {{}} removeItem() {{}} }}
      globalThis.window = {{ sessionStorage: new Storage(), localStorage: new Storage() }};
      globalThis.fetch = async () => ({{
        ok: false,
        status: 500,
        json: async () => ({{ error: "Unable to write Markdown conversion configuration" }}),
      }});
      const apiModule = await import({json.dumps(API_TS.as_uri())});
      const errorsModule = await import({json.dumps(SETTINGS_ERRORS_TS.as_uri())});
      const api = apiModule.default ?? apiModule;
      const errors = errorsModule.default ?? errorsModule;
      try {{
        await api.apiPost("/api/config/markdown-conversion", {{ default_tool: "markitdown" }});
      }} catch (error) {{
        console.log(JSON.stringify({{
          status: error.status,
          detail: error.detail,
          formatted: errors.formatSettingsMutationError(error, (key) => key, "settings.markdown_save_error"),
        }}));
      }}
    """

    assert _run_tsx(script) == {
        "status": 500,
        "detail": "Unable to write Markdown conversion configuration",
        "formatted": (
            "settings.error_config_write: Unable to write Markdown conversion configuration"
        ),
    }


def test_api_client_retains_settings_failure_status_and_detail() -> None:
    script = f"""
      class Storage {{ getItem() {{ return null; }} setItem() {{}} removeItem() {{}} }}
      globalThis.window = {{ sessionStorage: new Storage(), localStorage: new Storage() }};
      globalThis.fetch = async () => ({{
        ok: false,
        status: 403,
        json: async () => ({{ detail: "CSRF token missing or invalid" }}),
      }});
      const apiModule = await import({json.dumps(API_TS.as_uri())});
      const api = apiModule.default ?? apiModule;
      try {{
        await api.apiPost("/api/config/markdown-conversion", {{ default_tool: "markitdown" }});
      }} catch (error) {{
        console.log(JSON.stringify({{
          name: error.name,
          status: error.status,
          detail: error.detail,
          message: error.message,
        }}));
      }}
    """

    assert _run_tsx(script) == {
        "name": "ApiError",
        "status": 403,
        "detail": "CSRF token missing or invalid",
        "message": "CSRF token missing or invalid",
    }


def test_all_admin_settings_mutations_use_precise_error_formatter() -> None:
    settings_source = SETTINGS_TSX.read_text(encoding="utf-8")
    markdown_source = MARKDOWN_TAB_TSX.read_text(encoding="utf-8")

    for marker in (
        'apiPost("/api/config/provider-credentials",',
        "apiDelete(`/api/config/provider-credentials/${providerId}?category=llm`)",
        'apiPost<{ imported_count?: number; skipped_count?: number }>("/api/config/provider-credentials/import-env"',
        'apiPost<{ rotated_count?: number; failed_count?: number }>("/api/config/provider-credentials/re-encrypt"',
        'apiPost<{ rebuild_required?: boolean; affected_kb_count?: number; affected_kb_ids?: string[]; embedding_fingerprint?: string }>("/api/config/ai-routing"',
        'apiPost("/api/config/ai-models", payload)',
        'apiPost("/api/config/backend-settings", { defaults: editDefaults })',
        'apiPost("/api/config/provider-credentials", {\n        provider_id: providerName',
        "apiDelete(`/api/config/provider-credentials/${providerId}?category=search`)",
        'apiPost("/api/config/categories",',
        'apiPost("/api/config/backend-settings", { features:',
        'apiPost<{ token?: string; success?: boolean }>("/api/auth/tokens"',
        "apiPost(`/api/auth/tokens/${tokenId}/revoke`, {})",
    ):
        _assert_mutation_uses_settings_error_formatter(settings_source, marker)

    _assert_mutation_uses_settings_error_formatter(
        markdown_source,
        'apiPost<MarkdownConversionOptions>("/api/config/markdown-conversion", config)',
    )
