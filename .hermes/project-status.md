# Project Status — Issue #307 scheduler reconciliation

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\be1a\AI_actuarial_inforsearch`
- Branch: `codex/issue-307-scheduler-reconciliation`
- Original baseline: `origin/main@0fe3101df6f3834e33b609aff3d119b70df9a274`
- Integrated main: `origin/main@25d0e0ae96a938d97636041e77a175203184237f`
- Issue: `#307 fix(tasks): reconcile configured recurring tasks with effective scheduler jobs`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-307.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/325`
- Delivery stage: PR #325 is Ready; the full 10-minute feedback window completed, all five CI
  checks passed, and two confirmed Copilot findings are fixed and locally revalidated for push
- Progress heartbeat: id `bug-issue`, status `ACTIVE`, 15-minute cadence

## Issue #307 pause checkpoint (historical)

- Pause requested after local review round 1 returned PASS with no findings. The persistent state
  file remains at `local_review_complete` with `review_count: 1` and no PR recorded.
- Completed validation: Issue-focused tests (36 passed), worker extended backend regression
  (293 passed), reviewer regression (113 passed), rendered component assertions, real browser
  smoke for registered-reader/admin controls and English/Chinese copy, dead-code file/symbol gates,
  frontend lint/type-check/build, and `python scripts/quality_gate.py`.
- Unified quality result: PASS; full pytest was 1876 passed and 10 skipped, followed by passing
  Black, isort, and Pylint baseline checks. Frontend lint retained 5 existing warnings and build
  retained the existing large-chunk advisory.
- At this historical pause point, the separate CI-equivalent `python-smoke` commands had not run
  and no Git or remote lifecycle action had occurred. Both the smoke commands and all other
  post-integration local checks have now completed below; the Git/remote lifecycle still has not
  started.
- Resume entry: from this exact worktree and branch, verify `git status`, run the three
  `python-smoke` commands from `.github/workflows/ci.yml`, review the final diff/status, then commit,
  push, open the Draft PR with `Closes #307`, mark Ready, and continue the recorded remote-feedback
  workflow.
- Preserve all current tracked implementation/test changes, the two new test files, the three
  manager-generated `graphify-out/` directories, and the Issue state file. Sibling repositories
  remain off-limits.

## Issue #307 latest-main integration

- The controller reported and the manager verified that `origin/main` advanced five commits from
  `0fe3101` to `25d0e0a` through PR #324.
- A three-way preflight found no business-code or test conflict and no untracked-path collision.
  The only conflict was this manager-owned status file.
- The branch fast-forwarded to `25d0e0a`; all #307 tracked changes and both new tests were restored
  from the recoverable stash. The three `graphify-out/` directories remained untouched.
- The status-file conflict was resolved by preserving the complete #307 record and its prior
  #306/#317 history while adding the current main record for PR #324 below.
- PR #324 changed guest-only task-option caching and unrelated pages/tests. It did not change any
  #307 production or test file, nor a hook consumed by the #307 scheduling surfaces, so local
  review round 1 remains applicable and `review_count` stays at 1.

## Issue #307 post-integration validation

- Extended scheduler/API/frontend regression: 293 passed.
- FastAPI entrypoint/native-authority smoke: 13 passed. Agentic evaluation tests: 31 passed.
  Agentic command smoke: 3/3 cases passed with all reported quality rates at 1.0.
- Frontend lint passed with 0 errors and 5 existing hook warnings; type-check and production build
  passed, with only the existing large-chunk advisory.
- Dead-code file and symbol gates passed with zero findings.
- Unified quality gate passed: 1,880 tests passed and 10 skipped; Black, isort, and Pylint passed.
- Real browser smoke passed against the integrated branch. A registered reader saw both Effective
  Scheduler Jobs and Configured Recurring Tasks, including all five expected job kinds, while add,
  reinitialize, edit, and delete controls were absent. An admin saw add, reinitialize, edit, and
  configured-task delete controls, with no direct effective/system-job delete action. English and
  Chinese desired/effective, diagnostic/recovery, read-only, and deletion-consequence copy all
  rendered correctly. The confirmation was inspected without deleting the recurrence.
- `git diff --check` passed apart from informational CRLF conversion notices. No second local review
  was needed because the integrated upstream changes did not touch or feed the reviewed #307
  surfaces.

## Issue #307 remote feedback and follow-up

- PR #325 was created as Draft, verified to contain `Closes #307`, then marked Ready. The required
  observation window ran for 635 seconds before the one permitted feedback snapshot was fetched.
- Remote CI passed `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke`; the reviewed head was `e3109b4bcab6414c5d18f1de19657f5753c21334` and GitHub
  reported the PR mergeable and clean.
- Copilot raised four inline comments. Two were confirmed and fixed: unmanaged scheduler jobs now
  retain their generated sanitized metadata so identity survives in-process list reordering; and
  `daily at H:MM` is normalized to `HH:MM` both for runtime registration and desired/effective
  reconciliation.
- The two comments about absolute paths in this internal workflow record were rejected under the
  repository review policy because they do not map to any Issue #307 acceptance criterion.
- Red evidence reproduced both accepted findings, including a 503 reconciliation failure and the
  real scheduler rejecting the API-accepted single-digit hour. Green evidence: 2/2 focused tests,
  46/46 Issue/API tests, and the manager's 295/295 extended regression passed. Black, isort, and
  `git diff --check` passed for the follow-up patch.

## Issue #307 acceptance criteria and boundaries

- AC-1: Effective scheduler status exposes a deterministic within-process `job_key` plus only
  sanitized kind, source, display name, interval, last/next run, managed, and deletable metadata.
- AC-2: Configured recurring tasks, site jobs, the global job, Pipeline Baton, and Ready Data are
  distinguishable; configured effective jobs map back to their configured task.
- AC-3: Configured-task add, update, and delete return success only after desired YAML and live
  scheduler state match; recurrence removal needs no manual Reinitialize.
- AC-4: A forced registration or reconciliation failure returns failure and restores both the
  previous YAML and the previous scheduler state.
- AC-5: Reconciliation does not stop active tasks or alter history, logs, stop behavior, or
  unrelated system jobs; system jobs have no direct delete action.
