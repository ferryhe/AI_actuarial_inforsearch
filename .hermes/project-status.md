# Project Status — Canonical Handoff

- Updated: 2026-08-20 (America/New_York)
- Repository: `ferryhe/AI_actuarial_inforsearch`
- Workspace: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-194`
- Active branch: `codex/issue-194-kb-list-offline`
- Baseline: `origin/main` at `1c682650bee760ca0d58eedde33de2d7987d6ec1` (merged PR `#193`)
- Delivery: Issue `#194` application fix is implemented and locally verified; manager review, publication, and merge remain.
- Primary objective: finish Epic `#172` by completing Issues `#173`–`#179` and their declared dependencies.

## Issue #194 — KB list offline delivery

- For filesystem-backed databases, before constructing its normal `Storage`, `GET /api/rag/knowledge-bases` performs a raw SQLite, read-only schema readiness check for all selected KB metadata columns, all columns that `Storage._ensure_rag_kb_embedding_columns` can add, and the required `rag_kb_files` fields. Already-ready databases take no readiness write lock. Only missing schemas enter `BEGIN IMMEDIATE`, recheck under the cross-connection lock, apply the list-only migration, and commit; the later `Storage` construction therefore cannot race on those column additions. For connection-local `:memory:` and empty-string temporary databases, the same readiness logic runs on the exact `Storage` connection that performs the list query, so the prepared schema remains visible. No URI path semantics were added. No `KnowledgeBaseManager`, `SemanticChunker`, tokenizer encoding, or `EmbeddingGenerator` is constructed, and no RAG chunks or index tables are migrated.
- Existing ordering, `kb_mode`/`search` filters, `KnowledgeBase`-compatible provider/profile/dimension/timestamp normalization, chunk-profile decoration, current-embedding compatibility/status, and agentic ready-manifest decoration are preserved. A database with no RAG KB table continues to return an empty list.
- TDD red evidence: the original cold-cache regression failed at `list_knowledge_bases -> _manager_and_storage -> KnowledgeBaseManager`; Round 1 legacy regressions then failed with `no such column: description` and unnormalized provider value `' OpenAI '`; Round 2 exposed `duplicate column name: description`; Round 3 reproduced constructor-time `duplicate column name: embedding_provider` and an already-ready list blocked by an unrelated writer with `database is locked`; Round 4 reproduced `no such table: rag_knowledge_bases` for both `:memory:` and empty-string connection-local databases.
- TDD green evidence: the cold-cache, legacy-schema, legacy-value, constructor-time concurrent-first-migration, steady-state writer-lock, `:memory:`, and empty-string temporary-database regressions pass. Runtime dependency entry points remain fail-fast in the offline/concurrent/connection-local regressions, and the steady-state regression proves readiness remains read-only behind an existing writer. Two independent empty-string SQLite connections were also shown to have separate temporary schemas and empty `PRAGMA database_list` filenames on this host, supporting the narrow connection-local classification.
- Local verification: focused offline/legacy/locking/connection-local regressions `7 passed`; the two connection-local cases passed together in five consecutive isolated reruns; both Round 3 concurrency/lock regressions also passed together in five consecutive isolated reruns; complete `tests/test_fastapi_rag_admin_endpoints.py` `99 passed, 7 skipped`; a nested missing-parent/new-empty-database probe passed; touched-file Ruff, compileall, and `git diff --check` passed.
- Heartbeat `managed-pr-173-progress` is active during delivery.
- Parent Issue `#173` remains open pending separately authorized fixed-image no-network server smoke plus capacity, backup, and timer acceptance. This branch closes only `#194` and performs no server, image, container, deployment, backup, or timer operations.

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

- Complete ready-data/API/UI suite: `435 passed, 9 skipped`.
- Full repository: `1090 passed, 9 skipped, 5` known Windows baseline failures.
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

- Isolated worktree: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-194` on `codex/issue-194-kb-list-offline`, based on merged PR `#193` at `1c682650bee760ca0d58eedde33de2d7987d6ec1`.
- Modified only: `.hermes/project-status.md`, `ai_actuarial/api/services/rag_admin.py`, and `tests/test_fastapi_rag_admin_endpoints.py`.
- No untracked files exist in this isolated worktree.
