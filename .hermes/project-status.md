# Project Status — Canonical Handoff

- Updated: 2026-08-21 (America/New_York)
- Repository: `ferryhe/AI_actuarial_inforsearch`
- Workspace: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-196`
- Active branch: `codex/issue-196-sqlite-schema-runner`
- Baseline: `eb73875f64452317fe2ccfaebc58178b54729df7`
- Delivery: Issue `#196` SQLite schema-runner implementation is local worker state only; manager review, publication, and merge remain. No commit, push, PR, merge, server, Docker, frontend, backup, restore, timer, or sibling-repository action was performed.
- Primary objective: finish Epic `#172` by completing Issues `#173`–`#179` and their declared dependencies.

## Issue #194 — KB list offline delivery

- For filesystem-backed databases, `GET /api/rag/knowledge-bases` now uses a raw SQLite read-only storage-shaped view and does not construct general `Storage`, enter a write lock, create missing tables, add columns, or normalize metadata. A missing RAG KB table returns an empty list; legacy/incomplete KB metadata returns an explicit schema-apply-required response. Missing/empty and connection-local `:memory:`/empty-string databases also return an empty list with current embedding metadata and no schema bootstrap. No `KnowledgeBaseManager`, `SemanticChunker`, tokenizer encoding, or `EmbeddingGenerator` is constructed, and no RAG chunks or index tables are migrated.
- Existing ordering, `kb_mode`/`search` filters, `KnowledgeBase`-compatible provider/profile/dimension/timestamp normalization, chunk-profile decoration, current-embedding compatibility/status, and agentic ready-manifest decoration are preserved. A database with no RAG KB table continues to return an empty list.
- TDD red evidence: the original cold-cache regression failed at `list_knowledge_bases -> _manager_and_storage -> KnowledgeBaseManager`; Round 1 legacy regressions then failed with `no such column: description` and unnormalized provider value `' OpenAI '`; Round 2 exposed `duplicate column name: description`; Round 3 reproduced constructor-time `duplicate column name: embedding_provider` and an already-ready list blocked by an unrelated writer with `database is locked`; Round 4 reproduced `no such table: rag_knowledge_bases` for both `:memory:` and empty-string connection-local databases.
- TDD green evidence: the cold-cache, legacy-apply-required, raw RAG-only, no-KB-table, legacy-value, steady-state writer-lock, `:memory:`, and empty-string temporary-database regressions pass. Runtime dependency entry points remain fail-fast in the offline/concurrent/connection-local regressions, and the steady-state regression proves listing remains read-only behind an existing writer. Two independent empty-string SQLite connections were also shown to have separate temporary schemas and empty `PRAGMA database_list` filenames on this host, supporting the narrow connection-local classification.
- Local verification: Round 6 KB-list focus passed (`11 passed`), including legacy optional-table and view-shaped optional-object schema-apply-required regressions; the broader Round 4 related API/RAG/storage subset passed (`265 passed, 8 skipped`); touched-file Ruff, compileall, and `git diff --check` passed.
- Heartbeat `managed-pr-173-progress` is active during delivery.
- Parent Issue `#173` remains open pending separately authorized fixed-image no-network server smoke plus capacity, backup, and timer acceptance. This branch closes only `#194` and performs no server, image, container, deployment, backup, or timer operations.

## Issue #196 — SQLite schema runner

