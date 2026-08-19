# Project Status

- Date: 2026-08-18
- Branch: `codex/issue-174-ready-data-source-state`
- Baseline: `origin/main` at merge commit `6741cbb9bc3b0a8e3e419f963e7f0d8552d02ad5` (merged PR `#183`).
- Scope: Implement the Issue `#174` ready-data source-state foundation: durable generations and authoritative source identity, soft/hard serving policy, default-off automation flags, legacy-safe read models, and reserved `superseded_generation` lifecycle; do not add an executor, automatic GC, UI, full-pipeline, production work, or `#175`/`#176`/`#179` behavior.
- Managed PR heartbeat: PR `#184` is open and ready for review at `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/184`. Its confirmed code head includes feedback fix `2055a0b`, is mergeable, and `python-smoke` passed. Four local review cycles and the narrow feedback re-review ended with independent specification and quality/security reviews CLEAN. Copilot's two actionable comments were accepted narrowly: publication-column capability detection is cached per `Storage` instance while retaining immutable read-only legacy fallback, and the source-event transaction docstring now describes both top-level atomic execution and nested savepoints. Both threads were replied to and resolved; the full post-push observation window found no further review or check blocker.

## Active State

- PR `#181` is merged. Production now has an independent 40 GiB ext4 backup disk mounted at `/data`.
- A verified online SQLite backup and a verified quiesced database-and-data snapshot were created on the independent disk.
- File-level isolated restore passed. The isolated API health check passed, while `GET /api/rag/knowledge-bases` returned HTTP 500; the smoke container remains isolated and Issue `#173` is not ready to close.
- Issue `#173` has a least-privilege diagnostic authorization request posted at `https://github.com/ferryhe/AI_actuarial_inforsearch/issues/173#issuecomment-5331395524`. It is a request only; no new production diagnosis or command was executed.
- PR `#182` was merged into `main` as `9320efe8dd3c28f097d7f552189c24868c0c66b8`. Issue `#174` PR1 now provides durable publication records, active/previous slots, validated staging builds, atomic publish/rollback storage primitives, deterministic input provenance, and default-off manual-build integration.
- The earlier validated-but-inactive retry and corrupt-active idempotency blockers are resolved in the authorized continuation. Each build now has an independent attempt record, publication uses expected-active CAS, failed CAS/gate attempts remain retryable, and active/previous artifacts are fail-closed validated before dedupe, preservation, or rollback.
- The user authorized that continuation on 2026-08-18. The approved design separates per-build attempts from logical source/digest identity, keeps publish-failed validated candidates retryable, uses expected-active/CAS winner selection, revalidates active artifacts before deduplication, and excludes a corrupt active artifact from the previous slot. Scope remains backend/storage/tests only.
- Safe duplicate policy: because filesystem validation cannot be atomic with the SQLite serving slot, a healthy same-identity duplicate remains a validated, non-serving candidate and the response reports `duplicate_retained` / `duplicate_gc_deferred`. Bounded retention/GC is required before later automatic publication is enabled; it is intentionally outside PR1.
- The retention/GC audit found that the existing `discard_agentic_ready_publication()` delete-record-first order is not a safe GC primitive: a filesystem failure would lose the recovery anchor, and a generic validated candidate can still be retryable. The proposed fail-closed lifecycle is `protected -> eligible -> claimed -> deleted/delete_failed`, with slot-aware CAS before any filesystem action, deterministic quarantine under the verified staging root, and a retained tombstone for idempotent recovery.
- The user confirmed the retention policy: only explicitly classified `redundant_duplicate` attempts are eligible; active, previous, legacy, unknown historical rows, and retryable validated candidates remain protected. Eligibility requires both 14 days since classification and exclusion from the newest 2 eligible attempts per `(kb_id, profile)`, ordered deterministically by marked time and publication ID. Dry-run is default and zero-write, explicit execution requires an exact policy/cutoff/candidate/slot fingerprint, and automatic GC remains disabled.
- The implemented fail-closed lifecycle uses durable GC metadata and audit tombstones, deterministic staging quarantine, SQLite write-transaction fencing across claim/filesystem/finalize, crash-idempotent recovery, and normalized/resolved same-or-ancestor/descendant path reservations for every non-deleted publication, serving manifest, and quarantine path. No UI, full-pipeline, automatic stale/build, production, `#175`, or `#179` work is included.
- PR `#183` is merged as `6741cbb`; the bounded retention/GC phase is complete and automatic GC remains disabled. Issue `#174` was incorrectly auto-closed by the merge, so it was reopened and its remaining automatic stale/build, full-pipeline, and Knowledge Base page-status scope was recorded at `https://github.com/ferryhe/AI_actuarial_inforsearch/issues/174#issuecomment-5336310768`.
- The automatic stale/build audit found that the builder's exact `catalog_chunks_snapshot` consumes KB membership, selected catalog/file metadata, and bound (or fallback) global chunks. It does not currently consume the FAISS index or embedding vectors, so successful index commits should wake source evaluation but must not blindly mark ready-data stale when the exact source version is unchanged.
- The recommended next PR is storage/status only: add default-off per-`(kb_id, profile)` automatic-build configuration, durable source-generation/coalescing state, exact/legacy-compatible stale reporting fields, and post-commit mutation hooks without launching builds. Automatic execution, retry cadence, and publication follow in a separate PR after product policy is confirmed; durable parent/child/full-pipeline semantics remain `#179`.
- The source-state foundation now separates event/pending/evaluated generations from the builder-authored `source_version_id`. Soft changes keep the current active usable with explicit stale status; hard changes fail closed and Agentic chat falls back to standard retrieval restricted to the same KB and filtered against live `rag_kb_files` membership. Index/embedding-only evaluation does not synthesize stale when the authoritative source identity is unchanged.
- Automatic build/publish settings are persisted per `(kb_id, profile)` and remain default-off. `false/false`, `true/false`, and `true/true` are valid; `false/true` is rejected, and legacy publish-enabled rows migrate to `true/true`. The existing manual build API remains synchronous and safely settles only the generation it captured.
- `superseded_generation` is reserved independently from `redundant_duplicate`; serving, claimed, delete-failed, deleted, and quarantined attempts fail closed. Automatic GC remains disabled. Future executor policy is recorded only: 60-second quiet debounce, 15-second polling, SQLite concurrency 1, per-KB/profile single-flight, no initial automatic retry, offline 10-second staging smoke, citation validation for non-empty KBs, and manual confirmation for empty KBs.
- TDD and review evidence: 13 initial source-state tests were RED before implementation; three repair cycles added regressions for hard-state monotonicity/reset, registered-path and quarantine bypasses, legacy identity, generation races, manual build settlement, same-KB live-membership fallback, slot migration, and GC/disposition recovery. Final related suite is 198 passed / 5 Windows capability skips. Four independent review cycles ended CLEAN for both specification and quality/security.
- The mandatory local Codex CLI review gate could not start: Windows returned `Access is denied` for `C:\Program Files\WindowsApps\OpenAI.Codex_26.814.5167.0_x64__2p2nqsd0c76g0\app\resources\codex.exe`. The command was not retried through another executable; repository-permitted publication proceeds with the independent specification and quality/security reviews recorded above.
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
- PR `#182` was created from `codex/issue-174-ready-data-atomic-publish` with implementation commit `1c2048f` and merged into `main` as merge commit `9320efe`. It explicitly leaves `#174` open for automatic stale/build integration, UI status, and bounded duplicate retention/GC follow-up.
- Remote feedback classification for PR `#182`: the Copilot submission is an informational overview, explicitly states that no comments were generated, and requires no code change. Thread-aware and flat reads found zero inline review threads and zero ordinary comments after the full 15-minute window.
- Issue `#174` retention/GC TDD and review gates: the final root focused suite passed `133 passed, 5 skipped`; the dedicated GC suite passed `40 passed, 1 skipped`; broader ready-data/API validation passed `129 passed, 5 skipped`. Skips are real Windows link/reparse capability sentinels intended for Linux CI. Targeted Ruff, Python compilation, and `git diff --check` passed. Independent final specification and quality/security reviews are both CLEAN.
- A broad repository run before the final narrow path-reservation patch completed `783 passed, 5 skipped, 5 failed`; the five failures reproduce independently as unrelated Windows environment issues: one SQLite temp-file cleanup `WinError 32` and four tests invoking bare `npm` while only `npm.cmd` is available. The final narrow changes are covered by the focused and broader green suites.
- The mandatory pre-PR Codex CLI review was attempted on the final diff. The installed entry point `C:\Program Files\WindowsApps\OpenAI.Codex_26.814.5167.0_x64__2p2nqsd0c76g0\app\resources\codex.exe` failed to start with `Access is denied`; this is the same local tooling blocker recorded for earlier PRs, so publication continues under the repository's documented fallback.
- PR `#183` was created as a ready-for-review Issue `#174` follow-up and deliberately does not close the Issue. It contains only the bounded retention/GC backend, storage, status, and focused test changes; automatic GC remains disabled.
- Copilot reviewed all six PR files and produced one actionable compatibility comment: `duplicate_gc_deferred` must continue to mean that a retained duplicate was not immediately deleted, while the new `duplicate_gc_marked` field separately reports whether durable GC classification succeeded. The comment was accepted test-first; the guard-loss regression now proves the candidate remains retryable with `duplicate_gc_deferred=true` and `duplicate_gc_marked=false`. Follow-up validation passed `97 passed, 5 skipped`, targeted Ruff, Python compilation, `git diff --check`, and a narrow independent quality review.
- The accepted Copilot thread is fully addressed by commit `7d6debb` but remains marked unresolved on GitHub because no authorization was given to reply to or resolve review threads. Thread-aware final reads found no other inline threads and no conversation comments.

