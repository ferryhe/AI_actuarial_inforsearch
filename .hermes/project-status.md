# Project Status — Canonical Handoff

- Updated: 2026-08-19 (America/New_York)
- Repository: `ferryhe/AI_actuarial_inforsearch`
- Workspace: `C:\Project\AI_actuarial_inforsearch`
- Active branch: `codex/issue-174-ready-data-index-reevaluation`
- Baseline: `origin/main` at `1f4f4598040974bb3d3e1740643a6d909514f240` (merged PR `#190`)
- Delivery: commit `872695c`, Ready-for-review PR `#191`
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
- PR `#190` / merge `1f4f459`: transactional builder-visible metadata source events with canonical no-op and validity-transition semantics.

Current behavior: supported source changes advance a coalesced pending generation. When automatic build is enabled for `(kb_id, profile)`, the scheduler wakes the one-shot executor; it builds and validates in staging and, only when automatic publish is also enabled and all generation/artifact/expected-active checks pass, atomically publishes. Both flags remain off by default. Manual build remains available.

## Issue #174 — Remaining Owned Work

Do these sequentially, one PR at a time:

1. **Deterministic staging smoke**
   - Add an offline, bounded basic retrieval/smoke query to staging validation.
   - Smoke failure must block publication without changing active/previous.
   - Production/API/browser canary remains `#176`.

2. **KB page and provenance closure**
   - Existing Knowledge Base page shows current/stale/building/failed/ready, automation flags, last error/attempt, active/previous, manual build and rollback.
   - Resolve and test the publication provenance contract: actual builder source version versus Issue wording that requests index version.
   - Update Issue `#174` with final acceptance evidence and explicitly delegate durable full-pipeline waiting/reporting to `#179` and production canary to `#176`; then close `#174` only if all owned items pass.

## Active Index Re-evaluation Delivery

- Successful `ready` index-version commits now emit one neutral source event per known `(kb_id, profile)` in the same SQLite transaction. The reason is `embedding_index_committed` only when the latest successful ready embedding tuple changed; first and unchanged commits use `index_committed`. Non-ready commits emit no event.
- The latest successful ready embedding tuple is persisted independently of the latest-only index-version table. Marker/state failures roll back the index-version write, and ready recording failures now fail the indexing task closed while retaining already-written artifacts.
- A read-only fingerprint API reuses the builder's exact SQLite snapshot semantics and writes no staging files or artifacts. The automatic executor compares that fingerprint with a healthy, safely revalidated active publication before building.
- A healthy exact match settles the claimed generation atomically as `up_to_date` without invoking the builder or creating a candidate. Mismatch, missing/legacy/non-active active rows, or damaged artifacts continue through the existing staging build path.
- Claim token, lease, generation, automation flags, and expected-active pointer are fenced again immediately before either settlement or build. Fingerprint/validation failures and all races fail closed without changing active/previous.
- Knowledge-base deletion clears ready-index lifecycle state and index rows transactionally; nested deletion is rejected before database or filesystem mutation so an outer rollback cannot restore a KB whose files were removed. Legacy/minimal schemas retain a safe capability-based migration path.
- Manual build, build-only, optional auto-publish, default-off automation, and default-off GC behavior remain unchanged. No excluded UI, smoke, provenance, full-pipeline, retry/GC, deployment, server, or sibling-repository work was added.
- Four rounds of independent specification and quality/security review completed with no remaining actionable findings. The mandatory Codex CLI review could not start because packaged WindowsApps `codex.exe` returned `Access is denied`; no alternate entrypoint was attempted.
- PR `#191` is Ready-for-review, uses `Refs #174`, and awaits the required checks/review observation window. It must not be auto-merged.

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

- PR `#190`: metadata-event delivery merged at `1f4f4598040974bb3d3e1740643a6d909514f240`.
- Known unrelated Windows failures: one SQLite temporary-file cleanup lock and four tests invoking bare `npm` where this host exposes `npm.cmd`.
- Windows symlink/reparse capability tests may skip locally and must run in Linux CI.
- Current index re-evaluation plus ready-data automation/source-state, mutation events, publication/GC, task runtime, and RAG-admin regression: `320 passed, 5 skipped`.
- Current full repository run: `966 passed, 5 skipped, 5 known Windows-environment failures` (the same one temporary SQLite lock plus four bare-`npm` failures).
- Ruff passes for all touched Python files. Repository-wide Ruff still reports 68 pre-existing findings outside this change. `python -m compileall -q ai_actuarial tests` and `git diff --check` pass.

## Immediate Next Action

Observe PR `#191` checks and reviewer/Copilot feedback for the required window; fix only confirmed-safe in-scope findings. No server Agent, deployment, merge, or excluded follow-up is authorized.

## Current Worktree State

- The active index re-evaluation implementation is committed and pushed on `codex/issue-174-ready-data-index-reevaluation`; this status update is the only intended follow-up change.
- `ai_actuarial/api/routers/rag_admin.py`: pre-existing line-ending metadata only; content diff zero; do not include.
- `graphify-out/`: pre-existing untracked analysis output; do not include or clean.