- Added `ai_actuarial.sqlite_schema` with `CURRENT_SQLITE_SCHEMA_VERSION = 1`, an ordered idempotent migration registry, read-only `status`/`plan`, and explicit `apply` only.
- Fresh missing/empty databases may be initialized through `Storage` or explicit schema apply and are stamped to version `1`. Non-empty `user_version=0` databases now fail closed during ordinary `Storage` construction before journal-mode or schema initialization writes; explicit `schema apply` is required.
- Version-zero baseline semantics are conservative: only an empty/missing database or a repository-recognized current storage schema with legacy `user_version=0` can advance. Recognition now uses deterministic table signatures from `PRAGMA table_xinfo`, index metadata, and foreign-key metadata for Storage-owned tables, plus conservative repository-generated signatures for known optional RAG/chat tables.
- Status/plan/apply treat registry-covered old versions below current as migratable using ordered actions from `user_version + 1` through current. Newer-than-code databases, unknown tables, missing required schema, structural mismatches, and partial migration state fail closed.
- JSON diagnostics are sanitized: invalid status/plan payloads report stable problem codes plus counts/categories, not arbitrary database paths, business data, table names, or column names from invalid databases.
- `apply_schema` uses `BEGIN IMMEDIATE` and a lock-internal recheck so concurrent runners do not duplicate migrations. Failed migrations roll back and preserve the original `PRAGMA user_version`.
- Backup/restore/release metadata paths now read and record the explicit nonzero schema version, and the deployment runbook documents status/plan/apply as the preflight contract for a later deploy/rollback wrapper.
- Round 1 local review accepted findings are addressed locally. Focused schema/recovery, related API/RAG/storage, CLI smoke, Ruff, compileall, and `git diff --check` passed in this worker pass.
- Round 2 local review accepted findings are addressed locally. Registered old-version migrations can now declare a source-schema validator so future DDL migrations are plan/apply-capable even when the source signature differs from current. The exported `chat_service.ensure_conversation_schema` optional chat schema is now an accepted repository-created variant. Focused schema/recovery, related API/RAG/storage, CLI smoke, Ruff, compileall, and `git diff --check` passed in this worker pass.
- Round 3 local review accepted findings are addressed locally. Existing non-empty databases now pass schema preflight before `Storage._init_schema`; malformed current-version databases fail closed without schema/data mutation. Schema inventory now includes non-table user objects, rejects unexpected views/triggers, and treats version-zero view/trigger-only databases as non-empty. Migration source validators run under `PRAGMA query_only=ON` and mutation attempts are rejected without advancing `user_version`. The KB-list legacy metadata path no longer depends on general `Storage` startup for existing file-backed databases; it uses the explicit list-only readiness path and a read-only SQLite view. The temporary router auth-removal diff was reverted to baseline; no `ai_actuarial/api/routers/rag_admin.py` change remains, and the KB-list regressions exercise the existing public `catalog.read` branch without presented auth material.
- Round 4 local review accepted findings are addressed locally. Valid current non-empty `Storage` startup is now schema/data no-op after preflight, including no WAL mode switch and no `_init_schema` backfills. Existing file-backed KB-list GETs are read-only and return empty or schema-apply-required instead of applying hidden metadata upgrades. The read-only KB-list adapter tolerates raw RAG-only databases without core Storage tables. `apply_schema` now serializes missing/empty database creation with `BEGIN IMMEDIATE` and lock-internal recheck, using a deferred-commit fresh bootstrap while the write lock is held. Focused schema/recovery, KB-list, related API/RAG/storage, CLI smoke, Ruff, compileall, and `git diff --check` passed in this worker pass.
- Round 5 local review accepted finding is addressed locally. The KB-list read-only preflight now validates every optional decoration table the list path may query and returns the existing schema-apply-required response when an optional table exists with a legacy/incomplete column shape. The new regression covers a valid KB-list table plus legacy `agentic_ready_slots` missing `publication_revision`, proves the SQLite file/schema/data are unchanged, and confirms `ai_actuarial/api/routers/rag_admin.py` still has no diff.
- Round 6 local review accepted finding is addressed locally. The KB-list read-only preflight now checks `sqlite_schema.type` before probing known required/optional object columns, requires real tables when those objects exist, and converts SQLite probing errors into the same schema-apply-required response. The new regression covers a valid KB-list table plus a view-shaped `agentic_ready_slots` object referencing a missing source, proves no file/schema/data mutation, and confirms `ai_actuarial/api/routers/rag_admin.py` still has no diff.
- Round 7 local review passed with no findings. A subsequent full local pytest run found Python-side stale hidden-migration expectations, which were corrected without restoring startup mutation: GC fixtures now bootstrap a real current schema, manually damaged current schemas fail closed, known catalog incremental compatibility columns are allowed only with nullable plain `TEXT` signatures, and explicit KB creation clears stale `kb_index_items`, `kb_index_versions`, and `kb_ready_index_state` for recreated KB IDs.
- Supplemental post-PASS review first found the catalog-extra signature gap and stale index-version inheritance; both were fixed. A final supplemental read-only review passed with no findings.
- Issue `#173` remains open. Any eventual PR for this work must say only `Closes #196`.

