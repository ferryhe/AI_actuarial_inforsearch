# Project Status — Canonical Handoff

- Updated: 2026-08-19 (America/New_York)
- Repository: `ferryhe/AI_actuarial_inforsearch`
- Workspace: `C:\Project\AI_actuarial_inforsearch`
- Active branch: `codex/issue-174-ready-data-metadata-events`
- Baseline: `origin/main` at `1b0e6d9fbfc9afa3c9fa2e2dd173d50b7c465335` (merged PR `#189`)
- Delivery: commit `7247088a42f302b829f5ff6dd24a48ced3d1dcb9`, Ready-for-review PR `#190`
- Primary objective: finish Epic `#172` by completing Issues `#173`–`#179` and their declared dependencies.
- Execution rule: work on one bounded deliverable at a time. Do not start the next PR or a server action until the current deliverable reaches its terminal handoff.

## Hard Boundaries

- This repository is the only writable workspace unless a later task explicitly names another repository.
- Sibling repositories and their live Issue state were not inspected in this handoff.
- No production, deployment, restart, migration, server-Agent command, or automatic GC is authorized by this status file.
- Preserve `ai_actuarial/api/routers/rag_admin.py`: it has a known line-ending-only worktree state and a content diff of zero.
- Preserve `graphify-out/`: it is an existing untracked analysis artifact; do not stage, commit, or clean it. Graphify may update its own internal query memory when that required skill is used.

## Live Issue Board

| Issue | State | Current meaning | Close condition / next dependency |
|---|---|---|---|
| `#172` Epic | Open | Governs the complete acquisition-to-ready-data program. | Close last, after all child Issues and external prerequisites are complete and production acceptance is recorded. |
| `#173` OPS baseline | Open | PR `#181` is merged. Online backup, quiesced snapshot, file-level isolated restore, and API health smoke passed. The isolated KB list endpoint returned HTTP 500. | Requires explicitly authorized least-privilege diagnosis, root-cause classification, KB restore smoke, capacity gate recheck, then timer installation/evidence. |
| `#174` ready-data | Open/Reopened | Core publication, GC, source state, mutation wiring, chunk events, and default-off automatic executor are merged through PR `#189`. | Finish the four owned follow-ups below, record `#179`/`#176` boundaries, then close. |
| `#175` manifest/lineage | Open | Not implemented in this repository program yet. | Requires the declared `acquisition-manifest.v1` producer contract; re-triage external readiness before starting. |
| `#176` production rollout | Open | Final server-Agent phase. | Blocked by `#173`, `#174`, `#175`, `#177`, `#178`, `#179`, external prerequisites, and pre-production validation. |
| `#177` KB reconciliation | Open | Bidirectional rule membership, manual-member protection, dry-run and audit remain. | Implement before `#178`; its stable stage interface is needed by the final pipeline. |
| `#178` reclassification | Open | Dedicated taxonomy-versioned reclassification task remains. | Blocked by `#177`; must reuse reconciliation and then drive index/ready-data consistency. |
| `#179` durable pipeline | Open | Durable parent/child stages, resume, lease, watermark and Tasks-stage reporting remain. | Depends on stable `#175`, `#177`, and `#174` stage contracts; production cutover belongs to `#176`. |

Live GitHub status was reconciled on 2026-08-19. All Issues `#172`–`#179` are currently Open; `#174` has state reason `reopened`.

## Issue #174 — Completed

- PR `#182` / merge `9320efe`: independent publication attempts, staging validation, expected-active CAS, active/previous slots, safe retry and rollback primitives.
- PR `#183` / merge `6741cbb`: fail-closed bounded duplicate retention/GC; automatic GC remains disabled.
- PR `#184` / merge `1c742de`: durable source generations, stale policy, default-off automatic build/publish settings, legacy compatibility.
- PR `#185` / merge `57da07c`: transactional KB membership source events.
- PR `#186` / merge `99c43d0`: orphan-binding guard and effective-input semantics.
- PR `#187` / merge `d9f0e0f`: transactional chunk-binding source events.
- PR `#188` / merge `adf8c9e`: canonical chunk-content events and no-op detection.
- PR `#189` / merge `1b0e6d9`: default-off SQLite-backed automatic build/optional publish executor with durable lease/claim fencing.

