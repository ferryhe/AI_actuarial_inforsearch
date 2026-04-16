from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _migration_inventory_enabled() -> bool:
    return os.getenv("FASTAPI_ENABLE_MIGRATION_INVENTORY", "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/migration/status")
async def api_migration_status(request: Request) -> dict[str, object]:
    app = request.app
    native_paths = sorted(getattr(app.state, "native_paths", []))
    mount_error = getattr(app.state, "legacy_mount_error", None)
    expose_details = os.getenv("FASTAPI_EXPOSE_ERROR_DETAILS") == "1"
    inventory_enabled = _migration_inventory_enabled()
    legacy_api_route_count = int(getattr(app.state, "legacy_api_route_count", 0) or 0)
    legacy_flask_only_route_count = int(getattr(app.state, "legacy_flask_only_route_count", 0) or 0)
    legacy_flask_only_sample_signatures = list(getattr(app.state, "legacy_flask_only_sample_signatures", [])) if inventory_enabled else []
    return {
        "success": True,
        "backend": "fastapi",
        "api_authority": "fastapi",
        "legacy_backend": getattr(app.state, "legacy_backend", "flask"),
        "legacy_mount_enabled": bool(getattr(app.state, "legacy_mount_enabled", False)),
        "legacy_mount_failed": mount_error is not None,
        **({"legacy_mount_error": mount_error} if expose_details and mount_error else {}),
        "native_paths": native_paths,
        "legacy_api_route_count": legacy_api_route_count,
        "legacy_api_routes_remaining": legacy_flask_only_route_count,
        "legacy_flask_only_sample_signatures": legacy_flask_only_sample_signatures,
        "legacy_api_fallback_allowed": bool(getattr(app.state, "legacy_api_fallback_allowed", False)),
        "migration_inventory_enabled": inventory_enabled,
        "notes": [
            "FastAPI is the only long-term API authority for /api routes.",
            "Legacy Flask /api fallback is blocked by default; enable FASTAPI_ALLOW_LEGACY_API_FALLBACK=1 only for historical debugging.",
            "No new product API endpoints should be added to Flask during the migration.",
        ],
    }


@router.get("/migration/inventory")
async def api_migration_inventory(request: Request) -> dict[str, object]:
    if not _migration_inventory_enabled():
        raise HTTPException(status_code=404, detail="Migration inventory is disabled")

    app = request.app
    mount_error = getattr(app.state, "legacy_mount_error", None)
    native_paths = sorted(getattr(app.state, "native_paths", []))
    legacy_api_paths = sorted(getattr(app.state, "legacy_api_paths", []))
    native_route_signatures = sorted(getattr(app.state, "native_route_signatures", []))
    legacy_api_signatures = sorted(getattr(app.state, "legacy_api_signatures", []))
    native_override_signatures = sorted(getattr(app.state, "native_override_signatures", []))
    legacy_flask_only_signatures = sorted(getattr(app.state, "legacy_flask_only_signatures", []))
    return {
        "success": mount_error is None,
        "api_authority": "fastapi",
        "legacy_mount_enabled": bool(getattr(app.state, "legacy_mount_enabled", False)),
        "legacy_mount_failed": mount_error is not None,
        **({"legacy_mount_error": mount_error} if mount_error else {}),
        "legacy_api_fallback_allowed": bool(getattr(app.state, "legacy_api_fallback_allowed", False)),
        "native_paths": native_paths,
        "native_route_count": len(native_paths),
        "native_route_signatures": native_route_signatures,
        "legacy_api_paths": legacy_api_paths,
        "legacy_api_signatures": legacy_api_signatures,
        "legacy_api_route_count": int(getattr(app.state, "legacy_api_route_count", 0) or 0),
        "legacy_flask_only_signatures": legacy_flask_only_signatures,
        "legacy_flask_only_route_count": int(getattr(app.state, "legacy_flask_only_route_count", 0) or 0),
        "legacy_non_api_route_count": int(getattr(app.state, "legacy_non_api_route_count", 0) or 0),
        "native_override_signatures": native_override_signatures,
        "native_override_route_count": int(getattr(app.state, "native_override_route_count", 0) or 0),
    }
