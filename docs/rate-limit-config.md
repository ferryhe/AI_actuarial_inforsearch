# Rate Limiting Configuration

## Overview

Rate limiting is implemented by `RateLimitMiddleware` in the FastAPI application. The runtime source is `config/sites.yaml -> features`; environment variables remain available only as deployment-level overrides.

There are two related policies:

1. **Role/default limits** for selected product API endpoints such as search, chat, chat conversation management, and collection runs.
2. **Auth credential-submission limits** for public login/register POSTs, keyed by endpoint and client IP before session mutation work starts.

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

For non-auth limited endpoints, the middleware applies both the role limit and any configured global defaults. A request is allowed only when all matching rules still have capacity.

Role-based defaults:

| Role | Limit |
|------|-------|
| `guest` | 10 requests/minute |
| `registered` | 30 requests/minute |
| `premium` | 60 requests/minute |
| `operator` | 200 requests/minute |
| `admin` | 999999 requests/minute |

`rate_limit_defaults` accepts comma-separated rules such as `200 per hour, 50 per minute`. Supported units are second, minute, hour, and day.

Role/default rate limiting is applied to these endpoints only:

- `/api/search`
- `/api/chat/query`
- `/api/chat/conversations`
- `/api/collections/run`

Agentic Chat is sent through `/api/chat/query` with `rag_mode="agentic"`, so it uses the same chat rate-limit and quota path as standard Chat. Direct ready_data read endpoints such as `/api/agentic-rag/search/summaries`, `/api/agentic-rag/search/sections`, and `/api/agentic-rag/trace/relations` require normal permissions but are not part of the role/default rate-limited endpoint list above today.

Auth credential-submission limiting is separate:

- `POST /api/auth/login`
- `POST /api/auth/register`

The auth rule is 5 requests/minute per endpoint and client IP. It runs before session mutation and intentionally does not consume chat/search role quota. `OPTIONS` preflight requests skip rate limiting. When `TRUST_PROXY=true`, the client IP helper honors the left-most `X-Forwarded-For` value; only enable that setting when direct API access is restricted to trusted reverse proxy traffic.

## Storage

`memory://` is the supported storage backend today. It is process-local and resets on restart. Unsupported storage URIs fall back to memory and log a warning, so do not use multi-instance API deployment with rate limiting enabled until a shared backend is added.

## Response Headers

Limited endpoints include rate-limit headers on allowed responses:

```text
X-RateLimit-Limit: 50
X-RateLimit-Remaining: 49
X-RateLimit-Reset: 60
```

When a non-auth endpoint is limited, the API returns `429 Too Many Requests` while preserving the historical human-readable detail shape:

```json
{
  "detail": "Rate limit exceeded. Limit: 50 requests/minute.",
  "retry_after": 60
}
```

When login/register is limited, the response includes a stable auth error marker for the React UI plus `Retry-After` and CORS headers when the request origin is allowed:

```json
{
  "detail": "Rate limit exceeded. Limit: 5 requests/minute.",
  "error": "rate_limit_exceeded",
  "retry_after": 60
}
```

The browser login/register pages map `429` to a localized “too many attempts, try again later” message and map `5xx` to a generic system-unavailable message.
