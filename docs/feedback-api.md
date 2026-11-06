# Feedback contract v1 — Issues #459, #460 and #461

This is the isolated/local backend contract. It does not enable production,
the widget, an inbox poller, schedules, or AI. Feedback business code is in
`ai_actuarial/feedback/`; shared capabilities live in the core API router.
No feedback operation imports Chat or invokes a model.

## Configuration

Each deployment sets its own `config/sites.yaml` (production uses the existing
external `CONFIG_PATH`) and restarts the API. Nonblank environment overrides
YAML; YAML overrides the defaults, through `resolve_runtime_features`.

| YAML `features` key | Environment override | Default |
| --- | --- | --- |
| `feedback_enabled` | `FEEDBACK_ENABLED` | `false` |
| `assistant_enabled` | `ASSISTANT_ENABLED` | `false` |
| `feedback_site_key` | `FEEDBACK_SITE_KEY` | empty |
| `feedback_rate_limit` | `FEEDBACK_RATE_LIMIT` | `5 per minute, 30 per hour` |

Enabled feedback requires a deployment site key matching
`[a-z0-9][a-z0-9_-]{0,63}`; missing/invalid identity rejects startup. The
tracked development template uses `local`. Set distinct real deployment keys,
such as `china` and `overseas`. Browsers cannot select their stored site.
Settings UI is not extended; configuration changes take effect on restart.

Feedback has its own user/IP rate bucket, using existing trusted proxy IP and
auth resolution. It is enforced even with `enable_rate_limiting: false`, and
does not consume Chat quota. Each valid configured rule has at most 1000
requests per window; an empty/invalid rule set falls back to the default.
Storage uses the existing process-local rate limiter (per API process, resets
on restart), with the same deployment limitations as that limiter.

`GET /api/support/capabilities` is public and returns only
`{"feedback_enabled":false,"assistant_enabled":false}` by default.
Feedback reflects the effective switch. Assistant stays `false` even when its
configuration is `true`, because no assistant implementation is available in
this Issue. It reveals no configuration paths, secrets, or KB inventory.
No assistant ask endpoint is introduced; existing Chat behavior is unchanged.
The complete implemented-module four-way integration belongs to #464.

## Submit

`POST /api/feedback` works anonymously or with existing signed session/token
authentication. Existing CSRF policy applies: browser clients first GET
capabilities (which issues the CSRF cookie when enabled), then copy the cookie
to `X-CSRF-Token`. Existing API-token CSRF exemption also applies.

```json
{
  "client_request_id": "f1b8f461-0111-4bdc-b1a0-f35c73f756b0",
  "content": "请增加按日期筛选功能。",
  "kind": "suggestion",
  "origin": "widget",
  "page_path": "/database?search=private#results",
  "locale": "zh-CN"
}
```

`client_request_id` is a client-created UUID, retained for all retries of one
submission. Trimmed content must have 1–4000 Unicode characters and no NUL.
`kind` is `suggestion|problem|other` (default `suggestion`); `origin` is
`widget|assistant` (default `widget`). Origin labels a submission source and
does not enable or call an assistant. `page_path` defaults to `/`, accepts
only a site-relative path of at most 2048 characters, and discards query and
fragment before storage. External/protocol-relative URLs, backslashes and
control characters are rejected. `locale` defaults to `en`, is a language tag
of 2–35 characters (for example `zh-CN`). Text fields do not coerce numbers.
Extra request fields are ignored; in particular client `user_id` and
`site_key` never override server identity. Email-account sessions persist
their account ID; anonymous visitors and legacy API tokens without an email
account have null `user_id`. No contact details are collected.

Only a successful database commit returns HTTP **201**, including replay:

```json
{"feedback_id":"f6ab7860-316a-4e8b-b62c-916bcbbeced0","status":"recorded","created_at":"2026-11-05T12:00:00+00:00"}
```

