# Project Status

- Date: 2026-06-17
- Branch: `docs/final-readme-cleanup`
- Baseline: `origin/main` after merged PR #154.
- Scope: Documentation cleanup after completion of the AI Actuarial Feishu-plan managed PR backlog.
- Completed roadmap PRs:
  - [#147](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/147) — P0-1 Markdown conversion config split and admin/UI/runtime integration.
  - [#148](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/148) — P0-2 customer-facing dashboard homepage.
  - [#149](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/149) — P0-3 web-listening-agent-rule schema/API/materialization.
  - [#150](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/150) — P1-1 weekly updates API/storage/task runtime.
  - [#151](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/151) — follow-up fixes for valid Copilot comments on #147/#149/#150.
  - [#152](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/152) — P1-2 Chat KB-first UI plus Chat API/types/session extraction.
  - [#153](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/153) — follow-up fixes for valid Copilot comments on #152.
  - [#154](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/154) — final roadmap status marker.
- Previous Agentic RAG PRs: #133-#145 plus [#146](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/146) are complete; Agentic RAG is out of scope for new implementation work.

## Current State

- The remaining Feishu-plan backlog named in the managed controller prompt is complete and merged into `main`.
- This branch cleans up documentation so the active README/docs describe the final product state rather than old phase plans.
- Historical dated plans/reports/test notes/security summaries were moved into `docs/archive/` with an archive README warning that they may contain stale status or commands.
- Active docs now emphasize current production surfaces: FastAPI + React, customer Dashboard, Markdown conversion config, web-listening rules, weekly updates, KB-first Chat, standard RAG, and Agentic RAG.
- Local `docker-compose.override.yml` still has an unrelated production override diff and must remain uncommitted.

## Verification

- `git status --short --branch` checked before work; only the expected local production override was dirty on `main`.
- GitHub open PR state checked with `gh pr list --state open` before starting; there were no open PRs.
- Active Markdown relative-link check passed for 17 active docs outside `docs/archive/`.
- `git diff --check` passed.
- `python3 -m ai_actuarial --help` passed.
- Two read-only reviewer agents checked the docs; findings were resolved by fixing the web-listening module path and archiving stale OpenAPI exports.
- This documentation cleanup does not alter application runtime code.

## Notes

- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, active Docker volumes, logs, or local production overrides into PRs.