## Local Notes

- Intended source-state changes are `.hermes/project-status.md`, `ai_actuarial/storage.py`, `ai_actuarial/api/services/agentic_rag.py`, `ai_actuarial/api/services/chat.py`, `ai_actuarial/api/services/rag_admin.py`, `tests/test_ready_data_source_state.py`, `tests/test_fastapi_chat_endpoints.py`, `tests/test_fastapi_rag_admin_endpoints.py`, and `tests/test_ready_data_retention_gc.py`. `ai_actuarial/api/routers/rag_admin.py` retains its pre-existing line-ending-only worktree status with no content diff, and `graphify-out/` remains untracked and excluded.
- No production command, deployment, service installation, backup, restore, restart, migration, capacity change, or data write was performed.
- Sibling repositories remain off-limits and were not read or modified.
- Issue `#173` remains open: the independent backup disk, verified online backup, quiesced full snapshot, and file-level isolated restore are complete. Remaining work is to classify the isolated KB HTTP 500, pass the KB restore smoke, recheck the root-disk/deployment capacity gate, and only then install/enable the daily backup timer with recorded evidence.
- Next action: PR `#184` is ready for maintainer merge while Issue `#174` remains open. Follow-up mutation-path hooks and the automatic executor stay in separate PRs; full-pipeline/durable parent-child work stays in `#179`, UI stays later, and `#173` remains paused pending separate diagnostic authorization.
- Issue ordering decision: continue the local `#174` PR1 state-machine fix now because `#173` blocks production activation, not local feature development. Keep `#173` paused pending explicit least-privilege diagnostic approval, and keep Epic `#172` open until its child chain is actually complete.