Current behavior: supported source changes advance a coalesced pending generation. When automatic build is enabled for `(kb_id, profile)`, the scheduler wakes the one-shot executor; it builds and validates in staging and, only when automatic publish is also enabled and all generation/artifact/expected-active checks pass, atomically publishes. Both flags remain off by default. Manual build remains available.

## Issue #174 — Remaining Owned Work

Do these sequentially, one PR at a time:

1. **Metadata source events — active task now**
   - Wire builder-visible `catalog_items` fields: `status`, `category`, `summary`, `keywords`, `markdown_content`, `rag_chunk_count`.
   - Wire builder-visible `files` fields: `title`, `source_site`, `published_time`.
   - Emit source-state changes in the same SQLite transaction as the metadata mutation.
   - Valid metadata change or invalid→valid: soft `metadata_updated`.
   - Valid→invalid: hard `source_invalidated`; deletion: hard `source_deleted`.
   - Exact no-op, non-member, and invalid→invalid changes emit no event.
   - Audit all real mutation paths; do not change the automatic executor, UI, full pipeline, GC, deployment, or sibling repositories.

2. **Index commit re-evaluation**
   - Successful index/embedding commits wake source evaluation.
   - Do not blindly mark stale because the current builder does not consume FAISS vectors; compare the authoritative builder source identity and settle no-op evaluations safely.

3. **Deterministic staging smoke**
   - Add an offline, bounded basic retrieval/smoke query to staging validation.
   - Smoke failure must block publication without changing active/previous.
   - Production/API/browser canary remains `#176`.

4. **KB page and provenance closure**
   - Existing Knowledge Base page shows current/stale/building/failed/ready, automation flags, last error/attempt, active/previous, manual build and rollback.
   - Resolve and test the publication provenance contract: actual builder source version versus Issue wording that requests index version.
   - Update Issue `#174` with final acceptance evidence and explicitly delegate durable full-pipeline waiting/reporting to `#179` and production canary to `#176`; then close `#174` only if all owned items pass.

## Active Metadata-Events Delivery

- Added a canonical before/after Storage snapshot for exactly the builder-consumed Catalog/file fields. Only live KB memberships are selected, and the existing per-KB marker updates every known profile once.
- Wired `insert_file`, `upsert_file`, `upsert_catalog_item`, combined file/Catalog edits, Markdown edits, explicit deletion, incremental catalog writes, webpage collection, and indexing `rag_chunk_count` updates into the same SQLite transaction as source generation/reason/automation wake state.
- Semantics are `metadata_updated` for valid input changes and invalid-to-valid transitions, `source_invalidated` for valid-to-invalid transitions, and `source_deleted` for explicit deletion. Canonical no-ops, audit-only changes, invalid-to-invalid changes, and non-members emit nothing.
- The API and incremental catalog paths coalesce title plus Catalog changes into one comparison/marker call, so one high-level mutation advances each `(kb_id, profile)` at most once. A two-KB/two-profile failure-injection test confirms a marker failure rolls back metadata, all generations/reasons, and automation wake state.
- Direct SQL audit exclusions:
  - `crawler.py` uses `INSERT OR IGNORE` only for previously unseen page files; it cannot change an existing member's builder-visible fields. The separate webpage collector was active and could replace existing rows, so it was changed to `Storage.upsert_file` and covered by a regression test.
  - `Storage._migrate_catalog_items()` and `catalog_incremental._ensure_catalog_schema()` are schema/legacy-column backfills, not ordinary metadata mutation entry points; no runtime field update was left outside the wired production methods.
  - `db_backend.py`, `StorageV2`, and `storage_factory.py` are exercised only by compatibility/example/tests in this repository and are not used by the current SQLite ready-data/API/task production chain.
  - `clear_local_path()` updates only the non-builder `local_path` audit/storage field after explicit deletion; deletion itself is marked transactionally first.
