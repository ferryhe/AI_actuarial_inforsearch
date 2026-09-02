# Project Status — Issue #322 Markdown terminal preflight

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\8480\AI_actuarial_inforsearch`
- Branch: `codex/issue-322-markdown-terminal-preflight`
- Baseline: `origin/main@e0645f92b867a7209af91f2ddd28027cede28778`
- Issue: `#322 fix(markdown): preflight terminal source failures before conversion`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-322.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/330`
- Delivery stage: PR #330 is Ready. Its single feedback window completed after 720.2 seconds;
  the sole valid Copilot wording fix is pending commit/push and current-head CI.
- Progress heartbeat: id `issue-322-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #322 acceptance criteria

- AC-1: A legacy binary `.ppt` is classified as `unsupported_legacy_ppt` before converter
  execution and is excluded from later automatic Markdown backlogs while its source/state is
  unchanged, unless an operator explicitly retries it.
- AC-2: A missing local source is durably classified as `repair_required` before converter
  execution and does not repeat the same scheduled conversion error.
- AC-3: A `.pdf` whose declared MIME/content kind or magic identifies HTML is durably classified
  as `invalid_source` and is not accepted solely from its extension or URL.
- AC-4: Terminal preflight outcomes remain distinct from retryable converter failures. An unchanged
  terminal source stays out of ordinary incremental selection; a verified source/state change or
  explicit operator selection makes it eligible again under one narrow rule.
- AC-5: Terminal skips have their own task counter and per-item result visibility, separate from
  successful conversions, ordinary skips, and retryable errors; they cannot falsely make a run
  successful.
- AC-6: Auto exhaustion preserves every attempted converter and its concrete failure reason in
  task details instead of only `Auto conversion failed`.
- AC-7: Valid supported sources preserve the existing incremental selection, conversion,
  persistence, and retry behavior; downstream Chunk and Embedding contracts do not change.
- AC-8: Regression tests cover legacy PPT, missing source, HTML-disguised PDF, a valid supported
  control, durable exclusion/re-entry, separate terminal statistics, and Auto failure details.

## Issue #322 baseline and duplicate evidence

- After fetch, `HEAD`, `origin/main`, and their merge-base all matched the supplied baseline
  `e0645f92b867a7209af91f2ddd28027cede28778`; the worktree was clean and detached before the
  isolated task branch was created.
- No open, closed, or merged PR matched Issue #322, its URL/number, or the distinctive terminal
  Markdown-preflight title. The remote exposes only `main`, and targeted commit history found no
  equivalent terminal source state. Closed Issue #319 changes loose-coupled stage continuation and
  does not implement Markdown source preflight or terminal eligibility.
- A temporary-database reproduction made a real OLE-header `.ppt`, a missing `.pdf`, an HTML-body
  `.pdf` with `content_type=text/html` and `content_kind=web_page`, and a valid `%PDF` control.
  The first run called a converter for the PPT, HTML PDF, and valid PDF; the HTML PDF was accepted.
  The second ordinary run selected the unchanged PPT and missing PDF again and repeated both
  failures.
- A separate runtime reproduction forced `markitdown` and `local` to fail concretely. The exposed
  Auto error was only `Auto conversion failed for control.pdf`; only the final `local` failure
  survived as the exception cause.
- `git blame` and targeted `git log -S` trace broad candidate selection and missing-file retries to
  the original May task runtime, and generic Auto exhaustion to the February/June converter work.
  No later history establishes terminal preflight as intentionally excluded, so the bug premise is
  current.

## Issue #322 scope and validation

- Worker-owned scope is limited to Markdown candidate selection/preflight, the smallest durable
  state needed for unchanged-terminal exclusion and source-change/explicit-selection re-entry,
  task result/stat visibility, Auto failure details, and directly corresponding migrations/tests.
- Likely touched surfaces are `ai_actuarial/task_runtime.py`, storage/schema code only if durable
  state requires it, the two task display-summary services, the shared frontend task metrics/types
  and bilingual label, plus focused Python/React/schema tests. Exact edits must be justified by an
  acceptance criterion; `doc_to_md/registry.py` is an inspected sibling and is edited only if the
  task contract actually routes through it.
- Required final checks: Issue-focused red/green tests, relevant Markdown/task/API/schema/frontend
  regression, `git diff --check`, both dead-code gates, frontend lint/type-check/build, the unified
  quality gate, and all three Python smoke commands from CI. Browser smoke is required if visible
  Task metrics change.
- Non-goals: LibreOffice or new converter installation, automatic source repair/redownload,
  Issue #319 pipeline redesign, downstream Chunk/Embedding changes, sibling-repository work,
  security frameworks, schema registries, or speculative abstractions.
- No unrelated uncommitted or untracked files were present at startup. Generated ignored
  `graphify-out/` data is manager-created analysis output and will not be committed.

## Issue #322 implementation and local review

- A schema-v14 `markdown_terminal_source_state` record persists `unsupported_legacy_ppt`,
  `repair_required`, or `invalid_source` together with a bounded source fingerprint. Ordinary
  selection excludes an unchanged terminal source before logical offset/limit, while explicit
  selection and verified source changes re-enter preflight.
- Task results keep downstream-ready files separate from per-item outcomes, expose an independent
  `items_terminal_skipped` metric through both API summaries and the shared Task UI, and do not
  report a terminal-only run as successful. Retryable converter failures remain eligible.
- Runtime Auto and the same-shaped converter registry now retain every attempted converter and a
  bounded concrete reason. Candidate reasons share the 800-character public budget, so later
  candidates cannot disappear from the final task detail.
- TDD first reproduced 12 failures for the original implementation gap. Local review round 1 found
  two valid defects: generic-MIME OLE `.ppt` records were omitted from the automatic candidate
  predicate, and a long Auto aggregate was truncated before all converter reasons reached the
  public task result. The same persistent worker fixed both with red/green tests.
- Fresh read-only review round 2 independently checked the full diff and returned PASS. Current
  evidence includes 11 Issue-focused tests, 324 related regression tests, schema and Pipeline Baton
  coverage, frontend TaskMetrics runtime/type checks, and `git diff --check` passing.
- The first final dead-symbol gate found one Issue-added exported-but-module-private
  `TaskFileOutcome`. The same persistent worker removed only the unnecessary `export`; the gate
  then passed with zero findings. Because this happened after round 2 PASS, a third fresh read-only
  reviewer checked the full current diff and returned supplemental PASS with no findings.

## Issue #322 final local validation

- Unified quality gate passed: 2,011 tests passed and 10 skipped, then Black, isort, and Pylint all
  passed.
- Dead-code files and symbols both passed with zero baseline findings. Frontend lint passed with
  zero errors and five existing Hook warnings; TypeScript type-check and production build passed,
  with only the existing large-chunk advisory.
- Python CI smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI
  evaluation cases. Evidence/citation/refusal rates were 1.0 and unsupported-answer rate was 0.0.
- In-app-browser smoke used an isolated temporary database and one local test token. The real Task
  History page rendered `Terminal skips: 1` for a Markdown terminal-source result, and browser
  console errors were empty. Both local services were stopped after the check; no real account or
  production data was used.
- `git diff --check` passed. CRLF notices are informational workspace conversion warnings.
- Files in scope: Markdown runtime, storage/schema, both task summary services, shared Task metric
  UI/types/i18n, same-shaped converter registry, focused Issue test, related schema/task/frontend
  regression fixtures, and this manager-owned status file. No downstream Chunk/Embedding production
  code changed.

## Issue #322 remote feedback

- PR #330 was marked Ready at head `a0474909ee11b1c5fca8cc046753b737c80161ab`.
  One complete snapshot was fetched 720.2 seconds later; there will be no second feedback fetch.
- All five required checks on that head passed. No PR conversation comment or Issue comment was
  present. Copilot left one inline comment about a failed item still reporting `Converted` progress.
- The persistent worker and manager confirmed the comment under AC-5: a canonical
  `retryable_error` must not have success-shaped visible progress. The minimal fix changes only
  `Converted markdown` to neutral `Processed markdown` and adds a public-result progress assertion.
- The new assertion failed before the fix and passed afterward. The worker also passed 131 related
  tests plus Black, isort, Python compilation, and diff checks; the manager independently reran the
  focused public-result test successfully.

## Issue #322 blockers or decisions needed

- None. Commit and push the confirmed wording fix, wait for all five required checks on the new
  exact head, then squash merge, verify Issue closure, and clean the remote branch, worktree, and
  local branch.

# Project Status — Issue #320 strict manifest validation

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\7a36\AI_actuarial_inforsearch`
- Branch: `codex/issue-320-strict-manifest-validation`
- Baseline: `origin/main@29b73be7ecf65d236570b5f9d698783a8966cb46`
- Issue: `#320 fix(manifest): reject incompatible producer payloads instead of silent zero import`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-320.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/329`
- Delivery stage: Draft PR #329 created with `Closes #320`; final status commit pending before the
  Ready transition and single 600-second feedback/CI window

