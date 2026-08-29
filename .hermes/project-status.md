# Project Status — Issue #268 Weekly Dashboard

- Updated: 2026-08-29
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-268`
- Branch: `codex/issue-268-weekly-dashboard`
- Startup HEAD / local `origin/main` / merge-base: `e4d4c93a4610197b1808d3a5c24ccad3132cfd20`
- State: PR #289 is Ready. Its one permitted remote-feedback snapshot found one valid AC-3 issue; the focused TDD repair and full related regression are complete and ready to push.

## Startup and boundaries

- Read `AGENTS.md`, the previous `.hermes/project-status.md`, and the complete `karpathy-guidelines/SKILL.md` before editing.
- Startup `git status --short --branch` was clean on the assigned branch. HEAD, the local `origin/main` ref, and merge-base all matched the assigned baseline.
- Work was limited to this worktree. The primary checkout, sibling repositories/worktrees, Issue #264, Graphify/`graphify-out`, secrets/`.env`, providers/network, production, and GitHub/PR/Issue state were not inspected or accessed.
- No commit, push, PR/Issue mutation, merge, branch/worktree deletion, provider call, or lifecycle state change was performed. `.git\issue-to-merge\issue-268.json` was not modified.

## Assumptions and design choices

- The existing #266 latest endpoint remains the authority for selecting the latest successful, published, already-ended snapshot. The frontend first reads that lightweight response, then uses only its exact snapshot ID for the file preview and persisted explanation GETs.
- `snapshot_id` is retained as user/navigation context in Database. Exact `period_start` and `period_end` become the `/api/files` half-open filter boundaries.
- The existing Chat display-name helper was generalized in place so Chat keeps its existing exports and behavior while Dashboard and Database share the same rule: valid trimmed title, then `original_filename`/`filename`, then decoded URL basename, then localized fallback. Blank and case-insensitive trimmed `unknown` are invalid.
- The existing #266 weekly file API continues to return a string `title`. When current title and captured original filename are both absent, it now returns an empty string instead of copying the full URL into `title`, allowing the frontend URL-basename rule to run without changing the response field or type.
- Explanation errors remain independent from snapshot/file data. The UI never invokes generation, retry, task history, model configuration, or storage APIs.

## Acceptance criteria delivered

- **AC-1:** Added a typed GET-only weekly dashboard client. It resolves `/api/weekly-updates/latest`, then `/api/weekly-updates/{snapshot_id}/files?limit=8&offset=0` and `/api/weekly-updates/{snapshot_id}/explanation`. The view shows exact response period boundaries separately from snapshot/explanation generation times, the snapshot's full `file_count`, and at most eight rows.
- **AC-2:** The persisted `lang` supplied by the existing i18n hook selects the already-downloaded `explanation_zh` or `explanation_en` in a pure view-model. Missing, complete-but-empty, read-unavailable, and failed states are deterministic and localized. Those states do not hide snapshot metadata, full count, or file rows. No POST/generate/retry path exists in the client.
- **AC-3:** Added complete English/Chinese weekly labels and state text. Weekly and period-context dates use explicit `en-US` or `zh-CN` formatting in UTC. Exact RFC3339 values remain in `dateTime`/`title`. Long titles, explanations, IDs, and timestamps use accessible text plus wrapping/overflow containment.
- **AC-4:** Dashboard and Database use the generalized canonical display-name helper. Runtime tests cover title/original filename/filename/decoded URL/localized fallback, mixed-case `unknown`, and a 600-character title. The exact snapshot file API test edits `files.title`, reloads by the same snapshot ID, and sees the new title without rebuilding snapshot/chunks/embeddings/KB. Chat backend was untouched and Chat frontend regressions pass.
- **AC-5:** `/api/files` accepts aware RFC3339 `first_seen_from` and `first_seen_before`, validates them as a complete ordered pair, and applies `[from,before)` through SQLite `julianday`. `first_seen` is in backend and frontend sort allowlists. Invalid/blank `order_by`, invalid/blank `order_dir`, malformed/naive, inverted, one-sided, and explicitly empty boundary pairs return stable HTTP 400 JSON instead of fallback/coercion. Tests cover boundary inclusion/exclusion, first-seen sort, pagination, search/source/category composition, and include-deleted permissions.
- **AC-6:** Dashboard View all writes snapshot ID, exact period boundaries, and descending first-seen sort. Database parses the initial URL once and includes the context in URL serialization, `/api/files` params, request/cache keys, prefetch/pagination, sorting, debounced search, source/category/include-deleted changes, forced refresh, scroll/back location, and detail/preview `from` paths. A localized period banner keeps snapshot context visible.
- **AC-7:** The weekly surface contains no Search/Crawl/Job acquisition, lineage, or source statistics and adds no generation calls, charts, or report framework.
- **AC-8:** Added real FastAPI execution and executable TSX client/view-model/state/component tests. Existing source-contract tests remain supplementary. Production frontend build passes.

## TDD evidence

- Initial combined RED command: `python -m pytest --no-cov -q tests/test_issue_268_weekly_dashboard.py; ... tsx ...` first exposed test-harness defects (missing required seed arguments and a nonexistent worktree-local `.bin` path), so it was not accepted as feature evidence.
- After correcting only the harness, a second run exposed another fixture transaction issue and TSX top-level-await format issue; these were also corrected before accepting RED.
- Accepted backend RED: `python -m pytest --no-cov -q tests/test_issue_268_weekly_dashboard.py` — **8 failed, 1 passed, 4 warnings**. Period parameters were ignored (the composed query returned 4 instead of 2) and seven invalid sort/boundary cases returned HTTP 200. The one pass proved the baseline already projected an edited current title from an immutable snapshot membership.
- Accepted frontend RED: `npx --no-install tsx client/src/lib/issue268-weekly-dashboard.test.tsx` — failed with `MODULE_NOT_FOUND` for the not-yet-created `WeeklyDashboardSection` (the typed client/state modules were likewise absent).
- Self-review boundary RED: after adding explicit-empty coverage, the focused module was **1 failed, 11 passed, 4 warnings** because `first_seen_from=&first_seen_before=` returned 200. The parser was tightened; final focused GREEN is **12 passed, 4 warnings**.

## Final verification

- Final focused/related backend and frontend-source regression:
  `python -m pytest --no-cov -q tests/test_issue_268_weekly_dashboard.py tests/test_fastapi_read_endpoints.py tests/test_issue_266_weekly_snapshots.py tests/test_issue_267_weekly_explanations.py tests/test_weekly_updates.py tests/test_dashboard_react_source.py tests/test_database_react_source.py tests/test_chat_react_source.py` — **102 passed, 4 warnings in 10.41s**.
- Executable frontend behavior: `npx --no-install tsx client/src/lib/issue268-weekly-dashboard.test.tsx` — passed, printing `Issue #268 weekly dashboard executable assertions passed`.
- `npm test` — passed; Vite transformed **2,142 modules** in 1.96s. Existing >500 kB chunk warning only.
- Independent `npm run build` — passed; Vite transformed **2,142 modules** in 1.89s. Existing >500 kB chunk warning only.
- Touched-Python `compileall` — passed.
- Focused Ruff `--select E9,F63,F7,F82` — passed (`All checks passed!`).
- `git diff --check` — passed; only expected line-ending warnings.
- Extra `npx --no-install tsc --noEmit` — failed with **13 pre-existing strict-type errors** in category normalization, Settings `replaceAll`, and scheduled-task state files. No new Issue #268 module appeared in the error list; these out-of-scope errors were not changed.
- Extra full suite: `python -m pytest --no-cov -q` — **1,790 passed, 9 skipped, 18 failed, 25 warnings in 242.81s**. All Issue #268/#266/#267/read tests passed. The 18 out-of-scope failures were: two old v7 migration expectations that stop at v9, fourteen Ready Data runtime tests whose direct subprocess cannot locate its hard-coded `tsx` executable in this worktree, one old taxonomy migration expectation, and one permissions unit test using a dict where current code expects headers with `getlist`.

