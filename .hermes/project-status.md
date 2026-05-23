# Project Status

- Date: 2026-05-23
- Branch: codex/fix-gitee-sync-force-lease
- Scope: GitHub-to-Gitee sync workflow failure follow-up.
- Latest baseline: branch created from origin/main at 3b03c1e after PR #111 was merged.
- Security scan focus: tracked repository files for plaintext secrets, personal identifiers, runtime databases, deployment/server configuration, and CI secrets usage. Local `.env` files were not read.
- Security scan result: No real plaintext API keys, SSH private keys, or GitHub/Gitee tokens were found in tracked runtime configuration. Tracked `.env` files are limited to `.env.example`.
- Security follow-up: Removed the tracked 0-byte `config/storage.db` placeholder and ignored runtime database extensions to prevent accidental future commits of user/auth/provider data.
- Security hardening follow-up: Moving public deployment topology and production-only security policy into server-local environment variables; committed defaults should not expose real domains, fixed Docker bridge gateways, disabled CSRF, or empty CSP.
- Gitee sync: `.github/workflows/sync-gitee.yml` pushes GitHub `main` to `https://gitee.com/${GITEE_USER}/AI_actuarial_inforsearch.git` using GitHub repository variable `GITEE_USER` and repository secret `GITEE_TOKEN`; after the first main run failed in the push step, the workflow now fetches Gitee and uses `--force-with-lease` for the branch mirror instead of embedding credentials in the remote URL.
- GitHub Actions inspection: public API shows run 26335717916 failed in step `Push main and tags to Gitee`; `Configure Gitee credentials` succeeded.
- Model catalog follow-up: Updated `mistralai` pin to `1.12.4` and moved DeepSeek fallback models to current `deepseek-v4-flash` / `deepseek-v4-pro` while retaining legacy aliases for existing configs.
- CI follow-up: PR #111 `python-smoke` failed after enabling CSRF by default because the FastAPI-only auth roundtrip smoke test posted auth mutations without the frontend CSRF cookie/header flow. Updated the smoke test to seed `/api/auth/me` and send `X-CSRF-Token` on register/logout/login.
- PR: PR #111 was merged to main; this branch prepares a follow-up fix for the failed post-merge Gitee sync action.
- Verification: python -m pytest tests/test_gitee_sync_workflow_source.py -q; python -c YAML parse for .github/workflows/sync-gitee.yml; git diff --check.
- Verification gap: raw GitHub Actions logs could not be retrieved because local `gh` auth token is invalid; local Gitee `git ls-remote` could not run because Git for Windows Schannel reported `AcquireCredentialsHandle failed`.
- Pre-PR review gate: Blocked because `codex --help` fails with `Program 'codex.exe' failed to run: Access is denied`.
- Notes: No sibling repositories were read or modified.