## Issue #320 scope and acceptance criteria

- Accept only the exact supported legacy `web-listening-manifest.v1` object contract, with
  non-empty manifest/run/source identities and a `downloaded_assets` list. Full producer Result
  envelopes, nested manifests, unsupported schemas, missing identities, and wrong container types
  fail with stable machine-readable errors instead of succeeding with zero imported assets.
- Parse raw JSON fail-closed, including duplicate keys at any depth and non-standard numeric
  constants. Preflight every asset before any transaction: object and asset identity; absolute
  HTTP(S) URL; SHA-256 checksum; media type; non-boolean, non-negative integer byte count;
  filename; and at least one valid path field with documented precedence.
- Keep valid legacy behavior: archive the original manifest bytes exactly, retain content kind,
  preserve URL/SHA upsert behavior and path precedence, and make repeated ingestion idempotent.
- Direct ingestion, task execution, task history, and API-visible errors expose only stable codes
  and safe field metadata; malformed inputs cannot leak payload values, credentials, signed query
  strings, cookies, or local secret paths through error chains or logs.
- Non-goals: external consumer/adapter changes, producer API calls, artifact downloads, Baton or
  new lineage work, a schema registry, storage redesign, migration, or backfill. Sibling
  repositories remain off-limits.

## Issue #320 baseline and duplicate evidence

