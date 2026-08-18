# Project Status

- Date: 2026-08-18
- Branch: `codex/issue-174-ready-data-atomic-publish`
- Baseline: `origin/main` at `dac5e30` (merged PR `#181`).
- Scope: Implement the local, default-off ready-data staging, validation, atomic publication, and rollback baseline for Issue `#174`; do not change production.
- Managed PR heartbeat: active for draft PR `#182` (`https://github.com/ferryhe/AI_actuarial_inforsearch/pull/182`). The remote feedback window started at `2026-08-18T20:31:57Z` after commit `1c2048f`; no automation tool is available, so progress is reported through commentary updates.

## Active State

- PR `#181` is merged. Production now has an independent 40 GiB ext4 backup disk mounted at `/data`.
- A verified online SQLite backup and a verified quiesced database-and-data snapshot were created on the independent disk.
- File-level isolated restore passed. The isolated API health check passed, while `GET /api/rag/knowledge-bases` returned HTTP 500; the smoke container remains isolated and Issue `#173` is not ready to close.
- Issue `#173` has a least-privilege diagnostic authorization request posted at `https://github.com/ferryhe/AI_actuarial_inforsearch/issues/173#issuecomment-5331395524`. It is a request only; no new production diagnosis or command was executed.
- Issue `#174` local PR1 work is on `codex/issue-174-ready-data-atomic-publish`, based on clean `main` at `dac5e30`. It adds durable publication records, active/previous slots, validated staging builds, atomic publish/rollback storage primitives, deterministic input provenance, and default-off manual-build integration.
- The earlier validated-but-inactive retry and corrupt-active idempotency blockers are resolved in the authorized continuation. Each build now has an independent attempt record, publication uses expected-active CAS, failed CAS/gate attempts remain retryable, and active/previous artifacts are fail-closed validated before dedupe, preservation, or rollback.
- The user authorized that continuation on 2026-08-18. The approved design separates per-build attempts from logical source/digest identity, keeps publish-failed validated candidates retryable, uses expected-active/CAS winner selection, revalidates active artifacts before deduplication, and excludes a corrupt active artifact from the previous slot. Scope remains backend/storage/tests only.
- Safe duplicate policy: because filesystem validation cannot be atomic with the SQLite serving slot, a healthy same-identity duplicate remains a validated, non-serving candidate and the response reports `duplicate_retained` / `duplicate_gc_deferred`. Bounded retention/GC is required before later automatic publication is enabled; it is intentionally outside PR1.
- 2026-08-18 follow-up diagnosis confirmed both blockers in the current control flow. They share one design cause: a logical source/digest identity and a concrete staging attempt are collapsed into one mutable publication row. The next `#174` continuation should separate per-attempt lifecycle from logical idempotency, serialize/CAS the serving-slot winner, retain publish-failed validated artifacts as retryable, and validate an existing active artifact before a fresh duplicate can be discarded. No business-code edit was made during this diagnosis.
- Sibling repositories remain off-limits and are not read or modified.

## Historical Context (2026-08-17)

## Current State

- PR `#180` is merged into `main`; the Issue plan and production audit are recorded.
- Issue `#173` implementation is active on `ops/issue-173-production-recovery-baseline`.
- `scripts/production_recovery.py` now provides repeatable online SQLite backups, quiesced database-and-artifact snapshots, manifest/checksum verification, isolated restore smoke, a disk-capacity gate, and image/config/schema release records.
- `scripts/production_backup.sh` and systemd unit templates provide a reviewable daily online backup task without installing anything on production. The wrapper now requires an explicit, pre-created backup root on a filesystem separate from production data and shares a non-blocking lock with deployment snapshots.
- `scripts/deploy_update.sh` now refuses dirty worktrees and root-disk use at or above 80%, requires a quiesced full snapshot, builds the API with OCI revision labels, and records the resulting release metadata.
- The deployment runbook now resolves the real Docker named-volume mountpoint and no longer documents repository-local `data/index.db` copying as the production backup/restore method.
- GitHub Epic `#172` tracks the governed Agentic acquisition and knowledge-update program.
- AI InfoSearch implementation and operations Issues are open:
  - `#173`: production backup, recovery, capacity, and release traceability baseline.
  - `#174`: automatic ready-data build, validation, and atomic publication.
  - `#175`: acquisition manifest ingestion and source/derived artifact lineage.
  - `#176`: production migration, canary, rollback, and live validation.
  - `#177`: bidirectional category-to-KB membership reconciliation.
  - `#178`: reclassification-only task and taxonomy version audit.
  - `#179`: durable parent/child execution and recoverable end-to-end pipeline state.
