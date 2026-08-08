# Project Status

- Date: 2026-08-07
- Branch: `codex/fix-pr169-copilot-feedback`
- Baseline: `origin/main` at `0f66956` (merged PR `#169`).
- Scope: Address the two Copilot review clusters left on merged PR `#169` without changing the prototype architecture or reading sibling repositories.

## Current State

- Site add/update API writes now normalize `file_exts` to lowercase, dot-prefixed, first-seen-order values with duplicates removed.
- `SiteConfigForm` now keeps site-save failures separate from site-exploration failures.
- Save failures render next to the Save controls through a dedicated `saveError` state and use localized English/Chinese fallback text.
- Focused regression coverage exercises extension normalization on both add and update plus the independent save-error UI contract.
- Follow-up PR `#170` is open. Both `python-smoke` runs passed, and Copilot's one actionable test-maintainability comment was accepted: the i18n regression now asserts the English and Chinese translations directly instead of counting language-table occurrences.
- PR `#169` is merged. Its broader `web-listening-agent-rule.v1` implementation remains an application-layer prototype; this follow-up is limited to correctness and UX hardening.

## Verification

- Test-first reproduction: the new API and React assertions failed before implementation and passed afterward.
- Focused regression suite: `62 passed` across site write/read APIs, crawler behavior, and React source contracts.
- Frontend production build: passed; Vite reports the existing large-chunk advisory only.
- Browser smoke: passed against isolated local API/database and Vite ports. A site saved with `PDF, .DocX, pdf` persisted as `.pdf, .docx`; an unsafe-URL save failure rendered only in `text-site-save-error`, with no Explore error node or new page console errors.
- `git diff --check`: passed.
- Focused Ruff check reported two pre-existing findings outside the added lines: unused `PROVIDER_ENV_VARS` in `ops_write.py` and unused `src` in `test_tasks_react_source.py`.
- Mandatory Codex CLI review: passed with no actionable findings; the reviewer independently reran `47` focused tests and the frontend build.
- Post-review focused test: `21 passed` in `tests/test_tasks_react_source.py` after applying Copilot's PR `#170` feedback.
- Post-PR observation: completed after 15 minutes. Copilot marked its sole thread resolved/outdated after the fix; there are no other review threads or conversation comments.

## Local Notes

- Files in scope: `ai_actuarial/api/services/ops_write.py`, `client/src/pages/tasks/SiteConfigForm.tsx`, `client/src/hooks/use-i18n.ts`, focused API/React tests, and this status file.
- No unrelated local changes were present before implementation.
- The isolated smoke services, throwaway user/database, logs, and temporary configuration were stopped and removed after verification.
- Sibling repositories were not read or modified.
- Next action: merge PR `#170` after owner review.
