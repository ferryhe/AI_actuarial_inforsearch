from __future__ import annotations

import os

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/migration/status")
async def api_migration_status(request: Request) -> dict[str, object]:
    app = request.app
    native_paths = sorted(getattr(app.state, "native_paths", []))
    mount_error = getattr(app.state, "legacy_mount_error", None)
    expose_details = os.getenv("FASTAPI_EXPOSE_ERROR_DETAILS") == "1"
    return {
        "success": True,
        "backend": "fastapi",
        "legacy_backend": getattr(app.state, "legacy_backend", "flask"),
        "legacy_mount_enabled": bool(getattr(app.state, "legacy_mount_enabled", False)),
        "legacy_mount_failed": mount_error is not None,
        **({"legacy_mount_error": mount_error} if expose_details and mount_error else {}),
        "native_paths": native_paths,
        "notes": [
            "FastAPI is the new backend gateway for the React frontend.",
            "Unported routes currently fall back to the legacy Flask application.",
            "Migration should replace legacy routes with native FastAPI routers incrementally.",
        ],
    }
