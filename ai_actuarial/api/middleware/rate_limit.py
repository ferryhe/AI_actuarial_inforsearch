"""
Rate limiting middleware for FastAPI.

Applies per-user rate limits based on user role:
- guest: 10 requests/minute
- registered: 30 requests/minute
- premium: 60 requests/minute
- operator: 200 requests/minute

Applies to search and chat endpoints by default.
"""
from __future__ import annotations

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


# Rate limits per minute by role
ROLE_RATE_LIMITS: dict[str, int] = {
    "guest": 10,
    "registered": 30,
    "premium": 60,
    "operator": 200,
    "admin": 999999,
}

# Default rate limit for unknown roles
DEFAULT_RATE_LIMIT = 10

# Endpoints to apply rate limiting
RATE_LIMITED_PATHS = [
    "/api/search",
    "/api/chat/query",
    "/api/chat/conversations",
    "/api/collections/run",
]


@dataclass
class RateLimitBucket:
    """Sliding window rate limit bucket."""
    timestamps: list[float] = field(default_factory=list)

    def is_allowed(self, limit: int, window_seconds: int = 60) -> bool:
        """Check if a request is allowed under the rate limit."""
        now = time.time()
        # Remove timestamps outside the window
        self.timestamps = [ts for ts in self.timestamps if now - ts < window_seconds]
        if len(self.timestamps) >= limit:
            return False
        self.timestamps.append(now)
        return True

    def remaining(self, limit: int, window_seconds: int = 60) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        self.timestamps = [ts for ts in self.timestamps if now - ts < window_seconds]
        return max(0, limit - len(self.timestamps))


class RateLimitStore:
    """In-memory rate limit store per user."""

    def __init__(self) -> None:
        self._buckets: dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self._cleanup_thread_started = False

    def get_bucket(self, key: str) -> RateLimitBucket:
        return self._buckets[key]

    def clear_expired(self) -> None:
        """Clear expired entries to prevent memory growth."""
        now = time.time()
        for key in list(self._buckets.keys()):
            bucket = self._buckets[key]
            bucket.timestamps = [ts for ts in bucket.timestamps if now - ts < 60]
            if not bucket.timestamps:
                del self._buckets[key]

    def _start_cleanup_thread(self) -> None:
        """Start background cleanup thread if not already running."""
        import threading
        if self._cleanup_thread_started:
            return
        self._cleanup_thread_started = True

        def cleanup_loop() -> None:
            while True:
                time.sleep(300)  # Run cleanup every 5 minutes
                self.clear_expired()

        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()


# Global rate limit store
_rate_limit_store: RateLimitStore | None = None


def get_rate_limit_store() -> RateLimitStore:
    global _rate_limit_store
    if _rate_limit_store is None:
        _rate_limit_store = RateLimitStore()
        _rate_limit_store._start_cleanup_thread()
    return _rate_limit_store


def _get_user_role(request: Request) -> str:
    """Extract user role from the request auth context."""
    try:
        # Try to get auth context from request state
        auth_context = getattr(request.state, "auth_context", None)
        if auth_context is not None:
            token = getattr(auth_context, "token", None)
            if token is not None:
                group_name = token.get("group_name", "")
                if group_name in ROLE_RATE_LIMITS:
                    return group_name
    except Exception:
        pass

    # Try to get role from session
    try:
        session_data = getattr(request.state, "_fastapi_session_data", {})
        if isinstance(session_data, dict):
            role = session_data.get("role", "")
            if role in ROLE_RATE_LIMITS:
                return role
    except Exception:
        pass

    return "guest"


def _get_rate_limit_key(request: Request) -> str:
    """Generate a unique key for rate limiting."""
    # Try to get user ID from auth context
    try:
        auth_context = getattr(request.state, "auth_context", None)
        if auth_context is not None:
            token = getattr(auth_context, "token", None)
            if token is not None:
                email_user_id = token.get("_email_user_id")
                if email_user_id is not None:
                    return f"user:{email_user_id}"
                subject = token.get("subject", "")
                if subject:
                    return f"token:{subject}"
    except Exception:
        pass

    # Fall back to IP address
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _should_rate_limit(request: Request) -> bool:
    """Check if the request path should be rate limited."""
    path = request.url.path
    return any(path.startswith(p) for p in RATE_LIMITED_PATHS)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for FastAPI.

    Applies per-user rate limits based on user role.
    Only applies to configured paths (search, chat, collections).
    """

    def __init__(
        self,
        app: Callable,
        store: RateLimitStore | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.store = store or get_rate_limit_store()
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        if not _should_rate_limit(request):
            return await call_next(request)

        role = _get_user_role(request)
        limit = ROLE_RATE_LIMITS.get(role, DEFAULT_RATE_LIMIT)
        key = _get_rate_limit_key(request)
        bucket = self.store.get_bucket(key)

        # Calculate remaining BEFORE the request for accurate header
        remaining = bucket.remaining(limit)

        if not bucket.is_allowed(limit):
            logger.warning(f"Rate limit exceeded for {key} (role: {role})")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Limit: {limit} requests/minute for {role} role.",
            )

        try:
            response = await call_next(request)
        finally:
            # Add rate limit headers (remaining may have changed after request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(bucket.remaining(limit))
            response.headers["X-RateLimit-Reset"] = "60"

        return response
