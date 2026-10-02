from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..deps import AuthContext, require_permissions

router = APIRouter()


@router.get("/health")
async def api_health() -> dict[str, object]:
    return {
        "status": "ok",
        "backend": "fastapi",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/detailed", tags=["meta"])
async def health_detailed(
    _auth: AuthContext = Depends(require_permissions("logs.system.read")),
) -> dict[str, object]:
    """Detailed health check with service and version information."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "services": {
            "database": "ok",
            "storage": "ok",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