- AC-6: `tasks.view` readers can see Configured Recurring Tasks and Effective Scheduler Jobs but
  no mutation controls; direct writes remain 403 and operator/admin write flows remain valid.
- AC-7: Reinitialize remains a diagnostic/recovery action, and English/Chinese copy plus deletion
  confirmation clearly explain desired versus effective state.
- Implementation ownership is limited to `ai_actuarial/task_runtime.py`, the directly related
  FastAPI ops read/write services and routers, `client/src/pages/Tasks.tsx`,
  `client/src/pages/tasks/ScheduledTasksSection.tsx`, `client/src/hooks/use-i18n.ts`, the three
  same-shaped mutation callers `ScheduleFromTaskButton.tsx`, `WebListeningForm.tsx`, and
  `PipelineBaton.tsx`, and focused tests for those contracts. `.hermes/project-status.md` remains
  manager-owned.
- Sibling repositories are off-limits. Non-goals are schedule/timezone UX from #312, a database
  job table, a generic scheduler platform, direct system-job deletion, stopping current tasks,
  history/log/artifact deletion, APScheduler/Celery migration, and pipeline-order changes.

## Issue #307 baseline evidence

- The assigned worktree was clean; branch, `HEAD`, and supplied baseline matched exactly.
- A real `NativeTaskRuntime` reproduction showed add left only the existing 30-minute Pipeline
  Baton job, update left the old daily timer effective, and delete left the two-hour timer live
  after YAML became empty. Manual `init_scheduler()` was required after each mutation.
- `git blame` and targeted history trace the split to the original April FastAPI work: CRUD writes
  YAML and calls only `set_site_config`, while the separately exposed Reinitialize path alone calls
  `init_scheduler`. The status endpoint independently enumerates live jobs. Later changes added
  system jobs and stricter RBAC without creating an automatic reconcile contract, so the Issue is
  current and not a stale request.
- The linked #312 explicitly depends on #307 and owns only future schedule expression/timezone UX.
- Baseline CI run 33582893736 passed all five jobs at the assigned merge baseline.

## Issue #307 required validation

- Scheduler/runtime tests cover every job kind/source, stable keys, configured mapping,
  add/update/delete reconciliation, forced failure rollback, and unchanged system jobs.
- API tests cover the reader/operator/admin RBAC matrix and active/history/log/stop regressions.
- Frontend source and rendered-component tests cover read-only visibility, hidden mutations,
  bilingual copy, and deletion confirmation.
- Final validation includes focused scheduler/API/frontend tests, frontend lint/type-check/build,
  browser smoke, dead-code file/symbol checks, the unified quality gate, and Python smoke tests.

# Project Status — PR #324 guest UI permission gating

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\pr-324`
- Branch: `fix/guest-ui-permission-noise`
- Baseline merged: `origin/main@0fe3101`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/324`
- Task: review PR #324, fix its failing test gate, and evaluate Copilot feedback

## Scope and boundaries

- This repository is the only writable project workspace; sibling repositories are off-limits.
- Scope is limited to the guest UI permission behavior, the failed formatting gate, and the
  Copilot review comment on `useTaskOptions`.
- The primary checkout has unrelated user-owned changes and remains untouched. Work is isolated
  in this task worktree.

## Findings and implementation

- The original remote run passed all 1,880 pytest tests but failed the quality gate because
  `tests/test_knowledge_react_source.py` was not Black-formatted.
- Copilot's comment was confirmed: a disabled `useTaskOptions` consumer could expose module-level
  cached operator data and could retain a stale loading state.
- Disabled consumers now receive stable fallback/empty values, `loading=false`, `error=null`, and
  a request-free `refresh` function.
- A runtime TypeScript/React hook regression warms the authorized cache, expires it, mounts a
  disabled guest consumer, and verifies that no operator data or new requests escape.
- Black reformatted the original failing test file.
- The Copilot thread was answered with the fix and regression evidence.
- Latest `origin/main` was merged after it advanced through PR #323; its sole textual conflict in
  this status file was resolved in favor of the current PR #324 record.

## Local verification before latest-main merge

- New runtime regression: demonstrated the stale-data/loading failure before the hook fix and
  passed after the fix.
- Focused React source suite: 78 passed.
- Black check for the four relevant React source test files: passed.
- Frontend lint: passed with 0 errors.
- Frontend type-check: passed.
- Frontend production build: passed; only the existing Vite large-chunk advisory remained.
- Four-layer dead-code gate: passed with zero baseline findings.
- Unified quality gate: passed with 1,861 tests passed and 10 skipped; Black, isort, and Pylint
  passed.
- `git diff --check`: passed apart from informational CRLF conversion notices.
- Browser shell smoke as a signed-out user showed no operator diagnostics or console errors. The
  backend was not running, so proxied API requests returned connection-refused/500 responses;
  the runtime regression is the authoritative guest-cache check.

## Post-merge verification

- Focused React source suite: 78 passed.
- Frontend lint, type-check, production build, and four-layer dead-code gate: passed.
- Unified quality gate: 1,871 passed and 10 skipped; Black, isort, and Pylint passed.
- `git diff --check`: passed.

## Delivery state

- Fix commit `1d61054` is pushed to the PR branch.
- The Copilot reply is published at discussion comment `3910583670`.
- Post-merge local validation is complete; the new remote CI run is the remaining check at this
  snapshot.

## Preserved merged Issue #306 evidence

- PR #323 merged at `0fe3101df6f3834e33b609aff3d119b70df9a274` on 2026-09-02T02:21:06Z.
- Issue #306 closed automatically one second later.
- PR #323 passed `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke`; the post-merge main CI run 33582893736 also passed all five jobs.
- The detailed #306 implementation and validation record remains preserved below.

# Project Status — Issue #306 metadata-only Chunk & Embedding stats

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\692c\AI_actuarial_inforsearch`
- Branch: `codex/issue-306-metadata-only-stats`
- Baseline: `origin/main@1e7f5f6b1cf29e7e9c0a413e221e774d77bdeee2`
- Issue: `#306 perf(tasks): make Chunk & Embedding stats metadata-only`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-306.json`
- Delivery stage: merged through PR #323 at
  `0fe3101df6f3834e33b609aff3d119b70df9a274`; Issue #306 is closed and post-merge CI passed
