from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Request, Response
from itsdangerous import URLSafeSerializer

from ai_actuarial.config import settings
from ai_actuarial.shared_auth import (
    AI_CHAT_QUOTA,
    DUMMY_PASSWORD_HASH,
    VALID_USER_ROLES,
    check_password,
    hash_password,
    hash_token,
)
from ai_actuarial.storage import Storage

from ..deps import AuthContext, get_auth_context, public_permissions_for_request


def ensure_session_mutation_available(request: Request) -> None:
    secret = str(getattr(request.app.state, "fastapi_session_secret", "") or "")
    if secret:
        return
    raise AuthApiError("FastAPI session secret is not configured", status_code=503)


@dataclass(slots=True)
class SessionMutation:
    data: dict[str, Any] | None = None
    clear: bool = False


class AuthApiError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, detail: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = {"error": message}
        if detail:
            self.payload["detail"] = detail


_VALID_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise AuthApiError("Database path is unavailable", status_code=500)
    return db_path


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _client_ip(request: Request) -> str:
    trust_proxy = settings.TRUST_PROXY
    if trust_proxy:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    client = request.client.host if request.client else None
    return client or "unknown"


def _session_cookie_name(request: Request) -> str:
    return str(getattr(request.app.state, "fastapi_session_cookie_name", "session") or "session")


def _apply_session_mutation(response: Response, request: Request, mutation: SessionMutation | None) -> None:
    if mutation is None:
        return

    cookie_name = _session_cookie_name(request)
    if mutation.clear:
        response.delete_cookie(
            cookie_name,
            path=str(getattr(request.app.state, "fastapi_session_cookie_path", "/") or "/"),
            domain=getattr(request.app.state, "fastapi_session_cookie_domain", None) or None,
        )
        return

    secret = str(getattr(request.app.state, "fastapi_session_secret", "") or "")
    if not secret:
        return
    serializer = URLSafeSerializer(secret, salt="fastapi-session")
    response.set_cookie(
        key=cookie_name,
        value=serializer.dumps(mutation.data or {}),
        path=str(getattr(request.app.state, "fastapi_session_cookie_path", "/") or "/"),
        domain=getattr(request.app.state, "fastapi_session_cookie_domain", None) or None,
        secure=bool(getattr(request.app.state, "fastapi_session_cookie_secure", False)),
        httponly=bool(getattr(request.app.state, "fastapi_session_cookie_httponly", True)),
        samesite=getattr(request.app.state, "fastapi_session_cookie_samesite", "Lax") or "Lax",
    )


def _serialize_auth_user(token: dict[str, Any] | None) -> dict[str, Any] | None:
    if not token:
        return None
    email_user = token.get("_email_user") if isinstance(token, dict) else None
    if isinstance(email_user, dict):
        return {
            "id": email_user.get("id"),
            "email": email_user.get("email"),
            "display_name": email_user.get("display_name") or "",
            "role": email_user.get("role") or "registered",
            "is_active": bool(email_user.get("is_active", True)),
        }
    return {
        "id": None,
        "email": None,
        "display_name": token.get("subject") or "",
        "role": (token.get("group_name") or "reader").lower(),
        "is_active": True,
    }


def auth_me(*, request: Request) -> dict[str, Any]:
    context = get_auth_context(request)
    authenticated = bool(context.token)
    permissions = sorted(context.permissions if authenticated else public_permissions_for_request(request))
    return {
        "success": True,
        "data": {
            "require_auth": bool(getattr(request.app.state, "require_auth", False)),
            "authenticated": authenticated,
            "user": _serialize_auth_user(context.token),
            "token": (
                {
                    "id": context.token.get("id"),
                    "subject": context.token.get("subject"),
                    "group_name": context.token.get("group_name"),
                }
                if authenticated and isinstance(context.token, dict)
                else None
            ),
            "permissions": permissions,
        },
    }


