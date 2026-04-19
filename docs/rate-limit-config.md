# Rate Limiting Configuration

## Overview

Rate limiting is implemented via `RateLimitMiddleware` in the FastAPI application. It protects the API from abuse and ensures fair usage across clients.

## Configuration

Rate limiting is controlled via environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Enable/disable rate limiting | `true` |
| `RATE_LIMIT_PER_MINUTE` | Default requests per minute for unknown roles | `60` |
| `RATE_LIMIT_BURST` | Burst limit | `10` |

## Rate Limit Headers

Rate limit headers are attached to responses from limited endpoints only (not all endpoints):

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 60
```

## Role-Based Limits

Rate limits are applied per-user based on authenticated role:

| Role | Limit | Window |
|------|-------|--------|
| `guest` | 10 req | 60s |
| `registered` | 30 req | 60s |
| `premium` | 60 req | 60s |
| `operator` | 200 req | 60s |
| `admin` | 999,999 req | — |

Rate limiting is applied to these endpoints only: `/api/search`, `/api/chat/query`, `/api/chat/conversations`, `/api/collections/run`.

## Error Response

When rate limited, the API returns `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded. Limit: 30 requests/minute for registered role."
}
```

## Implementation Notes

- Rate limit counters are stored in memory by default (not shared across processes)
- For multi-instance deployments, use Redis as the storage backend
- The middleware runs after CORS middleware in the FastAPI stack
- Health check endpoints (`/api/health`) are exempt from rate limiting