## Browser-smoke readiness

- Manager-owned smoke sizes: 320/768/1024/1440, long title, zh/en switch with network observation, and period persistence.
- Use a disposable local DB/config. Seed files with `first_seen` inside an already-ended period, then publish without a provider call:
  `python -m ai_actuarial.cli weekly snapshot generate --db <db-path> --period-start <aware-RFC3339> --period-end <aware-RFC3339> --json`.
- Seed `weekly_explanations` locally for that snapshot using the complete/missing/empty/failed fixture patterns in `tests/test_issue_267_weekly_explanations.py`; do not run explanation generate/retry. Include a current `files.title` longer than the viewport and edit it between normal page reloads to verify live projection.
- Start API: `python -m ai_actuarial api --host 127.0.0.1 --port 8000`; start UI: `npm run dev`; open `http://127.0.0.1:5173/`.
- On Dashboard, verify only three weekly GETs (`latest`, exact `{id}/files`, exact `{id}/explanation`) and zero POSTs while toggling language. Follow View all, then exercise paging, sort, search, filters, refresh, detail, preview, and Back while confirming snapshot/period params remain in the address and `/api/files` query.

## Manager browser smoke — 2026-08-29

- Started the real FastAPI and Vite applications against a disposable local database containing one ended published snapshot with 12 files and one persisted bilingual explanation produced by a fake in-process generator. No provider/network generation was used.
- At 320, 768, 1024, and 1440 CSS pixels, the document scroll width equalled the viewport width, the weekly section stayed inside the viewport, and exactly eight preview rows rendered. A 1,331-character mixed English/Chinese canonical title wrapped without horizontal overflow at the narrow and tablet widths.
- Switching from English to Chinese selected the already-downloaded Chinese explanation and localized labels/dates without adding any resource request. Reload retained the Chinese locale. The API access log contained only GET requests for the weekly snapshot/files/explanation path and zero weekly/explanation/generate/retry POSTs.
- View all navigated with the exact snapshot ID, period boundaries, and descending `first_seen`. Database search, ascending sort, and the Risk filter retained those parameters in both browser URL and `/api/files` requests. File preview encoded the full period-scoped Database path in `from`, and browser Back restored it exactly.
- Browser console inspection found no application error; only unrelated browser-extension warnings appeared. FastAPI/Vite listeners and the disposable DB/log/seed directory were removed after the smoke.