- `web_listening` implementation Issues are open:
  - `ferryhe/web_listening#47`: unified SSRF, robots, redirect, and pacing gateway.
  - `ferryhe/web_listening#46`: governed Agentic exploration, raw HTML/PDF artifacts, and `acquisition-manifest.v1`.
- The Epic body links all child Issues and records the dependency chain.

## Production Findings

- `aiinforsearch.com` directly deploys this repository from `/opt/ai_actuarial_inforsearch`.
- The production worktree is at `a73bac6`, 15 commits behind GitHub `main` at the time of the read-only audit.
- Production uses Docker Compose with healthy FastAPI, React, and Caddy services and a SQLite database in a Docker named volume.
- The application data volume is approximately 2.8 GB; the root disk was approximately 83% used with about 11 GB free.
- The Issue `#173` server preflight confirmed that `/var/backups` is on the same root ext4 filesystem as production data. The COSFS mount at `/lhcos-data` is only a candidate until disposable-prefix write, rename, interruption, and checksum read-back tests pass.
- The current full-snapshot contract is approximately 2.19 GiB; the proposed retention set plus one isolated restore peaks around 8.23 GiB before safety margin. The server Agent recommends a 20–30 GiB independent ext4/xfs backup volume for the near-term baseline.
- Only one older SQLite backup was found, and no verified database-plus-files recovery rehearsal was found.
- Scheduled collection and asynchronous search fallback run in production, but no `full_pipeline` history was found.
- The current search fallback is not joined to its parent run; raw HTML is not retained; category KB synchronization is additive only; no reclassification-only task exists; ready-data is not automatically published after indexing.

## Compatibility Requirements

- Keep Site Configuration, Tasks, and Knowledge Base as the primary user-facing entry points.
- Do not require ordinary users to operate `web_listening`, manifests, workers, or raw artifact storage directly.
- Preserve existing YAML and single-stage task workflows through migration and retain an old-pipeline rollback switch during canary rollout.
- Show robots evidence, lineage, and stage details in advanced/detail views.
- Protect manual KB members; require dry-run and explicit confirmation for high-volume automatic removals.
- Make ready-data automatic publication configurable per KB and fail back to the previous validated version.

## Verification

