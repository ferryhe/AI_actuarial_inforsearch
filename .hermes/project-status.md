# Project Status

- Date: 2026-08-16
- Branch: `record-agentic-pipeline-issues`
- Baseline: `origin/main` at `10c38ce` (merged PR `#171`).
- Scope: Record the approved cross-repository plan for governed Agentic acquisition, recoverable processing, classification/KB consistency, ready-data publication, and production migration.

## Current State

- PR `#171` is merged into `main`; the local baseline is synchronized with `origin/main`.
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
- The mandatory Codex CLI review gate could not run because the local `codex.exe` WindowsApps entrypoint returned `Access is denied`.
- The local `gh` CLI authentication was revalidated on 2026-08-16; the threaded PR review fetch confirmed one unresolved, current Copilot wording comment.

## Local Notes

- Files in scope: `.hermes/project-status.md` only.
- No product code or configuration is changed by this branch.
- The remote `web_listening` repository was changed only by the two explicitly authorized GitHub Issue creations; no local sibling repository was read or modified in this run.
- Next action: merge PR `#180`, then start AI InfoSearch `#173` and `web_listening#47` in parallel. Do not update production application code until `#173` establishes backup/recovery/capacity/release gates. Then implement `web_listening#46`, AI InfoSearch `#175`, `#177`, `#178`, `#174`, and `#179`; finish with production Issue `#176`.
