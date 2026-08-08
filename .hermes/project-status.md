# Project Status

- Date: 2026-08-07
- Branch: `agent/respectful-crawler-requests`
- Baseline: `origin/main` at `a455b36` (merged PR `#170`).
- Scope: Repair the shared request path used by Site Configuration, Web Crawl, Ad-hoc URL, and Web Search after PR `#119`; Agentic Site Monitoring remains out of scope.

## Current State

- The crawler again uses `curl_cffi` browser-compatible TLS/HTTP2 behavior while retaining the configured, transparent project user agent.
- Every URL and redirect hop still goes through the SSRF validator. `CURLOPT_RESOLVE` pins the validated public IP and environment proxies are disabled so the request cannot bypass that pin.
- Redirects remain manual, sessions are reused per validated origin/address, and IPv4 is tried before IPv6 with IPv6 retained as fallback.
- All actual page, redirect, retry, and file-download requests use per-origin randomized pacing. `delay_seconds` is the minimum and the jittered interval is between 1.0x and 1.5x that value.
- `max_pages` is now a hard page-attempt limit, including failed/timed-out BFS pages. Crawl diagnostics include page attempts, request attempts, file-download attempts, dedup skips, and request errors.
- Site Configuration, Web Crawl, Ad-hoc URL, Web Search, and the CLI update path now pass their configured delay into the shared request layer.
- CLI site configuration now preserves and honors `acquisition_tools`, matching the native task runtime.
- SOA's main profile is search-only. Its two focused crawler profiles are restricted to anchored `soa.org` research/globalassets URL patterns, use a 2-second minimum delay, and share a total 30-page attempt budget (25 + 5).
- Draft PR `#171` is open from commit `e8a44a8`.

## Verification

- Test-first request-policy suite: the 8 initial assertions failed before implementation; the expanded suite now has 9 passing tests.
- Focused and integration regression suite: `127 passed` across crawler policy, URL safety, allow patterns, scheduled/URL collection, task runtime, stop support, site configuration APIs, and web-listening materialization.
- Full test suite: `703 passed`, with 5 unrelated baseline/environment failures. One SQLite migration test reproducibly leaves a failed transaction handle open before deleting its Windows temp DB; four frontend source tests invoke `npm` without the required `.cmd` suffix under Python `subprocess` on Windows.
- Targeted Ruff checks for the new crawler policy and new tests: passed.
- CLI checks: `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; `config/sites.yaml` loaded successfully with 32 sites and 3 SOA profiles.
- Live, one-request canaries through the new pinned curl transport: SOA AI Topic, AAA, and CAS all returned successful HTML responses.
- `git diff --check`: passed.
- Mandatory Codex CLI review: passed with no actionable findings; the reviewer independently reran 28 request-policy, URL-safety, and crawler tests.

## Local Notes

- Files in scope: shared crawler transport/pacing, CLI/runtime/collector wiring, SOA site configuration, focused tests, and this status file.
- No unrelated local changes were present before implementation.
- Sibling repositories were not read or modified.
- Next action: inspect PR `#171` checks and remote Copilot/review comments after the required observation window.
