from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ai_actuarial.config import settings

from ..deps import AuthContext, get_auth_context, require_permissions
from ..services.rag_admin import (
    RagAdminError,
    add_knowledge_base_files,
    bind_chunk_sets,
    cleanup_chunk_sets,
    build_agentic_ready_manifest,
    create_chunk_profile,
    create_index_task,
    create_knowledge_base,
    delete_chunk_profile,
    delete_knowledge_base,
    get_categories_mapping,
    get_category_stats,
    get_kb_bindings,
    get_knowledge_base,
    get_knowledge_base_categories,
    get_knowledge_base_stats,
    get_agentic_ready_manifest,
    get_pending_files,
    get_unmapped_categories,
    list_chunk_profiles,
    list_knowledge_base_files,
    list_knowledge_bases,
    list_selectable_files,
    remove_knowledge_base_file,
    set_knowledge_base_categories,
    update_chunk_profile,
    update_knowledge_base,
)

router = APIRouter()


def _presented_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "") or ""
    parts = auth.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    token = request.headers.get("X-API-Token") or request.headers.get("X-Auth-Token")
    return token.strip() if token else None


def _legacy_rag_write_context(request: Request) -> AuthContext | None:
    expected = os.getenv("CONFIG_WRITE_AUTH_TOKEN") or settings.CONFIG_WRITE_AUTH_TOKEN
    presented = _presented_token(request)
    if not expected or not presented or not secrets.compare_digest(presented, expected):
        return None
    return AuthContext(
        token={
            "id": None,
            "subject": "legacy-config-write-token",
            "group_name": "legacy_config_write",
            "is_active": True,
        },
        permissions=frozenset({"catalog.write", "config.write", "tasks.run", "tasks.view"}),
    )


def _require_permission_or_legacy_rag_write(request: Request, permission: str) -> AuthContext:
    context = get_auth_context(request)
    if context.token and permission in context.permissions:
        return context
    legacy_context = _legacy_rag_write_context(request)
    if legacy_context:
        return legacy_context
    if not context.token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    raise HTTPException(status_code=403, detail="Forbidden")


def require_rag_write(request: Request) -> AuthContext:
    return _require_permission_or_legacy_rag_write(request, "catalog.write")


def require_rag_task_run(request: Request) -> AuthContext:
    return _require_permission_or_legacy_rag_write(request, "tasks.run")


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


def _bridge_state(request: Request):
    return request.app.state


def _error_response(exc: RagAdminError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@router.get("/chunk/profiles")
def api_chunk_profiles(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    try:
        return list_chunk_profiles(db_path=_db_path(request))
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/chunk/profiles")
def api_create_chunk_profile(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        result = create_chunk_profile(db_path=_db_path(request), payload=payload, headers=dict(request.headers), auth=_auth)
        return JSONResponse(status_code=201, content=result)
    except RagAdminError as exc:
        return _error_response(exc)


@router.put("/chunk/profiles/{profile_id}")
def api_update_chunk_profile(
    profile_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return update_chunk_profile(db_path=_db_path(request), profile_id=profile_id, payload=payload, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.delete("/chunk/profiles/{profile_id}")
def api_delete_chunk_profile(
    profile_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return delete_chunk_profile(db_path=_db_path(request), profile_id=profile_id, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/chunk-sets/cleanup")
def api_chunk_sets_cleanup(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return cleanup_chunk_sets(db_path=_db_path(request), payload=payload, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases")
def api_list_knowledge_bases(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return list_knowledge_bases(db_path=_db_path(request), query=request.query_params)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases")
def api_create_knowledge_base(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        result = create_knowledge_base(db_path=_db_path(request), payload=payload, headers=dict(request.headers), auth=_auth)
        return JSONResponse(status_code=201, content=result)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}")
def api_get_knowledge_base(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return get_knowledge_base(db_path=_db_path(request), kb_id=kb_id)
    except RagAdminError as exc:
        return _error_response(exc)


@router.put("/rag/knowledge-bases/{kb_id}")
def api_update_knowledge_base(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return update_knowledge_base(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.delete("/rag/knowledge-bases/{kb_id}")
def api_delete_knowledge_base(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return delete_knowledge_base(db_path=_db_path(request), kb_id=kb_id, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/stats")
def api_get_knowledge_base_stats(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return get_knowledge_base_stats(db_path=_db_path(request), kb_id=kb_id)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/agentic-ready-manifest")
def api_get_agentic_ready_manifest(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return get_agentic_ready_manifest(db_path=_db_path(request), kb_id=kb_id, query=request.query_params)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build")
def api_build_agentic_ready_manifest(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_task_run),
):
    try:
        return build_agentic_ready_manifest(
            db_path=_db_path(request),
            kb_id=kb_id,
            payload=payload,
            headers=dict(request.headers),
            auth=_auth,
        )
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/files")
def api_list_knowledge_base_files(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return list_knowledge_base_files(db_path=_db_path(request), kb_id=kb_id, query=request.query_params)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases/{kb_id}/files")
def api_add_knowledge_base_files(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return add_knowledge_base_files(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.delete("/rag/knowledge-bases/{kb_id}/files/{file_url:path}")
def api_remove_knowledge_base_file(
    kb_id: str,
    file_url: str,
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return remove_knowledge_base_file(db_path=_db_path(request), kb_id=kb_id, file_url=file_url, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/categories/unmapped")
def api_unmapped_categories(
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return get_unmapped_categories(db_path=_db_path(request))
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/categories/mapping")
def api_categories_mapping(
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return get_categories_mapping(db_path=_db_path(request))
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/categories/stats")
def api_category_stats(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return get_category_stats(db_path=_db_path(request), payload=payload)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/files/selectable")
def api_selectable_files(
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return list_selectable_files(db_path=_db_path(request), query=request.query_params)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/categories")
def api_get_kb_categories(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return get_knowledge_base_categories(db_path=_db_path(request), kb_id=kb_id)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases/{kb_id}/categories")
def api_set_kb_categories(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return set_knowledge_base_categories(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/files/pending")
def api_pending_files(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    try:
        return get_pending_files(db_path=_db_path(request), kb_id=kb_id)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases/{kb_id}/bindings")
def api_bind_chunk_sets(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return bind_chunk_sets(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers), auth=_auth)
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/bindings")
def api_get_kb_bindings(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_rag_write),
):
    try:
        return get_kb_bindings(db_path=_db_path(request), kb_id=kb_id)
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases/{kb_id}/index")
def api_create_index_task(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_task_run),
):
    try:
        result, status_code = create_index_task(
            db_path=_db_path(request),
            kb_id=kb_id,
            payload=payload,
            headers=dict(request.headers),
            bridge_state=_bridge_state(request),
            auth=_auth,
        )
        return JSONResponse(status_code=status_code, content=result)
    except RagAdminError as exc:
        return _error_response(exc)
