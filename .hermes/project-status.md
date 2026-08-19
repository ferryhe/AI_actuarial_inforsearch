# Project Status — Canonical Handoff

- Updated: 2026-08-19 (America/New_York)
- Repository: `ferryhe/AI_actuarial_inforsearch`
- Workspace: `C:\Project\AI_actuarial_inforsearch`
- Active branch: `codex/issue-174-ready-data-staging-smoke`
- Baseline: `origin/main` at `5e870f166b38ec243952fa482558a16c84499096` (merged PR `#191`)
- Delivery: deterministic staging-smoke implementation and local gates are complete; create a Ready-for-review PR titled `feat: add deterministic ready-data staging smoke` with `Refs #174`.
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
- PR `#191` / merge `5e870f1`: transactional ready-index re-evaluation, builder-fingerprint no-op settlement, and pre-build generation/active-pointer fencing.

Current behavior: supported source changes advance a coalesced pending generation. When automatic build is enabled for `(kb_id, profile)`, the scheduler wakes the one-shot executor; it builds and validates in staging and, only when automatic publish is also enabled and all generation/artifact/expected-active checks pass, atomically publishes. Both flags remain off by default. Manual build remains available.

## Issue #174 — Remaining Owned Work

Do these sequentially, one PR at a time:

1. **Land deterministic staging smoke**
   - Current branch implements the bounded offline gate described below; merge remains a maintainer decision.
   - Production/API/browser canary remains `#176`.

2. **KB page and provenance closure**
   - Existing Knowledge Base page shows current/stale/building/failed/ready, automation flags, last error/attempt, active/previous, manual build and rollback.
   - Resolve and test the publication provenance contract: actual builder source version versus Issue wording that requests index version.
   - Update Issue `#174` with final acceptance evidence and explicitly delegate durable full-pipeline waiting/reporting to `#179` and production canary to `#176`; then close `#174` only if all owned items pass.

## Active Deterministic Staging-Smoke Delivery

- Every newly built staging candidate now runs one deterministic query after structural `ready_data_builder.validate()` and before it can be recorded as validated or published. Active/previous integrity rechecks remain structural-only and do not rerun smoke.
- The gate reuses `run_agentic_rag_loop` against the exact staging directory. Stable Catalog ordering and title/summary/heading/section fallback produce a normalized 160-character maximum query without LLMs, embeddings, FAISS/index reads, network access, random values, time, or external configuration.
- Query selection and retrieval execute together in a `spawn` worker under `Storage.AGENTIC_READY_FUTURE_EXECUTION_POLICY["staging_smoke_timeout_seconds"]`; timeout terminates/kills/joins before staging cleanup. Errors and audit data are allowlisted and bounded; answer/evidence/body text is never persisted.
- Non-empty success requires the exact v1 contract, evidence, and a citation/reference whose full `doc_id` or `file_url` matches the staging Catalog. Full identifiers are compared before bounded audit output, avoiding prefix-collision acceptance.
- Manual and automatic builds share `_build_agentic_ready_manifest_core`. Failed/invalid/timed-out smoke cannot change active/previous, and automatic claims settle to failure rather than remaining running.
- Empty manual builds are an explicit confirmation and may publish. Empty automatic builds remain validated/awaiting publish; automatic publish records awaiting-manual-confirmation once and cannot reacquire the same candidate. Legacy, malformed, wrong-contract, or reference-less candidates are readable but cannot be automatically published without a proven smoke.
- Smoke audit state is stored in its own backward-compatible `smoke_result_json` column rather than `schema_versions_json`. Legacy active/publication rows remain readable, while generation fences, expected-active CAS, duplicate classification, rollback, and GC contracts are unchanged.
- Independent specification and quality/security reviews completed after two material remediation cycles with no remaining findings. The mandatory local Codex CLI review could not start because the packaged WindowsApps `codex.exe` returned `Access is denied`; no alternate entrypoint was attempted.
- No UI, final provenance copy, full-pipeline/resume/watermark, production/browser canary, retry, automatic GC, deployment, server, or sibling-repository work was added.

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

- PR `#191`: index re-evaluation delivery merged at `5e870f166b38ec243952fa482558a16c84499096`.
- Known unrelated Windows failures: one SQLite temporary-file cleanup lock and four tests invoking bare `npm` where this host exposes `npm.cmd`.
- Windows symlink/reparse capability tests may skip locally and must run in Linux CI.
- Current staging smoke plus builder/tools/agentic-loop, publication/GC, automation/source-state/index re-evaluation, RAG-admin, and mutation-event regression: `372 passed, 5 skipped`.
- Post-review staging-smoke/automation focused re-run: `63 passed`; touched-file Ruff, compileall, and diff checks passed.
- Current full repository run: `1006 passed, 5 skipped, 5 known Windows-environment failures` (the same one temporary SQLite lock plus four bare-`npm` failures).
- Ruff passes for all touched Python files. Repository-wide Ruff still reports 68 pre-existing findings outside this change. `python -m compileall -q ai_actuarial tests` and `git diff --check` pass.

## Immediate Next Action

Commit and push the reviewed staging-smoke change, create its Ready-for-review PR with `Refs #174`, then observe CI and all review channels for the repository-required window. Do not auto-merge or close `#174`.

## Current Worktree State

- The deterministic staging-smoke implementation and tests are the only intended changes on `codex/issue-174-ready-data-staging-smoke`; commit/push/PR are the next delivery actions.
- `ai_actuarial/api/routers/rag_admin.py`: pre-existing line-ending metadata only; content diff zero; do not include.
- `graphify-out/`: pre-existing untracked analysis output; do not include or clean.