- Independent specification review and quality/security review completed with no remaining in-scope findings. The mandatory Codex CLI review could not start because packaged WindowsApps `codex.exe` returned `Access is denied`; no alternate entrypoint was attempted.
- PR `#190` is Ready, mergeable, and uses `Refs #174`. After the required observation window, `python-smoke` passed; Copilot reviewed all 7 changed files and generated no comments; ordinary comments, inline comments, and review threads were all empty.

## Program Dependency Order

Canonical dependency chain from Epic `#172`:

```text
#173 OPS baseline --------------------------------------------→ #176 production
external acquisition prerequisites → #175 → #177 → #178 ─┐
                                      #174 ------------------├→ #179 durable pipeline → #176
                                                          ──┘
#176 accepted → close #172
```

After `#174` closes, re-read all live Issue states before selecting the next item. If the user explicitly authorizes the pending `#173` server diagnosis, it can be the next single task. Otherwise select the next unblocked repository-only child according to the dependency chain; do not infer sibling-repository scope.

## Delivery Contract For Every PR

1. Start from latest clean `main`; identify and preserve unrelated local state.
2. Use a fresh `codex/` branch and one bounded scope.
3. Use TDD for behavior changes; run focused regressions, Ruff, Python compilation and `git diff --check`.
4. Complete independent specification and quality/security review. Maximum five material remediation cycles.
5. Attempt the mandatory local Codex CLI review. Known blocker: packaged WindowsApps `codex.exe` returns `Access is denied`; record it accurately and do not invent an alternate entrypoint.
6. Commit, push and create a Ready-for-review PR automatically after gates pass; do not close the parent Issue prematurely.
7. Observe GitHub checks and review/Copilot feedback for the repository-required window; fix only confirmed-safe in-scope findings and rerun validation.
8. Merge and branch deletion require the user's authorization/current repository policy; previous PRs were manually merged by the maintainer.

## Known Verification Baseline

- PR `#189`: automation `23 passed`; broader relevant regression `305 passed, 5 skipped`; GitHub `python-smoke` passed.
- Last full repository result: `905 passed, 5 skipped, 5 known Windows-environment failures`.
- Known unrelated Windows failures: one SQLite temporary-file cleanup lock and four tests invoking bare `npm` where this host exposes `npm.cmd`.
- Windows symlink/reparse capability tests may skip locally and must run in Linux CI.
- Current metadata-event specialty plus webpage-collector regression: `45 passed`.
- Current file mutation/API regression: `30 passed`; membership/binding/chunk-content regression: `48 passed`; automation/source-state/publication/GC regression: `112 passed, 2 skipped`; Catalog/builder regression: `22 passed`; task/indexing/RAG-admin regression: `101 passed, 3 skipped`.
- Current full repository run: `932 passed, 5 skipped, 5 known Windows-environment failures` (the same one temporary SQLite lock plus four bare-`npm` failures).
- Ruff passes for all touched Python files. Repository-wide Ruff still reports 68 pre-existing findings outside this change. `python -m compileall -q ai_actuarial tests` and `git diff --check` pass.

## Immediate Next Action

PR `#190` is ready for maintainer review/merge; no in-scope follow-up fix is pending. No server Agent and no deployment are needed. After this PR is merged, refresh `main`, reconcile GitHub status, and create a fresh branch for the index-commit re-evaluation task.

## Current Worktree State

- The active-delivery changes are committed and pushed on `codex/issue-174-ready-data-metadata-events`; this status update is the only intended follow-up change.
- `ai_actuarial/api/routers/rag_admin.py`: pre-existing line-ending metadata only; content diff zero; do not include.
- `graphify-out/`: pre-existing untracked analysis output; do not include or clean.