The receipt is public; it does not expose content or a read/list endpoint.
`status: recorded` describes the persisted receipt, independently of the
private workflow status. Same key and normalized fields/server site/account
return the identical receipt even after admin status changes. Reuse with any
different normalized request/site/account returns **409**
`IDEMPOTENCY_CONFLICT`. Equal content with distinct keys creates distinct rows.
After an uncertain network result the client retries with the same key; it
must not show success until it receives a 201 receipt.

Controlled failures use `{"error":{"code":"...","message":"..."}}`:

| HTTP | Code | Meaning |
| --- | --- | --- |
| 404 | `FEATURE_DISABLED` | Feedback disabled, including direct old-client POSTs |
| 422 | `INVALID_REQUEST` | Invalid submission fields |
| 409 | `IDEMPOTENCY_CONFLICT` | Key reused for a different request |
| 429 | `RATE_LIMITED` | No write; `Retry-After` header and `retry_after` seconds |
| 503 | `FEEDBACK_UNAVAILABLE` | No success receipt; retry with the same key |

Malformed JSON/missing body and invalid admin query/body parameters use the
existing FastAPI 422 `detail` validation response. Global CSRF failures use
the existing 403 `detail` response. Disabled feedback returns its stable 404
before CSRF/rate checks; admin history remains available.

## Admin inbox and status

Both routes use forced authentication even in public browse mode.
`feedback.read` and `feedback.manage` belong only to admin by default.
Anonymous callers get **401** `{"detail":"Unauthorized"}`; other roles get
**403** `{"detail":"Forbidden"}`. The existing signed email session and API
token mechanisms are supported.

`GET /api/admin/feedback?status=new&site_key=china&limit=50&cursor=0`
returns `{"items":[...],"next_cursor":123}`. Filters are optional. Limit is
1–100, default 50. Cursor is a nonnegative signed-64-bit internal ID, initially
0. Items sort ascending by immutable `id`, independent of equal timestamps or
mutable status. Fetch the next page with the returned cursor and unchanged
filters until `next_cursor` is null; no offset is used. The result is a live
list: filter changes or concurrent status changes can change membership.
The cursor is a page continuation, not a lossless durable sync watermark.
PostgreSQL allocates IDs before commit, so a lower ID can become visible after
a higher ID has already been observed. For #461, periodically scan from
cursor 0 and deduplicate by `feedback_id` to recover these late commits;
reconcile status updates on already ingested items as needed. A maximum
observed ID alone cannot guarantee complete ingestion.

The local consumer's commands, cached-state semantics and disabled scheduling
instructions are in [feedback-inbox.md](feedback-inbox.md).

Items include `id`, public/request UUIDs, `site_key`, immutable `content`,
`kind`, `origin`, nullable `user_id`, sanitized `page_path`, `locale`, `status`
and UTC ISO timestamps. The internal hash is not returned.

`PATCH /api/admin/feedback/{feedback_id}` takes only `{"status":"reviewed"}`.
Allowed explicit states are `new|reviewed|closed`, including reopening to
`new`; it returns the item. Extra fields (including `content`) are rejected.
It only changes status and `updated_at`; no AI rewrites are possible. Missing
UUID returns 404 `FEEDBACK_NOT_FOUND`. This route remains usable when intake
is disabled. There is no delete route.

The migration is `0007_feedback.sql`; the existing numbered PostgreSQL schema
runner owns the table, constraints and indexes. No additional DB service or
SQLite runtime is introduced. Automated checks:

```text
python -m pytest tests/test_fastapi_feedback_endpoints.py tests/test_feedback_storage.py
python -m ai_actuarial schema plan --json
python -m ai_actuarial schema apply --json
python -m ai_actuarial schema apply --json
```

Run these only against an explicitly isolated PostgreSQL 16 test database.
`tests/fixtures/feedback_contract.json` fixes request, receipt, pagination,
status and error examples for #460/#461. Local acceptance is recorded in
`reports/issue-459/acceptance.json` (the repository ignores `reports/`); the
manager retains full test/HTTP/PG evidence outside the disposable worktree.
