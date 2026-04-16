from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..deps import AuthContext, get_auth_context, require_permissions
from ..services.auth import (
    AuthApiError,
    _apply_session_mutation,
    auth_me,
    create_auth_token,
    list_auth_tokens,
    list_users,
    login_user,
    logout_user,
    register_user,
    reset_user_quota,
    revoke_auth_token,
    set_user_active,
    set_user_role,
    update_profile,
    user_activity,
    user_me,
)

router = APIRouter()


def _error_response(exc: AuthApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


@router.get("/auth/me")
def api_auth_me(request: Request):
    try:
        return auth_me(request=request)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/auth/register", status_code=201)
def api_auth_register(payload: dict[str, object], request: Request, response: Response):
    try:
        result, mutation = register_user(request=request, payload=payload)
        _apply_session_mutation(response, request, mutation)
        return result
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/auth/login")
def api_auth_login(payload: dict[str, object], request: Request, response: Response):
    try:
        result, mutation = login_user(request=request, payload=payload)
        _apply_session_mutation(response, request, mutation)
        return result
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/auth/logout")
def api_auth_logout(request: Request, response: Response):
    try:
        result, mutation = logout_user()
        _apply_session_mutation(response, request, mutation)
        return result
    except AuthApiError as exc:
        return _error_response(exc)


@router.get("/auth/tokens")
def api_list_auth_tokens(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tokens.manage")),
):
    try:
        return list_auth_tokens(request=request)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/auth/tokens", status_code=201)
def api_create_auth_token(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tokens.manage")),
):
    try:
        return create_auth_token(request=request, payload=payload)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/auth/tokens/{token_id}/revoke")
def api_revoke_auth_token(
    token_id: int,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tokens.manage")),
):
    try:
        return revoke_auth_token(request=request, token_id=token_id)
    except AuthApiError as exc:
        return _error_response(exc)


@router.get("/user/me")
def api_user_me(
    request: Request,
):
    try:
        auth = get_auth_context(request)
        return user_me(request=request, auth=auth)
    except AuthApiError as exc:
        return _error_response(exc)


@router.patch("/user/profile")
def api_update_profile(
    payload: dict[str, object],
    request: Request,
):
    try:
        auth = get_auth_context(request)
        return update_profile(request=request, auth=auth, payload=payload)
    except AuthApiError as exc:
        return _error_response(exc)


@router.get("/admin/users")
def api_list_users(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("users.manage")),
):
    try:
        return list_users(request=request)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/admin/users/{user_id}/role")
def api_set_user_role(
    user_id: int,
    payload: dict[str, object],
    request: Request,
    auth: AuthContext = Depends(require_permissions("users.manage")),
):
    try:
        return set_user_role(request=request, auth=auth, user_id=user_id, payload=payload)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/admin/users/{user_id}/enable")
def api_enable_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permissions("users.manage")),
):
    try:
        return set_user_active(request=request, auth=auth, user_id=user_id, is_active=True)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/admin/users/{user_id}/disable")
def api_disable_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permissions("users.manage")),
):
    try:
        return set_user_active(request=request, auth=auth, user_id=user_id, is_active=False)
    except AuthApiError as exc:
        return _error_response(exc)


@router.post("/admin/users/{user_id}/reset-quota")
def api_reset_user_quota(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permissions("users.manage")),
    payload: dict[str, object] | None = Body(default=None),
):
    try:
        normalized = payload if isinstance(payload, dict) else {}
        return reset_user_quota(request=request, auth=auth, user_id=user_id, payload=normalized)
    except AuthApiError as exc:
        return _error_response(exc)


@router.get("/admin/users/{user_id}/activity")
def api_user_activity(
    user_id: int,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("users.manage")),
):
    try:
        return user_activity(request=request, user_id=user_id)
    except AuthApiError as exc:
        return _error_response(exc)
