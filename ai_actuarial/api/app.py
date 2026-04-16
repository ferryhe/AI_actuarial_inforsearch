from __future__ import annotations

import logging
import os

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from .route_inventory import (
    collect_fastapi_api_paths,
    collect_fastapi_route_signatures,
    summarize_legacy_api_routes,
)
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router
from .routers.files_write import router as files_write_router
from .routers.meta import router as meta_router
from .routers.rag_admin import router as rag_admin_router
from .routers.migration import router as migration_router
from .routers.ops_read import router as ops_read_router
from .routers.ops_write import router as ops_write_router
from .routers.read import router as read_router
from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml
from ai_actuarial.task_runtime import NativeTaskRuntime

logger = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    raw = os.getenv(
        "FASTAPI_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    )
    return [part.strip() for part in raw.split(",") if part.strip()]


def _native_paths(app: FastAPI) -> list[str]:
    return collect_fastapi_api_paths(app)


def _resolve_db_path() -> str:
    config_data = load_yaml(get_sites_config_path(), default={})
    db_path = (config_data.get("paths") or {}).get("db", "data/index.db")
    db_path = str(db_path or "data/index.db")
    return os.path.abspath(db_path) if not os.path.isabs(db_path) else db_path


def _legacy_api_fallback_allowed() -> bool:
    return os.getenv("FASTAPI_ALLOW_LEGACY_API_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Actuarial Info Search API",
        version="0.1.0",
        summary="FastAPI gateway for the React frontend with Flask compatibility fallback.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta_router, prefix="/api", tags=["meta"])
    app.include_router(migration_router, prefix="/api", tags=["migration"])
    app.include_router(read_router, prefix="/api", tags=["read"])
    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(ops_read_router, prefix="/api", tags=["ops-read"])
    app.include_router(ops_write_router, prefix="/api", tags=["ops-write"])
    app.include_router(files_write_router, prefix="/api", tags=["files-write"])
    app.include_router(rag_admin_router, prefix="/api", tags=["rag-admin"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])

    app.state.legacy_backend = "flask"
    app.state.legacy_mount_enabled = False
    app.state.legacy_mount_error = None
    app.state.legacy_flask_app = None
    app.state.fastapi_session_secret = os.getenv("FLASK_SECRET_KEY", "")
    app.state.fastapi_session_cookie_name = "session"
    app.state.fastapi_session_cookie_path = "/"
    app.state.fastapi_session_cookie_domain = None
    app.state.fastapi_session_cookie_secure = False
    app.state.fastapi_session_cookie_httponly = True
    app.state.fastapi_session_cookie_samesite = "Lax"
    app.state.db_path = _resolve_db_path()
    app.state.require_auth = os.getenv("REQUIRE_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}
    native_runtime = NativeTaskRuntime()
    native_refs = native_runtime.refs()
    app.state.native_task_runtime = native_runtime
    app.state.active_tasks_ref = native_refs.active_tasks_ref
    app.state.task_history_ref = native_refs.task_history_ref
    app.state.task_lock = native_refs.task_lock
    app.state.schedule_ref = native_refs.schedule_ref
    app.state.start_background_task = native_refs.start_background_task
    app.state.init_scheduler = native_refs.init_scheduler
    app.state.set_site_config = native_refs.set_site_config
    app.state.legacy_start_background_task = None
    app.state.legacy_init_scheduler = None
    app.state.legacy_set_site_config = None
    app.state.native_route_signatures = collect_fastapi_route_signatures(app)

    app.state.legacy_route_inventory = []
    app.state.legacy_api_paths = []
    app.state.legacy_api_route_count = 0
    app.state.legacy_api_sample_paths = []
    app.state.legacy_api_signatures = []
    app.state.legacy_non_api_route_count = 0
    app.state.legacy_flask_only_signatures = []
    app.state.legacy_flask_only_route_count = 0
    app.state.legacy_flask_only_sample_signatures = []
    app.state.native_override_signatures = []
    app.state.native_override_route_count = 0
    app.state.legacy_api_fallback_allowed = _legacy_api_fallback_allowed()

    if not app.state.legacy_api_fallback_allowed:

        @app.api_route(
            "/api/{legacy_api_path:path}",
            methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )
        async def block_legacy_api_fallback(legacy_api_path: str) -> None:
            raise HTTPException(
                status_code=410,
                detail=(
                    "Legacy Flask /api fallback is disabled in FastAPI-authority mode. "
                    f"Port /api/{legacy_api_path} to ai_actuarial/api/routers before exposing it in React."
                ),
            )

    try:
        import ai_actuarial.web.app as legacy_web_app

        legacy_app = legacy_web_app.create_app()
        legacy_summary = summarize_legacy_api_routes(legacy_app, native_signatures=app.state.native_route_signatures)
        legacy_bridge = dict((getattr(legacy_app, "extensions", {}) or {}).get("fastapi_bridge", {}))
        app.mount("/", WSGIMiddleware(legacy_app))
        app.state.legacy_mount_enabled = True
        app.state.legacy_flask_app = legacy_app
        app.state.fastapi_session_secret = str(legacy_app.secret_key or app.state.fastapi_session_secret or "")
        app.state.fastapi_session_cookie_name = str(legacy_app.config.get("SESSION_COOKIE_NAME", "session") or "session")
        app.state.fastapi_session_cookie_path = str(legacy_app.config.get("SESSION_COOKIE_PATH") or "/")
        app.state.fastapi_session_cookie_domain = legacy_app.config.get("SESSION_COOKIE_DOMAIN") or None
        app.state.fastapi_session_cookie_secure = bool(legacy_app.config.get("SESSION_COOKIE_SECURE", False))
        app.state.fastapi_session_cookie_httponly = bool(legacy_app.config.get("SESSION_COOKIE_HTTPONLY", True))
        app.state.fastapi_session_cookie_samesite = legacy_app.config.get("SESSION_COOKIE_SAMESITE") or "Lax"
        app.state.require_auth = bool(legacy_app.config.get("REQUIRE_AUTH", False))
        app.state.legacy_start_background_task = legacy_bridge.get("start_background_task")
        app.state.legacy_init_scheduler = legacy_bridge.get("init_scheduler")
        app.state.legacy_set_site_config = legacy_bridge.get("set_site_config")
        app.state.legacy_route_inventory = legacy_summary["legacy_route_inventory"]
        app.state.legacy_api_paths = legacy_summary["legacy_api_paths"]
        app.state.legacy_api_route_count = legacy_summary["legacy_api_route_count"]
        app.state.legacy_api_sample_paths = legacy_summary["legacy_api_sample_paths"]
        app.state.legacy_api_signatures = legacy_summary["legacy_api_signatures"]
        app.state.legacy_non_api_route_count = legacy_summary["legacy_non_api_route_count"]
        app.state.legacy_flask_only_signatures = legacy_summary["legacy_flask_only_signatures"]
        app.state.legacy_flask_only_route_count = legacy_summary["legacy_flask_only_route_count"]
        app.state.legacy_flask_only_sample_signatures = legacy_summary["legacy_flask_only_sample_signatures"]
        app.state.native_override_signatures = legacy_summary["native_override_signatures"]
        app.state.native_override_route_count = legacy_summary["native_override_route_count"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to mount legacy Flask app into FastAPI gateway")
        app.state.legacy_mount_error = str(exc)

        @app.get("/{path:path}", include_in_schema=False)
        async def legacy_unavailable(path: str) -> PlainTextResponse:
            base_message = "Legacy Flask app is unavailable inside the FastAPI gateway."
            if os.getenv("FASTAPI_EXPOSE_ERROR_DETAILS") == "1":
                body = f"{base_message}\nReason: {exc}\n"
            else:
                body = f"{base_message}\n"
            return PlainTextResponse(body, status_code=503)

    try:
        app.state.init_scheduler()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize native FastAPI scheduler")

    app.state.native_paths = _native_paths(app)
    return app


def run_server(host: str = "127.0.0.1", port: int = 5000, reload: bool = False) -> None:
    import uvicorn

    uvicorn.run(
        "ai_actuarial.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
