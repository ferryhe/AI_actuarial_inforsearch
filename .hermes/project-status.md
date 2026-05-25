# Project Status

- Date: 2026-05-25
- Branch: `docs/security-rollout-completion`
- Latest baseline: `origin/main` at merged PR #122 (`fix: rate limit auth submissions`).
- Scope: documentation completion audit after security/RBAC rollout PRs #118-#122 were merged. Sibling repositories were not read or modified.
- Repo/PR audit: `gh pr list --state open` returned no open PRs; recent merged rollout PRs #118, #119, #120, #121, #122 are present on `origin/main`.
- README refresh: root English and Chinese READMEs now describe the current FastAPI + React stack, merged security rollout status, browser-upload file import contract, Chat/RAG source bounds, auth rate limiting, and current verification commands.
- Security docs refresh: `SECURITY.md` now reflects maintained FastAPI + React posture, auth/RBAC, encrypted credentials, SSRF/file import/Chat-RAG boundaries, production checklist, and security-focused test commands.
- Rate-limit docs refresh: `docs/rate-limit-config.md` now documents role/default endpoint limits plus separate login/register IP-scoped auth limits, `Retry-After`, CORS/preflight behavior, and `TRUST_PROXY` semantics.
- Docs index refresh: `docs/README.md` now points to current references and explains archive areas.
- Archive moves: stale Flask-era security review docs, stale quick-start/modular/chatbot roadmap guides, completed FastAPI migration plans, and the completed February hardening plan were moved under `docs/archive/` with archive notes.
- Link cleanup: updated moved-document references in impacted implementation/API token docs.
- Verification passed: repo-level markdown link checker over 143 Markdown files found 0 missing non-code internal links.
- Verification passed: `git diff --check`.
- Local Codex review gate: first pass found two doc issues (server-path import wording and archived roadmap references); both were fixed. Second pass found no discrete actionable issues.
- Next step: commit/push/create PR for documentation completion audit.
