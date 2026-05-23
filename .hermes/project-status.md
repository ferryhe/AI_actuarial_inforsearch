# Project Status

- Date: 2026-05-23
- Branch: codex/security-scan-gitee-sync
- Scope: Repository configuration exposure scan and GitHub-to-Gitee sync workflow.
- Latest baseline: main fast-forwarded to origin/main at 93a710f before branching.
- Security scan focus: tracked repository files for plaintext secrets, personal identifiers, runtime databases, deployment/server configuration, and CI secrets usage. Local `.env` files were not read.
- Security scan result: No real plaintext API keys, SSH private keys, or GitHub/Gitee tokens were found in tracked runtime configuration. Tracked `.env` files are limited to `.env.example`.
- Security follow-up: Removed the tracked 0-byte `config/storage.db` placeholder and ignored runtime database extensions to prevent accidental future commits of user/auth/provider data.
- Security hardening follow-up: Moving public deployment topology and production-only security policy into server-local environment variables; committed defaults should not expose real domains, fixed Docker bridge gateways, disabled CSRF, or empty CSP.
- Gitee sync: Added `.github/workflows/sync-gitee.yml` to push GitHub `main` and tags to `https://gitee.com/${GITEE_USER}/AI_actuarial_inforsearch.git` using GitHub repository variable `GITEE_USER` and repository secret `GITEE_TOKEN`.
- PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/111 (draft, open, mergeable; python-smoke pending after latest push).
- Verification: python -m pytest tests/test_deployment_config_source.py tests/test_gitee_sync_workflow_source.py tests/test_yaml_config.py tests/test_auth_react_source.py -q; python -c YAML parse for docker-compose.yml, docker-compose.override.yml, and config/sites.yaml; rg checks for removed public topology values; git diff --check.
- Verification gap: `docker compose config` could not run locally because Docker is not installed on this Windows environment.
- Pre-PR review gate: Blocked because `codex --help` fails with `Program 'codex.exe' failed to run: Access is denied`.
- Notes: No sibling repositories were read or modified.
