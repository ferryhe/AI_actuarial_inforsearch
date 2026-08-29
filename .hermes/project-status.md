# Project Status — Issue #267 Weekly Explanations

- Updated: 2026-08-29
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-267-weekly-explanations`
- Baseline/current HEAD/origin/main/merge-base at startup: `6278a67028e998b835a3ab9196c1f82f8e7f2a40`
- Issue: `#267` generate and persist bilingual AI explanations for weekly snapshots
- State: Managed Review Round 3 accepted P1 repaired and locally verified; all changes remain uncommitted by explicit user instruction.

## Managed Review Round 3 repair — 2026-08-29

### Accepted finding and repair

- Repaired the default weekly generator's request ownership bound. Its request-scoped OpenAI-compatible SDK options now apply the normalized weekly timeout and set SDK `max_retries=0`, so the existing application `max_retries=1` produces exactly one actual transport request. Length recovery remains disabled.
- The shared chat runtime was not changed. No schema, storage, public API, task, admin, prompt, or frontend production contract changed in this round.
- The existing lease remains the same normalized request timeout plus the bounded one-second grace. A real-SQLite concurrent test now uses a 0.1-second weekly timeout while the valid owner remains active for about 0.5 seconds; the contender does not reclaim it and only one generator call occurs. The existing expiry test still proves abandoned claims become atomically retryable, only one concurrent reclaimer wins, and stale token/fingerprint finalization cannot overwrite the replacement.
- A real OpenAI SDK client backed by `httpx.MockTransport` proves the 0.1-second timeout reaches connect/read/write/pool request options and a retryable 5xx response causes one transport attempt, with no provider or network access.

### Review 3 TDD and verification evidence

