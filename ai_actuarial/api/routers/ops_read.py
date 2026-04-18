from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ai_actuarial.ai_runtime import get_ai_routing, get_model_catalog, list_provider_credentials, list_provider_registry
from ai_actuarial.config import settings
from ai_actuarial.storage import Storage
from ..deps import AuthContext, require_permissions
from ..services.ops_read import (
    get_ai_models,
    get_backend_settings,
    get_config_categories,
    get_config_sites,
    get_global_logs,
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

_GLOBAL_LOGS_RATE_LIMIT = 30
_GLOBAL_LOGS_WINDOW_SECONDS = 60.0


def _get_db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


def _global_logs_rate_key(request: Request, auth: AuthContext) -> str:
    token = auth.token or {}
    if token.get("_email_user_id") is not None:
        return f"user:{token['_email_user_id']}"
    if token.get("id") is not None:
        return f"token:{token['id']}"
    client_host = getattr(getattr(request, "client", None), "host", None) or "unknown"
    return f"ip:{client_host}"


def _enforce_global_logs_rate_limit(request: Request, auth: AuthContext) -> JSONResponse | None:
    now = time.monotonic()
    bucket_key = _global_logs_rate_key(request, auth)
    buckets = getattr(request.app.state, "global_logs_rate_limit_buckets", None)
    if not isinstance(buckets, dict):
        buckets = {}
        request.app.state.global_logs_rate_limit_buckets = buckets
    recent = [stamp for stamp in buckets.get(bucket_key, []) if now - stamp < _GLOBAL_LOGS_WINDOW_SECONDS]
    if len(recent) >= _GLOBAL_LOGS_RATE_LIMIT:
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})
    recent.append(now)
    buckets[bucket_key] = recent
    return None


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


@router.get("/logs/global")
def api_logs_global(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("logs.system.read")),
) -> dict[str, object]:
    rate_limited = _enforce_global_logs_rate_limit(request, _auth)
    if rate_limited is not None:
        return rate_limited
    expected_token = settings.LOGS_READ_AUTH_TOKEN
    if expected_token:
        provided_token = request.headers.get("X-Auth-Token")
        if not provided_token or provided_token != expected_token:
            return JSONResponse(status_code=403, content={"error": "Forbidden"})
    result = get_global_logs()
    if result.get("error") == "Forbidden":
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return result


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


@router.get("/config/providers")
def api_config_providers(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    return list_provider_registry()


@router.get("/config/provider-credentials")
def api_config_provider_credentials(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    storage = Storage(_get_db_path(request))
    try:
        return list_provider_credentials(storage=storage)
    finally:
        storage.close()


@router.get("/config/model-catalog")
def api_config_model_catalog(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    return get_model_catalog()


@router.get("/config/ai-routing")
def api_config_ai_routing(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.read")),
) -> dict[str, object]:
    storage = Storage(_get_db_path(request))
    try:
        return get_ai_routing(storage=storage)
    finally:
        storage.close()


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


@router.get("/search")
def api_search(
    request: Request,
    q: str = "",
    kb_id: str | None = None,
    limit: int = 20,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
) -> dict[str, object]:
    if not q:
        return {"results": [], "count": 0}
    # Clamp limit to prevent abuse
    limit = min(max(1, limit), 100)
    storage = Storage(_get_db_path(request))
    try:
        query_lower = q.lower()
        # Build query with optional kb_id filter
        sql = """
            SELECT kb_id, name, description, created_at FROM rag_knowledge_bases
            WHERE (kb_mode = 'category' OR kb_mode = 'hybrid')
        """
        params: list[str | int] = []
        if kb_id:
            sql += " AND kb_id = ?"
            params.append(kb_id)
        # Fetch more than limit since we filter in Python for scoring
        cursor = storage._conn.execute(sql + " LIMIT 1000", params)
        results = []
        for row in cursor.fetchall():
            kb_id_row, name, description, created_at = row
            score = 0
            if name and query_lower in name.lower():
                score += 10
            if description and query_lower in description.lower():
                score += 5
            if score > 0:
                results.append({
                    "kb_id": kb_id_row,
                    "name": name,
                    "description": description,
                    "created_at": created_at,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"results": results[:limit], "count": len(results)}
    finally:
        storage.close()