- Progress heartbeat: id `bug-issue`, status `ACTIVE`, 15-minute cadence

## Issue #306 scope and boundaries

- This repository is the only writable project workspace; sibling repositories are off-limits.
- Ordinary `GET /api/chunk_generation/stats` must use aggregate metadata only and must not read
  `global_chunks.content` or `chunk_embeddings.vector_json`.
- Preserve the response shape, category filtering, embedding identity fields, and
  `first_without_chunks_index` semantics.
- Preserve deep vector-body validation for build, audit, repair, and explicit coverage paths.
- Add measured covering-index/query-plan evidence, regression guards, dimension/byte-size
  performance evidence, focused API/storage/schema checks, frontend build, and browser smoke.
- Non-goals remain caching the deep scan, changing embedding generation or serialization,
  weakening fail-closed build/audit behavior, replacing SQLite, or redesigning Tasks UI.

## Issue #306 baseline evidence

- Worktree was clean; assigned branch and `HEAD` exactly matched the supplied baseline.
- A baseline endpoint run with 3,072-dimension stored vectors called
  `Storage.embedding_coverage`, `Storage.list_chunks_for_embedding`, and
  `Storage.read_valid_chunk_embeddings` once each.
- Targeted blame/log evidence traces the deep statistics path to the persisted-embedding
  implementation; current intent already keeps metadata-only and deep validation paths separate
  for Knowledge Base detail, so Issue #306 is reproducible and not stale.

## Issue #306 current validation

- Issue-focused tests: 10 passed. The added v0 regression proves a real pre-v13 database
  without the new indexes is recognized, migrated with data preserved, and idempotent.
- Schema/API combinations: 153 schema migration checks and 42 related API/lightweight-path
  checks passed.
- Production-scale benchmark: 21,314 rows at 3,072 dimensions with about 262 MB of stored
  vector bodies; first new connection 0.02653s and 20-run warm p95 0.02172s.
- Frontend lint, type-check, production build, dead-code file/symbol gates, and the unified
  quality gate passed. Final full pytest result: 1,867 passed, 10 skipped, 0 failed;
  Black, isort, and Pylint also passed. Agentic eval smoke passed 3/3.
- Browser smoke passed on Tasks → Chunk & Embedding: stats and selected embedding identity
  rendered without a persistent loading state, the stats API returned 200, and the browser
  console had no errors.
- Local review closed after two rounds. One real v0 migration gap was fixed and independently
  revalidated. A proposed manual wrong-name index construction was rejected under the repository
  review policy because no supported create or migration path can produce it and Issue #306 does
  not require compatibility with manual schema tampering.

## Prior project status (Issue #317 historical record)

# Project Status — Issue #317 dead-code and unified quality gates

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch\.codex-tmp-agentic-rag`
- Branch: `codex/issue-317-dead-code-detection`
- Baseline: `origin/main@bd6f47f`
- Task: implement Issue #317 and the requested unified pytest/Black/isort/Pylint gate

## Scope and boundaries

- This repository is the only writable workspace.
- Sibling repositories are off-limits.
- The work covers TypeScript and Python file reachability, symbol detection,
  reviewed exceptions, shrink-only baselines, local hooks, CI, reports, and
  contributor documentation.
- CI only reports and blocks; it never deletes or rewrites source files.

## Implementation state

- PR #318 is open: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/318`.
- Added production-first Knip and AST module-reachability checks, followed by
  Knip/ESLint and Vulture symbol checks.
- Production and test entries are separate. Constant dynamic imports require a
  reasoned allowlist, and stale entries fail the gate.
- Added a statically validated Vulture whitelist for FastAPI routes, Pydantic
  validators, middleware hooks, and pytest fixtures.
- Added normalized `path + kind + symbol` dead-code baselines. New findings,
  stale findings, and all 100%-confidence Vulture findings fail; maintenance
  updates can only shrink the baseline.
- Classified the initial baseline: 9 TypeScript files, 5 Python modules, 28
  TypeScript symbols, and 93 Python symbols. Reviewed cleanups have since
  reduced all dead-file findings to zero and all symbol findings to 17 Python
  compatibility/test items.
- Added the requested unified quality gate: full pytest plus non-mutating
  Black, isort, and Pylint checks, with an exact shrink-only compatibility
  baseline for existing formatter/linter debt. Pytest failures cannot be
  baselined.
- Added pre-commit/pre-push hooks, ordered CI jobs, text/JSON artifacts,
  top-level commands, watch mode, and investigation/cleanup documentation.
- Removed confirmed unused TypeScript locals/imports and corrected narrow test
  contracts exposed by the new full-suite gate.
- The first PR #318 run passed file/symbol, frontend, and Python smoke jobs. Its
  full Linux gate exposed one POSIX path-normalization bug, two FastAPI 0.141
  route-introspection assumptions, five Linux symlink-path assertions, and
  four platform-dependent static-baseline entries. These were fixed narrowly:
  publication slots remain atomic while failed rollback audit fields advance,
  staging is reverified immediately after digesting, and optional marker
  Pylint findings are deterministically suppressed at their exact call sites.
- Copilot's one actionable review finding was confirmed and fixed: the
  synthetic commit-failure context manager now executes the transaction body,
  raises during exit, and delegates rollback to the real transaction manager.
- The second Linux run passed four jobs but showed that four symlink rollback
  assertions scrubbed audit fields from the direct publication projections,
  not from the same fields mirrored in the nested manifest projection. The
  helper now removes only those four audit keys recursively while comparing
  every other field, with a platform-independent regression for that shape.
- Historical cleanup now proceeds one directory at a time, with focused tests,
  the complete gate, and one path-specific commit per directory. The first
  completed directory is `config/`: Black/isort formatting was applied, the
  Pydantic path validator was explicitly marked as a classmethod, and the
  output-format validation was made type-explicit for Pylint.
