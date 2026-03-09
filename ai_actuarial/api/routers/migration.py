from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/migration/status")
async def api_migration_status(request: Request) -> dict[str, object]:
    app = request.app
    native_paths = sorted(getattr(app.state, "native_paths", []))
    return {
        "success": True,
        "backend": "fastapi",
        "legacy_backend": getattr(app.state, "legacy_backend", "flask"),
        "legacy_mount_enabled": bool(getattr(app.state, "legacy_mount_enabled", False)),
        "legacy_mount_error": getattr(app.state, "legacy_mount_error", None),
        "native_paths": native_paths,
        "notes": [
            "FastAPI is the new backend gateway for the React frontend.",
            "Unported routes currently fall back to the legacy Flask application.",
            "Migration should replace legacy routes with native FastAPI routers incrementally.",
        ],
    }
