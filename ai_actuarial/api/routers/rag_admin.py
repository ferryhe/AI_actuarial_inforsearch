from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.rag_admin import (
    RagAdminError,
    bind_chunk_sets,
    cleanup_chunk_sets,
    create_chunk_profile,
    create_index_task,
    create_knowledge_base,
    delete_chunk_profile,
    delete_knowledge_base,
    get_knowledge_base,
    get_knowledge_base_categories,
    get_knowledge_base_stats,
    get_pending_files,
    get_unmapped_categories,
    list_chunk_profiles,
    list_knowledge_base_files,
    list_knowledge_bases,
    list_selectable_files,
    set_knowledge_base_categories,
    update_knowledge_base,
)

router = APIRouter()


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
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
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
        result = create_chunk_profile(db_path=_db_path(request), payload=payload, headers=dict(request.headers))
        return JSONResponse(status_code=201, content=result)
    except RagAdminError as exc:
        return _error_response(exc)


@router.delete("/chunk/profiles/{profile_id}")
def api_delete_chunk_profile(
    profile_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return delete_chunk_profile(db_path=_db_path(request), profile_id=profile_id, headers=dict(request.headers))
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/chunk-sets/cleanup")
def api_chunk_sets_cleanup(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return cleanup_chunk_sets(db_path=_db_path(request), payload=payload, headers=dict(request.headers))
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
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        result = create_knowledge_base(db_path=_db_path(request), payload=payload, headers=dict(request.headers))
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
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return update_knowledge_base(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers))
    except RagAdminError as exc:
        return _error_response(exc)


@router.delete("/rag/knowledge-bases/{kb_id}")
def api_delete_knowledge_base(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return delete_knowledge_base(db_path=_db_path(request), kb_id=kb_id, headers=dict(request.headers))
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


@router.get("/rag/categories/unmapped")
def api_unmapped_categories(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return get_unmapped_categories(db_path=_db_path(request))
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/files/selectable")
def api_selectable_files(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
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
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return set_knowledge_base_categories(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers))
    except RagAdminError as exc:
        return _error_response(exc)


@router.get("/rag/knowledge-bases/{kb_id}/files/pending")
def api_pending_files(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
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
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        return bind_chunk_sets(db_path=_db_path(request), kb_id=kb_id, payload=payload, headers=dict(request.headers))
    except RagAdminError as exc:
        return _error_response(exc)


@router.post("/rag/knowledge-bases/{kb_id}/index")
def api_create_index_task(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    try:
        result, status_code = create_index_task(
            db_path=_db_path(request),
            kb_id=kb_id,
            payload=payload,
            headers=dict(request.headers),
            bridge_state=_bridge_state(request),
        )
        return JSONResponse(status_code=status_code, content=result)
    except RagAdminError as exc:
        return _error_response(exc)