- The second completed directory is `scripts/`. Eleven Python scripts received
  only Black/isort formatting; no behavior, dead-code decision, or script entry
  point was changed.
- The third completed directory is `ai_actuarial/agentic_rag/`. Graphify
  confirmed that its primary modules connect to runtime/API consumers and
  dedicated tests, so seven historical files received only Black/isort
  formatting and no file or symbol was removed.
- The fourth completed directory is `ai_actuarial/api/middleware/`. Its single
  implementation file is directly exercised by FastAPI auth and ops tests, so
  it received only Black/isort formatting and no file or symbol was removed.
- The fifth completed directory is `ai_actuarial/models/`. Both the package
  exports and `ApiToken` model have direct runtime/storage consumers and
  dedicated tests, so both files received only Black/isort formatting.
- The sixth completed directory is `ai_actuarial/security/`. Both production
  files are imported by crawler, listening-rule, and API-service paths and are
  covered by URL-safety and integration tests, so both files received only
  Black/isort formatting and no symbol was removed.
- The seventh completed directory is `ai_actuarial/services/`. The package
  export and token-encryption implementation have direct runtime, API, and
  diagnostic consumers plus dedicated integration tests, so both files
  received only Black/isort formatting and no symbol was removed.
- The eighth completed directory is `ai_actuarial/processors/`. Unlike the
  earlier directories, all three Python modules were production-unreachable,
  had no code or test callers, and were already classified `remove` in the
  reviewed dead-code baseline. The three modules and their inaccurate README
  were deleted rather than reformatted.
- The ninth completed directory is `ai_actuarial/collectors/`. Current source
  and exact repository search confirmed that `AdhocCollector` had no runtime,
  test, export, or dynamic caller; its stale Graphify edge pointed to an import
  no longer present in the current CLI. The orphan module and its README claim
  were deleted, two unused imports were removed, and the five reachable
  collector implementations were formatted. The exported
  `CollectionConfig.auto_download` constructor field was retained because
  Issue #317 forbids deleting a public API solely from static-analysis output.
- The tenth completed directory is the direct files under `ai_actuarial/api/`
  (excluding its separately reviewed subdirectories). `app.py`, `deps.py`, and
  `route_inventory.py` were formatted. The `deps.py` email-session selection
  now uses an explicit typed branch instead of a conditional expression,
  preserving behavior while removing its Pylint E1136 false inference. The
  reported `block_retired_api_fallback` symbol remains because its FastAPI
  decorator registers the framework route at runtime.
- The eleventh completed directory is `ai_actuarial/chatbot/`. Seven reachable
  implementation files and the package exports were formatted. Six confirmed
  unused public symbols plus the private `_extract_citations` helper used only
  by a removed method were deleted. No test imported or exercised those
  symbols, so no test was deleted; all tests covering retained chatbot behavior
  remain. `QueryRouter.select_kbs` remains because its source explicitly marks
  it as a backward-compatible alias, and the public configuration fields remain
  part of the configuration contract.
- The twelfth completed directory is `ai_actuarial/rag/`. All ten modules have
  production or test consumers, so no module was deleted. Ten confirmed unused
  baseline symbols were removed, along with four additional helpers or
  attributes that exact caller analysis and the cleanup itself showed were
  unreachable. `RAGConfig.chunk_strategy` remains because YAML, environment,
  migration, documentation, and tests establish it as a public configuration
  contract. The one test dedicated to proving the removed
  `_soft_delete_file_vectors` helper was not called was deleted with that
  helper; all retained RAG behavior remains covered.

## Acceptance results

- Unified quality gate: passed. Pytest reported 1,880 passed and 10 skipped;
  Black, isort, and Pylint exactly matched the current reviewed baselines at
  159 files, 99 files, and 19 error identities respectively.
- Dead-code gate: passed with 9/1 file findings and 28/72 symbol findings,
  exactly matching the classified baseline and with no 100%-confidence
  Vulture finding.
- Dead-code and quality-gate unit tests: 11 passed as part of the full suite.
- Flaky schema-validator isolation regression: passed five consecutive focused
  runs and then passed in the full suite.
- Frontend ESLint: passed with six existing React dependency warnings and no
  errors.
- Frontend TypeScript check: passed.
- Frontend production build: passed; Vite emitted only the existing large
  chunk advisory.
- Clean lockfile install: `npm ci` passed. npm reported nine dependency audit
  findings (2 low, 1 moderate, 6 high); dependency/security upgrades are
  outside Issue #317.
- Pre-commit config validation, CI YAML parsing, CLI `--help`, and
  `git diff --check`: passed.
- Post-CI focused regression: 6 passed and 5 Windows symlink skips. Static
  baselines now match exactly at 213 Black files, 142 isort files, and 22
  Pylint identities; the dead-code gate remains exact.
- After the Copilot fix, its focused regression passed, then the complete
  unified quality gate passed again with 1,880 passed and 10 skipped; the
  dead-code gate also remained exact at 9/5 files and 28/93 symbols.
- After the nested-audit assertion fix, its focused regression passed. Static
  baselines remain exact at 213/142/22 with no new or stale entries, and the
  dead-code gate remains exact at 9/5 files and 28/93 symbols. Final Linux CI
  run 33456929109 passed all five jobs; its unified gate reported 1,891 tests
  passed, including the four original symlink tests, then passed Black, isort,
  and Pylint.
- `config/` focused validation passed: Black, isort, and Pylint reported no
  findings; 36 tests passed and 1 platform-specific test skipped.
- The complete unified quality gate passed after the `config/` cleanup with
  1,881 tests passed and 10 skipped. Its reviewed baseline shrank only for this
  directory, from 213/142/22 to 210 Black files, 140 isort files, and 20 Pylint
  identities.
- The complete dead-code gate also passed unchanged at 9/5 file findings and
  28/93 symbol findings.
- Path-specific commit `fc814fa` was pushed to PR #318. CI run 33460353038
  passed all five jobs: both dead-code layers, frontend, Python smoke, and the
  complete Linux quality gate. No new review comment was added.
- `scripts/` focused validation passed: Black, isort, and Pylint reported no
  findings; 80 tests passed and 1 platform-specific test skipped.
