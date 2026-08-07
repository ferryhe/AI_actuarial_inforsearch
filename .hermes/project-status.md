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
- Draft PR `#169` was created at `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/169`; its last reviewed head is `832855d`.
- A user-authorized, read-only contract audit was completed against sibling repository `C:\Project\web_listening`; no sibling files were changed and its local `main` remained clean.
- The audit established that this PR's `web-listening-agent-rule.v1` is an application-layer prototype, not the canonical `web_listening` contract. Formal execution in `web_listening` binds a monitor scope, `acquisition-profile.v1`, and a versioned `site-skill.v1` package with exact version/hash/executor fields.
- PR `#169` should therefore remain Draft and should not be merged unchanged as the final integration. `AI_actuarial_inforsearch` should ultimately consume `web_listening` through MCP/API and persist job/scope/manifest identities instead of owning a second crawler/search/YAML authority.

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
- The post-PR review performed more than 15 minutes after creation passed: PR is open, Draft, and mergeable; CI run `31189169343` completed successfully; no PR comments, reviews, or unresolved review threads were present.

## Local Notes

- Files in scope: rule/schema, crawler/collector/task runtime, site read/write APIs, the Agentic and site-manager React forms/i18n, focused tests, and this status file. The sibling audit was read-only.
- No unrelated uncommitted or untracked files were present before implementation; browser smoke temporary files and processes were removed.
- Blocker: local Codex CLI executable access is denied by WindowsApps; this prevents the automated pre-PR review command but does not block tests, build, browser validation, or GitHub publication.
- GitHub authentication was refreshed and verified through the Windows keyring for `ferryhe` with `repo` and `workflow` scopes.
- Architecture decision: move the next implementation phase to `C:\Project\web_listening`. Add missing planning/Site Skill/health service APIs first, then a minimal local three-page UI for Explore & Build Skill, Run by Skill, and Evidence & Content. Keep the skill-maintenance health loop independent from the pinned work-agent execution loop.
- Next action: switch the writable workspace to `C:\Project\web_listening`, update its `main`, and implement the work as staged PRs before replacing this application's prototype runtime with a thin MCP/API adapter.
