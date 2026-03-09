from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import AuthContext, require_permissions
from ..services.read import get_dashboard_stats, list_categories, list_files, parse_file_list_query

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


@router.get("/stats")
def api_stats(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("stats.read")),
) -> dict[str, int]:
    return get_dashboard_stats(
        db_path=_get_db_path(request),
        active_tasks=_get_active_task_count(request),
    )


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