- The complete unified quality gate passed after the `scripts/` cleanup with
  1,881 tests passed and 10 skipped. The reviewed baseline shrank only for this
  directory, from 210/140/20 to 200 Black files, 132 isort files, and 20 Pylint
  identities. The complete dead-code gate remained exact at 9/5 files and
  28/93 symbols.
- Path-specific commit `c601182` was pushed to PR #318 and all five remote CI
  jobs passed with no new review feedback.
- `ai_actuarial/agentic_rag/` focused validation passed: Black, isort, and
  Pylint reported no findings, and all 94 dedicated tests passed.
- The complete unified quality gate passed after the `agentic_rag/` cleanup
  with 1,881 tests passed and 10 skipped. The reviewed baseline shrank only for
  this directory, from 200/132/20 to 193 Black files, 127 isort files, and 20
  Pylint identities. The complete dead-code gate remained exact at 9/5 files
  and 28/93 symbols.
- The machine's existing global Black cache caused high-CPU CLI stalls for the
  changed files. Black's API verified them immediately; the official CLI and
  complete gate then passed with an isolated temporary `BLACK_CACHE_DIR`.
- Remote commit `5356248` contains the exact `agentic_rag/` tree and passed all
  five PR #318 jobs in CI run 33467686369. GitHub authentication and the branch
  update used a task-scoped temporary credential because the sandbox cannot
  replace the invalid user-level GitHub CLI credential.
- `ai_actuarial/api/middleware/` focused validation passed: Black, isort, and
  Pylint reported no gate findings, and all 27 direct FastAPI tests passed.
- The temporary clone initially lacked its ignored root `node_modules`, so 16
  TypeScript subprocess tests could not start. `npm ci` restored the pinned
  dependencies, all 16 focused tests passed, and the complete pytest rerun then
  passed with 1,881 tests and 10 platform skips.
- The full static gate passed after the `middleware/` cleanup at 192 Black
  files, 126 isort files, and 20 Pylint identities, with zero new or stale
  entries. The complete dead-code gate remained exact at 9/5 files and 28/93
  symbols.
- Remote commit `b2c0d92` contains the exact `middleware/` tree. CI run
  33470766007 passed all five jobs, including the 6m27s Linux quality gate, and
  no new Review or Copilot comment was added.
- `ai_actuarial/models/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 23 model/storage integration tests passed.
- The complete pytest suite passed after the `models/` cleanup with 1,881 tests
  and 10 platform skips. The full static gate passed at 190 Black files, 124
  isort files, and 20 Pylint identities, with zero new or stale entries. The
  dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `2fff76c` contains the exact `models/` tree. CI run
  33472039867 passed all five jobs, including the 7m30s Linux quality gate, and
  no new Review or Copilot comment was added.
- `ai_actuarial/security/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 70 URL-safety and direct-consumer tests
  passed.
- The complete pytest suite passed after the `security/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 188 Black files,
  123 isort files, and 20 Pylint identities, with zero new or stale entries.
  The complete dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `0699b47` contains the exact `security/` tree. CI run
  33473548630 passed all five jobs, including the 11m04s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/services/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 120 token-encryption and direct-consumer
  tests passed.
- The complete pytest suite passed after the `services/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 186 Black files,
  122 isort files, and 20 Pylint identities, with zero new or stale entries.
  The complete dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `4bc201e` contains the exact `services/` tree. CI run
  33475164224 passed all five jobs, including the 7m05s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/processors/` focused validation found no remaining Python
  caller, compiled the repository successfully, and passed all 23 catalog,
  collector, and dead-code-gate regression tests.
- The complete pytest suite passed after removing `processors/` with 1,881
  tests and 10 platform skips. The full static gate passed at 184 Black files,
  121 isort files, and 20 Pylint identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/5 files and 28/93 symbols to 9/2
  files and 28/89 symbols.
- Remote commit `a7c502e` contains the exact `processors/` tree. CI run
  33476666119 passed all five jobs, including the 7m51s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/collectors/` compiled successfully, had no remaining
  `AdhocCollector` reference, passed Black and isort, and passed all 253 tests
  in the ten directly importing collector modules or their runtime consumers.
- The complete pytest suite passed after the `collectors/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 178 Black files,
  116 isort files, and 20 Pylint error identities, with zero new or stale
  entries. The dead-code gate shrank exactly from 9/2 files and 28/89 symbols
  to 9/1 files and 28/88 symbols.
- Remote commit `915fc4d` contains the exact `collectors/` tree. CI run
  33511516566 passed all five jobs, including the 7m48s Linux quality gate,
  and no new Review or Copilot comment was added.
- The direct `ai_actuarial/api/` files compiled successfully and passed Black,
  isort, and a zero-error focused Pylint scan. All 407 directly importing tests
  completed with 400 passed and 7 platform skips.
- The complete pytest suite passed after the direct `api/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 175 Black files,
  114 isort files, and 19 Pylint error identities, with zero new or stale
  entries. The dead-code gate remained exact at 9/1 files and 28/88 symbols.
- Remote commit `bf2d2a0` contains the exact direct `ai_actuarial/api/` cleanup.
  CI run 33513870640 passed all five jobs, including the 7m35s Linux quality
  gate, and no new Review or Copilot comment was added.
- `ai_actuarial/chatbot/` compiled successfully and passed Black, isort, and a
  zero-error focused Pylint scan. All 176 chatbot and direct-consumer tests
  passed. No dedicated test existed for any removed symbol, so no corresponding
  test removal was required.
