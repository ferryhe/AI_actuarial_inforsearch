# Rate Limiting Configuration

## Overview

Rate limiting is implemented via `RateLimitMiddleware` in the FastAPI application. It protects the API from abuse and ensures fair usage across clients.

## Configuration

Rate limiting is controlled via environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Enable/disable rate limiting | `true` |
| `RATE_LIMIT_STORAGE` | Storage backend (`memory`, `redis`) | `memory` |
| `RATE_LIMIT_DEFAULT` | Default requests per window | `100` |
| `RATE_LIMIT_WINDOW` | Time window in seconds | `60` |

## Rate Limit Headers

All API responses include rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1713500000
```

## Per-Endpoint Limits

| Endpoint Group | Limit | Window |
|----------------|-------|--------|
| `/api/auth/*` | 20 req | 60s |
| `/api/chat/*` | 30 req | 60s |
| `/api/read/*` | 100 req | 60s |
| `/api/meta/*` | 200 req | 60s |
| All others | `RATE_LIMIT_DEFAULT` | `RATE_LIMIT_WINDOW` |

## Error Response

When rate limited, the API returns `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded. Try again in 45 seconds."
}
```

## Implementation Notes

- Rate limit counters are stored in memory by default (not shared across processes)
- For multi-instance deployments, use Redis as the storage backend
- The middleware runs after CORS middleware in the FastAPI stack
- Health check endpoints (`/api/meta/health`) are exempt from rate limiting
