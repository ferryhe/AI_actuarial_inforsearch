# Project Status — Canonical Handoff

- Updated: 2026-08-20 (America/New_York)
- Repository: `ferryhe/AI_actuarial_inforsearch`
- Workspace: `C:\Project\AI_actuarial_inforsearch`
- Active branch: `codex/issue-174-ready-data-provenance-ui-closure`
- Baseline: `origin/main` at `001dd494ce0dafb633c34459053891c919180823` (merged PR `#192`)
- Delivery: Issue `#174` final provenance/API/Knowledge UI closure passed 15 review rounds plus the user-authorized final post-round-15 fix. Ready-for-review PR `#193` is open and mergeable; CI and remote/Copilot feedback observation are in progress.
- Primary objective: finish Epic `#172` by completing Issues `#173`–`#179` and their declared dependencies.

## Hard Boundaries

- This repository is the only writable workspace unless a later task explicitly names another repository.
- No production, deployment, restart, migration, server-Agent command, sibling-repository work, automatic retry, or automatic GC was performed for this delivery.
- Preserve `ai_actuarial/api/routers/rag_admin.py`: it has a known line-ending-only worktree state and a content diff of zero. It is excluded from the delivery.
- Preserve `graphify-out/`: it is an existing untracked analysis artifact; do not stage, commit, or clean it.
- Durable full-pipeline stages, resume, lease, watermark, and Tasks reporting belong to Issue `#179`.
- Production/API/browser canary belongs to Issue `#176`.

## Live Issue Board

| Issue | State | Current meaning | Close condition / next dependency |
|---|---|---|---|
| `#172` Epic | Open | Governs the complete acquisition-to-ready-data program. | Close after child Issues and external prerequisites complete and production acceptance is recorded. |
| `#173` OPS baseline | Open | PR `#181` is merged; isolated KB list diagnosis remains separately authorized work. | Explicitly authorized least-privilege diagnosis and remaining acceptance. |
| `#174` ready-data | Open/Reopened | PRs `#182`–`#192` are merged. Final provenance, public rollback API, and Knowledge UI closure are implemented and locally gated on the current branch. | Ready PR, CI/remote review, maintainer merge, then final acceptance comment and close. |
| `#175` manifest/lineage | Open | Declared producer contract remains. | Re-triage external readiness before starting. |
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

- Local implementation and final gates are complete.
- A subsequent authorized session successfully verified `.git` write access and the existing `ferryhe` GitHub login with `repo`/`workflow` scopes. No ACL workaround or alternate credential path was used.
- Ready-for-review PR `#193`, `feat: close ready-data provenance and KB controls`, was created with `Refs #174`. It targets `main` from `codex/issue-174-ready-data-provenance-ui-closure` and does not auto-close the Issue before acceptance.
- After the final push, observe GitHub Actions, Copilot, reviews, inline threads, and comments for the required remote-feedback window. Fix only confirmed-safe in-scope feedback and do not auto-merge.
- After maintainer merge, audit the merge on current `main`, post the Issue `#174` acceptance mapping, and close only the repository-owned scope. Do not claim `#179` or `#176` work as completed.

## Program Dependency Order

```text
#173 OPS baseline --------------------------------------------→ #176 production
external acquisition prerequisites → #175 → #177 → #178 ─┐
                                      #174 ------------------├→ #179 durable pipeline → #176
                                                          ──┘
#176 accepted → close #172
```

After `#174` closes, re-read live Issue state. The next repository-only dependency is `#175` when its external producer contract is ready; otherwise the explicitly authorized `#173` diagnosis may proceed. Do not infer sibling or server scope.

## Current Worktree State

- Issue `#174` final closure implementation is committed and published in PR `#193`.
- `ai_actuarial/api/routers/rag_admin.py`: pre-existing line-ending metadata only; content diff zero; exclude from staging.
- `graphify-out/`: pre-existing untracked analysis output; preserve and exclude.