- GitHub issue search confirmed that no pre-existing open AI InfoSearch Issue covers the same scope as this program.
- GitHub App creation succeeded for one Epic and nine child Issues across the two repositories.
- Post-creation search confirmed eight open Issues in `AI_actuarial_inforsearch` (`#172`-`#179`) and two in `web_listening` (`#46`, `#47`).
- Cross-repository and prerequisite links were added to the Epic and dependent Issue bodies.
- The server Agent supplied a read-only production audit; no production deployment, restart, migration, configuration change, or data write was authorized or performed.
- `git diff --check` passed for this status-only change.
- Copilot's single actionable wording comment on PR `#180` was accepted; the clarification does not change the plan or product behavior.
- The mandatory Codex CLI review gate was retried for Issue `#173` and remains blocked because the local `codex.exe` WindowsApps entrypoint returns `Access is denied`.
- The local `gh` CLI authentication was revalidated on 2026-08-16; after the fix, Copilot's original PR `#180` thread became outdated and the PR merged with passing CI.
- Issue `#173` test-first implementation: the initial recovery test failed because the module did not exist; the implemented suite now has 9 passing recovery/CLI/source-contract tests.
- Focused deployment verification: 16 tests passed across `tests/test_production_recovery.py` and `tests/test_deployment_config_source.py`.
- Targeted Ruff checks, Python bytecode compilation, Compose YAML parsing, Git Bash syntax checks for both operations scripts, CLI `--help`/JSON smoke, and `git diff --check` passed.
- PR `#181` is open and mergeable; GitHub `python-smoke` passed. Copilot generated three actionable comments at the end of the review window; all three were accepted for BOM removal, injected-clock consistency, and a standard-library Fernet-key example.
- Post-Copilot verification passed: 16 focused tests, targeted Ruff, BOM/shebang assertion, both Git Bash syntax checks, and `git diff --check`.
- The production preflight confirmed Python 3.11, SQLite 3.50, Docker/Compose, systemd 255, and bash 5.2 satisfy the PR runtime contract; it also confirmed no unit, timer, cron, Hermes, or running-backup conflict.
- A new fail-closed backup-location/locking contract test first failed against the unsafe default and then passed after the wrappers, unit, and runbook were tightened.
- Post-preflight hardening verification passed: 16 focused tests, targeted Ruff, both Git Bash syntax checks, CLI help, and `git diff --check`. The mandatory Codex CLI review was retried after these changes and remains blocked by the same WindowsApps `codex.exe` `Access is denied` error.
- Issue `#174` used five TDD/review cycles with separate implementation, specification, and quality agents. Earlier findings covering legacy-slot preservation, truthful source provenance, cross-connection idempotency, transactional rollback, staging cleanup, symlink/reparse containment, connection closure, and pre-publish TOCTOU checks were fixed.
- Final Issue `#174` focused verification collected 81 tests: `77 passed, 4 skipped`; all skips are real symlink safety sentinels that this Windows session cannot create and must run on Linux CI. Targeted Ruff and `git diff --check` passed.
- Follow-up read-only verification selected 17 publication/staging/build endpoint tests: `13 passed, 4 skipped`; the four skips are the same Windows link/reparse safety sentinels. The selected suite confirms the existing covered baseline but does not cover the two final-review failure scenarios, which must be added test-first in the next continuation.
- The final specification and quality reviews both reported the unresolved validated-but-inactive retry blocker. Because the managed-development review limit was reached, the branch was intentionally not committed, pushed, or published as a PR, and the mandatory Codex CLI review gate was not entered.
- The explicitly authorized state-machine continuation completed four fresh remediation/review cycles. Fresh specification and quality reviewers finished clean with no Critical, Important, or Minor findings after attempt identity, CAS, migration rollback, corrupt active/previous validation, stale-slot handling, and strict publication-status gates were covered.
- Final Issue `#174` validation collected 97 tests: `93 passed, 4 skipped`; the four skips are Windows-only inability to create real directory symlink/reparse sentinels and are expected to execute on Linux CI. Targeted Ruff, Python compilation, and `git diff --check` passed.
- The mandatory Codex CLI review gate was attempted again after final validation. The installed WindowsApps `codex.exe` still fails to start with `Access is denied`; the exact tooling blocker is recorded before publication as required.
- Draft PR `#182` was created from `codex/issue-174-ready-data-atomic-publish` into `main` with commit `1c2048f`. It contains eight scoped files and explicitly leaves `#174` open for automatic stale/build integration, UI status, and bounded duplicate retention/GC follow-up.

## Local Notes

- Current Issue `#174` files in scope: `.hermes/project-status.md`, `ai_actuarial/storage.py`, `ai_actuarial/agentic_rag/ready_data_builder.py`, `ai_actuarial/api/services/rag_admin.py`, `tests/agentic_rag/test_ready_data_builder.py`, `tests/test_ready_data_publication.py`, `tests/test_fastapi_rag_admin_endpoints.py`, and `tests/test_fastapi_agentic_rag_endpoints.py`.
- No production command, deployment, service installation, backup, restore, restart, migration, capacity change, or data write was performed.
- Sibling repositories remain off-limits and were not read or modified.
- Issue `#173` remains open: the independent backup disk, verified online backup, quiesced full snapshot, and file-level isolated restore are complete. Remaining work is to classify the isolated KB HTTP 500, pass the KB restore smoke, recheck the root-disk/deployment capacity gate, and only then install/enable the daily backup timer with recorded evidence.
- Next action: wait the required remote-feedback window for PR `#182`, then evaluate GitHub checks, reviews, inline threads, issue comments, and Copilot feedback. Separately, wait for explicit approval of the Issue `#173` diagnostic request before inspecting the isolated KB HTTP 500.
- Issue ordering decision: continue the local `#174` PR1 state-machine fix now because `#173` blocks production activation, not local feature development. Keep `#173` paused pending explicit least-privilege diagnostic approval, and keep Epic `#172` open until its child chain is actually complete.
