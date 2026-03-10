from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.read import (
    get_dashboard_stats,
    get_file_detail,
    get_file_markdown,
    list_categories,
    list_files,
    list_sources,
    parse_file_list_query,
)

router = APIRouter()


def _get_db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


def _get_active_task_count(request: Request) -> int:
    active_tasks_ref = getattr(request.app.state, "active_tasks_ref", None)
    if not isinstance(active_tasks_ref, dict):
        return 0

    task_lock = getattr(request.app.state, "task_lock", None)
    if task_lock is None:
        return len(active_tasks_ref)

    with task_lock:
        return len(active_tasks_ref)


def _extract_encoded_file_url(request: Request, *, suffix: str) -> str | None:
    raw_path = request.scope.get("raw_path")
    if not isinstance(raw_path, (bytes, bytearray)):
        return None

    try:
        raw_text = bytes(raw_path).decode("ascii")
    except Exception:
        return None

    prefix = "/api/files/"
    if not raw_text.startswith(prefix) or not raw_text.endswith(suffix):
        return None

    return raw_text[len(prefix):-len(suffix)]


def _decode_file_url_path(request: Request, file_url: str, *, suffix: str) -> str:
    encoded = _extract_encoded_file_url(request, suffix=suffix)
    if not encoded:
        return file_url

    try:
        return unquote(encoded)
    except Exception:
        return file_url


@router.get("/stats")
def api_stats(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("stats.read")),
) -> dict[str, int]:
    return get_dashboard_stats(
        db_path=_get_db_path(request),
        active_tasks=_get_active_task_count(request),
    )


@router.get("/sources")
def api_sources(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, list[str]]:
    return list_sources(db_path=_get_db_path(request))


@router.get("/categories")
def api_categories(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, list[str]]:
    mode = str(request.query_params.get("mode", "") or "")
    return list_categories(db_path=_get_db_path(request), mode=mode)


@router.get("/files")
def api_files(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, object]:
    query = parse_file_list_query(request.query_params)
    return list_files(db_path=_get_db_path(request), query=query)


@router.get("/files/detail")
def api_file_detail(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, object]:
    url = str(request.query_params.get("url", "") or "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"error": "url parameter is required"})

    file_data = get_file_detail(db_path=_get_db_path(request), url=url)
    if not file_data:
        return JSONResponse(status_code=404, content={"error": "File not found"})

    return {"file": file_data}


@router.get("/files/{file_url:path}/markdown")
def api_file_markdown(
    file_url: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("markdown.read")),
) -> dict[str, object]:
    decoded_url = _decode_file_url_path(request, file_url, suffix="/markdown")
    return get_file_markdown(db_path=_get_db_path(request), url=decoded_url)
