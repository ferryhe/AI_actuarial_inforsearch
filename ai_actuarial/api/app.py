from __future__ import annotations

import logging
import os

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from .routers.meta import router as meta_router
from .routers.migration import router as migration_router

logger = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    raw = os.getenv(
        "FASTAPI_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    )
    return [part.strip() for part in raw.split(",") if part.strip()]


def _native_paths(app: FastAPI) -> list[str]:
    paths: set[str] = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path.startswith("/api"):
            paths.add(path)
    return sorted(paths)


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

    app.state.legacy_backend = "flask"
    app.state.legacy_mount_enabled = False
    app.state.legacy_mount_error = None

    try:
        from ai_actuarial.web.app import create_app as create_legacy_flask_app

        legacy_app = create_legacy_flask_app()
        app.mount("/", WSGIMiddleware(legacy_app))
        app.state.legacy_mount_enabled = True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to mount legacy Flask app into FastAPI gateway")
        app.state.legacy_mount_error = str(exc)

        @app.get("/{path:path}", include_in_schema=False)
        async def legacy_unavailable(path: str) -> PlainTextResponse:
            return PlainTextResponse(
                (
                    "Legacy Flask app is unavailable inside the FastAPI gateway.\n"
                    f"Reason: {exc}\n"
                ),
                status_code=503,
            )

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
