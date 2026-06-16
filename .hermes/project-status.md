# Project Status

- Date: 2026-06-16
- Branch: `codex/docs-status-readme-review-fixes`
- Baseline: `origin/main` at `ee7b6d8`.
- Scope: README/docs/project metadata cleanup after the merged Agentic RAG QA follow-up.
- PR: [#146](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/146).
- Previous PRs: [#145](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/145) — merged; [#143](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/143) — merged; [#142](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/142) — merged.

## Current State

- `main` now includes the 2026 FastAPI/React migration, security/RBAC hardening, and the planned Agentic RAG implementation sequence through PR #142.
- PR #143 reconciled the Agentic RAG status file after the planned sequence.
- PR #145 merged the local-QA follow-up for CJK ready_data query matching, Agentic Chat KB section-count labels, and raw Agentic score display.
- This branch updates English/Chinese README content, the docs index, the Agentic RAG guide, and the service start guide so they describe the current post-PR #145 state.
- This branch aligns frontend runtime metadata with Vite 7 by documenting Node.js `^20.19.0 || >=22.12.0` and adding the same range to `package.json -> engines`.
- This branch removes unused direct Node server-era package dependencies that were left from the retired Express/Passport/Postgres/Drizzle runtime surface after source searches found no imports.
- `npm test` now runs the maintained frontend build instead of an always-failing placeholder.

## Verification

- `npm.cmd install --package-lock-only` passed after package metadata cleanup.
- `npm.cmd install` restored local `node_modules` after a clean-install probe hit Windows EPERM cleanup locks in ignored native package directories; install completed with cleanup warnings only.
- `npm.cmd test` passed and now runs `npm run build` / Vite production build; Vite still emits the existing large-chunk warning.
- Markdown link scan for the root READMEs and maintained docs touched in this branch passed.
- Source/package search found no maintained-code imports or root package entries for the removed Express/Passport/Postgres/Drizzle-era dependencies.
- `git diff --check` passed with LF/CRLF working-copy warnings only.
- Independent agent review #1 (README/docs/status consistency) found no Critical, Important, or Minor findings and recommended PASS.
- Independent agent review #2 (package/dependency diff) found no Critical, Important, or Minor findings and recommended PASS.
- Mandatory local `codex review --uncommitted` remains blocked by WindowsApps `codex.exe` returning `Access is denied`.

## Notes

- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, or unreviewed artifacts across projects.
