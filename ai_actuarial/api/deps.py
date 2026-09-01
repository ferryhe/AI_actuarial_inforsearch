from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.requests import cookie_parser

from ai_actuarial.shared_auth import (
    PERMISSIONS,
    PUBLIC_BROWSE_PERMISSIONS,
    hash_token,
    permissions_for_group,
)
from ai_actuarial.storage import Storage


@dataclass(slots=True)
class AuthContext:
    token: dict[str, Any] | None
    permissions: frozenset[str]


def _extract_presented_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "") or ""
    parts = auth.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    token = request.headers.get("X-API-Token") or request.headers.get("X-Auth-Token")
    return token.strip() if token else None


def _has_presented_auth_material(request: Request) -> bool:
    if _extract_presented_token(request):
        return True
    return bool(_session_cookie_values(request))


def _session_cookie_values(request: Request) -> list[str]:
    cookie_name = str(
        getattr(request.app.state, "fastapi_session_cookie_name", "session") or "session"
    )
    values: list[str] = []
    for header in request.headers.getlist("cookie"):
        for chunk in header.split(";"):
            parsed = cookie_parser(chunk)
            if cookie_name in parsed:
                values.append(parsed[cookie_name])
    return values


def _decode_signed_session(request: Request, cookie_value: str) -> dict[str, Any] | None:
    if not cookie_value:
        return None
    secret = str(getattr(request.app.state, "fastapi_session_secret", "") or "")
    if not secret:
        return None
    serializer = URLSafeSerializer(secret, salt="fastapi-session")
    try:
        data = serializer.loads(cookie_value)
    except BadSignature:
        return None
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _decode_request_sessions(request: Request) -> tuple[list[str], list[dict[str, Any]]]:
    cookie_values = _session_cookie_values(request)
    session_payloads = [
        payload
        for cookie_value in cookie_values
        if (payload := _decode_signed_session(request, cookie_value)) is not None
    ]
    return cookie_values, session_payloads


def _session_allows_explicit_token(request: Request) -> bool:
    cookie_values, session_payloads = _decode_request_sessions(request)
    session_has_auth_identity = any(
        "email_user_id" in payload or "auth_token_id" in payload for payload in session_payloads
    )
    return not cookie_values or (
        len(session_payloads) == len(cookie_values) and not session_has_auth_identity
    )


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
        _cookie_values, session_payloads = _decode_request_sessions(request)

        active_email_users: dict[int, dict[str, Any]] = {}
        for session_data in session_payloads:
            email_user_id = session_data.get("email_user_id")
            if email_user_id is None:
                continue
            try:
                user = storage.get_user_by_id(int(email_user_id))
            except Exception:
                user = None

            if user and user.get("is_active"):
                active_email_users[int(user["id"])] = user

        active_session_tokens: dict[int, dict[str, Any]] = {}
        for session_data in session_payloads:
            token_id = session_data.get("auth_token_id")
            if token_id is None:
                continue
            try:
                session_token = storage.get_auth_token_by_id(int(token_id))
            except Exception:
                session_token = None
            session_token = _validate_token_record(session_token)
            if session_token:
                active_session_tokens[int(session_token["id"])] = session_token

        ambiguous_email_identity = len(active_email_users) > 1
        ambiguous_token_identity = len(active_session_tokens) > 1
        email_user: dict[str, Any] | None = None
        if len(active_email_users) == 1:
            email_user = next(iter(active_email_users.values()))
        email_can_write_config = bool(
            email_user and "config.write" in permissions_for_group(str(email_user["role"]))
        )
        ambiguous_cross_mode_identity = bool(
            email_user and active_session_tokens and not email_can_write_config
        )

        # A valid admin email session remains authoritative over an older
        # token-mode session. A non-admin email identity cannot silently replace
        # a concurrently active token identity, so that combination fails closed.
        if email_user and not ambiguous_cross_mode_identity:
            email_user.pop("password_hash", None)
            token = {
                "id": None,
                "subject": email_user["email"],
                "group_name": email_user["role"],
                "is_active": True,
                "_email_user_id": email_user["id"],
                "_email_user": email_user,
            }
        elif (
            not ambiguous_email_identity
            and not ambiguous_cross_mode_identity
            and len(active_session_tokens) == 1
        ):
            token = next(iter(active_session_tokens.values()))

        # A missing cookie, or a fully valid non-auth session (for example a
        # guest-chat session), may still use explicit token auth. Invalid signed
        # material and unresolved session identities fail closed.
        if (
            not token
            and not ambiguous_email_identity
            and not ambiguous_token_identity
            and not ambiguous_cross_mode_identity
            and _session_allows_explicit_token(request)
        ):
            presented = _extract_presented_token(request)
            if presented:
                token = storage.get_auth_token_by_hash(hash_token(presented))
    finally:
        storage.close()

    token = _validate_token_record(token)
    permissions = permissions_for_group((token or {}).get("group_name", ""))
    context = AuthContext(token=token, permissions=permissions)
    request.state.auth_context = context
    return context


def get_auth_context(request: Request) -> AuthContext:
    return _load_auth_context(request)


def public_permissions_for_request(request: Request) -> frozenset[str]:
    return PUBLIC_BROWSE_PERMISSIONS


def _validate_required_permissions(required: tuple[str, ...]) -> None:
    for permission in required:
        if permission not in PERMISSIONS:
            raise ValueError(f"Unknown permission: {permission}")


def _assert_context_has_permissions(context: AuthContext, required: tuple[str, ...]) -> None:
    if not context.token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if any(permission not in context.permissions for permission in required):
        raise HTTPException(status_code=403, detail="Forbidden")


def require_permissions(*required: str):
    _validate_required_permissions(required)

    def dependency(request: Request) -> AuthContext:
        public_permissions = public_permissions_for_request(request)
        if all(permission in public_permissions for permission in required):
            if _has_presented_auth_material(request):
                context = _load_auth_context(request)
                if context.token:
                    return context
            return AuthContext(token=None, permissions=frozenset())

        context = _load_auth_context(request)
        _assert_context_has_permissions(context, required)
        return context

    return dependency


def require_authenticated_permissions(*required: str):
    _validate_required_permissions(required)

    def dependency(request: Request) -> AuthContext:
        if not _has_presented_auth_material(request):
            raise HTTPException(status_code=401, detail="Unauthorized")

        context = _load_auth_context(request)
        _assert_context_has_permissions(context, required)
        return context

    return dependency
