from __future__ import annotations

import logging
import os

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from .route_inventory import (
    collect_fastapi_api_paths,
    collect_fastapi_route_signatures,
    summarize_legacy_api_routes,
)
from .routers.meta import router as meta_router
from .routers.migration import router as migration_router
from .routers.read import router as read_router

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
    from ai_actuarial.web.app import _get_sites_config_path, _load_yaml

    config_data = _load_yaml(_get_sites_config_path(), default={})
    db_path = (config_data.get("paths") or {}).get("db", "data/index.db")
    db_path = str(db_path or "data/index.db")
    return os.path.abspath(db_path) if not os.path.isabs(db_path) else db_path


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

    app.state.legacy_backend = "flask"
    app.state.legacy_mount_enabled = False
    app.state.legacy_mount_error = None
    app.state.legacy_flask_app = None
    app.state.db_path = _resolve_db_path()
    app.state.require_auth = os.getenv("REQUIRE_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}
    app.state.active_tasks_ref = {}
    app.state.task_lock = None
    app.state.native_route_signatures = collect_fastapi_route_signatures(app)

    app.state.legacy_route_inventory = []
    app.state.legacy_api_paths = []
    app.state.legacy_api_route_count = 0
    app.state.legacy_api_sample_paths = []
    app.state.legacy_api_signatures = []
    app.state.legacy_non_api_route_count = 0

    try:
        from ai_actuarial.web.app import (
            _active_tasks,
            _task_lock,
            create_app as create_legacy_flask_app,
        )

        legacy_app = create_legacy_flask_app()
        legacy_summary = summarize_legacy_api_routes(legacy_app)
        app.mount("/", WSGIMiddleware(legacy_app))
        app.state.legacy_mount_enabled = True
        app.state.legacy_flask_app = legacy_app
        app.state.require_auth = bool(legacy_app.config.get("REQUIRE_AUTH", False))
        app.state.active_tasks_ref = _active_tasks
        app.state.task_lock = _task_lock
        app.state.legacy_route_inventory = legacy_summary["legacy_route_inventory"]
        app.state.legacy_api_paths = legacy_summary["legacy_api_paths"]
        app.state.legacy_api_route_count = legacy_summary["legacy_api_route_count"]
        app.state.legacy_api_sample_paths = legacy_summary["legacy_api_sample_paths"]
        app.state.legacy_api_signatures = legacy_summary["legacy_api_signatures"]
        app.state.legacy_non_api_route_count = legacy_summary["legacy_non_api_route_count"]
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
