from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.ops_read import (
    get_ai_models,
    get_backend_settings,
    get_config_categories,
    get_config_sites,
    get_llm_providers,
    get_schedule_status,
    get_scheduled_tasks,
    get_search_engines,
    get_task_log,
    list_active_tasks,
    list_task_history,
    parse_task_history_limit,
    parse_task_log_tail,
)

router = APIRouter()


def _get_db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


@router.get("/config/sites")
def api_config_sites(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
) -> dict[str, object]:
    return get_config_sites()


@router.get("/schedule/status")
def api_schedule_status(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
) -> dict[str, object]:
    return get_schedule_status(getattr(request.app.state, "schedule_ref", None))


@router.get("/scheduled-tasks")
def api_scheduled_tasks(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
) -> dict[str, object]:
    return get_scheduled_tasks()


@router.get("/tasks/active")
def api_tasks_active(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
) -> dict[str, object]:
    active_tasks_ref = getattr(request.app.state, "active_tasks_ref", {}) or {}
    task_lock = getattr(request.app.state, "task_lock", None)
    return list_active_tasks(active_tasks_ref, task_lock)


@router.get("/tasks/history")
def api_tasks_history(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
) -> dict[str, object]:
    limit = parse_task_history_limit(request.query_params.get("limit"))
    task_history_ref = getattr(request.app.state, "task_history_ref", []) or []
    task_lock = getattr(request.app.state, "task_lock", None)
    if task_lock is None:
        return list_task_history(task_history_ref, limit)
    with task_lock:
        return list_task_history(task_history_ref, limit)


@router.get("/tasks/log/{task_id}")
def api_task_log(
    task_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("logs.task.read")),
) -> dict[str, object]:
    tail = parse_task_log_tail(request.query_params.get("tail"))
    try:
        return get_task_log(task_id, tail)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


@router.get("/config/backend-settings")
def api_config_backend_settings(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    return get_backend_settings()


@router.get("/config/llm-providers")
def api_config_llm_providers(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    return get_llm_providers(db_path=_get_db_path(request))


@router.get("/config/ai-models")
def api_config_ai_models(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    return get_ai_models()


@router.get("/config/search-engines")
def api_config_search_engines(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
) -> dict[str, object]:
    return get_search_engines()


@router.get("/config/categories")
def api_config_categories(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    return get_config_categories()