def register_user(*, request: Request, payload: dict[str, Any]) -> tuple[dict[str, Any], SessionMutation]:
    if not isinstance(payload, dict):
        raise AuthApiError("Request body must be a JSON object", status_code=400)
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    display_name = str(payload.get("display_name") or "").strip()

    if not email or not _VALID_EMAIL_RE.match(email):
        raise AuthApiError("Valid email required", status_code=400)
    if len(password) < 8:
        raise AuthApiError("Password must be at least 8 characters", status_code=400)
    if len(password) > 1024:
        raise AuthApiError("Password too long (max 1024 characters)", status_code=400)
    if len(display_name) > 100:
        raise AuthApiError("Display name too long (max 100 characters)", status_code=400)

    storage = Storage(_db_path(request))
    try:
        user_id = storage.create_user(
            email=email,
            password_hash=hash_password(password),
            role="registered",
            display_name=display_name or None,
        )
        storage.log_user_activity("register", user_id=user_id, ip_address=_client_ip(request), detail=f"email={email}")
    except ValueError as exc:
        raise AuthApiError(str(exc), status_code=409) from exc
    finally:
        storage.close()

    return (
        {
            "success": True,
            "user": {
                "id": user_id,
                "email": email,
                "display_name": display_name,
                "role": "registered",
                "is_active": True,
            },
        },
        SessionMutation(data={"email_user_id": user_id}),
    )


def login_user(*, request: Request, payload: dict[str, Any]) -> tuple[dict[str, Any], SessionMutation]:
    if not isinstance(payload, dict):
        raise AuthApiError("Request body must be a JSON object", status_code=400)

    token_text = str(payload.get("token") or "").strip()
    if token_text:
        storage = Storage(_db_path(request))
        try:
            token = storage.get_auth_token_by_hash(hash_token(token_text))
            if not token or not token.get("is_active"):
                raise AuthApiError("Invalid token", status_code=401)
            expires_at = token.get("expires_at")
            if expires_at:
                try:
                    dt = datetime.fromisoformat(str(expires_at))
                    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                    if dt <= now:
                        raise AuthApiError("Invalid token", status_code=401)
                except ValueError as exc:
                    raise AuthApiError("Invalid token", status_code=401) from exc
            try:
                storage.touch_auth_token_last_used(int(token["id"]))
            except Exception:
                pass
        finally:
            storage.close()

        user = {
            "id": None,
            "email": None,
            "display_name": token.get("subject") or "",
            "role": (token.get("group_name") or "reader").lower(),
            "is_active": True,
        }
        return {"success": True, "user": user}, SessionMutation(
            data={
                "auth_token_id": int(token["id"]),
                "auth_group_name": token.get("group_name"),
            }
        )

    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    if not email or not password:
        raise AuthApiError("Email and password required", status_code=400)

    storage = Storage(_db_path(request))
    try:
        user = storage.get_user_by_email(email)
        password_ok = check_password(password, user["password_hash"] if user else DUMMY_PASSWORD_HASH)
        if not user or not password_ok:
            raise AuthApiError("Invalid email or password", status_code=401)
        if not user.get("is_active"):
            raise AuthApiError("Account disabled", status_code=403)
        storage.update_user_last_login(int(user["id"]))
        storage.log_user_activity("login", user_id=int(user["id"]), ip_address=_client_ip(request))
    finally:
        storage.close()

    return (
        {
            "success": True,
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "display_name": user.get("display_name") or "",
                "role": user.get("role") or "registered",
                "is_active": bool(user.get("is_active", True)),
            },
        },
        SessionMutation(data={"email_user_id": int(user["id"])}),
    )


def logout_user() -> tuple[dict[str, Any], SessionMutation]:
    return {"success": True}, SessionMutation(clear=True)


def user_me(*, request: Request, auth: AuthContext) -> dict[str, Any]:
    if not auth.token:
        raise AuthApiError("Not authenticated", status_code=401)

    email_user = auth.token.get("_email_user")
    storage = Storage(_db_path(request))
    try:
        today = _now_date()
        if isinstance(email_user, dict):
            used = storage.get_ai_chat_quota_used(today, user_id=int(email_user["id"]))
            role = str(email_user.get("role") or "registered")
            limit = AI_CHAT_QUOTA.get(role, 5)
            recent_activity = storage.list_user_activity(user_id=int(email_user["id"]), limit=20)
            return {
                "success": True,
                "user": {
                    "id": email_user.get("id"),
                    "email": email_user.get("email"),
                    "display_name": email_user.get("display_name") or "",
                    "role": role,
                    "is_active": bool(email_user.get("is_active", True)),
                    "created_at": email_user.get("created_at"),
                    "last_login_at": email_user.get("last_login_at"),
                },
                "quota": {
                    "used": used,
                    "limit": limit,
                    "remaining": max(0, limit - used),
                    "date": today,
                },
                "recent_activity": recent_activity,
            }

        role = str(auth.token.get("group_name") or "reader").lower()
        limit = AI_CHAT_QUOTA.get(role, 5)
        used = storage.get_ai_chat_quota_used(today, ip_address=_client_ip(request))
        return {
            "success": True,
            "user": {
                "id": None,
                "email": None,
                "display_name": auth.token.get("subject") or "",
                "role": role,
                "is_active": True,
                "created_at": None,
                "last_login_at": None,
            },
            "quota": {
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used),
                "date": today,
            },
            "recent_activity": [],
        }
    finally:
        storage.close()


