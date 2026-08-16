# Project Status

- Date: 2026-08-16
- Branch: `ops/issue-173-production-recovery-baseline`
- Baseline: `origin/main` at `7eb7c62` (merged PR `#180`).
- Scope: Implement the repository-side backup, isolated restore, capacity, and release-traceability baseline for Issue `#173`; do not change production.

## Current State

- PR `#180` is merged into `main`; the Issue plan and production audit are recorded.
- Issue `#173` implementation is active on `ops/issue-173-production-recovery-baseline`.
- `scripts/production_recovery.py` now provides repeatable online SQLite backups, quiesced database-and-artifact snapshots, manifest/checksum verification, isolated restore smoke, a disk-capacity gate, and image/config/schema release records.
- `scripts/production_backup.sh` and systemd unit templates provide a reviewable daily online backup task without installing anything on production.
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

## Local Notes

- Files in scope: `Dockerfile`, `docker-compose.yml`, `.hermes/project-status.md`, `docs/deployment-runbook.md`, `scripts/deploy_update.sh`, `scripts/production_backup.sh`, `scripts/production_recovery.py`, `ops/systemd/*`, and `tests/test_production_recovery.py`.
- No production command, deployment, service installation, backup, restore, restart, migration, capacity change, or data write was performed.
- Sibling repositories remain off-limits and were not read or modified.
- Issue `#173` remains open after this repository PR: production still needs separate-storage capacity, timer installation, one verified full snapshot, an isolated API restore rehearsal, and recorded evidence before the gate is complete.
- Next action: finish local review and create the Issue `#173` PR. After it merges, send the server Agent a read-only/preflight-first command; do not use `deploy_update.sh` on the current 83%-used root disk or while `.hermes/project-status.md` remains modified.
