# Project Status

- Date: 2026-05-24
- Branch: `feat/ssrf-url-safety`
- Latest baseline: latest `origin/main` when this branch was created after PR118 merged.
- Scope: PR2 security hardening for SSRF protection on user/crawler URLs. Sibling repositories were not read or modified.
- Backend security: Added centralized `ai_actuarial.security.url_safety` validator for HTTP/HTTPS-only URL validation, malformed URL/port normalization, localhost/private/link-local/metadata/non-global IP rejection, and DNS resolution checks.
- Backend security: Site configuration writes now validate URLs on add/update/import/preview paths and map unsafe URLs to controlled ops-write validation errors instead of server errors.
- Crawler security: `Crawler._request` and `_download_file` now validate each request and each redirect hop, manually enforce redirect revalidation, and reject unsafe redirects.
- Crawler security: Removed crawler fetch/download use of independent DNS resolution clients. Actual connections are opened directly to the already validated IP address while preserving the original host for Host/SNI, avoiding DNS-rebinding gaps without process-global DNS monkey-patching.
- Crawler security: Web page collection now reuses the crawler request path instead of calling `urllib.request.urlopen` directly, so page fetches inherit URL validation, redirect revalidation, and DNS pinning.
- Follow-up fix: Local Codex review found IPv6 literal Host headers needed bracket preservation in the pinned HTTP path; fixed and covered with a regression test.
- Tests: Added `tests/test_url_safety.py` covering public URL allow, scheme/local/private/metadata blocking, private DNS blocking, malformed URLs, invalid ports, crawler DNS pinning handoff, redirect-to-private rejection for request/download paths, and IPv6 literal Host header formatting.
- Tests: Extended FastAPI ops-write endpoint tests to cover unsafe site URL rejection in add/update/import flows with deterministic public DNS resolver fixtures.
- Tests: Extended WebPageCollector tests to prove `_fetch_html` uses `Crawler._request` and rejects unsafe loopback URLs before network access.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/test_url_safety.py tests/test_web_page_collector.py tests/test_fastapi_ops_write_endpoints.py tests/test_crawler_allow_patterns.py -q && git diff --check` (55 passed, 3 warnings).
- Full suite status: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest -q` currently reports 462 passed, 11 failed, 4 warnings. Failures are in pre-existing non-SSRF areas (`ai_actuarial/web` cleanup expectations, FastAPI entrypoint 503 responses, one RAG admin dirty-state assertion, and safe-pickle tests); no evidence links them to this PR2 SSRF diff.
- Local Codex review gate: Latest `codex -c 'model="gpt-5.5"' review --uncommitted` completed with no discrete correctness/security/maintainability issues after the IPv6 Host header fix.
- Next step: commit, push, create the PR from `feat/ssrf-url-safety`, then check remote Copilot/comments after the requested wait window.