def update_profile(*, request: Request, auth: AuthContext, payload: dict[str, Any]) -> dict[str, Any]:
    if not auth.token:
        raise AuthApiError("Not authenticated", status_code=401)
    email_user = auth.token.get("_email_user")
    if not isinstance(email_user, dict):
        raise AuthApiError("Profile updates require an email account", status_code=403)
    if not isinstance(payload, dict):
        raise AuthApiError("Request body must be a JSON object", status_code=400)

    display_name = payload.get("display_name")
    new_password = payload.get("new_password")
    current_password = payload.get("current_password")
    if display_name is not None and not isinstance(display_name, str):
        raise AuthApiError("display_name must be a string", status_code=400)
    if new_password is not None and not isinstance(new_password, str):
        raise AuthApiError("new_password must be a string", status_code=400)
    if current_password is not None and not isinstance(current_password, str):
        raise AuthApiError("current_password must be a string", status_code=400)
    if isinstance(display_name, str) and len(display_name) > 100:
        raise AuthApiError("Display name too long (max 100 characters)", status_code=400)

    password_hash = None
    storage = Storage(_db_path(request))
    try:
        if new_password is not None:
            if not current_password:
                raise AuthApiError("current_password is required to change password", status_code=400)
            user_with_hash = storage.get_user_by_id(int(email_user["id"]))
            if not user_with_hash:
                raise AuthApiError("User not found", status_code=404)
            if not check_password(current_password, user_with_hash.get("password_hash", "")):
                raise AuthApiError("Current password is incorrect", status_code=400)
            if len(new_password) < 8:
                raise AuthApiError("New password must be at least 8 characters", status_code=400)
            if len(new_password) > 1024:
                raise AuthApiError("New password is too long (max 1024 characters)", status_code=400)
            password_hash = hash_password(new_password)

        if display_name is None and password_hash is None:
            raise AuthApiError("No fields to update. Provide display_name or new_password.", status_code=400)

        ok = storage.update_user_profile(int(email_user["id"]), display_name=display_name, password_hash=password_hash)
        if not ok:
            raise AuthApiError("User not found", status_code=404)

        detail_parts: list[str] = []
        if display_name is not None:
            detail_parts.append("display_name updated")
        if password_hash is not None:
            detail_parts.append("password changed")
        storage.log_user_activity(
            "profile_updated",
            user_id=int(email_user["id"]),
            ip_address=_client_ip(request),
            detail=", ".join(detail_parts),
        )
        return {"success": True, "updated": detail_parts}
    finally:
        storage.close()


def list_auth_tokens(*, request: Request) -> dict[str, Any]:
    storage = Storage(_db_path(request))
    try:
        return {"success": True, "tokens": storage.list_auth_tokens()}
    finally:
        storage.close()


