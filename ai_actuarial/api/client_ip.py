from __future__ import annotations

from fastapi import Request

from ai_actuarial.config import settings


def client_ip(request: Request) -> str:
    """Return the request client IP, honoring trusted X-Forwarded-For when enabled."""
    if settings.TRUST_PROXY:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    client = request.client.host if request.client else None
    return client or "unknown"