- Startup confirmed the assigned worktree on the exact supplied baseline. Final pre-publication
  fetch again confirmed `HEAD`, `origin/main`, and their merge-base at `29b73be7`.
- Baseline reproduction showed that both a full `web-listening-result.v1` envelope and a nested
  incompatible manifest returned empty IDs with `imported=0`; an unsupported schema carrying a
  manifest ID also reported `imported=0` while writing one raw-manifest row.
- Focused baseline tests passed 44 tests, confirming the defect was an untested contract gap rather
  than an already-failing implementation.
- No equivalent open/merged PR, branch, or commit was found. Merged PR #205 introduced the
  permissive legacy importer and PR #136 covers an unrelated Agentic ready-manifest registry.

## Issue #320 implementation and review

- `manifest_ingest.py` now performs strict raw parsing and complete contract validation before
  opening the write transaction, then preserves the existing valid archive/upsert/idempotency
  path. `ManifestIngestError` carries safe machine code and field details.
- `task_runtime.py` validates and decodes the manifest before constructing storage, persists the
  safe error code/details in task history, and logs contract failures without unsafe exception
  chains. The public collection-run API remains unchanged and continues to reject manifest mode.
- Focused regression coverage now exercises incompatible envelopes, unsupported schemas, duplicate
  keys, every field/type rule, late-asset atomicity, backslash and invalid-port URLs, exact raw-byte
  archival, path priority, idempotency, task/history/API propagation, and secret-safe logs.
- TDD red evidence reproduced six core failures before implementation. Local review round 1 found
  two valid acceptance-criteria defects: backslash URLs were accepted, and chained URL/file errors
  could leak sensitive values. The same persistent worker fixed both with targeted red/green tests.
  Fresh read-only review round 2 returned PASS with no findings. Focused validation passed 102
  tests; the wider related regression selection passed 201 tests.

## Issue #320 final local validation

- Unified quality gate passed: 2,000 tests passed and 10 skipped, then Black, isort, and Pylint all
  passed.