- The complete pytest suite passed after the `chatbot/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 168 Black files,
  107 isort files, and 19 Pylint error identities, with zero new or stale
  entries. The dead-code gate shrank exactly from 9/1 files and 28/88 symbols
  to 9/1 files and 28/82 symbols.
- Remote commit `675c2b5` contains the exact `ai_actuarial/chatbot/` cleanup.
  CI run 33530581036 passed all five jobs, including the 8m02s Linux quality
  gate, and no new Review or Copilot comment was added.
- `ai_actuarial/rag/` compiled successfully and passed Black, isort, and a
  zero-error focused Pylint scan. The 24 directly importing test files completed
  with 646 passed and 8 platform skips after the one obsolete test was removed.
- The complete pytest suite passed after the `rag/` cleanup with 1,880 tests
  and 10 platform skips. The full static gate passed at 159 Black files, 99
  isort files, and 19 Pylint error identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/1 files and 28/82 symbols to 9/1
  files and 28/72 symbols.
- Remote commit `fdac797` contains the exact `ai_actuarial/rag/` cleanup. CI
  run 33534463645 passed all five jobs, including the 7m56s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/api/routers/` compiled successfully and all 15 route modules
  were confirmed as registered FastAPI production modules. The 15 directly
  related test files completed with 393 passed and 8 platform skips.
- `WeeklySnapshotFilesModel.truncated` is a live Pydantic response field, not
  dead code: the service populates it and endpoint tests assert it. An exact
  whitelist reference now records that framework contract; no source field or
  test was removed.
- The complete pytest suite passed after the router cleanup with 1,880 tests
  and 10 platform skips. The full static gate passed at 146 Black files, 91
  isort files, and 19 Pylint error identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/1 files and 28/72 symbols to 9/1
  files and 28/71 symbols.
- Remote commit `a71e984` contains the exact `ai_actuarial/api/routers/`
  cleanup. CI run 33537947899 passed all five jobs, including the 6m53s Linux
  quality gate, and no new Review or Copilot comment was added.
- `ai_actuarial/api/services/` compiled successfully. Seven confirmed dead
  baseline symbols and two resulting private orphans were removed; no test was
  dedicated to those deleted definitions, so no test removal was required.
- The provider-credential write and environment-import paths now pass
  `status_code=503` correctly when token encryption is unavailable instead of
  raising `TypeError`. A regression covers both HTTP entry points. The ready
  source gate also uses an explicit mapping check, removing a Pylint inference
  false positive without changing its behavior.
- The 12 directly related service test files completed with 462 passed and 9
  platform skips. The complete pytest suite passed with 1,881 tests and 10
  platform skips. The full static gate passed at 129 Black files, 81 isort
  files, and 16 Pylint error identities, with zero new or stale entries. The
  dead-code gate shrank exactly from 9/1 files and 28/71 symbols to 9/1 files
  and 28/64 symbols.
- Remote commit `cbd933b` contains the exact `ai_actuarial/api/services/`
  cleanup. CI run 33539534698 passed all five jobs, including the 6m47s Linux
  quality gate, and no new Review or Copilot comment was added.
- `client/src/components/` no longer contains the unreachable
  `LoadingSkeleton.tsx`. `transformMarkdownUrl` remains live inside
  `MarkdownContent.tsx` but is no longer exported solely for tests; the direct
  helper assertions were removed while the component-level link and hostile
  input coverage was retained.
- The focused component checks passed: both TypeScript dead-code ratchets,
  ESLint, the three Markdown content source tests, frontend type-check, and the
  production build. The complete pytest suite passed with 1,881 tests and 10
  platform skips, and the full unified quality gate passed at 129 Black files,
  81 isort files, and 16 Pylint error identities. The dead-code gate shrank
  exactly from 9/1 files and 28/64 symbols to 8/1 files and 27/64 symbols.
- Remote commit `182d0c0` contains the exact `client/src/components/` cleanup.
  CI run 33540711906 passed all five jobs, including the 13m42s Linux quality
  gate, and no new Review or Copilot comment was added.
- `client/src/hooks/` no longer contains the completely unreferenced
  `use-api-query.ts`. The two live task-option result shapes remain in use but
  are now private implementation types instead of unused public exports.
- The hooks directory passed ESLint, the 27 task React source tests, frontend
  type-check, and the production build. The complete pytest suite passed with
  1,881 tests and 10 platform skips, and the full unified quality gate passed
  at 129 Black files, 81 isort files, and 16 Pylint error identities. The
  dead-code gate shrank exactly from 8/1 files and 27/64 symbols to 7/1 files
  and 25/64 symbols.
- Remote commit `f80d52d` contains the exact `client/src/hooks/` cleanup. CI
  run 33542287174 passed all five jobs, including the 7m35s Linux quality gate,
  and no new Review or Copilot comment was added.
- `client/src/lib/` now exposes only externally consumed contracts. Two unused
  navigation helpers and the test-only knowledge-list authority helper were
  removed; the duplicate ready-data route helper was consolidated under the
  request name. Live helpers and data shapes that are internal to their module
  remain implemented but are no longer exported.
- Tests were updated to exercise the public ready-data merge helper and native
  URL parsing. The one runtime test segment dedicated only to the removed
  authority helper was deleted; the surrounding current behavior tests remain.
  All 77 focused tests, ESLint, frontend type-check, and the production build
  passed. The complete pytest suite passed with 1,881 tests and 10 platform
  skips, and the unified quality gate passed at 129/81/16. The dead-code gate
  shrank exactly from 7/1 files and 25/64 symbols to 7/1 files and 7/64 symbols.
- Remote commit `8beb8d8` contains the exact `client/src/lib/` cleanup. CI run
  33543437722 passed all five jobs, including the 7m41s Linux quality gate, and
  no new Review or Copilot comment was added.
- Five unreachable historical page implementations were removed from
  `client/src/pages/`: `FeatureUnavailable`, `NativeFileDetail`, `NativeLogs`,
  `NativeSettings`, and `NativeTasks`. The live chat route selection type is
  now private to its module.
- Test constants and assertions that read the deleted native file/task pages
  were removed while current FileDetail, FilePreview, task metrics, Markdown,
  and chat route coverage was retained. All 41 focused tests, directory ESLint,
  frontend type-check, and the production build passed. The complete pytest
  suite passed with 1,881 tests and 10 platform skips, and the unified quality
  gate passed at 129/81/16. The dead-code gate shrank exactly from 7/1 files
  and 7/64 symbols to 2/1 files and 6/64 symbols.
- Remote commit `77e54a9` contains the exact `client/src/pages/` cleanup. CI
  run 33544476773 passed all five jobs, and no new review comment was added.
