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
    inventory_enabled = _migration_inventory_enabled()
    return {
        "success": True,
        "backend": "fastapi",
        "api_authority": "fastapi",
        "runtime_mode": "fastapi_only",
        "legacy_runtime_present": False,
        "native_paths": native_paths,
        "legacy_api_fallback_allowed": bool(getattr(app.state, "legacy_api_fallback_allowed", False)),
        "migration_inventory_enabled": inventory_enabled,
        "notes": [
            "FastAPI is the current product API authority for /api routes.",
            "The FastAPI runtime no longer mounts the legacy Flask application.",
            "Legacy Flask /api fallback is blocked by default; enable FASTAPI_ALLOW_LEGACY_API_FALLBACK=1 only for historical debugging.",
        ],
    }


@router.get("/migration/inventory")
async def api_migration_inventory(request: Request) -> dict[str, object]:
    if not _migration_inventory_enabled():
        raise HTTPException(status_code=404, detail="Migration inventory is disabled")

    app = request.app
    native_paths = sorted(getattr(app.state, "native_paths", []))
    native_route_signatures = sorted(getattr(app.state, "native_route_signatures", []))
    return {
        "success": True,
        "api_authority": "fastapi",
        "runtime_mode": "fastapi_only",
        "legacy_runtime_present": False,
        "legacy_api_fallback_allowed": bool(getattr(app.state, "legacy_api_fallback_allowed", False)),
        "native_paths": native_paths,
        "native_route_count": len(native_paths),
        "native_route_signatures": native_route_signatures,
    }