- Both dead-code gates passed with zero baseline findings. Frontend lint passed with zero errors
  and five existing Hook warnings; type-check and production build passed, with only the existing
  large-chunk advisory.
- Python smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI
  evaluation cases with evidence/citation/refusal rates at 1.0 and unsupported-answer rate at 0.0.
- `git diff --check` passed. No browser smoke is required because this change has no UI behavior.
- Files in scope: `ai_actuarial/manifest_ingest.py`, `ai_actuarial/task_runtime.py`,
  `tests/test_manifest_ingest.py`, `tests/test_issue_320_manifest_contract.py`,
  `tests/test_issue_220_immutable_guards.py`, `tests/test_fastapi_ops_read_endpoints.py`,
  `tests/test_fastapi_ops_write_endpoints.py`, and this manager-owned status file.
- No unrelated uncommitted or untracked files are present. There are no local blockers; the next
  action is to push this final status commit, mark PR #329 Ready, then perform the single required
  feedback/CI/merge/cleanup lifecycle.

# Project Status — Issue #308 inapplicable retrieval metrics

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\2378\AI_actuarial_inforsearch`
- Branch: `codex/issue-308-inapplicable-retrieval-metrics`
- Baseline: `origin/main@0cdc25fce76d9eaf21d484020ccaa223fef0f3b6`
- Issue: `#308 fix(chat): distinguish inapplicable retrieval metrics from missing score data`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-308.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/326`
- Delivery stage: Draft PR #326 created with `Closes #308`; final status commit pending before
  Ready for review

## Issue #308 scope and acceptance criteria

- AC-1: Keyword-only methods (`summaries`, `titles`, `sections`, `relations`, `formulas`,
  `tables`, and `calculation_terms`) show Keyword relevance plus Retrieval method and omit
  Semantic relevance when its canonical value is absent.
- AC-2: `vector` evidence shows Semantic relevance plus Retrieval method and omits Keyword
  relevance when its canonical value is absent.
- AC-3: A metric applicable to the method remains visible as `—` when its canonical value is
  missing, invalid, non-integer, or outside `0..100`.
- AC-4: Any present valid canonical semantic or keyword value is shown regardless of method, so
  hybrid evidence can show both.
- AC-5: Unknown methods infer no applicability and show only valid scores actually present, plus
  the safely normalized Other method badge.
- AC-6: Citation Cards and Retrieved Blocks use the same shared component and therefore the same
  rendering rules.
- AC-7: Every rendered badge remains screen-reader labeled, `whitespace-nowrap`, flex-wrapping,
  and free of horizontal overflow at 320, 768, 1024, and 1440 px.
- AC-8: Backend response fields, persistence/history, ranking, result order, thresholds, planner,
  tool selection, and retrieval APIs remain unchanged.

## Issue #308 ownership, non-goals, and validation

- Implementation ownership is limited to
  `client/src/pages/chat/RetrievalIndicators.tsx` and its focused component test. The manager owns
  this status file. `Chat.tsx` is inspected as the two-call-site contract and is edited only if the
  shared-component contract cannot satisfy AC-6.
- Sibling repositories are off-limits.
- Non-goals: adding vector scoring to Ready Data, relabeling scores, creating a combined score,
  changing any backend contract or retrieval behavior, backfilling history, adding a security
  framework, or introducing a speculative abstraction.
- Component matrix: vector-only; every keyword-only method; valid hybrid scores; applicable
  missing/invalid/out-of-range scores; all missing; and unknown method with absent, one, or both
  valid scores. Assertions cover exact visible and absent accessible labels.
- Regression matrix: the existing backend Issue #265 suite preserves Agentic raw-score and
  Standard vector-mapping contracts; frontend lint, type-check, build, real browser smoke, both
  dead-code gates, the unified quality gate, and all three Python smoke commands are required.

## Issue #308 baseline evidence

- The assigned worktree arrived clean but detached. After fetching, `HEAD`, `origin/main`, and
  their merge-base all matched the supplied baseline exactly; the manager created the isolated
  branch named above without changing files.
