# Project Status

- Date: 2026-08-07
- Branch: `codex/agentic-search-web-listening`
- Baseline: `origin/main` at `a73bac6`.
- Scope: Prepare the next `agentic_search` iteration, using the existing `web_listening` tool path as the agent-driven information acquisition capability.

## Current State

- Local `main` was fast-forwarded from `32ebedd` to the latest GitHub `origin/main` at `a73bac6`.
- The task branch `codex/agentic-search-web-listening` was created from that clean baseline.
- `Agentic Site Monitoring` now has an SSRF-safe, bounded one-page exploration endpoint that observes same-domain page/file links and recommends tracking scope, acquisition tools, content types, queries, and a content selector without downloading files.
- The backward-compatible `web-listening-agent-rule.v1` contract now supports optional `crawler`/`search` acquisition tools and `file`/`webpage` content policies, then materializes them into the site YAML and scheduled full-pipeline task.
- Site YAML CRUD/read/sample management and both React configuration forms expose monitoring goal, path allow-list, search queries, file extensions, acquisition tools, content policy, selector, and schedule.
- Runtime collection honors explicit strategy: search-only sites skip direct crawling, crawler-only sites skip search fallback, linked-file collection can be disabled, and search-discovered pages can be stored as page content.
- Legacy site YAML remains compatible: omitted strategy fields retain prior crawler/file behavior, and the UI infers search only when legacy queries exist.
- Sibling repositories remain out of scope.

## Verification

- `git fetch origin main`: passed; discovered 51 newer commits.
- `git merge --ff-only origin/main`: passed.
- `git switch -c codex/agentic-search-web-listening`: passed.
- Baseline check: branch starts from `a73bac6`, matching `origin/main` before this status update.
- Focused regression suite: `107 passed` across rule, crawler, collector, task runtime, API, and React source tests.
- Frontend production build: passed; Vite reports the existing large-chunk advisory only.
- Browser smoke: passed against isolated local API/database; verified Agentic form strategy controls and enablement plus per-site YAML exploration/configuration controls, with no new console errors.
- `git diff --check`: passed.
- `python -m ruff check` surfaced six pre-existing lint findings outside the added lines (existing import order/unused imports); no task-scoped lint regression was identified.
- Mandatory Codex CLI review was attempted in normal and approved system-level execution, but WindowsApps returned `Access is denied` both times. A manual full-diff review found and fixed the legacy site/search inference and missing-query UI issue; final tests/build were rerun afterward.

## Local Notes

- Files in scope: rule/schema, crawler/collector/task runtime, site read/write APIs, the Agentic and site-manager React forms/i18n, focused tests, and this status file.
- No unrelated uncommitted or untracked files were present before implementation; browser smoke temporary files and processes were removed.
- Blocker: local Codex CLI executable access is denied by WindowsApps; this prevents the automated pre-PR review command but does not block tests, build, browser validation, or GitHub publication.
- GitHub authentication was refreshed and verified through the Windows keyring for `ferryhe` with `repo` and `workflow` scopes.
- Next action: commit the scoped implementation, push the task branch, create a draft PR, and evaluate CI plus remote review/Copilot comments after the required wait.