def create_auth_token(*, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AuthApiError("Invalid JSON body", status_code=400)
    subject = str(payload.get("subject") or "").strip()
    group_name = str(payload.get("group_name") or "").strip().lower()
    if not subject:
        raise AuthApiError("subject required", status_code=400)
    valid_groups = {"registered", "premium", "reader", "operator", "operator_ai", "admin"}
    if group_name not in valid_groups:
        raise AuthApiError("invalid group_name", status_code=400)

    plaintext = secrets.token_urlsafe(32)
    storage = Storage(_db_path(request))
    try:
        token_id = storage.create_auth_token(subject=subject, group_name=group_name, token_hash=hash_token(plaintext))
        return {
            "success": True,
            "token": {
                "id": token_id,
                "subject": subject,
                "group_name": group_name,
                "token": plaintext,
            },
        }
    finally:
        storage.close()


def revoke_auth_token(*, request: Request, token_id: int) -> dict[str, Any]:
    storage = Storage(_db_path(request))
    try:
        ok = storage.revoke_auth_token(int(token_id))
        if not ok:
            raise AuthApiError("Not found", status_code=404)
        return {"success": True}
    finally:
        storage.close()


def _normalize_activity(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries or []:
        if isinstance(entry, dict) and "timestamp" not in entry and "created_at" in entry:
            entry = {**entry, "timestamp": entry["created_at"]}
        normalized.append(entry)
    return normalized


def _serialize_user_row(storage: Storage, user: dict[str, Any]) -> dict[str, Any]:
    role = str(user.get("role") or "registered")
    today = _now_date()
    quota_used = storage.get_ai_chat_quota_used(today, user_id=int(user["id"]))
    return {
        **{k: v for k, v in user.items() if k != "password_hash"},
        "username": user.get("display_name") or user.get("email") or f"user-{user.get('id')}",
        "quota_used": quota_used,
        "quota_limit": AI_CHAT_QUOTA.get(role, 5),
        "last_login": user.get("last_login_at"),
    }


def list_users(*, request: Request) -> dict[str, Any]:
    query = request.query_params
    try:
        page = max(1, int(query.get("page", "1")))
    except ValueError:
        page = 1
    try:
        per_page = min(100, max(1, int(query.get("per_page", "50"))))
    except ValueError:
        per_page = 50
    role_filter = (query.get("role") or "").strip() or None
    search = (query.get("q") or "").strip() or None

    storage = Storage(_db_path(request))
    try:
        users, total = storage.list_users(page=page, per_page=per_page, role=role_filter, search=search)
        safe_users = [_serialize_user_row(storage, user) for user in users]
        return {"success": True, "users": safe_users, "total": total, "page": page, "per_page": per_page}
    finally:
        storage.close()


def set_user_role(*, request: Request, auth: AuthContext, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AuthApiError("Request body must be a JSON object", status_code=400)
    new_role = str(payload.get("role") or "").strip().lower()
    if new_role not in VALID_USER_ROLES:
        raise AuthApiError(f"Invalid role. Valid roles: {', '.join(VALID_USER_ROLES)}", status_code=400)
    storage = Storage(_db_path(request))
    try:
        ok = storage.update_user_role(user_id, new_role)
        if not ok:
            raise AuthApiError("User not found", status_code=404)
        actor = auth.token or {}
        storage.log_user_activity(
            "admin_set_role",
            user_id=user_id,
            ip_address=_client_ip(request),
            detail=f"new_role={new_role} by {actor.get('subject', 'unknown')}",
        )
        return {"success": True, "user_id": user_id, "role": new_role}
    finally:
        storage.close()


def set_user_active(*, request: Request, auth: AuthContext, user_id: int, is_active: bool) -> dict[str, Any]:
    storage = Storage(_db_path(request))
    try:
        ok = storage.update_user_active(user_id, is_active)
        if not ok:
            raise AuthApiError("User not found", status_code=404)
        actor = auth.token or {}
        storage.log_user_activity(
            "admin_set_active",
            user_id=user_id,
            ip_address=_client_ip(request),
            detail=f"is_active={is_active} by {actor.get('subject', 'unknown')}",
        )
        return {"success": True, "user_id": user_id, "is_active": is_active}
    finally:
        storage.close()


def reset_user_quota(*, request: Request, auth: AuthContext, user_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    raw_date = payload.get("quota_date")
    if raw_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(raw_date)):
        raise AuthApiError("quota_date must be YYYY-MM-DD format", status_code=400)
    quota_date = str(raw_date or _now_date())
    storage = Storage(_db_path(request))
    try:
        storage.reset_user_quota(user_id, quota_date)
        actor = auth.token or {}
        storage.log_user_activity(
            "admin_reset_quota",
            user_id=user_id,
            ip_address=_client_ip(request),
            detail=f"date={quota_date} by {actor.get('subject', 'unknown')}",
        )
        return {"success": True, "user_id": user_id, "quota_date": quota_date}
    finally:
        storage.close()


def user_activity(*, request: Request, user_id: int) -> dict[str, Any]:
    try:
        limit = min(200, max(1, int(request.query_params.get("limit", "50"))))
    except ValueError:
        limit = 50
    try:
        offset = max(0, int(request.query_params.get("offset", "0")))
    except ValueError:
        offset = 0

    storage = Storage(_db_path(request))
    try:
        logs = storage.list_user_activity(user_id=user_id, limit=limit, offset=offset)
        normalized = _normalize_activity(logs)
        return {"success": True, "logs": normalized, "activity": normalized}
    finally:
        storage.close()