## Hard Boundaries

- This repository is the only writable workspace unless a later task explicitly names another repository.
- No production, deployment, restart, migration, server-Agent command, sibling-repository work, automatic retry, or automatic GC was performed for this delivery.
- Outside this isolated worktree, the primary checkout has a known line-ending-only state for `ai_actuarial/api/routers/rag_admin.py` and an existing untracked `graphify-out/` analysis artifact. Neither is part of this delivery and neither was touched here.
- Durable full-pipeline stages, resume, lease, watermark, and Tasks reporting belong to Issue `#179`.
- Production/API/browser canary belongs to Issue `#176`.

## Live Issue Board

| Issue | State | Current meaning | Close condition / next dependency |
|---|---|---|---|
| `#172` Epic | Open | Governs the complete acquisition-to-ready-data program. | Close after child Issues and external prerequisites complete and production acceptance is recorded. |
| `#173` OPS baseline | Open | Diagnosis is complete; Issue `#194` is the application correction for the KB-list defect. | Keep open only for separately authorized fixed-image no-network server smoke plus capacity, backup, and timer acceptance. |
| `#174` ready-data | Closed / Completed | PR `#193` is merged and final acceptance was recorded; closed at `2026-08-20T16:36:02Z`. | Complete. |
| `#175` manifest/lineage | Open / Blocked | Producer contract readiness is tracked by `web_listening #48`. | Start only after that external contract is ready. |
| `#176` production rollout | Open | Production/API/browser canary and final rollout. | Blocked by repository work and external prerequisites. |
| `#177` KB reconciliation | Open | Bidirectional rule membership and audit remain. | Implement before `#178`. |
| `#178` reclassification | Open | Taxonomy-versioned reclassification remains. | Blocked by `#177`. |
| `#179` durable pipeline | Open | Durable stages, resume, lease, watermark, and Tasks reporting remain. | Depends on stable stage contracts; production cutover belongs to `#176`. |

## Issue #174 — Merged Foundations

- PR `#182`: independent publication attempts, staging validation, expected-active CAS, active/previous slots, safe retry and rollback storage primitives.
- PR `#183`: fail-closed bounded duplicate retention/GC; automatic GC remains disabled.
- PR `#184`: durable source generations, stale policy, default-off automatic build/publish settings, legacy compatibility.
- PRs `#185`–`#188`: transactional KB/chunk membership/content source events and no-op semantics.
- PR `#189`: default-off SQLite-backed automatic build/optional publish executor with durable claim fencing.
- PR `#190`: transactional builder-visible metadata events.
- PR `#191`: transactional ready-index re-evaluation, builder-fingerprint no-op settlement, and generation/pointer fencing.
- PR `#192` / merge `001dd494ce0dafb633c34459053891c919180823`: deterministic offline staging smoke with bounded audit state and active/previous failure isolation.

## Issue #174 — Final Closure Delivery

