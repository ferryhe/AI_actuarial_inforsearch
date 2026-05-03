from __future__ import annotations

import logging
import os
import secrets

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, URLSafeSerializer

from .middleware import RateLimitMiddleware
from .route_inventory import (
    collect_fastapi_api_paths,
    collect_fastapi_route_signatures,
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
from .routers.metrics import router as metrics_router
from ai_actuarial.config import settings
from ai_actuarial.shared_auth import hash_token
from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml, resolve_fastapi_env, resolve_runtime_features
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _native_paths(app: FastAPI) -> list[str]:
    return collect_fastapi_api_paths(app)


def _resolve_db_path() -> str:
    config_data = load_yaml(get_sites_config_path(), default={})
    return settings.resolve_db_path(config_data)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _presented_api_token(request) -> bool:
    auth = request.headers.get("Authorization", "") or ""
    parts = auth.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return True
    return bool((request.headers.get("X-API-Token") or request.headers.get("X-Auth-Token") or "").strip())


def _csrf_serializer(request) -> URLSafeSerializer | None:
    secret = str(getattr(request.app.state, "fastapi_session_secret", "") or "")
    if not secret:
        return None
    return URLSafeSerializer(secret, salt="fastapi-csrf")


def _create_csrf_token(request) -> str:
    serializer = _csrf_serializer(request)
    if serializer is None:
        return ""
    return serializer.dumps({"nonce": secrets.token_urlsafe(32)})


def _valid_csrf_token(request, token: str) -> bool:
    serializer = _csrf_serializer(request)
    if serializer is None or not token:
        return False
    try:
        data = serializer.loads(token)
    except BadSignature:
        return False
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("nonce"), str) and bool(data.get("nonce"))


def _default_session_cookie_secure(require_auth: bool, config_data: dict[str, object]) -> bool:
    fastapi_env, _source = resolve_fastapi_env(config_data)
    if not fastapi_env:
        fastapi_env = settings.FASTAPI_ENV
    return fastapi_env in {"prod", "production"} and require_auth


def _apply_runtime_feature_state(app: FastAPI, features: dict[str, object]) -> None:
    app.state.require_auth = bool(features.get("require_auth"))
    app.state.enable_global_logs_api = bool(features.get("enable_global_logs_api"))
    app.state.enable_rate_limiting = bool(features.get("enable_rate_limiting"))
    app.state.enable_csrf = bool(features.get("enable_csrf"))
    app.state.enable_security_headers = bool(features.get("enable_security_headers"))
    app.state.expose_error_details = bool(features.get("expose_error_details"))
    app.state.rate_limit_defaults = str(features.get("rate_limit_defaults") or "")
    app.state.rate_limit_storage_uri = str(features.get("rate_limit_storage_uri") or "memory://")
    app.state.content_security_policy = str(features.get("content_security_policy") or "")


def _bootstrap_admin_token(db_path: str) -> None:
    token = os.getenv("BOOTSTRAP_ADMIN_TOKEN", "").strip()
    if not token:
        return
    subject = os.getenv("BOOTSTRAP_ADMIN_SUBJECT", "").strip() or "bootstrap-admin"
    storage = Storage(db_path)
    try:
        storage.upsert_auth_token_by_hash(
            subject=subject,
            group_name="admin",
            token_hash=hash_token(token),
            is_active=True,
        )
    finally:
        storage.close()


