# Project Status — Issue #248 Embedding Generation Progress

- Updated: 2026-08-27
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-248`
- Branch: `codex/issue-248-embedding-progress` (tracking `origin/main`)

## Delivered behavior

- `ensure_chunk_embeddings()` now accepts an optional backward-compatible progress callback.
- The callback reports once immediately after valid reuse is counted, then once after each attempted provider batch.
- Processed counts are monotonic and include reused, generated, invalid-regenerated, and failed chunks.
- Provider exceptions, count mismatches, and invalid vectors advance batch progress with aggregate-only activity text.
- `NativeTaskRuntime._run_embedding_generation()` connects the service callback to the existing task progress fields consumed by the active-task API and `TaskCard`.
- Stopped embedding tasks preserve actual attempted counts and partial progress instead of being finalized as 100% expected/expected.
- Successful embedding tasks retain the existing strict 100% expected/expected terminal state and existing result-count semantics.

## TDD evidence

- Pre-fix RED: `python -m pytest tests/test_issue_248_embedding_progress.py -q` produced `5 failed, 1 passed`.
  - Three service tests failed because `progress_callback` was not accepted.
  - Two runtime tests failed because the callback was not passed to the service.
- Post-fix GREEN: the same command produced `6 passed`.

## Verification

- Direct embedding service/runtime/API/UI regression selection: `17 passed`.
- Full KB index call-path suite: `28 passed`.
- Existing Issue #237 embedding domain plus task API/CLI/UI and Issue #248 tests: `70 passed`; two unrelated pre-existing migration assertions failed because current baseline applies v10 while those assertions end at v9.
- Required FastAPI authority selection: `13 passed`.
- Required agentic eval tests: `31 passed`.
- Required formula-profile CLI eval: `3/3 passed` with all reported rates at expected passing values.
- Ruff on changed Python files: passed.
- Compileall on the changed modules/test: passed.
- `git diff --check`: passed.

## Same-shaped sibling review

- `ai_actuarial/task_runtime.py` is the only production embedding-generation task caller and is connected to the new callback.
- `ai_actuarial/rag/kb_index.py` also calls `ensure_chunk_embeddings()`; the optional default preserves that independent four-stage indexing workflow, confirmed by its full 28-test suite.
- Direct service test callers omit the optional callback and remain compatible.
- `ai_actuarial/rag/embeddings.py` batches provider requests internally but does not own reuse, persistence, stop, or task counts; adding task progress there would duplicate the service-level batch contract.
- `ai_actuarial/catalog.py` has an unrelated catalog persistence batch loop and is outside the embedding-generation acceptance criteria.
- `client/src/pages/tasks/TaskCard.tsx` already renders `progress`, `items_processed`, `items_total`, and `current_activity`; no production UI change was needed.

## Scope and worktree state

- Production changes are limited to `ai_actuarial/embedding_service.py` and `ai_actuarial/task_runtime.py`.
- Regression coverage is isolated in `tests/test_issue_248_embedding_progress.py`.
- No provider/model/config, chunk identity, persistence schema, generic progress framework, production data, or sibling repository was changed.
- Implementation is complete and intentionally uncommitted for the Issue manager's local review and lifecycle steps.
- Known unrelated blocker: two existing v7 migration tests expect migrations only through v9 although the current baseline also applies `add_agentic_ready_manual_operation_state_v10`.