- Publication provenance records the ready index observed in the builder's consistent SQLite snapshot while keeping source version kind/ID authoritative. The observed index is not a builder input and does not enter the source fingerprint.
- The public manifest endpoint returns a stable allowlisted projection for serving, stale/source, automation, active/previous publication provenance, current ready index, and smoke state. Sensitive filesystem paths, tokens, traceback/query/evidence content are excluded from the new projection; legacy top-level compatibility fields remain supported.
- A `tasks.run` rollback endpoint uses expected active/previous IDs, transaction-local scope/status and artifact validation, publication-pointer CAS, and atomic rollback semantics. Lexical root/output/artifact link/reparse/traversal preflight and digest verification occur before structure parsing.
- Knowledge list/detail pages separate serving from automation state; expose permission-gated build, automation controls, provenance, confirmation-based rollback, conflict refresh, bounded polling, cleanup, and synchronized Chinese/English copy.
- SQLite publication pointer revision and frontend route/request/manifest episode ordering prevent stale asynchronous responses from reverting publication/provenance state. Build safe snapshots also use monotonic publication/source/evaluated-generation evidence for same-revision races.
- Review rounds used: `15/15`, followed by the single user-authorized final fix with no further local Reviewer cycle.
- Round 15 final findings `R15-Q001` and `R15-SPEC001` were independently adjudicated as valid/Important and fixed in the final pass. Focused regressions confirm path preflight-before-validator and server-monotonic build snapshot ordering.

## Verification

- Issue #196 focused schema/recovery plus post-PASS storage/migration regressions: `python -m pytest tests/test_sqlite_schema_runner.py tests/test_production_recovery.py tests/test_ready_data_retention_gc.py tests/test_ready_data_index_reevaluation.py::test_legacy_orphan_index_state_is_not_inherited_by_recreated_kb tests/test_ready_data_metadata_events.py::test_incremental_catalog_combines_title_and_catalog_event_without_bypass tests/test_ready_data_staging_smoke.py::test_legacy_publication_without_smoke_column_is_readable_but_startup_fails_closed tests/test_database_migration.py -q --tb=short --disable-warnings --no-cov` passed (`82 passed, 1 skipped`).
- Issue #196 chat-service signature regression is included in `tests/test_sqlite_schema_runner.py` and passed with the focused schema/recovery run.
- Issue #196 ready-data publication/source-state focus: `python -m pytest tests/test_ready_data_publication.py tests/test_ready_data_source_state.py -q --tb=short --disable-warnings --no-cov` passed (`51 passed, 1 skipped`) after final fixes.
- Issue #196 KB-list focus: the legacy-apply-required/offline/locking/raw-RAG-only/no-KB-table/connection-local/legacy-optional-table/view-shaped-optional-object KB-list regressions in `tests/test_fastapi_rag_admin_endpoints.py` passed (`103 passed, 7 skipped`) after final fixes.
- Issue #196 related API/RAG/storage subset: `python -m pytest tests/test_code_review_fixes.py tests/test_fastapi_rag_admin_endpoints.py tests/test_fastapi_chat_endpoints.py tests/test_ready_data_publication.py tests/test_ready_data_source_state.py tests/agentic_rag/test_ready_data_builder.py tests/test_storage_v2.py tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_file_preview.py tests/test_fastapi_file_mutations.py -q` passed (`265 passed, 8 skipped`) after Round 4 fixes and router auth restoration.
- Issue #196 CLI smoke: `python -m ai_actuarial.cli --help` and `python -m ai_actuarial.cli schema --help` passed. JSON `schema plan` and `schema apply` passed on a missing/fresh throwaway database; JSON `schema plan`, `schema apply`, and post-apply `status` passed on a recognized `user_version=0` baseline database; repeated `apply` on current returned no migrations.
- Issue #196 mandatory local Codex CLI review gate: `codex review --uncommitted` could not start because `C:\Program Files\WindowsApps\OpenAI.Codex_26.818.2441.0_x64__2p2nqsd0c76g0\app\resources\codex.exe` returned `Access is denied`. No alternate entrypoint was attempted.
- Issue #196 touched-file Ruff passed after final fixes.
- Issue #196 compile/diff checks: `python -m compileall ai_actuarial tests` passed; `git diff --check` passed.
- Issue #196 full local pytest after final fixes: `python -m pytest -q --tb=short --disable-warnings --no-cov` reached `1109 passed, 9 skipped`; the only `17 failed` cases are TypeScript runtime tests failing with `FileNotFoundError` because local `tsx` is absent (`client/node_modules/.bin/tsx.cmd` and `node_modules/.bin/tsx.cmd` were not present). No frontend setup action was performed.
- Prior complete ready-data/API/UI suite: `435 passed, 9 skipped`.
- Prior full repository: `1090 passed, 9 skipped, 5` known Windows baseline failures.
- Known failures: one Windows SQLite temporary-file lock and four tests invoking bare `npm` where this host exposes `npm.cmd`.
- Windows symlink/reparse capability tests may skip locally; Linux CI is expected to exercise the new root, leaf, and intermediate-link cases.
- Management final focused audit: `34 passed, 1 skipped`.
- `npm.cmd run build`: passed (`2134` modules; existing chunk-size warning only).
- Touched-file Ruff, `python -m compileall -q ai_actuarial tests`, and `git diff --check`: passed.
- Optional `tsc --noEmit`: 15 pre-existing errors in untouched files; no errors in touched Knowledge/ready-data files.
- Earlier rounds completed real local browser smoke. Later official Browser attempts reached Vite HTTP 200 but the browser binding was blocked by the trusted RPC dependency path for `browser-service.mjs`; production TypeScript runtime tests cover the final concurrency paths. No alternate browser entrypoint was used.
- Mandatory local Codex CLI review attempt: `codex review --uncommitted` could not start because packaged WindowsApps `codex.exe` returned `Access is denied`. No alternate entrypoint was attempted.