def create_app() -> FastAPI:
    config_data = load_yaml(get_sites_config_path(), default={})
    runtime_features = resolve_runtime_features(config_data)
    app = FastAPI(
        title="AI Actuarial Info Search API",
        description=(
            "REST API for the AI Actuarial Info Search platform. "
            "Provides document search, RAG administration, chat, and system management endpoints."
        ),
        version="0.1.0",
        summary="FastAPI product API for the React frontend.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={
            401: {"description": "Authentication required"},
            403: {"description": "Insufficient permissions"},
            429: {"description": "Rate limit exceeded"},
            500: {"description": "Internal server error"},
        },
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware (applied after CORS)
    app.add_middleware(
        RateLimitMiddleware,
        enabled=None,
    )

    from starlette.middleware.base import BaseHTTPMiddleware

    class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if bool(getattr(request.app.state, "enable_security_headers", False)):
                response.headers.setdefault("X-Content-Type-Options", "nosniff")
                response.headers.setdefault("X-Frame-Options", "DENY")
                response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
                csp = str(getattr(request.app.state, "content_security_policy", "") or "").strip()
                if csp:
                    response.headers.setdefault("Content-Security-Policy", csp)
            return response

    app.add_middleware(_SecurityHeadersMiddleware)

    class _CsrfProtectionMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if not bool(getattr(request.app.state, "enable_csrf", False)):
                return await call_next(request)

            if request.url.path.startswith("/api/"):
                serializer = _csrf_serializer(request)
                if serializer is None:
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "FastAPI session secret is required when CSRF protection is enabled"},
                    )

                unsafe_method = request.method.upper() not in CSRF_SAFE_METHODS
                if unsafe_method and not _presented_api_token(request):
                    cookie_token = request.cookies.get(CSRF_COOKIE_NAME) or ""
                    header_token = request.headers.get(CSRF_HEADER_NAME) or ""
                    if (
                        not cookie_token
                        or not header_token
                        or not secrets.compare_digest(cookie_token, header_token)
                        or not _valid_csrf_token(request, cookie_token)
                    ):
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "CSRF token missing or invalid"},
                        )

            response = await call_next(request)
            if request.url.path.startswith("/api/"):
                current_token = request.cookies.get(CSRF_COOKIE_NAME) or ""
                if not _valid_csrf_token(request, current_token):
                    response.set_cookie(
                        key=CSRF_COOKIE_NAME,
                        value=_create_csrf_token(request),
                        path="/",
                        secure=bool(getattr(request.app.state, "fastapi_session_cookie_secure", False)),
                        httponly=False,
                        samesite=getattr(request.app.state, "fastapi_session_cookie_samesite", "Lax") or "Lax",
                    )
            return response

    app.add_middleware(_CsrfProtectionMiddleware)

    app.include_router(meta_router, prefix="/api", tags=["meta"])
    app.include_router(metrics_router, prefix="/api", tags=["metrics"])
    app.include_router(migration_router, prefix="/api", tags=["migration"])
    app.include_router(read_router, prefix="/api", tags=["read"])
    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(ops_read_router, prefix="/api", tags=["ops-read"])
    app.include_router(ops_write_router, prefix="/api", tags=["ops-write"])
    app.include_router(files_write_router, prefix="/api", tags=["files-write"])
    app.include_router(rag_admin_router, prefix="/api", tags=["rag-admin"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])

    app.state.fastapi_session_secret = os.getenv("FASTAPI_SESSION_SECRET", settings.FASTAPI_SESSION_SECRET)
    app.state.fastapi_session_cookie_name = "session"
    app.state.fastapi_session_cookie_path = "/"
    app.state.fastapi_session_cookie_domain = None
    app.state.fastapi_env, app.state.fastapi_env_source = resolve_fastapi_env(config_data)
    app.state.fastapi_session_cookie_secure = _env_bool(
        "FASTAPI_SESSION_COOKIE_SECURE",
        settings.FASTAPI_SESSION_COOKIE_SECURE
        or _default_session_cookie_secure(bool(runtime_features["require_auth"]), config_data),
    )
    app.state.fastapi_session_cookie_httponly = True
    app.state.fastapi_session_cookie_samesite = "Lax"
    app.state.db_path = _resolve_db_path()
    try:
        _bootstrap_admin_token(app.state.db_path)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to bootstrap admin auth token")
    _apply_runtime_feature_state(app, runtime_features)
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
    app.state.native_route_signatures = collect_fastapi_route_signatures(app)
    app.state.legacy_api_fallback_allowed = False

    @app.api_route(
        "/api/{retired_api_path:path}",
        methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def block_retired_api_fallback(retired_api_path: str) -> None:
        raise HTTPException(
            status_code=410,
            detail=(
                "Legacy /api fallback is disabled in FastAPI-only mode. "
                f"Port /api/{retired_api_path} to ai_actuarial/api/routers before exposing it in React."
            ),
        )

    try:
        app.state.init_scheduler()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize native FastAPI scheduler")

    app.state.native_paths = _native_paths(app)

    # Attach metrics tracking to request lifecycle
    from .routers.metrics import record_request

    class _MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            record_request(request.url.path)
            return response

    app.add_middleware(_MetricsMiddleware)

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