- Focused RED before the production edit: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py::test_default_generator_enforces_timeout_and_one_sdk_transport_attempt` — **1 failed, 4 warnings in 3.40s**. Exact failure: `assert 3 == 1`; the SDK issued three POST requests to `/v1/chat/completions`.
- First focused GREEN after the production edit: the same test — **1 passed, 4 warnings in 1.60s**.
- Final focused ownership/lease/fencing set: four selected tests — **4 passed, 4 warnings in 2.41s**.
- Final Issue #267 module: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py` — **23 passed, 4 warnings in 4.65s**.
- Established affected weekly/schema/runtime/config/admin/task regression: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_sqlite_schema_runner.py tests/test_ai_runtime.py tests/test_yaml_config.py tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_settings_react_source.py tests/test_tasks_react_source.py tests/test_task_stop_support.py` — **254 passed, 5 warnings in 27.07s**.
- Relevant FastAPI/admin regression: `python -m pytest --no-cov -q tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_fastapi_entrypoint.py tests/test_fastapi_react_cleanup.py tests/test_react_fastapi_authority.py` — **57 passed, 5 warnings in 9.65s**.
- Touched-Python `compileall` — passed.
- Focused Ruff `--select E9,F63,F7,F82` — passed (`All checks passed!`).
- `git diff --check` — passed; only expected LF-to-CRLF working-copy warnings.
- Completed a full dirty-diff self-review against Issue #267 acceptance criteria. Confirmed atomic claim/reclaim, no database write lock across provider calls or poll sleeps, token+fingerprint stale-finalize fencing, terminal ownership clearing, public redaction, v12 migration/Storage parity, task failure isolation, HTTP-only CLI, and the single bilingual prompt remain intact. No additional accepted finding was identified.

### Exact Review 3 repair files and boundaries

- `ai_actuarial/api/services/weekly_explanations.py`
- `tests/test_issue_267_weekly_explanations.py`
- `.hermes/project-status.md`

No other file was edited by the Review 3 replacement worker. The worker accessed only the assigned worktree and did not access the primary checkout, sibling repositories/worktrees, Issue #264, Graphify/`graphify-out`, secrets/`.env`, providers/network, production, GitHub, PRs, or Issues. No real provider call, commit, push, PR/Issue mutation, merge, branch cleanup, or remote-feedback fetch was performed.

## Managed Review Round 2 repair — 2026-08-29

### Accepted finding and repair

- Repaired the permanent-busy failure mode for an abandoned durable weekly explanation claim. The already-uncommitted v12 `weekly_explanations` schema now includes internal `claim_expires_at` state; no v13 migration was added.
- Claim acquisition receives a lease duration derived from the effective generation timeout plus a fixed one-second grace. It stores fixed-microsecond aware UTC RFC3339 timestamps and evaluates expiry inside the conditional SQLite update under a short `BEGIN IMMEDIATE` transaction.
- A live owner remains exclusive. Once its lease expires, concurrent reclaimers race through the same conditional update and exactly one receives a new token. Finalization still requires the current fingerprint and token, clears token/fingerprint/expiry on terminal success or failure, and prevents an original stale owner from overwriting the replacement result.
- The busy generation path now retries atomic claim acquisition while polling, so it can reclaim an expired lease and proceed through the injected generator. Provider execution and polling sleeps remain outside database write transactions.
- Public API shape remains unchanged. `claim_expires_at`, claim token/fingerprint, provider, model, input fingerprint, error, and coverage remain internal.

### Review 2 TDD and verification evidence

- Focused RED before production edits: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py::test_abandoned_weekly_explanation_lease_is_reclaimed_and_retry_recovers` — **1 failed, 4 warnings in 1.58s**. Exact failure: `TypeError: Storage.claim_weekly_explanation() got an unexpected keyword argument 'lease_ttl_seconds'`.
- First focused GREEN after production repair: the same test — **1 passed, 4 warnings in 1.29s**.
- Final Issue #267 module: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py` — **22 passed, 4 warnings in 3.84s**.
- Established affected regression set: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_sqlite_schema_runner.py tests/test_ai_runtime.py tests/test_yaml_config.py tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_settings_react_source.py tests/test_tasks_react_source.py tests/test_task_stop_support.py` — **253 passed, 5 warnings in 25.84s**.
- Relevant FastAPI/admin regression: `python -m pytest --no-cov -q tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_fastapi_entrypoint.py tests/test_fastapi_react_cleanup.py tests/test_react_fastapi_authority.py` — **57 passed, 5 warnings in 8.80s**.
- Touched-Python `compileall` — passed.
- Focused Ruff `--select E9,F63,F7,F82` — passed (`All checks passed!`).
- `git diff --check` — passed; only expected LF-to-CRLF working-copy warnings.
- Completed line-by-line self-review of the lease schema, atomic reclaim predicate, timeout/grace calculation, busy-loop acquisition, conditional finalize, and public redaction. The existing concurrency test still proves a separate SQLite `BEGIN IMMEDIATE` succeeds while the injected generator is active.

### Exact Review 2 repair files and boundaries

- `ai_actuarial/api/services/weekly_explanations.py`
- `ai_actuarial/storage.py`
- `ai_actuarial/sqlite_schema.py`
- `tests/test_issue_267_weekly_explanations.py`
- `.hermes/project-status.md`

`tests/test_sqlite_schema_runner.py` required no Round 2 edit; its pre-existing Issue #267 fixture changes were preserved and its full module passed in the affected regression set. No other file was edited by the Round 2 worker.

The worker accessed only the assigned worktree and did not access the primary checkout, sibling repositories/worktrees, Issue #264, Graphify/`graphify-out`, secrets/`.env`, providers/network, production, GitHub, PRs, or Issues. No real provider call, commit, push, PR/Issue mutation, merge, branch deletion, or worktree removal was performed.

## Managed Review Round 1 repair — 2026-08-29

### Accepted findings and repair

- P1 concurrent default idempotency/failure isolation: replaced the read-before-generate and unconditional upsert path with a durable SQLite claim and token-conditional finalize contract. `claim_fingerprint` and `claim_token` were added surgically to the already-uncommitted v12 `weekly_explanations` schema. Claim and finalize each use a short `BEGIN IMMEDIATE` transaction; the provider callback runs after claim commit and before finalize begins. Same-fingerprint concurrent callers wait for the owner result and never invoke the provider twice. A finalize updates only the matching snapshot, fingerprint, and claim token, so a reused/stale token cannot overwrite a complete row. Terminal failures clear the token and remain independently retryable.
- P2 provider/model validation parity: weekly admin writes now resolve the effective provider and model for provider-only, model-only, and combined changes, reject providers not supported by the existing chat runtime, validate the effective chat model against discovered capabilities, and then apply the existing chat routing-model validation before any config write. `anthropic` plus a Claude chat model is rejected; the supported `mistral` plus `mistral-small-latest` pair is accepted.
- Public API shape is unchanged. Provider, model, fingerprint, error, coverage, `claim_fingerprint`, and `claim_token` remain internal. An initial claimed placeholder is exposed as `missing`, never as an internal claim state. No UI change was made.

### Review 1 TDD evidence

- Focused RED before production repair: three selected tests — **3 failed, 4 warnings in 1.89s**.
  - Real SQLite synchronized threads invoked the generator twice and the late timeout won the unconditional upsert race.
  - `Storage` had no `claim_weekly_explanation` / conditional-finalize contract.
  - A provider-only `anthropic` weekly admin update returned HTTP 200 instead of HTTP 400.
- First focused GREEN after production repair: the same three tests — **3 passed, 4 warnings in 2.10s**.
- Final Issue #267 module: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py` — **21 passed, 4 warnings in 3.65s**.
- Established affected regression set, including the two new Review 1 tests: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_sqlite_schema_runner.py tests/test_ai_runtime.py tests/test_yaml_config.py tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_settings_react_source.py tests/test_tasks_react_source.py tests/test_task_stop_support.py` — **252 passed, 5 warnings in 26.98s**.
- Relevant FastAPI/admin regression: `python -m pytest --no-cov -q tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_fastapi_entrypoint.py tests/test_fastapi_react_cleanup.py tests/test_react_fastapi_authority.py` — **57 passed, 5 warnings in 9.02s**.
- Touched-Python `compileall` — passed.
- Focused Ruff `--select E9,F63,F7,F82` — passed (`All checks passed!`).
- `git diff --check` — passed; only expected LF-to-CRLF working-copy warnings.
- Completed a line-by-line review of the repair. The concurrency test also proves a separate SQLite `BEGIN IMMEDIATE` succeeds while the provider callback is active, confirming no database write lock is held across that callback.

### Exact Review 1 repair files

- `ai_actuarial/api/services/weekly_explanations.py`
- `ai_actuarial/storage.py`
- `ai_actuarial/api/services/ops_write.py`
- `ai_actuarial/sqlite_schema.py` — required for the durable claim columns in the uncommitted v12 schema; no new schema version was introduced.
- `tests/test_issue_267_weekly_explanations.py`
- `.hermes/project-status.md`

No other implementation, test, fixture, frontend, or configuration file was changed by the Review 1 repair worker. The other dirty files listed below are preserved parts of the pre-existing full Issue #267 implementation.

## Startup and boundaries

- Read `AGENTS.md` and the previous `.hermes/project-status.md` completely before editing.
- Startup `git status --short --branch` showed the assigned branch and a clean worktree.
- Verified HEAD, `origin/main`, and merge-base were the assigned baseline SHA.
- Directly inspected only this worktree. Graphify and every `graphify-out` path were explicitly forbidden and were not loaded, queried, inspected, created, or used.
- Primary checkout, sibling repositories, other worktrees, secrets, `.env`, credentials, providers, production, and GitHub/PR/Issue state remained off-limits.
- No commit, push, PR/Issue mutation, merge, branch deletion, worktree removal, provider call, or production access was performed.

## Minimal design and acceptance-criteria map

- AC-1/2: Added an independent `WeeklyExplanationGenerator` protocol and service. One injected call returns strict JSON with non-empty `zh` and `en`. Input is bound to immutable snapshot ID, canonical period, deterministic file count, and bounded URL/title/summary/keywords material inside explicit untrusted-data delimiters. Acquisition lineage and source/search/crawl/job statistics are excluded.
- AC-3: Added exact SQLite v12 migration `add_weekly_explanations_v12` after v11. It persists snapshot ID, deterministic input fingerprint, both explanations, provider/model/prompt version, generated time, status, internal error, and coverage while preserving v11 data and Storage/schema-runner parity.
- AC-4/5: Complete matching fingerprints reuse without a generator call. Failed attempts persist independently and can be retried without rebuilding or mutating the snapshot. Latest resolves the current latest published ended snapshot first and never falls back to an older explanation.
- AC-6: Added one versioned `ai_config.weekly_explanation` prompt and reused existing AI runtime, model validation, and credential resolution. Admin read/write supports one prompt only; Settings provides English and Chinese help for that single bilingual prompt.
- AC-7/8: Added typed generate, retry, get-by-snapshot-ID, and latest APIs plus matching HTTP-only CLI commands. Public results contain only snapshot ID, status, zh/en, and generated time; audit fields and internal errors remain storage/admin/task evidence only.
- AC-9: After a successful weekly snapshot task, runtime launches a separate `weekly_explanation` background task bound only to the returned snapshot ID. Child failure does not change the parent task or published snapshot. Duplicate follow-ups are idempotent at generation time.
- AC-10: No Dashboard/navigation, weekly statistics recomputation, generic AI plugin, language-specific model call, lineage feature, workflow engine, or unrelated UI was added.

## TDD and verification evidence

- Initial RED, before production edits: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py` — **16 failed, 4 warnings in 2.42s**. Missing contracts covered v12, service import, typed routes, CLI, task injection/follow-up, and config/admin behavior.
- Focused GREEN: the same Issue #267 module after implementation — **19 passed, 4 warnings in 2.81s**.
- Final affected regression: `python -m pytest --no-cov -q tests/test_issue_267_weekly_explanations.py tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_sqlite_schema_runner.py tests/test_ai_runtime.py tests/test_yaml_config.py tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_settings_react_source.py tests/test_tasks_react_source.py tests/test_task_stop_support.py` — **250 passed, 5 warnings in 25.83s**.
- Additional affected FastAPI regression: `python -m pytest --no-cov -q tests/test_fastapi_read_endpoints.py tests/test_fastapi_entrypoint.py tests/test_fastapi_react_cleanup.py tests/test_react_fastapi_authority.py` — **21 passed, 4 warnings in 2.69s**.
- One attempted regression command named nonexistent `tests/test_route_inventory.py`; pytest exited 1 without running tests. It was immediately corrected to the existing FastAPI files above and is not a product blocker.
- Frontend `npm test` — exit 0; Vite production build completed with 2,139 modules in 2.01s. Existing chunk-size warning only.
- Frontend `npm run build` — exit 0; Vite production build completed with 2,139 modules in 1.98s. Existing chunk-size warning only.
- Touched-Python `compileall` — passed.
- Focused Ruff `--select E9,F63,F7,F82` — passed (`All checks passed!`).
- `git diff --check` — passed; only expected LF-to-CRLF working-copy warnings.