- `client/src/pages/tasks/` no longer contains the unreachable
  `FolderBrowser.tsx` or its unreachable barrel `index.ts`. Three live
  implementation details remain in use but are no longer exported, and three
  duplicate schedule types with no caller were removed. The negative test
  proving that browser uploads do not use the retired folder browser remains
  because it covers current behavior.
- The task-page cleanup passed 32 focused source/runtime tests, directory
  ESLint, frontend type-check, and the production build. One full-suite source
  assertion was corrected to inspect the shared `TaskMetrics` implementation
  instead of relying on a removed re-export comment; its focused rerun passed.
- The complete pytest suite then passed with 1,881 tests and 10 platform skips,
  and the unified quality gate passed at 129/81/16. The dead-code gate shrank
  exactly from 2/1 files and 6/64 symbols to 0/1 files and 0/64 symbols, so the
  TypeScript historical dead-code baseline is now empty.
- Remote commit `0bbda30` contains the exact `client/src/pages/tasks/`
  cleanup. CI run 33547151953 passed all five jobs, including the complete
  Linux quality gate, and no new review comment was added.
- The exported `CollectionConfig.auto_download` dataclass field was retained as
  a public constructor contract and added to the statically validated exact
  whitelist. No source or test was deleted. All 112 directly related collector
  tests passed, and Black, isort, and Pylint passed for the touched whitelist
  and collector base files.
- The complete pytest suite passed with 1,881 tests and 10 platform skips, and
  the unified quality gate passed at 129/81/16. The dead-code gate shrank
  exactly from 0/1 files and 0/64 symbols to 0/1 files and 0/63 symbols.
- Remote commit `1a792e0` contains the exact collector public-contract
  classification. CI run 33549779936 passed all five jobs, including the
  complete Linux quality gate, and no new review comment was added.
- The final unreachable Python module `ai_actuarial/pipeline_config.py` was
  deleted. Its 20-test dedicated file and four tests in the immutable-guards
  suite that imported only that module were deleted with it; the live manifest
  schema-version ingestion traceability test remains.
- The pipeline-config cleanup compiled successfully, passed all 44 retained
  focused tests, and left no repository reference to the deleted module. The
  complete pytest suite passed with 1,857 tests and 10 platform skips. The
  unified quality gate passed after shrinking to 127 Black files, 80 isort
  files, and 16 Pylint identities. Both TypeScript and Python dead-file
  baselines are now empty; symbol findings remain 0/63.

## Files changed

- Gate implementation/config: `scripts/dead_code_gate.py`,
  `scripts/quality_gate.py`, `knip.json`, `eslint.config.mjs`, `pyproject.toml`,
  `package.json`, lockfile, development requirements, and both baselines.
- Framework review: `config/dead_code_whitelist.py`.
- Automation: `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.
- Documentation: `docs/dead-code.md`, docs index, and both root READMEs.
- Focused cleanup/tests: affected React files, small Python unused-argument
  cleanups, gate tests, and narrow full-suite contract corrections.
- First historical directory cleanup: `config/__init__.py`,
  `config/settings.py`, `config/yaml_config.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Second historical directory cleanup: eleven formatted Python files under
  `scripts/` and the matching removals from `quality-gate-baseline.json`.
- Third historical directory cleanup: seven formatted Python files under
  `ai_actuarial/agentic_rag/` and the matching removals from
  `quality-gate-baseline.json`.
- Fourth historical directory cleanup:
  `ai_actuarial/api/middleware/rate_limit.py` and the matching removals from
  `quality-gate-baseline.json`.
