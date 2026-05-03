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

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.responses import Response

from ai_actuarial.api.deps import get_auth_context

logger = logging.getLogger(__name__)


# Rate limits per minute by role
ROLE_RATE_LIMITS: dict[str, int] = {
    "guest": 10,
    "registered": 30,
    "premium": 60,
    "operator": 200,
    "admin": 999999,
}

# Default rate limit for unknown roles, applied as a role floor. Runtime
# defaults from config/sites.yaml -> features add an additional global cap.
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

    def prune(self, now: float, window_seconds: int) -> None:
        self.timestamps = [ts for ts in self.timestamps if now - ts < window_seconds]

    def is_allowed(self, limit: int, window_seconds: int, now: float | None = None) -> bool:
        """Check if a request is allowed under the rate limit."""
        effective_now = time.time() if now is None else now
        self.prune(effective_now, window_seconds)
        return len(self.timestamps) < limit

    def add(self, now: float) -> None:
        self.timestamps.append(now)

    def remaining(self, limit: int, window_seconds: int = 60, now: float | None = None) -> int:
        """Get remaining requests in the current window."""
        effective_now = time.time() if now is None else now
        self.prune(effective_now, window_seconds)
        return max(0, limit - len(self.timestamps))


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int
    label: str


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


_rate_limit_stores: dict[str, RateLimitStore] = {}
_unsupported_storage_uri_warnings: set[str] = set()


def _normalize_storage_uri(storage_uri: str | None) -> str:
    raw = str(storage_uri or "memory://").strip() or "memory://"
    if raw.startswith("memory://"):
        return raw
    if raw not in _unsupported_storage_uri_warnings:
        logger.warning("Unsupported rate limit storage URI %r; using in-memory store", raw)
        _unsupported_storage_uri_warnings.add(raw)
    return "memory://"


def get_rate_limit_store(storage_uri: str | None = None) -> RateLimitStore:
    normalized = _normalize_storage_uri(storage_uri)
    store = _rate_limit_stores.get(normalized)
    if store is None:
        store = RateLimitStore()
        store._start_cleanup_thread()
        _rate_limit_stores[normalized] = store
    return store


_RATE_LIMIT_PATTERN = re.compile(
    r"^\s*(?P<limit>\d+)\s*(?:requests?|reqs?)?\s*(?:/|per)\s*"
    r"(?P<window>second|minute|hour|day|seconds|minutes|hours|days)\s*$",
    re.IGNORECASE,
)


def parse_rate_limit_rules(raw: str | None) -> list[RateLimitRule]:
    """Parse strings like '200 per hour, 50 per minute' into runtime rules."""
    if not raw:
        return []
    windows = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
    }
    labels = {
        1: "second",
        60: "minute",
        3600: "hour",
        86400: "day",
    }
    rules: list[RateLimitRule] = []
    for part in str(raw).split(","):
        match = _RATE_LIMIT_PATTERN.match(part)
        if not match:
            logger.warning("Ignoring invalid rate limit rule: %r", part.strip())
            continue
        limit = int(match.group("limit"))
        window_seconds = windows[match.group("window").lower()]
        if limit < 1:
            continue
        rules.append(RateLimitRule(limit=limit, window_seconds=window_seconds, label=labels[window_seconds]))
    return rules


def _get_user_role(request: Request) -> str:
    """Extract user role from the request auth context."""
    try:
        # Call get_auth_context to properly load auth context in middleware
        # (request.state.auth_context is set by require_permissions dependency, which runs after middleware)
        auth_context = get_auth_context(request)
        if auth_context.token is not None:
            group_name = auth_context.token.get("group_name", "")
            if group_name in ROLE_RATE_LIMITS:
                return group_name
    except Exception:
        pass

    return "guest"


def _get_rate_limit_key(request: Request) -> str:
    """Generate a unique key for rate limiting."""
    try:
        # Call get_auth_context to properly load auth context in middleware
        auth_context = get_auth_context(request)
        if auth_context.token is not None:
            email_user_id = auth_context.token.get("_email_user_id")
            if email_user_id is not None:
                return f"user:{email_user_id}"
            subject = auth_context.token.get("subject", "")
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
        enabled: bool | None = True,
    ) -> None:
        super().__init__(app)
        self.store = store
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        enabled = bool(getattr(request.app.state, "enable_rate_limiting", False)) if self.enabled is None else bool(self.enabled)
        if not enabled:
            return await call_next(request)

        if not _should_rate_limit(request):
            return await call_next(request)

        role = _get_user_role(request)
        role_limit = ROLE_RATE_LIMITS.get(role, DEFAULT_RATE_LIMIT)
        rules = [RateLimitRule(limit=role_limit, window_seconds=60, label="minute")]
        rules.extend(parse_rate_limit_rules(getattr(request.app.state, "rate_limit_defaults", "")))
        key = _get_rate_limit_key(request)
        store = self.store
        if store is None:
            store = get_rate_limit_store(getattr(request.app.state, "rate_limit_storage_uri", "memory://"))
        now = time.time()

        buckets: list[tuple[RateLimitRule, RateLimitBucket]] = []
        for rule in rules:
            bucket = store.get_bucket(f"{key}:{rule.window_seconds}:{rule.limit}")
            buckets.append((rule, bucket))
            if not bucket.is_allowed(rule.limit, rule.window_seconds, now=now):
                logger.warning("Rate limit exceeded for %s (role: %s)", key, role)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded. Limit: {rule.limit} requests/{rule.label} for {role} role."
                    },
                )

        for _rule, bucket in buckets:
            bucket.add(now)

        response = None
        try:
            response = await call_next(request)
        finally:
            if response is not None:
                remaining_by_rule = [
                    (
                        rule,
                        bucket.remaining(rule.limit, rule.window_seconds, now=now),
                    )
                    for rule, bucket in buckets
                ]
                active_rule, remaining = min(remaining_by_rule, key=lambda item: item[1])
                response.headers["X-RateLimit-Limit"] = str(active_rule.limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(active_rule.window_seconds)

        return response