- Runtime server rendering reproduced both defects: `titles` with keyword score `31` rendered an
  extra `Semantic relevance: —` badge, and `vector` with semantic score `83` rendered an extra
  `Keyword relevance: —` badge.
- `git blame` and the complete path history show that PR #286 introduced the component with a
  fixed three-badge array and no later change. Issue #308 explicitly supersedes that earlier layout
  rule as a focused UX follow-up, so the report is current rather than stale or duplicate work.
- Duplicate search found no equivalent PR or branch. Merged PR #286 is the linked #265 origin and
  does not implement the new applicability distinction.

## Issue #308 implementation and validation

- The shared component now treats `vector` as semantic-applicable, the seven Ready Data methods as
  keyword-applicable, and unknown methods as having no inferred applicability. Any valid canonical
  score is still rendered regardless of method, while an applicable invalid/missing score remains
  visible as `—`.
- TDD red evidence showed the original vector-only and keyword-only cases each rendered the extra
  inapplicable `—` badge. The expanded component matrix then passed after the minimal component
  change.
- Local review completed after one fresh read-only reviewer round with no valid findings. Citation
  Cards and Retrieved Blocks were independently confirmed to pass identical fields to the same
  shared component.
- The Issue-focused component test passed. The retrieval/backend regression selection passed 143
  tests, preserving Agentic raw-score and Standard vector-mapping contracts.
- Frontend lint passed with zero errors and five existing Hook warnings; type-check and production
  build passed, with only the existing large-chunk advisory. Both dead-code gates passed with zero
  findings.
- Python smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI smoke
  cases with quality rates at 1.0.
- The unified quality gate passed: 1,882 tests passed and 10 skipped; Black, isort, and Pylint all
  passed.
- Real browser smoke used controlled local API responses in the actual Chat page. Citation Cards
  and expanded Retrieved Blocks rendered keyword-only, vector-only, applicable-missing, unknown,
  and hybrid cases identically. At 320, 768, 1024, and 1440 px, all 22 expected badges stayed
  within their containers, retained `nowrap`, wrapped as whole badges, and produced no page
  overflow or console errors. The existing narrow-screen sidebar was closed before inspecting the
  conversation content.
- Final fetch confirmed `origin/main`, branch merge-base, and the original baseline remain
  `0cdc25fce76d9eaf21d484020ccaa223fef0f3b6`.

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

# Project Status — Issue #319 loose-coupled incremental stages

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\e680\AI_actuarial_inforsearch`
- Branch: `codex/issue-319-loose-coupled-stages`
- Baseline: `origin/main@ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`
- Issue: `#319 fix(pipeline): continue loose-coupled incremental stages after partial success`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-319.json`
- Delivery stage: remote feedback assessed; one confirmed contract fix validated; follow-up push pending

## Issue #319 acceptance criteria

- AC-1: Production-shaped Markdown `status=error` with `items_downloaded=2` launches Catalog
  exactly once while preserving the Markdown task's original status, errors, counters, result,
  and log.
- AC-2: Scheduled, Markdown, Catalog, Chunk, and Embedding all use the same terminal decision
  matrix: `completed/error + successful outputs > 0` advances once; `completed + 0` completes as
  a clean no-op; `error + 0` ends in error; `stopped` ends stopped; missing task or hard exception
  ends in error.
- AC-3: Catalog launches from its saved/default incremental configuration without predecessor
  `file_urls` and may select its normal historical uncataloged/outdated backlog.
- AC-4: Chunk launches from its saved/default incremental configuration without predecessor
  Markdown `files` and may select its normal historical Markdown-ready backlog.
- AC-5: Embedding launches without predecessor `chunk_set_ids` or `file_urls`; a minimal
  module-owned selector-free incremental backlog mode computes its own eligible ready chunk-set
  backlog and is available through both manual/API and Baton launches.
- AC-6: Given the same saved/default module configuration, Baton and manual launches resolve
  equivalent runtime parameters and work-selection behavior; raw frontend payload equality is not
  required.
- AC-7: Existing skipped, reused, retry-eligible, and historical backlog behavior remains owned by
  each module; skipped work is not reinterpreted as a predecessor handoff artifact.
