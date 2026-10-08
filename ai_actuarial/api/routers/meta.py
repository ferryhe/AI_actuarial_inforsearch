from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ai_actuarial.build_info import detailed_build_info, public_build_info

from ..deps import AuthContext, require_authenticated_permissions

router = APIRouter()


@router.get("/health")
async def api_health() -> dict[str, object]:
    return {
        "status": "ok",
        "backend": "fastapi",
        "build_info": public_build_info(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/detailed", tags=["meta"])
async def health_detailed(
    _auth: AuthContext = Depends(require_authenticated_permissions("logs.system.read")),
) -> dict[str, object]:
    """Detailed health check with service and version information."""
    return {
        "status": "healthy",
        "version": public_build_info()["release_manifest_id"],
        "build_info": detailed_build_info(),
        "services": {
            "database": "ok",
            "storage": "ok",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
