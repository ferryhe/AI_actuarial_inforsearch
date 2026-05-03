# Rate Limiting Configuration

## Overview

Rate limiting is implemented by `RateLimitMiddleware` in the FastAPI application. The runtime source is `config/sites.yaml -> features`; environment variables remain available only as deployment-level overrides.

## Configuration

Admins can edit these values from Settings, or directly in `config/sites.yaml`:

```yaml
features:
  enable_rate_limiting: true
  rate_limit_defaults: 200 per hour, 50 per minute
  rate_limit_storage_uri: memory://
```

`RATE_LIMIT_DEFAULTS` and `RATE_LIMIT_STORAGE_URI` override YAML when set in the process environment. The Settings page marks env-controlled values as locked because saving YAML cannot override a live environment variable.

## Rule Semantics

The middleware applies both role limits and global defaults. A request is allowed only when all matching rules still have capacity.

Role-based defaults:

| Role | Limit |
|------|-------|
| `guest` | 10 requests/minute |
| `registered` | 30 requests/minute |
| `premium` | 60 requests/minute |
| `operator` | 200 requests/minute |
| `admin` | 999999 requests/minute |

`rate_limit_defaults` accepts comma-separated rules such as `200 per hour, 50 per minute`. Supported units are second, minute, hour, and day.

Rate limiting is applied to these endpoints only: `/api/search`, `/api/chat/query`, `/api/chat/conversations`, `/api/collections/run`.

## Storage

`memory://` is the supported storage backend today. It is process-local and resets on restart. Unsupported storage URIs fall back to memory and log a warning, so do not use multi-instance API deployment with rate limiting enabled until a shared backend is added.

## Response Headers

Limited endpoints include rate-limit headers:

```text
X-RateLimit-Limit: 50
X-RateLimit-Remaining: 49
X-RateLimit-Reset: 60
```

When rate limited, the API returns `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded. Limit: 50 requests/minute for guest role."
}
```
