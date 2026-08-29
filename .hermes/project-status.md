# Project Status — Issue #266 Weekly Snapshots

- Updated: 2026-08-29
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-266-weekly-snapshots`
- Baseline: `origin/main` at `20780cbacee5b26da33ef158d336a0890ce9497c`
- Issue: `#266` weekly snapshot contract
- Worker boundary: only `ai_actuarial/sqlite_schema.py`, `ai_actuarial/storage.py`, `ai_actuarial/cli.py`, `tests/test_issue_266_weekly_snapshots.py`, `tests/test_sqlite_schema_runner.py`, `tests/test_weekly_updates.py`, and this status file were in scope. Primary checkout, sibling repositories, other worktrees, `graphify-out`, secrets, and generated credentials remained off-limits.
- Lifecycle boundary: implementation and local verification only; no commit, push, PR, merge, branch deletion, worktree removal, provider access, or production access.
- Replacement repair boundary: only `ai_actuarial/sqlite_schema.py`, `tests/test_sqlite_schema_runner.py`, `tests/test_issue_266_weekly_snapshots.py`, and this status file were touched for the second mandatory pre-PR gate finding. All prior Issue #266 dirty-worktree changes were preserved.
- Third-gate repair boundary: only `ai_actuarial/task_runtime.py`, `tests/test_issue_266_weekly_snapshots.py`, and this status file were touched for the UTC weekly-summary scheduling finding. All prior Issue #266 dirty-worktree changes were preserved.
- Fourth-gate repair boundary: only `ai_actuarial/cli.py`, `tests/test_issue_266_weekly_snapshots.py`, and this status file were touched for the CLI missing-snapshot JSON parity finding. All prior Issue #266 dirty-worktree changes were preserved.

## Accepted pre-PR gate findings and repairs

1. **P1 migration canonicalization**
   - v11 now accepts legacy boundaries only when both are timezone-aware RFC3339 timestamps, normalizes both to canonical UTC text, and requires `period_end > period_start`.
   - Invalid, naive, malformed, and reversed rows remain unchanged in `weekly_update_summaries` but are not copied into either snapshot table.
   - Canonical collisions are resolved deterministically by canonical interval, earliest legacy `generated_at`, then legacy ID. The surviving row retains its legacy identity and timestamp; members are copied only for that survivor.
   - Offset-equivalent replay now returns the migrated identity/timestamp and leaves one published logical interval.

2. **P2 legacy list compatibility**
   - `Storage.list_weekly_update_summaries()` now pages a single combined view of published snapshots and unmatched legacy rows.
   - Migrated rows, forced replacements, exact-period duplicates, and UTC-equivalent legacy periods are not double-counted.
   - The compatibility row shape remains `id`, period boundaries, `generated_at`, `file_count`, `files`, `summary_markdown`, and `metadata`; pagination is applied after de-duplication.

3. **P2 legacy latest compatibility**
   - The legacy fallback now applies the same completed-period rule as the snapshot query: `period_end <= now` using SQLite timestamp comparison.
   - Future-only migrated/legacy data returns `None`; ended legacy fallback data remains visible.

4. **P2 schema source validation**
   - `_accept_version_10_source()` now validates the exact adjusted v10 signature without auto-backfill tolerance and includes unexpected schema-object counts.
   - An exact v10 source remains migratable. A missing unrelated auto-backfill table or an unexpected trigger is invalid with `can_apply=false`.

5. **P2 CLI JSON SQLite errors**
   - `cmd_weekly_snapshot()` now catches `sqlite3.Error` at the weekly command boundary.
   - A directory used as the SQLite path returns exit 2, one stable JSON error object, empty stderr, and no traceback.

6. **Second mandatory pre-PR gate — AC9 exact-v10 source compatibility**
   - `_accept_version_10_source()` now requires both v11 tables, `weekly_snapshots` and `weekly_snapshot_members`, to be absent.
   - A v10-stamped database that otherwise matches the current schema is also checked by the v10 source validator, so one or both pre-existing snapshot tables produce `state=invalid`, `can_apply=false`, and no migration attempt.
   - Regression coverage includes snapshots-only, members-only with its unresolved FK metadata, both tables, and a populated published collision that would otherwise override the deterministic legacy survivor.

7. **Third mandatory pre-PR gate — AC8 explicit UTC weekly scheduling**
   - Weekly `weekly_summary` tasks now register Monday 00:30 explicitly in UTC through the installed `schedule` library; unrelated global, site, daily, and non-summary weekly registration semantics are unchanged.
   - The internal fallback scheduler accepts the same optional timezone argument and retains equivalent `at_time_zone` metadata.
   - Focused coverage freezes Monday 2026-08-31 00:30 UTC, verifies the immediately preceding full UTC week is `[2026-08-24, 2026-08-31)`, contrasts the former Asia/Shanghai-local firing instant that selects `[2026-08-17, 2026-08-24)`, and exercises registration, two invocations, persistence, and repeat-run idempotency for both scheduler implementations.

