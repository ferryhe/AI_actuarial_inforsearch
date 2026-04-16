from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request

from ai_actuarial.storage import Storage
from ai_actuarial.web.app import (
    _PERMISSIONS,
    _PUBLIC_PERMISSIONS_WHEN_AUTH_DISABLED,
    _hash_token,
    _permissions_for_group,
)


_ANONYMOUS_PERMISSIONS: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "catalog.read",
        "markdown.read",
        "chat.view",
        "chat.query",
        "chat.conversations",
    }
)


@dataclass(slots=True)
class AuthContext:
    token: dict[str, Any] | None
    permissions: frozenset[str]


def _extract_presented_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "") or ""
    parts = auth.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    token = request.headers.get("X-API-Token")
    return token.strip() if token else None


def _decode_flask_session(request: Request) -> dict[str, Any]:
    legacy_app = getattr(request.app.state, "legacy_flask_app", None)
    if legacy_app is None:
        return {}

    cookie_name = legacy_app.config.get("SESSION_COOKIE_NAME", "session")
    cookie_value = request.cookies.get(cookie_name)
    if not cookie_value:
        return {}

    serializer = legacy_app.session_interface.get_signing_serializer(legacy_app)
    if serializer is None:
        return {}

    try:
        data = serializer.loads(cookie_value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _validate_token_record(token: dict[str, Any] | None) -> dict[str, Any] | None:
    if not token:
        return None
    if not token.get("is_active"):
        return None

    expires_at = token.get("expires_at")
    if not expires_at:
        return token

    try:
        dt = datetime.fromisoformat(str(expires_at))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    except Exception:
        return None

    return token if dt > now else None


def _load_auth_context(request: Request) -> AuthContext:
    cached = getattr(request.state, "auth_context", None)
    if cached is not None:
        return cached

    db_path = getattr(request.app.state, "db_path", "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")

    token: dict[str, Any] | None = None
    storage = Storage(db_path)
    try:
        session_data = _decode_flask_session(request)

        email_user_id = session_data.get("email_user_id")
        if email_user_id is not None:
            try:
                user = storage.get_user_by_id(int(email_user_id))
            except Exception:
                user = None

            if user and user.get("is_active"):
                user.pop("password_hash", None)
                token = {
                    "id": None,
                    "subject": user["email"],
                    "group_name": user["role"],
                    "is_active": True,
                    "_email_user_id": user["id"],
                    "_email_user": user,
                }

        if not token:
            token_id = session_data.get("auth_token_id")
            if token_id is not None:
                try:
                    token = storage.get_auth_token_by_id(int(token_id))
                except Exception:
                    token = None

        if not token:
            presented = _extract_presented_token(request)
            if presented:
                token = storage.get_auth_token_by_hash(_hash_token(presented))
    finally:
        storage.close()

    token = _validate_token_record(token)
    permissions = _permissions_for_group((token or {}).get("group_name", ""))
    context = AuthContext(token=token, permissions=permissions)
    request.state.auth_context = context
    return context


def get_auth_context(request: Request) -> AuthContext:
    return _load_auth_context(request)


def public_permissions_for_request(request: Request) -> frozenset[str]:
    require_auth = bool(getattr(request.app.state, "require_auth", False))
    return _ANONYMOUS_PERMISSIONS if require_auth else _PUBLIC_PERMISSIONS_WHEN_AUTH_DISABLED


def require_permissions(*required: str):
    for permission in required:
        if permission not in _PERMISSIONS:
            raise ValueError(f"Unknown permission: {permission}")

    def dependency(request: Request) -> AuthContext:
        public_permissions = public_permissions_for_request(request)
        if all(permission in public_permissions for permission in required):
            return AuthContext(token=None, permissions=frozenset())

        context = _load_auth_context(request)
        if not context.token:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if any(permission not in context.permissions for permission in required):
            raise HTTPException(status_code=403, detail="Forbidden")

        return context

    return dependency
