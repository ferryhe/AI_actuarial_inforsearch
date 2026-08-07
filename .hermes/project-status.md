# Project Status

- Date: 2026-08-07
- Branch: `codex/agentic-search-web-listening`
- Baseline: `origin/main` at `a73bac6`.
- Scope: Prepare the next `agentic_search` iteration, using the existing `web_listening` tool path as the agent-driven information acquisition capability.

## Current State

- Local `main` was fast-forwarded from `32ebedd` to the latest GitHub `origin/main` at `a73bac6`.
- The task branch `codex/agentic-search-web-listening` was created from that clean baseline.
- Current `main` already includes web-listening rule validation, task runtime integration, React task configuration, and focused tests.
- The current repository has no `agentic_search` symbol or module. Its existing `web_listening` v1 flow drafts a rule and materializes one `sites.yaml` entry plus one scheduled full-pipeline task.
- Existing executable acquisition paths are direct crawler collection, search fallback, linked-file downloads, and optional HTML page-content capture.
- The site manager does not yet expose a structured per-site tracking scope, acquisition-tool choice, or file-versus-webpage content policy.
- Product implementation is waiting for the exact sibling repository that owns the already-built `agentic_search` module so this repository can match its `web_listening` tool contract instead of inventing a competing schema.
- Sibling repositories remain out of scope.

## Verification

- `git fetch origin main`: passed; discovered 51 newer commits.
- `git merge --ff-only origin/main`: passed.
- `git switch -c codex/agentic-search-web-listening`: passed.
- Baseline check: branch starts from `a73bac6`, matching `origin/main` before this status update.
- Current-repository source search and call-chain inspection completed for `web_listening_rule.py`, site CRUD/read APIs, scheduler registration, task runtime, crawler, collectors, and React site management.

## Local Notes

- Files in scope for branch initialization: `.hermes/project-status.md` only.
- No unrelated uncommitted or untracked files were present before branch creation.
- Likely current-repository files in scope after contract confirmation: `ai_actuarial/web_listening_rule.py`, `ai_actuarial/crawler.py`, `ai_actuarial/task_runtime.py`, site config APIs/UI, `config/sites.yaml`, and focused tests.
- Blocker: the sibling repository name/path containing `agentic_search` has not been provided.