8. **Fourth mandatory pre-PR gate — AC7 CLI JSON/API missing-snapshot parity**
   - `cmd_weekly_snapshot()` now normalizes only `WeeklySnapshotNotFoundError` to the stable API domain message `Weekly snapshot not found` at the CLI boundary; all other caught exceptions retain their existing text.
   - The service exception class was not changed. Missing-ID `weekly snapshot files` remains exit 2 and emits exactly one JSON stdout line, empty stderr, and no traceback.

## TDD evidence

- RED command: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py::test_v11_migration_canonicalizes_offset_period_for_idempotent_replay tests/test_issue_266_weekly_snapshots.py::test_v11_migration_resolves_normalized_period_collisions_deterministically tests/test_issue_266_weekly_snapshots.py::test_v11_migration_skips_invalid_naive_and_reversed_legacy_periods tests/test_issue_266_weekly_snapshots.py::test_legacy_and_snapshot_lists_share_current_rows_without_double_counting tests/test_issue_266_weekly_snapshots.py::test_legacy_latest_excludes_future_rows_and_keeps_ended_fallback tests/test_issue_266_weekly_snapshots.py::test_weekly_snapshot_cli_json_handles_sqlite_operational_error tests/test_sqlite_schema_runner.py::test_exact_version_10_source_is_migratable tests/test_sqlite_schema_runner.py::test_version_10_source_missing_auto_backfill_table_is_invalid tests/test_sqlite_schema_runner.py::test_version_10_source_with_unexpected_trigger_is_invalid`.
  - Result before production edits: **8 failed, 1 passed, 4 warnings in 2.28s**.
  - The exact-v10 control passed; the other eight failures reproduced all five accepted findings.
- Focused GREEN: the same nine-node command — **9 passed, 4 warnings in 1.74s**.
- Complete owned weekly/schema tests: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_sqlite_schema_runner.py` — **84 passed, 4 warnings in 14.07s**.
- Required combined regression: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_sqlite_schema_runner.py` — **118 passed, 5 warnings in 20.56s**.
- Second-gate RED command: `python -m pytest --no-cov -q tests/test_sqlite_schema_runner.py::test_version_10_source_with_v11_snapshot_tables_is_invalid tests/test_issue_266_weekly_snapshots.py::test_v10_source_rejects_preexisting_published_collision_before_migration` — **4 collected, 4 failed, 4 warnings in 1.90s** before production edits; every malformed source incorrectly returned `needs_migration`.
- Second-gate GREEN: the identical command after the narrow repair — **4 passed, 4 warnings in 1.32s**.
- Current available Issue #266/schema regression: `python -m pytest -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_sqlite_schema_runner.py` — **88 passed, 4 warnings in 22.98s**.
- The earlier `tests/test_api_smoke.py` name was a manager prompt typo, not a repository or product blocker. Before the third-gate repair, the established five-module manager command passed **122 tests**.
- Third-gate RED command: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py::test_real_scheduler_registration_invokes_previous_week_snapshot_to_persistence` — **2 collected, 2 failed, 0 passed, 4 warnings in 1.66s** before the production edit. The real job reported `at_time_zone=None`; the fallback job had no `at_time_zone` metadata.
- Third-gate GREEN: the identical command after the narrow repair — **2 collected, 2 passed, 0 failed, 4 warnings in 1.31s**.
- Third-gate full manager regression: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_sqlite_schema_runner.py` — **123 collected, 123 passed, 5 warnings in 20.53s**.
- Fourth-gate RED command: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py::test_weekly_snapshot_cli_json_missing_id_uses_stable_domain_error` — **1 failed, 4 warnings in 1.56s** before the production edit. The CLI returned `error="'missing-id'"` instead of the stable API message.
- Initial fourth-gate GREEN (superseded by the manager's exact-parity correction): the identical command after the narrow CLI-boundary repair — **1 passed, 4 warnings in 1.15s**.
- Fourth-gate full manager regression: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_sqlite_schema_runner.py` — **124 passed, 5 warnings in 20.72s**.
- Fourth-gate manager correction focused test: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py::test_weekly_snapshot_cli_json_missing_id_uses_stable_domain_error` — **1 passed, 4 warnings in 1.23s** with the exact no-period API message.
- Fourth-gate manager correction full regression: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_sqlite_schema_runner.py` — **124 passed, 5 warnings in 20.71s**.

## Additional checks

- Compile: `python -m compileall -q ai_actuarial/sqlite_schema.py ai_actuarial/storage.py ai_actuarial/cli.py tests/test_issue_266_weekly_snapshots.py tests/test_sqlite_schema_runner.py tests/test_weekly_updates.py` — passed.
- Ruff: `python -m ruff check --select E9,F63,F7,F82` over the same six Python files — passed (`All checks passed!`).
- CLI help: root, `weekly`, `weekly snapshot`, and `generate|latest|list|files` help commands — all seven exited 0.
- CLI JSON success probes: generate exited 0 with one JSON object; latest exited 0 with the same snapshot identity; list exited 0 with `total=1`.
- CLI JSON error probe: directory SQLite path exited 2 with `{"error":"unable to open database file","success":false}`, exactly one stdout JSON object, empty stderr, and no traceback.
- `git diff --check` — passed; Git emitted only expected LF-to-CRLF working-copy warnings.
- No UI behavior changed, so browser/build validation was not applicable.
- Second-gate compile: `python -m compileall -q ai_actuarial/sqlite_schema.py tests/test_sqlite_schema_runner.py tests/test_issue_266_weekly_snapshots.py` — passed.
- Second-gate Ruff: `python -m ruff check --select E9,F63,F7,F82 ai_actuarial/sqlite_schema.py tests/test_sqlite_schema_runner.py tests/test_issue_266_weekly_snapshots.py` — passed (`All checks passed!`).
- Second-gate `git diff --check` — passed with only the existing LF-to-CRLF working-copy warnings.
- Third-gate compile: `python -m compileall -q ai_actuarial/task_runtime.py tests/test_issue_266_weekly_snapshots.py` — passed.
- Third-gate Ruff: `python -m ruff check --select E9,F63,F7,F82 ai_actuarial/task_runtime.py tests/test_issue_266_weekly_snapshots.py` — passed (`All checks passed!`).
- Third-gate `git diff --check` — passed with only the existing LF-to-CRLF working-copy warnings.
- Third-gate CLI help was not rerun because the repair does not affect the CLI contract.
- Fourth-gate compile: `python -m compileall -q ai_actuarial/cli.py tests/test_issue_266_weekly_snapshots.py` — passed.
- Fourth-gate Ruff: `python -m ruff check --select E9,F63,F7,F82 ai_actuarial/cli.py tests/test_issue_266_weekly_snapshots.py` — passed (`All checks passed!`).
- Fourth-gate `git diff --check` — passed with only the existing LF-to-CRLF working-copy warnings.
- Fourth-gate manager correction compile: `python -m compileall -q ai_actuarial/cli.py tests/test_issue_266_weekly_snapshots.py` — passed.
- Fourth-gate manager correction Ruff: `python -m ruff check --select E9,F63,F7,F82 ai_actuarial/cli.py tests/test_issue_266_weekly_snapshots.py` — passed (`All checks passed!`).
- Fourth-gate manager correction `git diff --check` — passed with only the existing LF-to-CRLF working-copy warnings.
- Mandatory fresh whole-diff pre-PR review: independent read-only Codex CLI session `01a04c43-4077-7c50-94a1-ea101de056a8` returned **PASS** with no remaining in-scope reproducible findings across AC1–AC10. The reviewer made no changes, `git diff --check origin/main` passed, and HEAD/origin/main/merge-base remained at the assigned baseline `20780cbacee5b26da33ef158d336a0890ce9497c`.
- Final manager regression after the exact missing-ID wording correction: `python -m pytest --no-cov -q tests/test_issue_266_weekly_snapshots.py tests/test_weekly_updates.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_read_endpoints.py tests/test_sqlite_schema_runner.py` — **124 passed, 5 warnings in 20.35s**; touched-file compileall and focused Ruff both passed.

## Scope decisions and remaining risks

- The fixes are limited to the five accepted findings. No Dashboard, AI explanation, source field, report DSL, workflow engine, ordering threshold, provider, or scheduler redesign was added.
- Existing out-of-scope modifications in four API/runtime files were not edited. One narrow `rg` lookup unintentionally displayed the RFC3339 helper lines from `ai_actuarial/api/services/weekly_updates.py`; no other out-of-scope file contents were inspected.
- Existing Starlette/SWIG/cookie deprecation warnings remain; there are no test failures or Issue #266 implementation blockers.
- The lifecycle-owning manager completed the required fresh whole-worktree Codex CLI review after all repairs; it passed without findings or file changes.
- No Git or GitHub lifecycle action was taken.
- The replacement worker did not read or modify the primary checkout, sibling repositories/worktrees, `graphify-out`, secrets, providers, or out-of-scope dirty files. It did not commit, push, create/update a PR, merge, change Issue/review state, or clean any branch/worktree.
- The third-gate worker used one narrow read-only inspection of the current-worktree UTC period helper needed by the focused test, modified no out-of-scope file, and performed no lifecycle, provider, production, or forbidden-repository action. There are no remaining blockers from the obsolete `tests/test_api_smoke.py` prompt typo.
- The fourth-gate worker changed only the authorized CLI, regression-test, and status files; it preserved every pre-existing dirty file and took no lifecycle, provider, production, secret, primary/sibling checkout, other-worktree, or `graphify-out` action. The accepted AC7 finding is resolved with no remaining implementation/test blocker.
- The manager correction removed the erroneous trailing period only from the authorized CLI constant, regression expectation, and status wording. No API/service or other out-of-scope file was edited, and no lifecycle action was taken.