## Contract evidence

- CLI help probes for root, `weekly`, `weekly explanation`, and `generate|retry|get|latest` all exited 0.
- Fake HTTP CLI tests cover all four methods/paths, JSON success, JSON error with exit 2 and empty stderr, and prove the explanation command does not import/call Storage, the generator service, or AI runtime.
- Migration tests prove exact v11→v12 planning/application, legacy snapshot preservation, Storage initialization parity, and rejection of a v11-stamped database with a pre-existing v12 table.
- Generation tests cover success, timeout, empty output, invalid JSON, missing/empty language, extra keys, retry, fingerprint reuse and prompt invalidation, bounded/delimited input, coverage, and exclusion of source lineage.
- API tests prove typed route ordering, latest isolation after force rebuild, public audit redaction, and that GET or `?language=zh|en` never calls the model.
- Task tests exercise real threaded follow-up invocation, persistence, duplicate idempotency, and child failure isolation from the completed snapshot task.
- Admin/config tests prove one prompt, version/default resolution, chatbot-compatible model validation, and persisted admin overrides. Frontend source/build proves one bilingual prompt editor with English and Chinese descriptions.

## Files in scope

- New: `ai_actuarial/api/services/weekly_explanations.py`
- New: `tests/test_issue_267_weekly_explanations.py`
- Modified: `ai_actuarial/ai_runtime.py`, `ai_actuarial/storage.py`, `ai_actuarial/sqlite_schema.py`, `ai_actuarial/api/services/ops_read.py`, `ai_actuarial/api/services/ops_write.py`, `ai_actuarial/api/routers/weekly_updates.py`, `ai_actuarial/task_runtime.py`, `ai_actuarial/cli.py`
- Modified: `config/yaml_config.py`, `config/sites.yaml`
- Modified: `client/src/pages/Settings.tsx`, `client/src/hooks/use-i18n.ts`
- Directly related fixture updates: `tests/test_issue_266_weekly_snapshots.py`, `tests/test_sqlite_schema_runner.py`
- Status: `.hermes/project-status.md`

## Risks, blockers, and next action

- No known Issue #267 or Managed Review Round 1 repair blocker remains. Only existing dependency deprecation warnings were observed during the repair validation.
- The mandatory external Codex CLI review was not run because this worker was explicitly forbidden from provider access and from entering the PR lifecycle. A local line-by-line self-review was completed instead; it removed an unsupported recurring-schedule admission for the snapshot-bound task.
- The repair worker did not access the primary checkout, sibling repos, other worktrees, secrets/`.env`, providers/network, Graphify/`graphify-out`, GitHub, PRs, Issues, or lifecycle state. No provider call was made.
- All changes are intentionally uncommitted/unpushed. The lifecycle-owning manager should inspect the dirty worktree and Review 1 evidence, then continue its separately authorized review/commit/PR workflow.