- Fifth historical directory cleanup: `ai_actuarial/models/__init__.py`,
  `ai_actuarial/models/api_token.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Sixth historical directory cleanup: `ai_actuarial/security/__init__.py`,
  `ai_actuarial/security/url_safety.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Seventh historical directory cleanup: `ai_actuarial/services/__init__.py`,
  `ai_actuarial/services/token_encryption.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Eighth historical directory cleanup: deleted the unreachable
  `ai_actuarial/processors/` package and its inaccurate README, then removed
  exactly three module and four method findings from `dead-code-baseline.json`
  plus the three matching formatter paths from `quality-gate-baseline.json`.
- Ninth historical directory cleanup: deleted
  `ai_actuarial/collectors/adhoc.py`, removed its inaccurate README section and
  two dead-code findings, removed two unused imports, formatted the five
  reachable collector implementations, and removed their eleven matching
  formatter paths from `quality-gate-baseline.json`.
- Tenth historical directory cleanup: formatted `ai_actuarial/api/app.py`,
  `ai_actuarial/api/deps.py`, and `ai_actuarial/api/route_inventory.py`, made
  the authentication type narrowing explicit, and removed their six matching
  Black/isort/Pylint entries from `quality-gate-baseline.json`.
- Eleventh historical directory cleanup: formatted all eight Python files under
  `ai_actuarial/chatbot/`, removed six confirmed unused public symbols and one
  private helper, reclassified the explicit `select_kbs` compatibility alias,
  and removed the matching dead-code and formatter baseline entries. No test
  file or test case was removed because none corresponded to the deleted code.
- Twelfth historical directory cleanup: formatted the nine historical Python
  files under `ai_actuarial/rag/`, removed ten reviewed dead-code baseline
  symbols plus four exact or cascading orphans, deleted the single test tied to
  the removed immutable-index helper, and removed the matching dead-code and
  formatter baseline entries.
- Thirteenth historical directory cleanup: formatted all 15 files under
  `ai_actuarial/api/routers/`, added the precise Pydantic response-field
  whitelist for `WeeklySnapshotFilesModel.truncated`, and removed its stale
  dead-code entry plus the 21 matching formatter baseline entries.
- Fourteenth historical directory cleanup: formatted all 17 files under
  `ai_actuarial/api/services/`, removed seven reviewed dead-code baseline
  symbols plus two cascading private orphans, fixed three Pylint identities,
  added the two-entry-point encryption failure regression, and removed the
  matching dead-code and 27 formatter/linter baseline entries.
- Fifteenth historical directory cleanup: deleted the unreachable
  `client/src/components/LoadingSkeleton.tsx`, made the live Markdown URL
  transformer private, removed only its direct test-only import and assertions,
  and removed the matching two TypeScript dead-code baseline entries.
- Sixteenth historical directory cleanup: deleted the unreachable
  `client/src/hooks/use-api-query.ts`, made two live task-option interfaces
  private, and removed the matching three TypeScript dead-code baseline entries.
- Seventeenth historical directory cleanup: removed three confirmed dead
  `client/src/lib/` functions, consolidated a duplicate ready-data request
  export, made fourteen live implementation details private, updated the one
  cross-directory caller and focused tests, and removed the matching eighteen
  TypeScript dead-code baseline entries.
- Eighteenth historical directory cleanup: deleted five unreachable legacy
  files under `client/src/pages/`, made the live chat route selection type
  private, removed only the test constants and assertions tied to the deleted
  pages, and removed the matching six TypeScript dead-code baseline entries.
- Nineteenth historical directory cleanup: deleted the unreachable
  `client/src/pages/tasks/FolderBrowser.tsx` and barrel `index.ts`, removed
  three unused exports and three unused duplicate schedule types, corrected
  one source-contract test to inspect the real shared metrics component, and
  removed the final eight TypeScript dead-code baseline entries.
- Twentieth historical directory cleanup: retained the public exported
  `CollectionConfig.auto_download` constructor field, recorded its exact
  compatibility reference in the validated whitelist, and removed its stale
  Python dead-code baseline entry without changing source or tests.
- Twenty-first historical directory cleanup: deleted the unreachable
  `ai_actuarial/pipeline_config.py` module and its 24 module-only tests,
  formatted the touched immutable-guards test while preserving its live
  manifest traceability case, and removed the final Python dead-file baseline
  plus the matching Black/isort baseline entries.
- Twenty-second historical directory cleanup: formatted all 31 direct Python
  files under `ai_actuarial/`, deleted 20 confirmed-unused root symbols plus one
  cascading legacy weekly-summary reader, retained 27 framework/public
  contracts through exact validated whitelist references, and narrowed seven
  SQLAlchemy/Pydantic Pylint suppressions to their individual call sites. No
  test was removed because none was dedicated to the deleted code. Focused
  tests passed 132/1, the full suite passed 1857/10, the dead-code gate passed
  at 0 files/17 symbols, and the quality baseline fell from 127/80/16 to
  96/60/9.
- Twenty-third historical directory cleanup: retained the nested
  `block_retired_api_fallback` FastAPI 410 route in `ai_actuarial/api/app.py`
  and added its exact source-level framework reference. Focused tests passed
  20/20; after one host-resource-abnormal test run was stopped and isolated,
  the unchanged historical file passed 83/83 and a clean full rerun passed
  1857/10 plus Black, isort, and Pylint. The dead-code symbol baseline fell
  from 17 to 16; the quality baseline remains 96/60/9. The first remote
  quality-gate attempt hit a concurrent-test race in an unrelated historical
  schema test; the failed job rerun passed without source changes, and all five
  remote CI jobs are green.
- Twenty-fourth historical directory cleanup: retained six public exported
  `ChatbotConfig` fields loaded from environment/YAML settings plus the
  explicit `QueryRouter.select_kbs` compatibility alias, recording each as an
  exact validated whitelist reference. No production code or tests were
  removed. Focused tests passed 115/115, the full suite passed 1857/10 plus
  Black, isort, and Pylint, and the dead-code symbol baseline fell from 16 to
  9; the quality baseline remains 96/60/9. All five remote CI jobs passed.
- Twenty-fifth historical directory cleanup: retained the public
  `RAGConfig.chunk_strategy` field loaded from environment/YAML settings and
  recorded its exact validated whitelist reference. No production code or
  tests were removed. Focused tests passed 41/41, the full suite passed 1857/10
  plus Black, isort, and Pylint, and the dead-code symbol baseline fell from 9
  to 8; the quality baseline remains 96/60/9. All five remote CI jobs passed.
- Twenty-sixth historical directory cleanup: formatted all six Python files
  under `tests/agentic_rag/` (five Black and two isort baseline identities) and
  strengthened `test_evaluate_single_pass` to verify the fake retriever
  receives the query and `top_k`. No tests were removed. Focused tests passed
  102/102, the full suite passed 1857/10 plus Black, isort, and Pylint, the
  dead-code symbol baseline fell from 8 to 6, and the quality baseline fell
  from 96/60/9 to 91/58/9. All five remote CI jobs passed.
- Twenty-seventh historical directory cleanup: formatted the two historical
  Python test files under `tests/unit/`, removing two Black and two isort
  baseline identities. No code or tests were removed. Focused tests passed
  40/40, the full suite passed 1857/10 plus Black, isort, and Pylint, the
  dead-code baseline remains 0 files/6 symbols, and the quality baseline fell
  from 91/58/9 to 89/56/9. All five remote CI jobs passed.
- Twenty-eighth and final historical directory cleanup: formatted all 105
  direct Python files under `tests/` (89 historical Black and 56 isort baseline
  identities), resolved all nine Pylint identities, removed six unused test
  symbols without deleting any test case, strengthened the API-token timestamp
  assertion, and isolated the mutating schema-validator test from background
  database activity. Focused tests passed 319/7, the full suite passed 1857/10,
  independent semantic and mechanical reviews found no issues, and both the
  dead-code and quality baselines are now completely empty: 0 files/0 symbols
  and 0/0/0 respectively. All five remote CI jobs passed. PR #318 is clean and
  mergeable; the only review thread was an older Copilot finding already fixed
  and acknowledged before this final cleanup.

## Working tree notes

- Existing untracked `diagrams/` and `graphify-out/` remain user-owned,
  untouched, and excluded from the commit.
- Generated `reports/`, coverage output, build output, and installed
  dependencies are ignored.

## Blockers or decisions needed

- No implementation or local validation blocker.
- Merge is not authorized by the current request; publication stops at an open
  PR unless explicit merge authorization is given.

## Recommended next action

- Report the completed directory-by-directory cleanup and leave the clean,
  mergeable PR #318 open. Merge only after explicit authorization.
