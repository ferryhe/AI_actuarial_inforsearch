# Project Status

- Date: 2026-05-23
- Branch: codex/address-missed-review-comments
- Scope: Follow-up for missed Copilot review comments on merged PRs #107-#113.
- Latest baseline: origin/main at a2a1e3e after PR #112 was merged into main.
- Security scan focus: tracked repository files for plaintext secrets, personal identifiers, runtime databases, deployment/server configuration, and CI secrets usage. Local `.env` files were not read.
- Security scan result: No real plaintext API keys, SSH private keys, or GitHub/Gitee tokens were found in tracked runtime configuration. Tracked `.env` files are limited to `.env.example`.
- Security follow-up: Removed the tracked 0-byte `config/storage.db` placeholder and ignored runtime database extensions to prevent accidental future commits of user/auth/provider data.
- Security hardening follow-up: Moving public deployment topology and production-only security policy into server-local environment variables; committed defaults should not expose real domains, fixed Docker bridge gateways, disabled CSRF, or empty CSP.
- Gitee sync: PR #112 was merged; `.github/workflows/sync-gitee.yml` now fetches Gitee and uses `--force-with-lease` for the branch mirror instead of embedding credentials in the remote URL.
- Review follow-up: Verified PR #107 Caddy log path/healthcheck loopback, PR #108 markdown response typing, and PR #109 page-jump integer parsing are already addressed on main.
- Review follow-up: Addressing remaining PR #111/#113 comments by using container-safe `FASTAPI_HOST=0.0.0.0` in the Docker entrypoint, defaulting `TRUST_PROXY` to false unless explicitly enabled, removing duplicated inline CSP defaults from Compose, using PEP 440-aware version parsing for the `mistralai` guard, and clarifying CSP pass-through docs.
- Model catalog follow-up: Updated `mistralai` pin to `1.12.4` and moved DeepSeek fallback models to current `deepseek-v4-flash` / `deepseek-v4-pro` while retaining legacy aliases for existing configs.
- CI follow-up: PR #111 `python-smoke` failed after enabling CSRF by default because the FastAPI-only auth roundtrip smoke test posted auth mutations without the frontend CSRF cookie/header flow. Updated the smoke test to seed `/api/auth/me` and send `X-CSRF-Token` on register/logout/login.
- PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/113
- Verification: python -m pytest tests/test_deployment_config_source.py tests/test_dependency_versions.py tests/test_gitee_sync_workflow_source.py -q; python -c YAML parse for docker-compose.yml, docker-compose.override.yml, config/sites.yaml, and .github/workflows/sync-gitee.yml; rg checks for conflict markers and removed unsafe/obsolete patterns; git diff --check.
- Verification gap: `docker compose config` could not run locally because Docker is not installed on this Windows environment; raw GitHub Actions logs could not be retrieved because local `gh` auth token is invalid.
- Pre-PR review gate: Blocked because `codex --help` fails with `Program 'codex.exe' failed to run: Access is denied`.
- Notes: No sibling repositories were read or modified.
