from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_actuarial.api.deps import AuthContext
from ai_actuarial.api.services.auth import (
    AuthApiError,
    list_users,
    set_user_active,
    set_user_role,
)
from ai_actuarial.storage import Storage


def _create_user(storage: Storage, email: str, *, role: str = "admin") -> int:
    return storage.create_user(email, "not-a-real-password-hash", role=role)


def _request(db_path: Path, **query_params: str) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_path=str(db_path))),
        query_params=query_params,
    )


def _email_admin(user_id: int) -> AuthContext:
    return AuthContext(
        token={"id": None, "group_name": "admin", "_email_user_id": user_id},
        permissions=frozenset({"users.manage"}),
    )


def _credential_admin() -> AuthContext:
    return AuthContext(
        token={"id": 73, "group_name": "admin"},
        permissions=frozenset({"users.manage"}),
    )


def _audit_event(storage: Storage) -> dict[str, object]:
    entry = storage._conn.execute(
        "SELECT detail FROM audit_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return json.loads(str(entry[0]))


def test_single_active_email_admin_cannot_be_disabled_by_credential_principal(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "users.db"
    storage = Storage(str(db_path))
    try:
        admin_id = _create_user(storage, "only@example.com")
    finally:
        storage.close()

    with pytest.raises(AuthApiError) as exc_info:
        set_user_active(
            request=_request(db_path), auth=_credential_admin(), user_id=admin_id, is_active=False
        )
    assert exc_info.value.status_code == 409

    storage = Storage(str(db_path))
    try:
        assert storage.get_user_by_id(admin_id)["is_active"] == 1
        assert _audit_event(storage) == {
            "operation": "admin_set_active",
            "operator": {"id": 73, "kind": "token"},
            "reason": "last_active_email_admin",
            "result": "blocked",
            "target_user_id": admin_id,
        }
    finally:
        storage.close()


def test_email_session_admin_cannot_demote_or_disable_self_with_two_admins(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    storage = Storage(str(db_path))
    try:
        first_admin_id = _create_user(storage, "first@example.com")
        _create_user(storage, "second@example.com")
    finally:
        storage.close()

    for action in (
        lambda: set_user_role(
            request=_request(db_path),
            auth=_email_admin(first_admin_id),
            user_id=first_admin_id,
            payload={"role": "registered"},
        ),
        lambda: set_user_active(
            request=_request(db_path),
            auth=_email_admin(first_admin_id),
            user_id=first_admin_id,
            is_active=False,
        ),
    ):
        with pytest.raises(AuthApiError) as exc_info:
            action()
        assert exc_info.value.status_code == 409

    storage = Storage(str(db_path))
    try:
        assert storage.get_user_by_id(first_admin_id)["role"] == "admin"
        entries = storage._conn.execute(
            "SELECT detail FROM audit_events ORDER BY id DESC LIMIT 2"
        ).fetchall()
        assert {json.loads(entry[0])["reason"] for entry in entries} == {"self_protection"}
    finally:
        storage.close()


def test_two_admins_allow_one_demotion_and_records_success(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    storage = Storage(str(db_path))
    try:
        first_admin_id = _create_user(storage, "first@example.com")
        second_admin_id = _create_user(storage, "second@example.com")
    finally:
        storage.close()

    result = set_user_role(
        request=_request(db_path),
        auth=_email_admin(first_admin_id),
        user_id=second_admin_id,
        payload={"role": "registered"},
    )
    assert result["success"] is True

    storage = Storage(str(db_path))
    try:
        assert storage.get_user_by_id(second_admin_id)["role"] == "registered"
        assert _audit_event(storage) == {
            "operation": "admin_set_role",
            "operator": {"id": first_admin_id, "kind": "email"},
            "reason": None,
            "result": "success",
            "target_user_id": second_admin_id,
        }
    finally:
        storage.close()


def test_inactive_admin_is_not_counted_as_a_recovery_principal(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    storage = Storage(str(db_path))
    try:
        active_admin_id = _create_user(storage, "active@example.com")
        inactive_admin_id = _create_user(storage, "inactive@example.com")
        storage.update_user_active(inactive_admin_id, False)
    finally:
        storage.close()

    with pytest.raises(AuthApiError) as exc_info:
        set_user_role(
            request=_request(db_path),
            auth=_credential_admin(),
            user_id=active_admin_id,
            payload={"role": "registered"},
        )
    assert exc_info.value.status_code == 409

    result = set_user_role(
        request=_request(db_path),
        auth=_credential_admin(),
        user_id=inactive_admin_id,
        payload={"role": "registered"},
    )
    assert result["success"] is True


def test_concurrent_demotions_leave_one_active_email_admin(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    initializer = Storage(str(db_path))
    try:
        first_admin_id = _create_user(initializer, "first@example.com")
        second_admin_id = _create_user(initializer, "second@example.com")
    finally:
        initializer.close()

    barrier = threading.Barrier(2)
    outcomes: list[dict[str, str]] = []

    def demote(user_id: int) -> None:
        storage = Storage(str(db_path))
        barrier.wait()
        try:
            outcomes.append(
                storage.update_user_with_admin_protection(
                    user_id,
                    role="registered",
                    operator_kind="token",
                    operator_id=73,
                    operation="admin_set_role",
                )
            )
        finally:
            storage.close()

    threads = [
        threading.Thread(target=demote, args=(first_admin_id,)),
        threading.Thread(target=demote, args=(second_admin_id,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcome["result"] for outcome in outcomes) == ["blocked", "success"]

    storage = Storage(str(db_path))
    try:
        count = storage._conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()[0]
        assert count == 1
    finally:
        storage.close()


def test_list_users_reports_global_active_admin_count_beyond_page(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    storage = Storage(str(db_path))
    try:
        _create_user(storage, "first-admin@example.com")
        _create_user(storage, "second-admin@example.com")
        for index in range(51):
            _create_user(storage, f"member-{index:02d}@example.com", role="registered")
    finally:
        storage.close()

    response = list_users(request=_request(db_path, page="1", per_page="1"))

    assert len(response["users"]) == 1
    assert response["total"] == 53
    assert response["active_admin_count"] == 2


def test_list_users_refreshes_active_admin_count_after_role_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    storage = Storage(str(db_path))
    try:
        _create_user(storage, "admin@example.com")
        member_id = _create_user(storage, "member@example.com", role="registered")
    finally:
        storage.close()

    assert list_users(request=_request(db_path))["active_admin_count"] == 1

    promoted = set_user_role(
        request=_request(db_path),
        auth=_credential_admin(),
        user_id=member_id,
        payload={"role": "admin"},
    )
    assert promoted["success"] is True
    assert list_users(request=_request(db_path))["active_admin_count"] == 2

    demoted = set_user_role(
        request=_request(db_path),
        auth=_credential_admin(),
        user_id=member_id,
        payload={"role": "registered"},
    )
    assert demoted["success"] is True
    assert list_users(request=_request(db_path))["active_admin_count"] == 1