- AC-8: Repeated ordinary ticks do not launch a next stage or subtask twice.
- AC-9: Current indexable KBs are enumerated in stable order across `manual`, `category`, and `all`
  modes; zero KBs completes cleanly.
- AC-10: One failed KB Index or Ready Data task is recorded and does not block later KBs; any
  stopped KB subtask stops the whole round immediately and launches no later KB.
- AC-11: If relay reaches the end, `round_status=completed` means orchestration completed and does
  not rewrite any individual task outcome.
- AC-12: Baton state remains compact: current stage/task plus existing KB summary only; no copied
  per-item errors, partial-evidence schema, or source-task mutation.
- AC-13: Existing standalone/manual task APIs, forms, saved/default configuration, module logs,
  status semantics, and Ready Data/KB behavior remain unchanged except for the shared Embedding
  selector-free backlog mode required by AC-5.
- AC-14: Existing Baton/runtime tests, the full stage matrix, production-shape Markdown regression,
  selector-absence and historical-backlog regressions, manual/Baton equivalence, KB failure/stop
  paths, duplicate-tick behavior, and all repository-required checks pass.

## Issue #319 stage decision matrix

| Task outcome | Successful output count | Baton result |
| --- | ---: | --- |
| `completed` | `> 0` | Launch the next module's normal incremental task once |
| `error` | `> 0` | Preserve the task error and launch the next module once |
| `completed` | `0` | Complete the round as a clean no-op |
| `error` | `0` | End the round as `error` |
| `stopped` | any | End the round as `stopped` |
| missing task or hard exception | unknown / `0` | End the round as `error` |

## Issue #319 scope and non-goals

- Owned production scope: `ai_actuarial/pipeline_baton.py`; minimal shared runtime/API/Embedding
  wiring only where AC-5/AC-6 requires it. Focused Baton/runtime/API/domain tests are in scope.
  Pipeline status/UI copy changes are conditional on observable wording changes.
- Sibling repositories and the primary checkout's Issue #317 changes are off-limits.
- No predecessor file/hash/chunk-set handoff, frozen cohort, global lineage, new publication
  transaction, DAG, retry/resume/checkpoint/lease framework, automatic retry, crawler change,
  module redesign, or suppression/rewriting of task errors.
- Review-policy override: none. Findings must be realistically reproducible and map directly to
  an AC above.

## Issue #319 baseline and history evidence

- The assigned worktree was clean and detached at the supplied baseline. After fetch, `HEAD`,
  `origin/main`, and their merge-base all remained exactly `ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`;
  the isolated branch above was then created.
- A production-shaped no-edit reproduction showed Markdown `error + items_downloaded=2` leaves
  `round_status=error` and starts no Catalog task. Existing #292 Scheduled partial-success tests
  still pass.
- The same baseline reproduction showed Catalog receives predecessor `file_urls`, Chunk receives
  predecessor Markdown `files`, and Embedding receives predecessor `chunk_set_ids`.
- `git blame` and `git log -S` trace the general terminal behavior to the original Baton, the
  Scheduled-only exception to merged PR #292, and all three exact selector injections to commit
  `7a175050` (`feat: persist chunk embeddings`). The original #179 Baton regression explicitly
  asserted independent tasks without output handoff before that commit changed the contract.
- Duplicate search across open/closed/merged PRs, local/remote branches, and commit messages found
  no equivalent #319 work. Merged PR #292 covers Scheduled only and is not a duplicate.

## Issue #319 implementation state

- Baton now uses `items_downloaded` as the single authoritative successful-output count for all
  five non-KB phases. Partial errors advance once, clean zero-output completions stop cleanly,
  zero-output errors fail, stopped tasks halt, and missing tasks or hard orchestration failures fail.
- Catalog and Chunk now launch their normal saved/default incremental backlog without predecessor
  selectors. Baton no longer persists copied Markdown file evidence.
- Embedding now exposes a selector-free `incremental` mode owned by the embedding module. It
  resolves the current server identity first, scans ready chunk sets in stable order, validates
  chunk-set stability, and selects sets containing missing or invalid embeddings while preserving
  existing reuse and repair behavior.
