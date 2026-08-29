# Project Status — Issue #271 Ready Data Busy State

- Updated: 2026-08-29
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\bec8\AI_actuarial_inforsearch`
- Branch: `codex/issue-271-ready-data-busy`
- Baseline HEAD / merge-base / `origin/main`: `ac4a02429e8000e2efdccc3eeafd36ea5f39de90`
- State: PR #290 is Ready; the single remote feedback window completed, the only inline suggestion was rejected by a real-path regression, and a focused AC-7 regression test is pending commit/push before final checks and merge.

## Startup and boundaries

- Read the complete `issue-to-merge` and `karpathy-guidelines` skills, project `AGENTS.md`, prior project status, Issue #271, linked #245/#256, PR #270, CI, relevant Ready Data code, tests, and history.
- Startup worktree was clean and detached at the supplied baseline. It was safely switched before editing to the assigned branch, which points to the same baseline.
- Only this repository and worktree are writable. Sibling repositories, secrets, production data, unrelated branches/worktrees, and unrelated user changes are off-limits.
- Duplicate-work search was completed by the controller: no equivalent PR or branch exists; merged PR #270 is the non-equivalent #256 lightweight-list change.
- Review state: `C:\Project\AI_actuarial_inforsearch\.git\issue-to-merge\issue-271.json` (outside the checkout; never commit).

## Baseline reproduction and history

- A disposable real API/SQLite fixture reproduced the production shape on `ac4a024`: after a successful manual Ready Data build, source evaluation cleared generation 4, Serving was `ready`/usable and Latest operation was `build`/`succeeded`, but Storage, KB list, KB detail, and dedicated manifest still exposed `automation_state=pending` while both pending/running generation fields were null.
- The first stdin-based reproduction attempt was invalid because Windows multiprocessing could not reload `<stdin>`; a temporary script with a normal module path then reproduced the bug and was removed. The worktree returned clean before this status update.
- Targeted `git blame`/`git log` traces the source-evaluation settlement to `ec988f1` and the status-only frontend busy predicate to `63d0cb7` / Issue #245. #245 explicitly separates Serving from Latest operation and does not intend generation-free pending to remain busy.

## Numbered acceptance criteria

- **AC-1:** Orphan pending with null pending/running generation is non-busy in API and UI; Build follows existing permission/selector rules.
- **AC-2:** Pending with a real pending generation remains busy, disabled, spinning, and polled.
- **AC-3:** Running/building with a real running generation remains busy, disabled, spinning, and polled.
- **AC-4:** When generation disappears or a terminal state arrives, Knowledge and KB Detail stop polling and clear Building/spinner UI.
- **AC-5:** Successful manual build/source evaluation settles orphan pending without changing publication pointers, revision/CAS, or Serving.
- **AC-6:** Existing production rows work through safe read-time normalization without rebuild or destructive migration.
- **AC-7:** KB list, KB detail, and manifest/detail expose consistent serving, operation, automation, and generation semantics while preserving #245.
- **AC-8:** Executable regressions cover orphan pending, real pending, running, succeeded, failed, and legacy payloads in Knowledge and KB Detail.
- **AC-9:** #256 list performance remains metadata-only; focused backend/runtime/source tests, frontend build, touched-file Ruff/compile, `git diff --check`, and GitHub `python-smoke` pass.
- **AC-10:** Active/previous publication, CAS, build selector, and Serving semantics remain unchanged.

## Scope and non-goals

- Expected scope: `ai_actuarial/storage.py`, Ready Data public projection/list view only if required, `client/src/lib/ready-data-ui-state.ts`, `client/src/pages/Knowledge.tsx`, `client/src/pages/KBDetail.tsx`, and focused Ready Data API/runtime/source tests.
- Same-shaped sites to inspect: primary `Storage`, `_KBListStorageView`, all `isReadyDataAutomationBusy` call sites, and both list/detail polling paths.
- Non-goals: schema migration, production rebuild, pointer/CAS/selector changes, Serving changes, broad UI/state-machine refactors, caching, security frameworks, and unrelated cleanup.

## Verification plan

- Worker must capture a new pre-fix failing regression and post-fix pass, then run focused backend Ready Data/API tests, executable TypeScript runtime/source tests, and frontend build.
- Manager will inspect the complete diff and test evidence, run the bounded fresh-reviewer loop, perform browser smoke for Knowledge and KB Detail, run touched-Python compile/Ruff and `git diff --check`, and run the independent Codex CLI pre-PR review gate before publication.
- Required remote check: GitHub `python-smoke`. Draft PR must contain exact `Closes #271`, then become Ready. One feedback snapshot is allowed after the full ten-minute Ready window.

