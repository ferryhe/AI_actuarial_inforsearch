from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from ai_actuarial.api.deps import AuthContext, require_permissions
from ai_actuarial.api.middleware.rate_limit import ROLE_RATE_LIMITS

router = APIRouter()

# Global metrics state (protected by _metrics_lock for thread safety)
_metrics_start_time: float = time.time()
_request_counts: dict[str, int] = defaultdict(int)
_total_requests: int = 0
_metrics_lock = threading.Lock()


def record_request(endpoint: str) -> None:
    """Record a request to an endpoint (thread-safe)."""
    global _total_requests
    with _metrics_lock:
        _total_requests += 1
        _request_counts[endpoint] += 1


def get_uptime_seconds() -> float:
    return time.time() - _metrics_start_time


@router.get("/metrics")
async def get_metrics(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("stats.read")),
) -> dict:
    """Return system metrics in JSON format (auth required)."""
    rate_limit_tiers = {}
    for role, limit in ROLE_RATE_LIMITS.items():
        rate_limit_tiers[role] = {"limit_per_minute": limit}

    with _metrics_lock:
        total = _total_requests
        by_endpoint = dict(_request_counts)

    return {
        "uptime_seconds": round(get_uptime_seconds(), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requests": {
            "total": total,
            "by_endpoint": by_endpoint,
        },
        "rate_limits": {
            "enabled": bool(getattr(request.app.state, "enable_rate_limiting", False)),
            "defaults": str(getattr(request.app.state, "rate_limit_defaults", "") or ""),
            "storage_uri": str(getattr(request.app.state, "rate_limit_storage_uri", "memory://") or "memory://"),
            "tiers": rate_limit_tiers,
        },
        "version": "0.1.0",
    }
