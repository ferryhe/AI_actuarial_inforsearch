# Project Status — Issue #179 Thin Pipeline Baton

- Updated: 2026-08-26
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-179`
- Branch: `codex/issue-179-thin-baton` (based on `origin/main`)

## Delivered behavior

- Replaced the unused Full Pipeline product path with one fixed sequence:
  `Scheduled Collection -> Markdown -> Catalog -> Chunk -> incremental RAG Index` for all current category KBs in stable `kb_id` order.
- Every step remains an independent task with its own task ID, history, and log. No output payload is passed between stages.
- A compact JSON baton document stores only optional per-stage overrides and the current round fields: current step/task ID/current RAG KB/round status/last check/consumed scheduled task ID.
- The configured enabled generic daily task named `Scheduled Collection` starts each round; the runtime ticks the baton every 30 minutes.
- `pending`/`running` waits, `completed` advances once, `error`/`stopped` terminates, repeated start/tick is idempotent, category KBs run one at a time, and zero category KBs completes.
- Added small shared-runtime API and CLI surfaces for status, start, tick, and read-only config inspection; configuration writes remain on the existing inline module forms/API.
- Tasks UI now shows exactly five initially collapsed fixed cards. Each expands existing module settings inline; optional saves persist only a stage payload override. RAG target remains all category KBs with incremental indexing.
- Removed Full Pipeline new-task, Pipeline Runs, scheduled type, collection acceptance, runtime dispatch, site scheduler mode, and web-listening materialization. Historical SQLite schemas/tables/storage compatibility remain untouched.

## Verification

- Focused baton/runtime/API/CLI/UI/web-listening manager run: `58 passed, 4 warnings`; final-fix worker superset: `62 passed, 4 warnings`.
- Related standalone-task/scheduler/API/storage regressions: `182 passed, 5 warnings`.
- Earlier related subset: `126 passed`; frontend source suite: `25 passed`.
- Frontend `npm.cmd run build`: passed, 2135 modules; existing bundle chunk-size warning only.
- CLI root, pipeline, and each status/start/tick/config `--help`: passed.
- CLI JSON contract tests cover all four commands, including parseable nonzero error output; service tests cover repeat start/tick idempotence.
- `python -m compileall -q ai_actuarial tests`: passed.
- Ruff on new baton/tests: passed. Ruff on all touched Python passed with `F401,E731` ignored because the two findings are unchanged baseline issues in `origin/main`.
- `git diff --check`: passed (Git emitted only line-ending conversion warnings).
- Production-source residual scan found no `full_pipeline`, Full Pipeline, Pipeline Runs, old runtime dispatch, site pipeline mode, or old runs API references.
- `ai_actuarial/storage.py` and `ai_actuarial/sqlite_schema.py` have no diff.

## Review evidence

- Scripted local review Round 1 accepted three concrete default/config findings; the replacement fix worker addressed them. Round 2 returned `PASS` for the full minimal Issue #179 diff.
- The mandatory Codex CLI review gate completed twice: the first pass identified five accepted contract defects, and the final pass identified five more direct duplicate-scheduling/scheduler-isolation/config-hydration defects. All accepted findings were fixed and revalidated.
- Restart takeover/recovery was deliberately rejected because Issue #179 explicitly excludes automatic retry/resume, leases, and durable recovery.
- The original review agent was interrupted during a session transition without a report; the review attempt was aborted without consuming a round. One replacement fix worker was reused for all accepted findings.

## Browser smoke

- Vite served `/tasks` successfully and the API process started.
- The in-app browser reached the Tasks page but rendered `403 — insufficient permissions`; the local API migration preflight also reported 503 for the existing local database state.
- No credentials or permission bypass were introduced. Next smoke command is to start the API/Vite services with a local session holding `tasks.view`, then open `http://127.0.0.1:5177/tasks` and expand the five cards.

## Scope decisions

- No generalized pipeline abstraction, new security/auth model, retries, resume flow, lineage, checkpoints, watermarks, leases/fencing, child barriers, aggregate logs, output handoff, or duplicate default/config storage was added.
- Production rollout Issue #176 is excluded.
- Implementation followed the Karpathy guidelines by keeping the baton state and transition service small, deleting obsolete product paths, reusing existing forms/runtime callbacks, and proving behavior with focused tests first.

## Worktree state

- The reviewed Issue #179 change set includes new baton backend/UI/test files plus deletions of obsolete Full Pipeline UI/tests.
- No unrelated worktree changes were identified.