## Managed review and mandatory pre-PR gate — 2026-08-29

- Managed Review Round 1 used fresh read-only Codex CLI thread `01a04cf5-1f4a-7201-9854-7a65c52fced5` (session `12034`) and returned **PASS** with no Issue #268 findings or changes. The review cycle state is closed at `local_review_complete`, review count 1.
- The manager then reran the 102-test related suite, executable TSX behavior test, `npm test`, independent production build, touched-Python compile, focused Ruff, and `git diff --check`; all passed.
- Mandatory independent pre-PR review used a second fresh read-only Codex CLI thread `01a04cfb-0fb5-79f1-bd26-fe80bc942cbf` (session `84439`) and returned **PASS** with no findings or changes.
- The gate's own Python rerun could not collect because its read-only sandbox exposed no writable temporary directory. This was recorded as an environment-only check blocker; its TSX behavior test and diff check passed, and the manager's immediately preceding 102-test run remains the authoritative Python evidence.

## PR and unique remote-feedback follow-up — 2026-08-29

- Initial commit `d6fd8840806475bd40cc048fc3c6aa7ac2df445b` was pushed and PR #289 was opened Draft with exact `Closes #268`, then marked Ready. Required `CI/python-smoke` passed for that head.
- After 959 seconds, the workflow captured its one permitted complete remote snapshot. It contained one current Copilot inline comment (`3886271966`) and no PR or Issue comments. No second feedback fetch is permitted or planned.
- Fresh read-only classifier thread `01a04d0f-e0bb-70f3-a78c-187ca536bcc1` / session `69454` accepted that comment as a realistic AC-3 defect: when explanation `generated_at` was absent, SSR emitted `<time dateTime="" title="">—</time>`. The Copilot review summary duplicated the same finding; there were no other valid, invalid, or ambiguous findings.
- The original implementation worker completed a focused TDD repair. RED reproduced the empty time attributes; GREEN keeps semantic `<time>` for exact timestamps and renders the same localized unavailable value in a plain `<span>` when the timestamp is absent. Only the component and its executable regression test changed.
- Manager post-fix verification: the 102-test related suite passed with 4 existing warnings; the executable TSX behavior test passed; production build passed with 2,142 modules and only the existing large-chunk warning; `git diff --check` passed with expected Windows line-ending notices.
- The repair changes no layout, sizing, navigation, locale selection, or request behavior. The earlier four-width real-browser smoke therefore remains applicable; the new SSR regression directly covers the changed semantic branch.

## Files changed

- Backend: `ai_actuarial/api/services/read.py`, `ai_actuarial/api/routers/read.py`, `ai_actuarial/storage.py`.
- Frontend: `client/src/lib/weekly-dashboard.ts`, `client/src/lib/database-query.ts`, `client/src/components/WeeklyDashboardSection.tsx`, `client/src/pages/Dashboard.tsx`, `client/src/pages/Database.tsx`, `client/src/pages/chat/displayName.ts`, `client/src/hooks/use-i18n.ts`.
- Tests: `tests/test_issue_268_weekly_dashboard.py`, `client/src/lib/issue268-weekly-dashboard.test.tsx`, `tests/test_dashboard_react_source.py`, `tests/test_database_react_source.py`.
- Status: `.hermes/project-status.md`.
- `git status` also reports `ai_actuarial/api/routers/weekly_updates.py` as modified after a temporary nullable-title experiment was fully reverted. `git diff`, `git diff --name-only`, and the filtered working-tree/HEAD object hashes show no content difference (`09eef37ad8b29b896e7a077512da0a677b0c5388`); this is a mixed-line-ending/stat artifact, not a delivered change.

## Risks, blockers, and next action

- No known Issue #268 functional blocker remains. Browser smoke, managed review, the mandatory independent Codex CLI pre-PR review, and the accepted remote-feedback repair passed.
- The unrelated full-suite and strict-TypeScript failures above remain baseline/tooling blockers outside Issue #268 scope.
- The focused remote repair remains uncommitted and unpushed. The next authorized action is to commit and push it to PR #289, record the remote fix, monitor required checks without fetching feedback again, then merge and clean up once green.