## Publication State

- PR `#193`, `feat: close ready-data provenance and KB controls`, merged at `2026-08-20T16:30:07Z` with merge SHA `1c682650bee760ca0d58eedde33de2d7987d6ec1`.
- Issue `#174` final acceptance and closure are complete; it closed at `2026-08-20T16:36:02Z`.
- Issue `#194` is the current unpublished application correction. Publication and closure belong to its manager workflow; Issue `#173` must remain open for the separate server acceptance scope.
- Issue `#196` is local implementation worker state only. Publication and closure belong to the manager workflow; any eventual PR must close only `#196`.

## Program Dependency Order

```text
#173 OPS baseline --------------------------------------------→ #176 production
external acquisition prerequisites → #175 → #177 → #178 ─┐
                                      #174 ------------------├→ #179 durable pipeline → #176
                                                          ──┘
#176 accepted → close #172
```

Issue `#175` remains blocked on producer contract readiness tracked by `web_listening #48`. The Issue `#173` application correction is Issue `#194`; fixed-image no-network smoke and capacity/backup/timer acceptance remain a separate, explicitly authorized server-validation scope. Do not infer sibling or server scope.

## Current Worktree State

- Isolated worktree: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-196` on `codex/issue-196-sqlite-schema-runner`, based on `eb73875f64452317fe2ccfaebc58178b54729df7`.
- Modified: `.hermes/project-status.md`, `ai_actuarial/api/services/rag_admin.py`, `ai_actuarial/cli.py`, `ai_actuarial/rag/knowledge_base.py`, `ai_actuarial/storage.py`, `docs/deployment-runbook.md`, `tests/test_database_migration.py`, `tests/test_fastapi_rag_admin_endpoints.py`, `tests/test_production_recovery.py`, `tests/test_ready_data_index_reevaluation.py`, `tests/test_ready_data_publication.py`, `tests/test_ready_data_retention_gc.py`, `tests/test_ready_data_source_state.py`, and `tests/test_ready_data_staging_smoke.py`.
- Added: `ai_actuarial/sqlite_schema.py` and `tests/test_sqlite_schema_runner.py`.
- Generated verification artifacts are ignored under `.codex/` and will be removed with the isolated worktree after merge.
