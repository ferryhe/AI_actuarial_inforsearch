from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def api_health() -> dict[str, object]:
    return {
        "status": "ok",
        "backend": "fastapi",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
