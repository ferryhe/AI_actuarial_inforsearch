from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ai_actuarial.shared_auth import AI_CHAT_QUOTA, GROUP_PERMISSIONS
from ai_actuarial.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_fastapi_auth_endpoints import _build_test_client


def test_assignable_role_schema_matches_every_successful_email_role_write(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['admin_token']}"}

    response = client.get("/api/admin/roles", headers=headers)
    assert response.status_code == 200, response.text
    roles = response.json()["roles"]
    assert [role["value"] for role in roles] == [
        "registered",
        "premium",
        "operator",
        "admin",
    ]
    assert all(
        set(role) == {"value", "name_key", "description_key", "legacy"}
        and role["name_key"] == f"users.role_{role['value']}"
        and role["description_key"] == f"users.role_{role['value']}_description"
        and role["legacy"] is False
        for role in roles
    )

    storage = Storage(str(app.state.db_path))
    try:
        user_ids = [
            storage.create_user(f"role-{role['value']}@example.com", "hash") for role in roles
        ]
    finally:
        storage.close()

    for role, user_id in zip(roles, user_ids, strict=True):
        write = client.post(
            f"/api/admin/users/{user_id}/role",
            json={"role": role["value"]},
            headers=headers,
        )
        assert write.status_code == 200, (role, write.text)

    for forbidden in ("guest", "operator_ai"):
        rejected = client.post(
            f"/api/admin/users/{seed['user_id']}/role",
            json={"role": forbidden},
            headers=headers,
        )
        assert rejected.status_code == 400, rejected.text


def test_legacy_operator_alias_migrates_through_atomic_role_audit(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['admin_token']}"}
    storage = Storage(str(app.state.db_path))
    try:
        legacy_id = storage.create_user("legacy@example.com", "hash", role="operator_ai")
    finally:
        storage.close()

    listed = client.get("/api/admin/users", headers=headers)
    legacy = next(user for user in listed.json()["users"] if user["id"] == legacy_id)
    assert legacy["role"] == "operator_ai"
    assert legacy["canonical_role"] == "operator"

    migrated = client.post(
        f"/api/admin/users/{legacy_id}/role",
        json={"role": legacy["canonical_role"]},
        headers=headers,
    )
    assert migrated.status_code == 200, migrated.text

    storage = Storage(str(app.state.db_path))
    try:
        assert storage.get_user_by_id(legacy_id)["role"] == "operator"
        operator_id = storage._conn.execute(
            "SELECT id FROM auth_tokens WHERE subject = 'admin@example.com'"
        ).fetchone()[0]
        detail = storage._conn.execute(
            "SELECT detail FROM audit_events WHERE event_type = 'admin_set_role' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert json.loads(detail) == {
            "new_role": "operator",
            "old_role": "operator_ai",
            "operation": "admin_set_role",
            "operator": {"id": operator_id, "kind": "token"},
            "reason": None,
            "result": "success",
            "target_user_id": legacy_id,
        }
    finally:
        storage.close()


def test_role_permissions_copy_and_frontend_menu_contract_are_bilingual() -> None:
    assert GROUP_PERMISSIONS["registered"] == GROUP_PERMISSIONS["premium"]
    assert AI_CHAT_QUOTA["registered"] < AI_CHAT_QUOTA["premium"]

    users = (ROOT / "client/src/pages/Users.tsx").read_text(encoding="utf-8")
    profile = (ROOT / "client/src/pages/Profile.tsx").read_text(encoding="utf-8")
    translations = (ROOT / "client/src/hooks/use-i18n.ts").read_text(encoding="utf-8")
    settings = (ROOT / "client/src/pages/Settings.tsx").read_text(encoding="utf-8")

    assert 'apiGet<AssignableRolesResponse>("/api/admin/roles")' in users
    assert 'const roleOptions = ["admin"' not in users
    assert "role.description_key" in users
    assert 'resolveEnumLabel("role", role, t)' in users
    assert 'import { EnumDiagnostic, resolveEnumLabel } from "@/lib/enum-display"' in users
    assert 't("users.role_operator_ai_legacy")' in profile
    for text in (
        '"users.role_operator_ai_legacy": "Operator (legacy alias)"',
        '"users.role_operator_ai_legacy": "Operator（旧版别名）"',
        '"users.role_registered_description": "Same permissions as Premium; 20 AI chats per day."',
        '"users.role_premium_description": "Same permissions as Registered; 50 AI chats per day."',
        '"users.role_registered_description": "权限与 Premium 相同；每日 20 次 AI 对话。"',
        '"users.role_premium_description": "权限与 Registered 相同；每日 50 次 AI 对话。"',
    ):
        assert text in translations

    assert '<option value="reader">Reader</option>' not in settings
    assert (
        '(["registered", "premium", "operator", "admin"] as const).map((role) => <option key={role} value={role}>{resolveEnumLabel("role", role, t)}</option>)'
        in settings
    )


@pytest.mark.parametrize("path", ["/api/admin/roles"])
def test_role_schema_is_in_native_endpoint_inventory(
    tmp_path: Path, monkeypatch, path: str
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    response = client.get("/api/migration/status")
    assert response.status_code == 200, response.text
    assert path in response.json()["native_paths"]