## Implementation and local review

- `Storage.get_agentic_ready_automation_state` and the metadata-only list projection normalize stored `pending` with no pending/running generation to `succeeded` on read, preserving existing rows without a migration.
- Successful source evaluation settles the same orphan state transactionally only when there is no running generation or claim token; publication pointers, revisions, CAS, Serving, and selectors are untouched.
- The shared frontend busy predicate now uses generation evidence for modern manifests while retaining status-only compatibility for legacy payloads. Knowledge and KB Detail share it for polling, spinner, button state, and action text.
- New regressions cover orphan pending, real pending/running work, legacy payloads, API projections, source settlement, and both React pages.
- The implementation worker captured valid RED evidence before the fix, then GREEN evidence after it. Fresh read-only reviewer round 1 passed with no in-scope findings; review-cycle state is `local_review_complete`.

## Verification results

- Manager focused/backend/API/runtime suite: `259 passed, 8 skipped`.
- CI-equivalent Python smoke selection: `44 passed`.
- Frontend production build: passed (`2142` modules transformed; only the existing large-chunk advisory).
- Touched-file Python compile and Ruff: passed. `git diff --check`: passed (Git only reported checkout line-ending notices).
- Browser smoke with disposable local SQLite data: orphan pending rendered Latest operation as succeeded, no spinner, and an enabled rebuild button in both Knowledge and KB Detail; a real pending generation remained spinning and disabled.
- After more than one polling interval on the orphan detail page, the API received no further manifest request. Browser console errors: none.
- Disposable services were stopped after the smoke test. Repository files remain the only intended changes.
- Independent Codex CLI pre-PR review (`codex review --uncommitted`) passed with no actionable findings. It independently reran `210 passed, 7 skipped`, the production frontend build, and `git diff --check`.

## Publication and remote feedback

- Commit `159430e28742332f6a42e5d65b8aaac3d3989e8d` was pushed and Draft PR #290 was created with exact `Closes #271`; it became Ready at `2026-08-29T11:38:09Z`.
- After the full ten-minute window, the one permitted manager feedback snapshot was captured at `2026-08-29T11:48:40Z`: `python-smoke` passed, the PR was mergeable, there were no PR or Issue comments, and the only feedback was Copilot inline comment `3886507498` suggesting that orphan settlement refresh `agentic_ready_automation.updated_at`.
- The same implementation worker first reproduced the suggested timestamp change, then tested it through the real disposable FastAPI/SQLite manual-build path. RED evidence showed that the later automation timestamp incorrectly replaced public Latest operation `build/succeeded` with `automation/succeeded`. Restoring PR-head production behavior made the same path pass. The suggestion is therefore invalid for AC-7/#245: orphan settlement is cleanup, while `updated_at` is also the public operation-ordering timestamp.
- No production change from the suggestion remains. A focused regression now exercises a real manual build with an orphan pending row and proves settlement still clears the pending generation while Latest operation remains the successful build. Focused GREEN evidence: `2 passed`; related source-state suite: `30 passed`; touched-test Ruff, compile, and diff checks passed.
- Protocol note: during the post-snapshot independent local CLI review, that CLI autonomously repeated read-only `gh pr list` / `gh issue view` metadata reads despite a local-diff-only intent. The repeated data matched the frozen snapshot, disclosed no new feedback, and made no remote writes. No further feedback fetches will be performed.
- A second, explicitly local-only Codex CLI gate for the test/status follow-up was started with network and `gh` forbidden; it stayed local and reran the relevant tests successfully. The user then explicitly cancelled that review before its final verdict, so it is recorded as cancelled rather than passed and will not be restarted.

## Current next action

- Independently review the focused regression and this status update, commit and push them, reply to and resolve the addressed inline thread, wait only for required checks on the new head, then merge and perform the authorized branch/worktree cleanup. No blocker or decision is currently needed.