- Manual/API, Baton, Tasks, and scheduled Chunk & Embedding composition use the same selector-free
  Embedding mode. File Detail retains its explicit single-file `chunk_set_ids` scope.
- Scheduled composition and Tasks both retain their existing empty Chunk-result guard. Reused
  stable chunk sets still launch selector-free Embedding so historical missing/invalid coverage can
  be repaired.
- KB Index/Ready Data preserves stable `manual`/`category`/`all` enumeration: one KB error is
  recorded and later KBs continue; a stopped KB task halts the round immediately.

## Issue #319 local review

- Round 1 found and fixed a scheduled-composition regression where reused stable chunk sets had
  `items_downloaded=0` and incorrectly skipped Embedding. The fix gates on non-empty stable
  `result.chunk_sets` and still launches only `incremental: true`.
- Round 2 found and fixed the matching Tasks regression where an empty Chunk result could launch an
  unrelated global Embedding backlog. Tasks now keeps the non-empty result guard without handing
  the IDs to Embedding.
- Round 3 used a fresh read-only reviewer and passed with no reproducible #319 finding. The final
  reviewer independently ran 96 focused tests.

## Issue #319 verification

- TDD red baseline for the new focused file: 18 product failures and 15 passes after correcting
  three test-fixture defects; final focused file: 33 passes.
- Final related Baton/runtime/API/CLI/UI suite: 102 passes; broader related suite previously passed
  151 tests plus 40 Embedding/Chunk domain tests.
- Unified quality gate: 1916 passed, 10 skipped; Black, isort, and Pylint passed. The first attempt
  was stopped after the pytest process reached 23.6 GB and left 0.1 GB host memory; a clean isolated
  rerun used normal memory and passed without source changes.
- Dead-code file and symbol gates: 0 findings. Frontend lint: 0 errors and five existing warnings;
  typecheck and production build passed.
- Python smoke: FastAPI 13 passed; Agentic RAG eval 31 passed; eval CLI passed all 3 cases with full
  evidence/citation/refusal metrics.
- `git diff --check` passed. No visible form, layout, or wording changed, so browser visual smoke was
  not required; the changed request contract is covered by source tests, typecheck, and build.
- After final fetch, `HEAD`, `origin/main`, and their merge-base remain
  `ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`.

## Issue #319 remote feedback

- PR #327 was marked Ready at head `02a085339a64ddd9b7d131e897c0b33ff3f2497b`. The single
  feedback window ran for 680.49 seconds before one complete snapshot was fetched.
- All five required remote checks passed. No human review, PR comment, or Issue comment was
  present. Copilot left two inline comments.
- The first Copilot comment was confirmed: selector-free `incremental` accepted and echoed a
  `profile_id` that it did not apply. The minimal fix rejects `incremental + profile_id` at both
  the API launch boundary and the Embedding selection boundary; it does not add profile-filter
  semantics or change Baton's `{incremental: true}` payload.
- The second Copilot comment was rejected under the repository review policy. It proposed loading
  chunk IDs before content as a performance optimization but provided no reproducible functional,
  workflow, data-contract, or error-handling failure mapped to #319.
- The confirmed fix failed two new tests before implementation, then passed them. Manager reran the
  final Embedding/API/Baton/UI combination with 169 passes; the focused #319 file now has 35 passes.

## Issue #319 working tree notes

- Scoped production changes are limited to Pipeline Baton, Embedding selection/runtime/API wiring,
  and the Tasks request path. Scoped test changes cover the matrix, storage backlog, API/manual
  parity, scheduled/Tasks empty and reused results, and KB error/stop behavior.
- The new untracked `tests/test_issue_319_loose_coupled_pipeline.py` is an intentional scoped test
  file and will be included in the commit. Generated reports, coverage, build output, and installed
  dependencies are ignored.
- No unrelated local change is present. Sibling repositories and the primary checkout's Issue #317
  changes remain unread and untouched.

## Issue #319 blockers or decisions needed

- No implementation, review, validation, or publication blocker.

## Issue #319 recommended next action

- Commit and push the confirmed remote contract fix, allow required checks to rerun, reply to both
  captured Copilot threads with the accepted/rejected disposition, then merge once the updated head
  is green.
