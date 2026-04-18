from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ai_actuarial.api.deps import get_auth_context
from ai_actuarial.api.middleware.rate_limit import ROLE_RATE_LIMITS
from ai_actuarial.config import settings

router = APIRouter()

# Global metrics state
_metrics_start_time: float = time.time()
_request_counts: dict[str, int] = defaultdict(int)
_total_requests: int = 0


def record_request(endpoint: str) -> None:
    """Record a request to an endpoint."""
    global _total_requests
    _total_requests += 1
    _request_counts[endpoint] += 1


def get_uptime_seconds() -> float:
    return time.time() - _metrics_start_time


@router.get("/metrics")
async def get_metrics(request: Request) -> dict:
    """Return system metrics in JSON format."""
    # Resolve auth context to determine rate limit tier
    rate_limit_tiers = {}
    try:
        auth_context = get_auth_context(request)
        if auth_context.token is not None:
            group_name = auth_context.token.get("group_name", "guest")
        else:
            group_name = "guest"
    except Exception:
        group_name = "guest"

    for role, limit in ROLE_RATE_LIMITS.items():
        rate_limit_tiers[role] = {"limit_per_minute": limit}

    return {
        "uptime_seconds": round(get_uptime_seconds(), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requests": {
            "total": _total_requests,
            "by_endpoint": dict(_request_counts),
        },
        "rate_limits": {
            "enabled": settings.RATE_LIMIT_ENABLED,
            "tiers": rate_limit_tiers,
        },
        "version": "0.1.0",
    }
