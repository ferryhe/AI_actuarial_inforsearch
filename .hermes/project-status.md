## 2026-11-10 Issue #480 — local review passed; Draft PR authorized; live UAT still blocked

- The first fresh local review was completed on the verified gpt-6-sol/high route and requested one AC3/AC4 clarification in T12. TypeSafe's preliminary assessment was ambiguous; controller review of the fixture and runbook confirmed the concrete conflict, so the finding was accepted and the review cycle recorded as changes.
- The same approved gpt-6.1-sol/high worker updated the frozen fixture and runbook: T12's user-requested retry remains turn 2, attempt 1; evaluator replay restores that turn's original state/history, appends a later attempt, and preserves attempt 1 for scoring. A contract test locks the distinction. Red/green evidence: the new assertion failed before the repair; all 3 matrix tests passed afterward. Black, isort, Ruff, whitespace and old-fixture checks passed. Evidence: `reports/issue-473-480-20261107/issue-480/r1/worker-fix/`.
- Overseas provider intent is clarified as ChatGPT/OpenAI, not GitHub Models. The prior read-only server inspection showed DeepSeek/deepseek-flash for China and OpenAI/gpt-6-luna overseas; exact API endpoints and credential validity remain unverified. Approved isolated site snapshots are still missing. No provider calls, production writes, deployment, live browser run or physical iOS UAT occurred; production observation and #489 remain `NOT_RUN`. The UAT batch is incomplete.
- Authorized read-only discovery through the existing China and overseas bridges found a usable Spring 2026 Ready artifact in each site's `ai` KB, with separate publication and index-version IDs and a `Key Findings` section. The stored catalog record is the unversioned SOA alias; the fixture's `/2026/` URL, Summer 2025 page and March recruitment PDF were not found by exact detail lookup. The stored publication date is null. China has 13 published weekly snapshots and overseas has 22; their current database snapshots are not approved isolated UAT inputs. Both connections were read-only; database and container checks stayed unchanged, with zero provider calls or production writes. Sanitized metadata is under `reports/issue-473-480-20261107/issue-480/controller-public-metadata-readonly.json` and `controller-public-file-metadata-readonly.json`.
- First-execution output/request ceiling from current per-site settings: 64 independent questions plus 34 task turns = 98 inputs/site; up to 6 physical Chat requests per input and 4,000 requested output tokens per request means 588 requests and 2,352,000 requested output tokens/site (1,176 requests and 4,704,000 requested output tokens across both sites). This does not bound prompt/input tokens: `max_context_tokens=8000` is the ordinary Chat API budget, while Assistant constructs `LLMClient` directly and passes generated messages through unchanged. Actual input and embedding use need measurement or an explicit cap; evaluator replays need a separate cap. This is not a monetary spend approval; provider endpoint, pricing and billing account remain unverified.
- The first round-2 attempt is preserved but aborted without consuming the round because its reviewer saw prior #480 review status. A fresh reviewer then reviewed an isolated detached snapshot with no #480 review result; its actual substantive route was gpt-6-sol/high, all three candidate hashes matched, and the report is PASS with zero findings. TypeSafe Jev 1.14 reported no findings (coverage 0.04, treated as limited support). Formal review_count is 2 with one failed cycle; local review is complete. Evidence: `reports/issue-473-480-20261107/issue-480/review-2-attempt-2/`.
- Draft PR [#490](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/490) is open with `Closes #480`; it remains Draft and its description separates offline validation from live UAT, production and device gates. GitHub CI is tracked against the latest pushed PR HEAD. Copilot review was requested once but could not run because the requester's remaining quota was insufficient; no retry will be made for this issue. Before real UAT, provide the approved PostgreSQL 16 snapshot/restore record and local path for each site, confirm each existing HTTPS endpoint and non-secret credential source, and approve a per-site spend cap. Direct server deployment remains outside this task's authorization; no live UAT, production observation, device run or merge has occurred.
- 2026-11-10 follow-up: the same gpt-6.1-sol/high worker corrected the SOA links using read-only publisher evidence. The reachable Spring 2026 page is the unversioned URL; its public date is 2026-10-29 while each site's stored date remains null. The year-qualified suggested-citation URL returned 404; the beta March PDF hostname failed DNS, and the official `www.soa.org` PDF works. Question/task roster, denominators and gates are unchanged. The fresh independent gpt-6-sol/high review passed the exact three-file candidate with zero findings. The four focused matrix tests pass. Evidence: `reports/issue-473-480-20261107/issue-480/controller-soa-public-url-verification-20261110.json` and local review receipt.
- The ignored local offline package at `reports/issue-473-480-20261107/issue-480/offline-public-export-20261110/` preserves separate China `deepseek/deepseek-flash` and overseas `openai/gpt-6-luna` bindings, each site's distinct Ready publication/index IDs, and three weekly snapshots (8, 7 and 0 members; 15 rows/site). Its new SOA fixture contains one short public Key Findings excerpt plus paraphrased facts, bound to the separate per-site Ready IDs; it is not a full article copy or approved DB snapshot, and server-body parity is unverified. The combined entrypoint used two fresh loopback-only PostgreSQL 16 containers and the normal `create_app()` factory; health, capabilities and weekly list/latest/detail/files passed on both sites. A local `LLMClient` stub also passed a 9,032-word input unchanged for both provider/model bindings and captured synthetic prompt/completion/total/reasoning usage; no credentials were read or external requests made. Both containers were removed; provider clients/background tasks were 0 for the metadata check. Full assistant answer/citation, embeddings, actual provider usage, endpoint/credential validity, weekly summaries, remaining snapshots, staff fixtures and skill/help release hashes remain unverified. No production writes or deployment occurred.
- The old PR CI run `42757697700` completed successfully on previous HEAD `e2ed66c852a906cd358b3020785eb7dfd0c9ef7b`; all six jobs passed. The immutable run snapshot is `reports/issue-473-480-20261107/issue-480/controller-ci-run-42757697700.json`. This is historical evidence for that SHA; the status-only push will trigger checks for its new HEAD.
- Review routing correction: `controller-review3-unqualified-attempt.json` preserves an attempted PASS whose actual route was gpt-6.1-sol/xhigh and whose input included earlier #480 review status; it is excluded from formal review counts. The qualified replacement was registered as review round 3, attempt 2, and independently reviewed the three-file clean snapshot on gpt-6-sol/high. It passed AC1/AC2/AC6 with zero findings; the three file hashes match candidate `e2ed66c852a906cd358b3020785eb7dfd0c9ef7b`, and the source, roster, denominators and gates were confirmed. Formal `review_count` is now 3 with one failed cycle. The required TypeSafe assessment (`jev-latest` → `jev-1.14.0`) returned review-summary coverage 0.24 and zero candidate findings; its low coverage is limited support and does not replace the reviewer PASS or CI. Evidence: `reports/issue-473-480-20261107/issue-480/review-3-attempt-2/controller-review3-dispatch.json`, `review-report.json` and `typesafe-review.json`.

## 2026-11-09 Issue #479 — #487 main integration validated

- On the existing `codex/issue-479-assistant-ui` branch, fetched `origin/main` at `09d4bfd4c3ea61e63931f48bff6e3cfc156b7363` and combined it with the #479 parent `04de1b1c20beb5bd8f715a14916385eb38d6b6b5`. The sole content conflict was this status file; both branches' entries are retained. The seven #479 product-file blobs and `config/dead_code_whitelist.py` remain byte-for-byte identical to the #479 parent; both incoming #487 files match `origin/main`.
- Focused offline integration validation passed: the NUL-free evidence-span/source-offset case and two Assistant exact-body/authorization cases yielded 10 passing test instances; the raw-only extraction/read-back case passed against an owned temporary PostgreSQL 16 container, which was stopped and removed. #487 changes Content Hub annotation spans while retaining original Markdown and its hash. Assistant body reads use Ready/Standard section search and do not import that annotation builder. The prior two-site Q4–Q6 raw run used only `usage_navigation.guide` and `resources_updates.weekly`, with no NUL evidence; its old-HEAD CI and UAT remain historical evidence, not new-HEAD checks. No further live UAT is needed for the unchanged affected flow; the one-shot authorization is consumed. New-HEAD CI and thread gates remain with the controller. No provider/site rerun, deployment, physical iOS run, or PR merge occurred in this worker stage.

## 2026-11-09 Issue #479 — R6 internal-KB authorization repair validated

- On `codex/issue-479-assistant-ui`, the final Host check revalidates current permitted KB membership for body evidence, citations, resource cards and the returned target. If staff access is revoked during a request, it returns `SCOPE_REVOKED` and clears factual answer, citations, evidence IDs and selected target; public KB results remain available.
- Independent manager verification of the worker's frozen source passed: four actual role-update route cases (staff body/resource denied, public body/resource controls passed) and the unfiltered four-file PostgreSQL backend suite (233 passed, 0 failed, 0 deselected, 4 warnings). The complete Assistant runtime file contains 109 passing tests. Black, isort, Ruff and `git diff --check` passed.
- Raw post-fix route, suite, formatter, source and database lifecycle evidence is under `reports/issue-473-480-20261107/issue-479/r6-worker-fix/`. The previous 644d-bound real-UAT harness is stale. No live provider/model, site/API server, production or physical iOS UAT was run; the controller owns the neutral R7 package audit and reviewer dispatch.

## 2026-11-09 Issue #479 — R6 internal knowledge-base authorization finding adjudicated

- Pinned candidate `644d2f0e36284b5c2bf6f7b995ba29610f33517c` received a qualified R6 source review finding mapped to AC3 and AC7. An isolated local PostgreSQL reproduction passed 4 cases: staff body evidence and a staff resource card still returned after the actual role-update route changed the same user from operator to registered and removed `assistant.internal`; public controls behaved as authorized. The temporary test file is removed. Evidence: `reports/issue-473-480-20261107/issue-479/r6-reproduction/`.
- TypeSafe Review marked R6-F1 preliminary valid and in scope (criterion mapping 0.91; reproduction evidence 0.82; in-scope probability 0.81, confidence 0.72; review-summary coverage 0.08). The keyed TypeSafe Judge selected `accept_and_repair` (probability 0.63; confidence 0.44); formal lifecycle is review 6 changes, six failed cycles, adjudication resolved, stage `fixing`.
- The same existing `gpt-6-sol` / senior worker thread received a narrow task to recheck current authorization and actual KB membership for returned evidence, reuse `SCOPE_REVOKED` fail-closed behavior, and add staff-revocation plus public-control regressions. The final shared-worktree snapshot after dispatch showed uncommitted changes in `ai_actuarial/features/assistant/feature.py` and `tests/test_assistant_agent_runtime.py` (43 insertions/9 deletions in the feature and 129 test insertions); this phase did not inspect or validate their contents and did not wait for the worker. No commit, push, PR, production, provider, site, or device changes were made.
- Cleanup correction from independent controller verification: the manager successfully stopped owned container `7c9033c5d5d9d8c4d44a22cb8dc8b35f6c68b03849d035b6ff3465bfa77c8338` in command `exec-144ad782-ae1b-46bd-a269-b1fe0f8a4a12`; Docker auto-removed it. Docker events confirm stop then destroy, the exact ID is absent, and loopback port 55481 is released. The earlier handoff and original Docker label record remain preserved. Evidence: `reports/issue-473-480-20261107/issue-479/controller-r6-postgres-closure-verification.json`. Real provider/site/device UAT remains NOT RUN.
## 2026-11-08 Issue #479 — R5 final-answer authorization repair ready for fresh review

- On `codex/issue-479-assistant-ui`, the Host now refreshes identity and the scopes required by tools used in a finished answer after the final model callback. This also covers the body-summary verifier callback. If access changed, it returns the existing `SCOPE_REVOKED` response with no factual answer, evidence IDs, citations, or selected target; per-tool checks and authorized answers remain intact.
- Two new revocation cases failed before the product fix while two authorized controls passed; all four pass after the fix. The unfiltered four-file backend suite passed 229 tests with 4 warnings against an Issue-owned ephemeral PostgreSQL database; no cases were deselected. Black, isort, Ruff and diff checks passed. Raw logs and database ownership/cleanup evidence: `reports/issue-473-480-20261107/issue-479/r5-worker-fix/`.
- This scoped repair is committed and awaits fresh independent review. The earlier ce5-bound real-UAT harness is stale after this source change and was not run. No live provider/model, remote API server, browser, physical iOS, push, PR edit, or merge occurred in this phase.

## 2026-11-08 Issue #479 — R4 help request ordering repair ready for fresh review

- On `codex/issue-479-assistant-ui`, each guide browse or citation read now invalidates earlier in-flight help requests. A late older success cannot replace the newer section, and a late older error cannot appear after the newer section succeeds. Clear and identity-change invalidation remain in place.
- Two regression tests failed before the product fix and passed afterward. The AssistantPanel suite passed 39/39; typecheck, build, changed-file ESLint, diff check, and stubbed Chromium conversation smoke passed. Raw evidence is in `reports/issue-473-480-20261107/issue-479/r4-worker-fix/`.
- Local worker repair awaits fresh independent review. The previous a43-bound real-UAT harness was not run after this change. No live provider/model call, remote server call, commit, push, PR edit, or merge occurred in this worker stage.

## 2026-11-08 Issue #479 — R3 clicked-card target repair ready for fresh review

- On `codex/issue-479-assistant-ui`, clicking a verified catalog/body file card now carries that exact KB/file hint into the next Assistant turn across in-app file-detail navigation. Clicking an unassigned catalog card clears an older hint. The server still rechecks current scope and KB membership before any document read or citation.
- The two UI regressions failed before the product fix and passed afterward. Final focused backend target/reauthorization tests: 13 passed; frontend assistant/feedback suite: 50 passed. Typecheck, build, ESLint, diff check, and stubbed Chromium conversation smoke passed. Raw logs are in `reports/issue-473-480-20261107/issue-479/r3-worker-fix/`.
- R3 changes await fresh independent review; the exact candidate SHA is in the external review receipt. No push, PR edit, merge, live provider/model, production, or physical iOS call.

## 2026-11-08 Issue #479 — R2 F1/F2 repair ready for fresh review

- On `codex/issue-479-assistant-ui`, the accepted AC5 catalog-card gap and AC3/AC7 post-Clear help-result race are repaired. Authorized catalog files without KB membership now get an in-site catalog card without a KB target; late guide and citation results from a cleared session are ignored.
- Red regressions: 2 backend cases failed and 2 frontend cases failed before the fix. After the fix, the focused backend 8/8 and frontend 2/2 passed. Final isolated PostgreSQL backend suite: 262 passed, 4 warnings; frontend: 48 passed. Typecheck, build, Black, isort, Ruff, ESLint, diff check, and stubbed Chromium conversation/viewport smoke passed. Raw evidence is in `reports/issue-473-480-20261107/issue-479/r2-worker-fix/`.
- Candidate is frozen on this branch for fresh independent review. No push, PR edit, merge, production write, current-source live provider UAT, or physical iOS check has occurred.
## 2026-11-09 Issue #487 — PR #488 ready; remote feedback clear; current-head CI pending

- Branch `codex/issue-487-nul-evidence`, from clean `origin/main` baseline `bf92fb5ebbe19914d88b42a913f7687027603220`. The only product/test files changed are `ai_actuarial/local_collection_runtime.py` and `tests/test_local_collection_runtime.py`; this change splits evidence windows at NUL while preserving original Markdown offsets.
- Baseline PostgreSQL red test failed at the annotation JSONB insert with `\u0000 cannot be converted to text`; the fixed test passed and read back the same content version, Markdown text/hash, NUL-free annotation evidence, and one Hub version. The focused NUL/non-NUL evidence test passed; a fresh independent review passed; TypeSafe Jev 1.14 found no candidate issues (review-summary coverage 0.97). Ruff and `git diff --check` passed. Three related frontier, budget/receipt, and AI-only retry checks first hit Windows `WinError 5` with the default temp directory, then all passed when rerun with `--basetemp reports/issue-487-20261109/pytest-basetemp`.
- The one remote-feedback snapshot contained only two identical Copilot quota notices, no code findings, and zero unresolved threads; the same worker and TypeSafe remote assessment found no actionable item. An automatic quota notice appeared when PR #488 became Ready, and the single explicit request returned the same quota result. No further Copilot request will be made. Current-head CI remains a merge gate.
- The saved SOA UEC case remains `pending_retry`. No live source, model, Hub, target, schedule, receipt, or production-runtime write was run because the configured local data/state/Hub paths are outside this Issue worktree. After the fix is available in the original runtime checkout, run `python -m ai_actuarial.local_collection_runtime preflight --config reports/local-automation-state/config.local.json --json`, then `python -m ai_actuarial.local_collection_runtime run-site --site soa-ai-bulletin-focused --exact-url https://www.soa.org/globalassets/assets/files/edu/2026/2026-27-uec-prog-app-form.pdf --source-page-url https://www.soa.org/education/resources/uec/uec-program/ --article-limit 1 --request-limit 30 --config reports/local-automation-state/config.local.json --json`. Verify saved content version 45821, source Markdown/hash, Hub annotation readback, and both target dispositions. This validates one URL only; keep NAAJ and Issue #479 separate. PR #488 is Ready; current-head CI and merge gates remain outstanding.

## 2026-11-08 Issue #478 — R2 F2/F3 repair ready for fresh review

- Same senior worker fixed only the accepted R2 weekly guide answer and bilingual feedback-guide text. A guide-only weekly answer now follows current guide steps, reads the latest published snapshot only with current `chat.query`/`files.read` authorization, states no snapshot or the published period when verified, and leaves status unasserted on denial/read failure. The guide now describes the actual single question input and automatic tool selection; both guide versions are 1.1.2.
- Six new cases failed before product edits and passed after. Final isolated PostgreSQL focused suite: 361 passed, 4 warnings; Black, isort, Ruff and `git diff --check` passed. Raw evidence and the 35-file current-source package are under `reports/issue-473-480-20261107/issue-478/r2/fix-f2-f3/`; source fingerprint `c571938a6319c5bc931ca24660856b37dff2cc08fbdbd5de09343b420678b00f`.
- HEAD remains `977083471cb2ba7c37195bceba16133d06f361ad`. No commit, push, PR, provider run, browser-continuous run or production write by this worker. Fresh independent review is next.

## 2026-11-08 Issue #478 — generic catalog discovery and multi-turn tests ready for review

- Follow-up correction removed per-skill finder names from the agent loop. A registered `catalog_discovery` manifest result contract now drives loop evidence and Host current-member validation; a third test-only packaged finder succeeds without another loop edit. Previously published manifests that omit the field inherit the registered contract.
- SOA resource or alternate finder → exact body quote/source → selected-target follow-up is covered. Usage overview → weekly guide plus snapshot in one RunContext → `/weekly` → additions follow-up is covered; each new turn has a fresh budget and evidence set. Ordinary widget remains on the legacy route and browser-continuous flow is reserved for #479; the `config.write` admin gate is unchanged.
- Task-isolated PostgreSQL focused suite: 348 passed, 4 warnings. Black, isort, Ruff and whitespace checks passed. Evidence: `reports/issue-473-480-20261107/issue-478/worker-implementation.md`. No live provider, production write, commit, push or PR by this worker. Independent review is next.

## 2026-11-08 Issue #478 — built-in skill implementation ready for independent review

- Branch `codex/issue-478-builtin-skills`, baseline `977083471cb2ba7c37195bceba16133d06f361ad`; code remains uncommitted in the isolated Issue worktree.
- Four packaged skill contracts are registered: usage_navigation, resources_updates, document_research and feedback. Current guide sections, canonical source/catalog data and published weekly snapshots are used; resource lookup now supplies Host-verified provenance for a later document body read. Feedback remains an editable draft until the existing form is explicitly submitted.
- Task-isolated PostgreSQL focused suite: 344 passed, 4 warnings. Black, isort, Ruff and whitespace checks passed. One end-to-end isolated feedback case checked API receipt, local pull deduplication, reviewed status and exact text/ID/source/origin. Evidence: `reports/issue-473-480-20261107/issue-478/worker-implementation.md`.
- No live model, browser smoke, production data/config, commit, push or PR was attempted by the worker. Fresh independent review is next; manager owns publication and CI gates.

## 2026-11-08 R11 候选修复完成本地验证，等待独立评审

- Issue #477 仍在 Draft PR #484：`codex/issue-477-document-research`。本轮候选源码增加单一当前 Ready Key Findings 片段的受限中文摘要路径，并保留原有第四次摘要核验、引文校验、权限复查与预算；同时修复静态符号门禁发现的序列化引用。
- 相关隔离 PostgreSQL 测试 332 通过、4 条警告；Black/isort/Ruff、Python 与 TypeScript dead-code symbols、`git diff --check` 通过。证据见 `reports/issue-473-480-20261107/issue-477/guarded-experiment/`。
- 候选仍未独立评审，未在新源码上运行 Provider/UAT。原海外站结果继续记为失败，不能用本地脚本化测试代替。远端 CI 尚未针对此候选源码出结果。
- 本轮未改生产配置、索引或权限，也未触碰 `graphify-out/` 或兄弟仓库。下一步是固定完整源码快照，进行独立评审，再按原问题每站最多一次做新源码 UAT。

## 2026-11-07 R9 两项 AC 缺口已裁定并交同一 worker

- R9 独立审查报告 5bc3d931...d48b 已经 root 审计为合格；TypeSafe Review 两项 preliminary valid（mapping .95/.93、repro .85/.82），Jev Judge 选 accept_both（p .63，confidence .54）。经理独立复现后 append-recorded 两项：AC5 target-specific Ready 未确认；AC8 目标从 KB 移除后，旧目录 evidence ID 仍可生成链接。第二条也在 find/read 两个普通 tool call 之间撤销 membership 后复现，不依赖并发删除。
- 生命周期当前 fixing，R9 / 9 failed cycles；两项已交回同一持久 worker。修复要求分别覆盖目标 Ready URL、成员撤销后的 not_found 以及失败回退释放目录证据；保持 AC6 对仍授权目录条目的来源链接行为。
- R9 当前源码 patch SHA-256 6ee478c84aab6d760b166b9a0ae9d6eb633fe926ae5c6c3e6d7359186601a2b1；修后会重冻完整 current-source 包。R10 唯一 fresh reviewer 由 root 派发，本经理只准备包和请求；不得自行创建或复用被中断的 collab reviewer。
- 未运行 live provider、生产索引、部署或远程操作；没有 commit、push、PR。hermes 和 graphify-out 不属于产品 patch。

## 2026-11-07 R9 独立源码评审已正式开始

- 当前评审为唯一 native reviewer 01a1b8ca-c399-78e3-9aa0-ea629dea48d2（local），probe 与实质 turn 均为 gpt-6-sol/high；实质 turn 01a1b8cd-0d05-7d22-b8b4-8ecc024bcf03 已开始。第 9 轮 official lifecycle 已 start-review，计数仍 8/8，尚未消费报告。
- 已只派发 R9 中立 brief、完整 13 路径 manifest/patch、当前 244 passed 与 style 原始日志，以及 Issue worktree 当前源与调用方/测试；报告唯一目标 r9/reviewer-round-9.md。最终独立性审计回执仍 pending，完成前不读取报告正文、不finish、不派修复。
- 派发收据和实际路线记录位于 reports/issue-473-480-20261107/issue-477/r9/controller-dispatch-receipt.json 与 manager-round9-route-observation.json。先前已中断的 collab 尝试单独保留，不计 review 轮次。

## 2026-11-07 R9 快照冻结，等待控制器派发独立评审

- R8 两项修复已由经理核实并正式记为 worker fix：旧 Bulletin 明确纠正排序、Ready soft-stale 状态回答；244 项相关隔离 PG 测试通过，4 条警告，Black/isort/Ruff/临时索引 diff 检查全过。
- 当前 R9 完整 13 路径快照已从 HEAD 重建并独立反向重放，全部源码哈希与补丁一致；patch SHA-256 6ee478c84aab6d760b166b9a0ae9d6eb633fe926ae5c6c3e6d7359186601a2b1。当前 lifecycle awaiting_review，已完成 8/8，未启动第 9 轮。
- 唯一有效 R9 派发须由控制器按既有门执行。一个误启动的子代理在开始读源前即被停止；偏离记录在 reports/issue-473-480-20261107/issue-477/r9/review-dispatch-request.json。没有生成评审报告或完成评审。
- 无生产/远程操作、提交或 PR；.hermes 与 graphify-out 排除产品补丁。

## 2026-11-07 R8 两项修复已交回同一 worker

- Issue #477 当前 worktree codex/issue-477-document-research。R8 已正式记录为第 8 轮 changes，累计 8/8；TypeSafe Review 两项均 preliminary valid（mapping .92、repro .89/.88），TypeSafe Judge 选 accept_both（p .71，confidence .64），经理独立复现并接受两项窄修复。
- 修复项：显式纠正为旧 SOA Bulletin 时必须将该报告排在新 Survey 前；显式问 Ready/过期状态时保留并回答 usable Ready 与 soft-stale 元数据。已交同一持久 worker，在本地 worktree 加回归测试；待最终 handoff 与验证，未动远程/生产，未提交或建 PR。
- 当前产品基线仍是 R8 冻结 HEAD df2fea2acdd9a61c7ccc58ef2f0b590bc5f08851；历史 R8 的 241 tests 与 style 检查通过不代表本轮修复验证。hermes 和 graphify-out 排除产品 patch。
### 2026-11-08 Issue #477 — R7 follow-up read-error repair ready for fresh Review 8

- Fresh R7 review found a reproducible AC6/AC7 gap: a validated follow-up target lost its report title and source link when body reading raised. TypeSafe Judge chose a narrow same-worker repair (0.79 probability; confidence 0.68), independently confirmed against current source and the isolated reproduction.
- The same worker now rechecks current identity, `chat.query` / `markdown.read`, permitted KB membership, and non-deleted file state before returning the current title and source URL. A five-case regression covers a valid target plus membership removal, deletion, permission revocation, and identity change.
- Final isolated PostgreSQL focused suite: 241 passed, 4 warnings. Black, isort, Ruff, and the temporary-index whitespace check across all 13 product paths passed. Handoff and raw logs are under `reports/issue-473-480-20261107/issue-477/r7/`; a fresh full-patch Review 8 is next.
- No live provider or production index was tested. No commit, push, PR, or merge was performed.

### 2026-11-08 Issue #477 — R6 Standard section repair (included in R7 review)

- The Standard findings fallback now requires a real Markdown heading boundary, returns only that section slice, and applies the same predicate before the five-result candidate cap. The optional retriever filter is used only by document research; ordinary RAG calls keep their default path.
- The scoped repair adds mixed-section, false-mention, and rank-six regressions. Worker handoff and evidence are under `reports/issue-473-480-20261107/issue-477/r6/`; the frozen 13-path source snapshot and neutral Review 7 brief are under `r7/`.
- Worker-reported isolated PostgreSQL focused suite: 236 passed, 4 existing warnings. Black, isort, Ruff, and temporary-index whitespace checks passed. Review 7 later completed with one AC6/AC7 finding; that follow-up error path was fixed by the same worker in the R7 update; no production index, live provider, commit, push, PR, or merge was performed.
- Standard chunks without a verifiable Markdown heading remain unavailable for Key Findings evidence. Production index coverage and real vector ranking were not checked.

### 2026-11-07 Issue #477 — R5 repair ready for fresh review

- R5 Judge disposition is resolved. The current 12-path patch addresses scoped catalog candidate selection/relevance before its cap and findings routing within the existing independent-verification budget. The optional scoped Storage filter preserves the general assistant's unscoped query behavior; readiness remains available for explicit status questions.
- Final isolated PostgreSQL focused suite: 213 passed, 4 warnings. Black, isort, Ruff, and the temporary-index 12-path whitespace check passed. R6 patch SHA-256: `cda9f9c59f144929953aa40cd0d4634c96e2a5e90eb37ca96996a061ebd22e4a`; source manifest and raw logs are under `reports/issue-473-480-20261107/issue-477/r6/` and `worker-logs/`.
- Same-KB regression covers an older exact target against 50 newer but less-relevant current members; cross-KB regression covers 50 newer non-member matches. No live model or production check, commit, push, PR, merge, or cleanup was performed. Fresh native Review 6 is active on the frozen 12-path source manifest; no source changes were made after dispatch.
- The model may still spend a call on a redundant readiness step; the fixed budget then fails closed with `SUMMARY_UNVERIFIED`. No limit or validation was weakened.
## 2026-11-07 PR #481 — supplemental late inline threads

- On supplied HEAD `fd8f935709e25beb657708a90db18183685c6bd8`, the 07:22:09Z visual-viewport keyboard comment reproduced: the fixed trigger remained below the shortened visual viewport while the panel lift was 0px. This maps to AC6. `SupportWidget` now measures lift from `triggerBounds.top - gap` to the constrained panel bottom; a focused visualViewport regression covers the geometry.
- The 07:22:10Z failed-follow-up alert comment also reproduced: after a long answer, a rejected next request placed the alert inside the history scroller while the composer remained visible. This is not directly required by AC2, AC3, or AC6, which cover successful answer placement/feedback cancellation, preserving older-history reading, and the freeform/mobile UI. No product change was made for it; the temporary reproducer and scope rationale are preserved in `reports/issue-473-480-20261107/issue-474/remote-ci/supplemental-late-thread-assessment-fd8f935.json`.
- Focused assistant regression: 24 passed. Changed-file ESLint: zero errors; two existing React Hook dependency warnings. No Git/GitHub operation was performed; physical iOS keyboard behavior remains untested.

## 2026-11-07 Issue #474 — PR #481 status update

- Branch `codex/issue-474-mobile-assistant`, PR #481, baseline `33198dd87b413bdec5d9a60a4a60f9e857bd831b`. The assistant uses one freeform question input with automatic routing; mobile panel geometry and delayed-answer visibility are fixed while the independent older-history reading path is preserved.
- Six completed local review rounds are retained; Review 6 and its TypeSafe assessment passed with no findings. The Review 5 Judge outcome remains unresolved and is not recorded as PASS. The accepted in-scope work continued under the controller's recorded decision.
- Focused validation: AssistantPanel 23/23; PostgreSQL routing 48/48; feature matrix 11/11; typecheck, build, changed-file ESLint (0 errors, 4 existing warnings), Python style checks, and `git diff --check` passed. Current-source mocked Chromium covered both routes, eight viewport cases, feature flags, resize/composer growth, feedback cancellation, preserved older reading, and bilingual clarification.
- GitHub run 844 passed its 3,559-test suite (1 skipped) but failed only the final Black gate for a newly changed long tuple in `tests/test_assistant_routing.py`. The format-only correction in `f842b90` passed Black and 47 routing tests; the PostgreSQL-only case was deselected because no endpoint was configured. GitHub run 845 then passed all six jobs on `f842b90`.
- PR #481 is Ready. GitHub did not register the single Copilot review request; the request list was empty, so Copilot is recorded unavailable with no retry. The one feedback snapshot on `f842b90` contained zero comments, reviews, and review threads; the worker's clean assessment report is pending.
- This status-only refresh will create a new PR head and require a new current-head CI run before merge. Live-provider/API checks on this branch and physical iOS/soft-keyboard validation were not run. No production deployment or configuration write occurred.

## 2026-11-07 Issue #474 — local review passed

- Branch: `codex/issue-474-mobile-assistant`, baseline/head `33198dd87b413bdec5d9a60a4a60f9e857bd831b`. The assistant now uses one freeform question input with automatic routing; clarification asks users to add detail or rephrase in English and Chinese while legacy backend mode handling remains intact. The panel shares available host geometry with the Chat footer, and assistant history scrolls independently from its composer.
- Delayed reply after manual feedback cancellation is revealed once inside the history pane. The separate case where a user keeps reading older history without opening feedback retains its scroll position. Current-source mocked browser coverage includes `/` and `/chat`, short viewports, all feature-flag combinations, composer growth/resize, these two scroll paths, and bilingual clarification.
- Focused checks passed: AssistantPanel 23/23; Issue PostgreSQL routing 48/48 and feature matrix 11/11; typecheck; changed-file ESLint (0 errors, 4 existing warnings); build; Python style checks; `git diff --check`. A fresh native gpt-6-sol/high review and its TypeSafe assessment are recorded. A controller-authorized handoff preserved the selected worker tier and all review history; the R5 Judge result remains unresolved, not a PASS.
- Current-head GitHub CI and current-branch live-provider/API checks have not run; physical iOS/soft-keyboard validation was not run. No production deployment/config write occurred. Source changes remain uncommitted; the Draft PR/current-head CI and remote-feedback gates are next.

## 2026-11-06 CIA news — final reviewed recovery/exclusion fixes

- Current source passed fresh independent Sol/high review 4, zero findings. Controlled four-module suite: 287 passed; frozen-runtime-v2 QA: 227 passed. Black/Ruff/whitespace checks passed. Source-byte hashes were checked before publication.
- Exact CIA news HTML now checks source exclusions at the final redirected URL before capture. Matching legacy pending replay rows use the page route while preserving processed history/cursor and retry evidence; other exact document routes remain unchanged. Source-portal fixture accounts for the new feed and resolves the sole initial CI test failure.
- Existing source/import acceptance is retained: one visible article on each native target, both Ready; two different HTML originals have identical extracted text and remain preserved in Hub. AI-first monitoring remains a proposal. Controller owns the new frozen-runtime activation and final current-HEAD CI readback; no merge authorized.

## 2026-11-06 CIA news — current remote-feedback code checkpoint

- Current scope is final-destination source exclusions for operator-selected CIA news HTML and pending legacy exact-replay route upgrade, with existing prefix/cursor/retry history preserved. Source-portal test fixtures account for the added news-feed request.
- Controlled runtime/target-worker/source-portal-daily/source-portals suite: 287 passed, 3 warnings. Black/Ruff/whitespace checks passed. Current code awaits fresh independent review and controller-owned frozen-runtime follow-up acceptance; no new live operation was performed for this code revision.

## 2026-11-06 CIA news collection — reviewed code checkpoint

- `fix/cia-news-discovery`: fresh independent Sol/high review 3 PASS, zero findings; actual code/test fingerprints checked. Controlled product suite 264 passed; narrow frozen runtime suite 204 passed. Black/Ruff/whitespace checks passed.
- A real four-request discovery preview reached the supplied CIA news article with its genuine headline and 7581-character body. Production runtime state was unchanged. Frozen local candidate `52db7a9` contains only this reviewed source fix over the existing collector baseline; live exact-article import and native automation pointer acceptance are controller-owned follow-up evidence.
- Broad collection/categorization, the 32-monitor rotation and 30-request cap remain. AI focus is a proposal only. No merge authorization; unrelated root-checkout changes and sibling boundaries remain preserved.

### Issue #464 manager current repair-source verification — 2026-11-06

- Restarted the current task-worktree API on loopback with the task-owned PostgreSQL 16 fixture. Current-source real-provider checks passed for the seven-case identity/scope matrix and a CAS catalog query: authorized operator/admin each received the configured staff-KB citation, unauthorized and forged-scope cases had zero answer-generation attempts, and the catalog query returned a catalog citation. Three actual answer-generation attempts were recorded; raw answers, questions, auth tokens and personal identifiers were discarded. The API was stopped after the probes; PostgreSQL remains isolated on loopback without a persistent volume for review tests.
- Current-source source/version metadata is in `reports/issue-464/runtime-evidence-current-source.json`. The original full browser, feedback→PostgreSQL/#461 and four-switch acceptance remains PASS on implementation SHA `bc1fdab`; those flows were not rerun after the backend repair because their client and persistence paths were unchanged. The receipt records those phases separately.
- Controller C4 probe confirms Standard RAG requests k=5 then k=6 and returns the current rank-six member; the durable regression exercises the actual FAISS→RAGRetriever→body_evidence path. Final focused C4 suite: 104 passed, 3 warnings; static checks passed. Fresh independent gpt-6-sol/high review PASS with no actionable AC-mapped findings. The repair and evidence bundle are ready for commit and push; current-head CI will run after publication.

### Issue #464 C4 Standard membership completion — 2026-11-06

- The earlier C4 repair filtered Ready Data only; Standard retrieval still truncated to five vectors before current-membership filtering. This completes the same accepted remote finding and does not add a review cycle.
- Assistant now passes current file membership through the existing optional Standard retrieval scope. The same loaded vector store progressively expands its ranked search until the valid-member budget is filled or the index is exhausted, filters before final truncation, and reuses one query embedding and the pinned served-index metadata. Default unscoped Chat calls retain their existing path.
- Two real FAISS→RAGRetriever.retrieve→body_evidence regressions failed before repair: five removed nearest vectors hid current rank6; with six current vectors the budget was also empty. Both now return only current members, cap at five, preserve served-c4 version, and generate one query embedding. Knowledge/RAG/Chat PostgreSQL regression passed104; Black/isort/Ruff/Pylint errors-only, Python symbol and diff checks passed. Historical real-provider evidence is unchanged; current-source real acceptance and fresh review remain pending. No commit/push or service operation.

### Issue #464 PR #470 scoped runtime and provenance repairs — 2026-11-06

- Backend settings validate the effective feedback site key before persistence/activation. Catalog publisher requests ignore grammatical `from`. Standard retriever initialization failures are isolated per KB. Ready Data filters current file membership before its result budget. Standard stores pin matching ready index/version/date/stale metadata at load and return it with their cached chunks, so citations cannot acquire a later index's version.
- Seven pre-fix regression variants failed as expected. Affected assistant/feature/source-registry/Ready/RAG/Chat run passed191; final knowledge/feature/RAG/backend-settings regression passed60. Black/isort/Ruff/Pylint errors-only, Python symbol and diff checks passed. No frontend source changed.
- Added minimal durable sanitized `reports/issue-464/runtime-evidence.json` and `local-validation.json`: historical identity/call/citation/prompt-source observations and matched one-way PostgreSQL/CLI receipt/request/content hashes. No answers, URLs, raw suggestions, IP/user identities, credentials, full prompts/logs or review/Judge reports are included. Historical runtime provenance is archived PR head5a101347 over implementationbc1fdab; it is not post-repair proof. Current-source real acceptance and fresh independent review remain pending in acceptance.json.
- No commit/push or running service operation by the worker. The manager restored only the task-owned isolated PostgreSQL16 fixture endpoint for tests; its ownership inventory remains outside the PR evidence. The two new ignored JSON artifacts require explicit force-add when the manager stages the final evidence.

### Issue #464 manager live acceptance and local review completion — 2026-11-06

- Restarted the loopback acceptance API against the final R6 worktree source (`ai_actuarial/assistant/knowledge.py` SHA-256 `d48e176fdd90777df6c7aa6b849719f17094d6247f458ecbbd00cc3f2a3b9a52`) and the Issue-owned PostgreSQL 16 database. No public sites or scheduled tasks were enabled; the shared Chat provider/configuration path remained unchanged.
- Chrome `/chat` used the real `gpt-5.4-mini` provider to classify an English suggestion and open the exact original sentence in the editable feedback form. After the user-confirm step, the UI receipt, PostgreSQL row, and #461 local inbox all matched (`81974bf9-dc11-4acd-af76-ac02971136cb`); one generation, zero embedding attempts, three total feedback rows and three unique request IDs.
- The initial request displayed the actual shared daily-quota error. For a separate retry phase, only the synthetic Issue #464 IP/date ledger row was reset 9→0; the normal provider then consumed one quota unit. Product quota limits and provider settings were not changed. Prior quota-error evidence remains intact.
- Off/off UI acceptance was repeated on the final source: an already-open page's feedback and assistant requests returned 404, wrote no feedback row, and generated no model call. After refresh, the Help and feedback entry was absent. The route observer recorded only capability reads after refresh and zero assistant/help/feedback business requests. The local #461 inbox remained readable while intake was disabled. Both flags were restored to true.
- A separate earlier Chrome run already demonstrated quota error followed by manual suggestion submission; receipt `83620296-199f-4563-9fa6-55e40d3ad6c8` and its exact text remain in the local inbox. The two routes and replay steps are separated in `reports/issue-464/browser-smoke.json`.
- A fresh replay of the final 13-module backend/API/RAG selection passed 364 tests (4 warnings; exit 0) on implementation SHA `bc1fdab375b7db748a9c6a8f5df406be021cc3b8`; its exact command, isolated PostgreSQL environment, and log are in `reports/issue-459-464-20261105/issue-464/controller-recorded-backend-proof.json` and `controller-recorded-backend.log`. The earlier manager run remains archived separately, but its literal shell command was not retained. Frontend Vitest 26, typecheck, build and accessibility 96 apply to the unchanged client blobs. The earlier whole-repository dead-code check is historical-only; final R6 Python file/symbol gates and static checks are in `reports/issue-459-464-20261105/issue-464/worker-report.json`. Fresh Sol/high local review 7 passed; the TypeSafe assessment is recorded. No source change followed R6. GitHub checks, PR review and publication are still pending.
- Desktop and mobile browser evidence was captured on the reviewed `/chat` build: 1280×900 English and 390×844 Chinese, with the help panel open. The completed native CUA screenshot calls are `call_1dbb2c42c08a4920a2e25099db1a6448` (desktop) and `call_4021d1398a03465384680d4da75d5ab1` (mobile), retained inline in the task thread; no separate image attachment ID or file path was exposed. The canonical receipt contains the D1–D4, AC1–AC6 and R1–R7 evidence map and screenshot origins; receipt and status metadata will be committed with the branch. Task-owned API/Vite processes and the no-volume PostgreSQL container were stopped after capture; ports 8000, 4173 and 55464 were verified free. No production settings, credentials, external sites, or sibling repositories were used.

### Issue #464 accepted R6-1 matching body excerpt repair — 2026-11-06

- Real search/query red regressions reproduced exact-tail rejection for an ordinary second-paragraph answer after240 characters and the same answer after more than10000 characters in a much longer chapter. Default search preview excluded both answers.
- Added an opt-in matched-excerpt argument to existing `search_sections`; it uses the full matching section already loaded from the exact manifest.output_dir, selecting a maximum1600-character exact substring around the best-covered query match. Default240-character previews and formula/table/context snippet callers are unchanged. Assistant passes its existing filtered bilingual query terms; membership, publication/version/stale metadata, source cap and call budgets remain unchanged.
- The actual serialized prompt now includes the exact answer, preserves same serving file/section/publication/stale (a conflicting non-serving publication is present in the fixture), and passes existing exact-quote validation with generation1/embedding0. Focused isolated-PG assistant/routing/API/RAG/permission plus Ready helper regressions passed138; Black/isort/Ruff/Pylint errors-only, Python symbol and diff checks passed. Red/green logs and current fingerprints are in the external worker report. No running API/Vite/PG process, provider, publication or commit action; fresh independent review and API restart remain manager-owned.

### Issue #464 accepted R5-F1 / R5-F2 repairs — 2026-11-06

- R5-F1: real isolated-PG red evidence showed the three ordinary listing requests left `me`, `please` or `we` as subjects. Added those request words plus adjacent grammatical `could`/`would` to the existing query-only stopwords. Equivalent listings now agree; mortality-positive and climate/US-negative cases verify meaningful filters remain.
- R5-F2: red evidence used real Ready Data JSONL scoring (staff keyword score7) plus Standard generic similarity0.75; mixed six-KB selection dropped the only direct staff excerpt. Removed the incompatible numeric score comparison and unused internal score field. All candidates now use the same question-to-excerpt token coverage based on existing bilingual tokenization/function-word handling. Equal coverage preserves native per-KB result order; fair rotation, permission checks, five-source cap, generation/embedding budgets and citation contracts are unchanged.
- The upgraded operator regression uses real Ready search for both homogeneous and mixed paths, covers two and six KBs, checks actual serialized prompt support and staff file/section citation, and proves equal-coverage per-KB rank stability using reversed chunk identities. Pre-fix run had3 expected failures /4 passing homogeneous cases. Final focused knowledge/routing/API/help/RAG/permission tests passed158; explicit final prompt/citation variants passed6. Black/isort/Ruff/Pylint errors-only, Python symbols and diff checks passed. Running acceptance services were untouched; API restart and fresh independent review remain manager-owned.

### Issue #464 accepted R4-F1 list-all repair — 2026-11-06

- Reproduced the normal `List all documents` catalog miss on the same isolated PostgreSQL row returned by `List documents` and `What materials are available?`.
- Added only `all` to the existing catalog subject stopwords. The shared catalog regression now verifies all three listing phrasings return the same file; SQL projection, permissions and model budgets are unchanged.
- Knowledge/routing/API/help focused tests passed 118 after the expected red failure. Black/isort/Ruff/Pylint errors-only, Python symbol gate and diff check passed. Evidence and refreshed fingerprints are in the external worker report. The running manager-owned acceptance API/frontend were untouched and need API restart to load the new source; fresh independent review remains required. No commit or provider/browser operation.

### Issue #464 accepted R3-F1 publisher projection repair — 2026-11-06

- Reproduced two real isolated-PostgreSQL failures: a CAS-host file collected as `local_docling`, and a CDN file explicitly corrected to CAS, were missing from CAS catalog queries. The adapter also used the raw collection label as organization.
- Catalog SQL now uses the existing `source_sql()` current-registry resolver for its canonical publisher join, matches canonical key and English/Chinese names, and projects those localized names. Assistant context uses the requested locale's publisher name. No Markdown search or unrelated source-resolution code changed.
- New regression compares catalog results/context with actual `get_file_with_catalog` source projection for both ordinary hostname resolution and reviewed exact override. Both failed before repair. Source registry plus assistant knowledge/routing/API focused tests passed 138; Black/isort/Ruff/Pylint errors-only, Python symbol gate and diff check passed. External worker report preserves red/green evidence and refreshed fingerprints. No commit/provider/browser/API service action; new independent review remains required.

### Issue #464 F1 completion for more than five KBs — 2026-11-06

- The initial interleave still let six KBs compete in configuration order. There is no enforced five-KB configuration limit. This completes the same accepted F1 and does not represent another review cycle.
- Evidence now carries the existing retrieval relevance (Ready Data keyword percentage; Standard RAG similarity normalized by the existing helper). Candidates and KB turns are ordered by relevance, with deterministic source identity for ties, before the fair round selection and unchanged five-source cap. Permission filters and generation limits are unchanged.
- Operator actual-query/prompt regressions now cover public5 generic + staff1 and six KBs (five public generic singleton results followed by the only supporting high-relevance staff result), each on Ready Data and Standard fallback. Four variants failed before this completion; all pass after it. Focused knowledge/routing/API/RAG/permission run passed 116; latest four regression variants passed again after using an above-threshold generic Standard score. Black/isort/Ruff/Pylint errors-only, Python symbols and diff checks passed. Real provider/browser acceptance remains manager-owned.

### Issue #464 review round 1 accepted F1 repair — 2026-11-06

- Reproduced the accepted public-first truncation defect for both usable Ready Data and Standard RAG fallback: five generic public matches excluded the operator's sole supporting staff excerpt from the prompt. Both new regression variants failed before the repair.
- The same worker now interleaves each permitted KB's existing ranked evidence before applying the unchanged five-source prompt budget. Scope checks and strict client KB-field rejection are unchanged. The operator regression verifies the staff excerpt is in the actual prompt and the answer cites that staff source.
- Post-fix focused knowledge/routing/API/retrieval/permission tests passed 114; Black/isort/Ruff/Pylint errors-only, Python symbol gate and diff check passed. Red/green logs and refreshed working-byte fingerprints are in the external worker report. No provider/browser/API service was started; fresh review and real acceptance remain manager-owned.

## 2026-11-06 Issue #464 local implementation awaiting real acceptance

- Branch `codex/issue-464-assistant-knowledge`, baseline `f40da1a065c314db6b2239d52e82525ca04949cc`: added fixed public catalog-only evidence and allowlisted KB body evidence. Public/staff lists default empty; staff additionally requires authenticated `assistant.internal` (operator/admin). Explicit empty KB scope and directory permission failures precede quota/retrieval/model work; client KB IDs remain forbidden.
- Current usable Ready Data publication (including soft stale) is searched first; unavailable/hard-stale data can use the same permitted KB's Standard RAG, filtered to current membership. Answers use exact evidence excerpts and typed help/catalog/kb citations with internal file/guide links and available source version/date/stale state. Stage generation and provider embedding attempts remain separate and deadline bounded; no Chat rows or unconfirmed feedback writes.
- Added catalog question mode and bilingual labels/guides; preserved the original 18-question fixture. Backend settings now apply the two independent switches immediately. Lazy existing API exports fix independent assistant import order without assembling API routers during business imports.
- Local validation: required backend/Chat/RAG/help run passed 220 tests before final AC5 follow-ups; focused post-follow-up import-order/feature/RAG run passed 27; expanded catalog/embedding/backend-settings regressions passed 19. Frontend assistant/feedback 26, typecheck/build, a11y 96 and full dead-code gates passed. A final broader backend rerun is recorded in the external worker report. Three baseline a11y fixtures were narrowly corrected (missing capabilities mock/localization context); initial failures are retained.
- All source changes remain uncommitted for manager review. Real provider, real restricted-KB identity matrix, browser and feedback-to-#461 inbox acceptance are manager-owned and not claimed here. No server, schedule, credential, production setting or sibling repository was changed. Evidence/report: `reports/issue-459-464-20261105/issue-464/worker-report.json` outside this disposable worktree.

## 2026-11-06 Issue #463 assistant and feedback — remote review fixes

- Implemented single-turn intent/clarification, cited guide-backed usage, explicit feedback confirmation, and shared Chat identity/quota under `codex/issue-463-single-turn-assistant`. The original feedback lazy-load retry defect and two accepted PR #469 remote findings were fixed by the same worker. Source fix commit `9b54b95b409e7604f51d0a1516a4a978e2b11a62` follows the original implementation commit.
- V1–V4 isolated acceptance passed on the original source commit and remains recorded in `reports/issue-463/acceptance.json`. On the final source, the real OpenAI `gpt-5.4-mini` provider returned both the English “How about adding a feedback button?” and Chinese feedback-help suggestion as exact editable drafts. Each used one generation call and zero embeddings; isolated feedback rows remained unchanged. The isolated quota row was reset for this validation phase only; the original 5/5 evidence is preserved.
- Chrome desktop and 390×844 checks passed in both languages; mobile document width stayed 390px. The existing Chat UI showed its normal retryable retrieval error because the isolated database has no indexed knowledge base; the separate direct-content Chat API test succeeded.
- The original online `openai:llm:instance:default` binding remains unverified locally. The isolated provider profile used the repository-supported env binding and existing `.env` credential in server memory only; no key was created or persisted, no production database or schedule was used, and no sibling repository was touched.
- Final focused assistant/API regressions passed 54 tests; an earlier complete assistant/API/Chat run passed 107 before the final one-guard refinement. Black, isort, Ruff, Pylint errors-only, Python symbol gate, and diff checks passed. PR #469 has a single official remote-feedback snapshot; fresh local review, current-head CI, review-thread resolution, merge, and cleanup remain pending.

## 2026-11-06 Issue #462 help loader and guides — local implementation

- Branch `codex/issue-462-help-docs`: added allowlisted English/Chinese user guides (`docs/help/user-guide.en.md`, `docs/help/user-guide.zh.md`) with seven shipped-behavior sections each, stable IDs, language/title/source-version metadata, and section hashes generated in search references. Added deterministic file-reload search and same-version exact lookup under `ai_actuarial/assistant/`; only the two allowlisted guide files are read. Search matches section headings, rejects section IDs outside `[a-z0-9][a-z0-9-]{0,63}`, and is bounded to 10 results and 280-character snippets, with no model/vector/external crawl path.
- Added `/api/assistant/help` and `/api/assistant/help/section`, gated by the existing `assistant_enabled` setting (default false) and included that independent setting in support capabilities. Existing feedback behavior and `feedback_enabled` remain separate. The docs accurately say the #460 feedback widget is currently feedback-only and the assistant/KB question panel planned in #463/#464 is not shipped.
- Added the fixed 14 positive + 4 negative bilingual query fixture, parser/search and endpoint tests, and `docs/assistant-help-maintenance.md` with the allowlist/update rules and V1 UI/API version evidence checklist. Current evidence checked: root `package.json` version `1.0.0`; API `/api/health` build fields are `unknown` in this local environment. UI permission gates were checked in Layout, Database, Categories, FileDetail, Knowledge, and Chat; backend role permission sets were checked in `shared_auth.py` and read routes.
- Review R1/R2 follow-up preserves and indexes section headings (heading-only English/Chinese query regressions) and rejects overlong section IDs before they can be returned. The fixed 18-question fixture remains unchanged; returned search references continue to round-trip through exact lookup.
- Required focused suite `python -m pytest tests/test_assistant_help.py tests/test_fastapi_assistant_help_endpoints.py` passed 13 tests; the complete changed feedback endpoint module passed 36 tests against isolated PostgreSQL 16.15. Touched-file Black/isort/Ruff/compileall and `git diff --check` pass. Real HTTP V2 checked all 18 fixed questions (14/14 positive exact sections in top 3; 4/4 negatives empty), with no generation call, at most 3 candidates and 280-character snippets. Real full-app HTTP V3 verified exact lookup, changed-version hash and old-ref 410/no content, removed-section zero search/404, bad refs, duplicate IDs/bad metadata rejected by the loader, and disabled feature responses; temporary guide and config edits were restored with matching SHA-256. Fresh independent Sol/high review round 2 PASS and real Jev round 2 returned no findings (coverage 0.96). Source commit `a871e22236edb01f590a04e6d7f14c0db54af3ec` contains the implementation; `reports/issue-462/acceptance.json` binds all 14 V1 rows, 18 V2 cases and real V3 evidence to that SHA. Local acceptance only; production was not enabled or changed. PR #468 is Ready; aggregate CI rerun/current-head status and merge remain pending. Worker made no commit/push/PR action.
- PR #468 is Ready. Initial CI run #821 passed `dead-code-files` but failed `dead-code-symbols` because Vulture missed the two decorated assistant help routes. The scoped Python symbol gate passes after adding the two existing-convention whitelist references. The aggregate `npm run dead-code:symbols` could not run because local Knip is absent (`npm ci` would be required); no CI repair pass is claimed yet. Earlier V1/V2/V3 and reviewer PASS evidence above is unchanged.

### Issue #462 round-4 accepted AC1/AC2 fix — 2026-11-06

- Fresh Sol/high review round 4 required changes; the bounded all-section audit and separate Architect review were recorded. TypeSafe Judge selected `accept_ac1_copy_and_curated_20_token_fix` (0.83 probability, 0.74 confidence). The Architect also suggested two Database UI placeholder edits, but the user explicitly excluded them; no frontend placeholder or Database search behavior changed.
- Same worker corrected the four bilingual guide statements and added the 20 current-corpus function-word/contraction tokens to the existing query-only stopword set. The fixed 18-question fixture remains byte-for-byte unchanged. Pre-fix regressions showed 27 false matches; post-fix focused help/API suite passed 43 tests, and Black/isort/Ruff/Pylint errors-only/diff-check passed. Source commit: `982f9db02f071cd5a1bc039258169fbaba455827`.
- Manager real HTTP V2 rerun on that source commit used full `create_app` Uvicorn plus task-isolated PostgreSQL 16.15. All 26 query cases passed (15 positive, 11 negative); all four bilingual guide search/exact-reference checks passed; limits remained 3 candidates/280 characters; generation calls were 0 and OpenAI/TypeSafe keys were absent from the app process. Evidence: `reports/issue-459-464-20261105/issue-462/final-v2-http-r4-468.json`. Earlier V1/V2/V3 evidence remains preserved separately; no production deployment or enablement occurred.
- Round count is 4 completed local reviews, 3 formal local failed cycles, and 4 cumulative completed reviews requiring changes including the one Copilot review. A fresh Sol/high round 5, final pushed-HEAD CI, and current review-thread check are required before merge.


## 2026-11-05 Issue #461 local feedback inbox implementation

- PR #467 one-shot remote feedback repair on base HEAD `07d35a11e421368410ef01d02c4b4696c98e8a76`: all four manager-accepted Copilot comments are fixed within #461. Management Authorization is unredirected; malformed HTTPException responses become safe per-site connection failures; cached sync values/error shape are validated before use; sync/report persistence failures preserve prior last-success, return local_write and continue later sites even when failure evidence remains unwritable. No JSON envelope/schema/exit-code change or new dependency.
- Remote red/green: 20 new focused cases reproduced the findings on the original HEAD, then the final feedback suite passed 66 tests and feedback plus pipeline CLI passed 70. Actual loopback cross-origin redirects and malformed status/header responses are included. Black/isort/Pylint errors-only/Ruff, Python file/symbol gates and diff check pass. Current source/hash details and raw evidence are retained separately in `worker-remote-*`; earlier acceptance runs remain unchanged historical evidence. No PostgreSQL/V4 rerun, scheduled-task operation, Copilot request, commit or push by the worker; manager owns remaining review/current-head publication gates.
- Round 1 fixes: a real truncated Content-Length response now returns the safe connection failure, preserves prior site evidence and continues to the next site. Mark commits canonical JSON only after the readable report succeeds, restoring the exact prior report bytes/absence when canonical replacement fails. Default text list and Markdown explicitly label local cached state and show per-site outcome/error plus last-success/attempt times; pull refreshes the report after each site's sync evidence changes. JSON schema/envelope and exit codes are unchanged.
- Round 1 red/green: focused new regressions reproduced all three findings (3 failures / 1 passing companion case before repair); final feedback suite passed 46 tests and feedback plus existing pipeline CLI regression passed 50. Black/isort/Pylint errors-only/Ruff, Python file/symbol gates and diff check pass. An initial dead-symbol warning for a redundant HTTP test-handler attribute was removed without a whitelist. Detailed post-fix evidence is retained separately in `worker-round1-*` files; manager V1/V3/V4 evidence remains historical pre-fix acceptance and was not overwritten. Fresh independent review and repaired-source real acceptance remain manager gates; no commit/push/schedule operation by this worker.
- Branch `codex/issue-461-feedback-inbox`: added HTTP-only `feedback pull/list/mark`, complete local JSON and readable original-text Markdown under the resolved data root's `feedback/` directory, plus separate per-site last-success/failure evidence. Pull always scans `status=new` from cursor 0 and deduplicates by `(site_key, feedback_id)`; no durable watermark or server status mutation. Mark sends only status and caches the authoritative server response. Local list/history remains independent of public intake and remote credentials.
- Atomic page persistence, per-site failure isolation, safe static error categories and nonzero exit codes, JSON schema/contract fixtures, and one OS writer lock cover repeat scans, late lower-ID commits, connection outages, partial pages, write/report failures and overlapping manual/scheduled writers. The lock is limited to whole-file pull/mark writes; list remains lock-free. Separate `.invalid` example config and Windows setup/disable instructions leave the formal task uninstalled/disabled. No dependencies, API routes, frontend, production config or existing schedules changed.
- Worker verification: exact `python -m pytest tests/test_feedback_cli.py` passed 41 tests; the focused feedback plus existing pipeline CLI run passed 45 tests. Black, isort, Pylint errors-only, Ruff, Python dead-code file/symbol gates and `git diff --check` passed. Existing API/storage adjacency run was blocked by absent `POSTGRES_TEST_URL` (6 failed, 35 setup errors, 5 passed); all failure reasons were that designated PostgreSQL prerequisite. No database service was touched to bypass this blocker.
- Detailed worker report and raw logs are retained outside this worktree under `reports/issue-459-464-20261105/issue-461/`. Real isolated PostgreSQL/browser/Task Scheduler V1-V4 acceptance, canonical `reports/issue-461/acceptance.json`, independent review, commit/push/PR and merge remain manager-owned. This worker did not install/enable a task, access a production service, call a model, send messages, commit or push.

- PR #468 remote Copilot R1 was accepted against AC2 after manager/worker reproduction and a TypeSafe Judge decision. Commit `9c238dad2f4415149cebd4d7f09e452a3b1bb51e` filters a bounded English function-word set before help-search scoring and adds two unsupported-query regressions; the fixed 18-question fixture is unchanged. The pre-fix regressions failed, the post-fix focused suite passed 15 tests, and Black/isort/Ruff/diff-check passed. Evidence and historical V1/V2/V3 boundaries are recorded in `reports/issue-462/acceptance.json` and the Issue #462 external report folder. No production deployment or enablement occurred.
- Fresh Sol/high round 3 identified and the same worker corrected both user guides: Download remains visible but is enabled only when a local file exists and the account has download permission. TypeSafe Judge accepted the AC1 wording correction. The focused suite passed 15 tests, and a post-correction full-app HTTP V2 rerun passed all 20 questions (14 positive, 6 negative), with at most 3 candidates, 280-character snippets, and zero generation calls; both AI keys were absent from the service environment. See `reports/issue-462/acceptance.json` and the Issue #462 external evidence folder. Original V1/V2/V3 evidence remains separately bound; no production deployment or enablement occurred.
## 2026-11-06 Issue #461 repaired-source acceptance and review

- Manager repeated the real post-fix V4 chain with source bundle SHA-256 c95267a180c69405e4b8a5d8bcb55cbe7cc56ac5f7f50736082bc2274208813c and feedback/inbox.py SHA-256 40e0c8bafbf2327043deaa894fbbb6d77055d3a736c58715852cb8f2cdd61970. Browser receipt 13dd82d9-bea6-4d03-9c59-3c59b46623e2 and exact text matched isolated PostgreSQL feedback_items, scheduled CLI JSON, inbox.json, and inbox.md; Markdown included local-cache and per-site sync status.
- The one-shot temporary task ran at its registered trigger with result 0 and new_count=1, then remained disabled across the next due time. LastRunTime stayed at the first run and all five raw CLI/report hashes stayed unchanged. The reviewer matched all nine source fingerprints at review time. This status note was added afterward; the only now-different fingerprint is .hermes/project-status.md, and all source/test/config/doc hashes remain unchanged. The comparison diagnostic records an initial ISO-string precision mismatch; UTC ticks show the same instant.
- The temporary task, isolated PostgreSQL container, local API/Vite processes, test credential, and ports were cleaned up. Existing PostgreSQL containers remain running; Task Scheduler Operational logging was left disabled. No formal project schedule or production service was enabled.
- Independent round 2 code review and repaired-source V4 addendum both passed with no in-scope findings. TypeSafe assessment used jev-1.14.0, found no candidate findings, and reported review-summary coverage 0.93. One completed review cycle required changes; no Judge trigger was met.
- Initial V1/V3 and first V4 raw runs remain preserved as pre-fix evidence. V2 injected failures are simulated as authorized; the worker first PostgreSQL adjacency attempt lacked POSTGRES_TEST_URL and is retained alongside the manager isolated-PostgreSQL rerun (46 passed). Implementation commit cdcf17f60876e0b24e2f141d765b5fe6be4bcb10 was created; reports/issue-461/acceptance.json binds that SHA and records AC/D/V evidence. V3 distinguishes the initial credential failure from the retry with error.code=permission. Local acceptance and review are complete; push, PR, current-HEAD checks and merge are pending.

## 2026-11-05 Issue #459 local feedback backend delivery

- Review round 2 found no source behavior defect. It identified a stale SHA-256 fingerprint for the regenerated migration CLI evidence. The receipt checksum is corrected and all 23 evidence fingerprints match. This metadata-only change did not rerun product tests; current-head CI remains the final gate.

- PR #465 remote feedback repair against HEAD `4abad9831327cb43b662efb6a70d4568c840ef94`: added migration0007 to the existing schema-plan test expectation and corrected the downstream cursor contract. The ID cursor is only page continuation; #461 must use periodic scans from0 with feedback_id deduplication to recover late commits and reconcile status as needed. An isolated-PG regression reproduces lower-ID late commit and full-rescan recovery without changing pagination implementation. Exact migration test plus feedback endpoint/storage tests:43 PASS; touched Python Black/isort/Ruff and diff whitespace checks PASS. Combined fix is material because of its consumer-contract correction; fresh independent Sol/high review and current-HEAD CI remain manager gates. No commit, push or Copilot re-request by this worker; details in retained `worker-remote-fix-report.md`.

- Fresh independent review PASS for AC1-AC5; TypeSafe assessment had no candidate findings. The retained HTTP/PostgreSQL evidence was replayed against the current code after UTC timestamp serialization; response timestamps are +00:00. Current-head CI, PR publication and merge remain pending.

- Branch `codex/issue-459-feedback`: independent feedback business/store and migration 0007; anonymous/account submission, transactional UUID replay/conflict, admin-only keyset list/status updates, immutable submitted text, independent bounded limiter, default-off feedback/assistant configuration and truthful core capabilities. No assistant implementation, Chat change, UI, inbox polling, production or schedule operation.
- Fixed downstream contract: `docs/feedback-api.md` and `tests/fixtures/feedback_contract.json`. Shared site key comes from deployment config; intake-disabled POST returns stable `FEATURE_DISABLED` before CSRF/rate/body checks; historical management remains enabled.
- Isolated PostgreSQL 16.15 (`codex-issue-459-pg16`, loopback 51974, disposable database) validation: 41 focused tests PASS; 25 synthetic HTTP/PG evidence steps PASS; empty initialization, v6 upgrade preserving all preexisting table data, and repeat schema apply PASS. Native CLI help/JSON plan/apply/reapply evidence retained. Commit-failure proof uses a real deferred PostgreSQL constraint trigger, not a mock.
- Additional regression: 148 PASS / 1 skip / 4 FAIL in the combined worker invocation; four existing runtime-config bootstrap tests were denied Windows hard-link creation (`os.link`, WinError 5). Controller then ran the requested runtime-config test file separately in the authorized host environment: 18 PASS / 1 skip, exit 0 (`controller-runtime-result.json`; JUnit totals 19). Initial captured native FAISS import also failed; direct invocation with `FAISS_OPT_LEVEL=generic --capture=sys` ran the tests. No dependency or unrelated product change was made for these host limitations.
- Touched-file Black/isort/Pylint and existing Python dead-code file/symbol gates PASS. Full combined dead-code gate needs local Knip installation (`npm ci`); required CI and independent review remain manager gates. Framework whitelist additions reference only new feedback/capabilities routes and Pydantic hooks.
- Local receipt `reports/issue-459/acceptance.json` is ignored by Git and has not been force-added; retained copy, hashes, exact commands, detailed report and raw evidence are under root-checkout `reports/issue-459-464-20261105/issue-459/`. Receipt records tested base/source hashes and leaves implementation commit null until the manager commits; no circular SHA claim. This worker did not commit, push, publish or merge.

## 2026-11-06 PR #458 合并准备

- 用户已授权按检查结果直接合并 #458。分支 `fix/periodic-ai-materials` 正常合并最新 main `2e4cd2424ba511fec2fcf7d80eb52d70116be660`；唯一冲突为本状态文档，双方原始记录完整保留。
- 三个产品/测试文件与已通过 Sol/high 和 Copilot 审查的 `daf205d` 精确一致；相对 main 的代码补丁与原审查补丁逐字节一致。本次只处理合并和文档，不新增产品逻辑；等待新 HEAD 的全部必需 CI 后合并，不重请 Copilot。
- 先前已授权的采集端部署及三库历史修正保持原状；本轮不修改运行包、生产数据或排程。下方“未授权合并或部署”仅描述 11 月 5 日原始实现阶段。

## 2026-11-05 定期更新仅披露新发现的 AI 资料

- 项目 `AI_actuarial_inforsearch`，任务分支 `fix/periodic-ai-materials`，基于 `origin/main` 的 `b9bb05b`。本次范围为 `source_portal_daily.py`、`content_hub.py`、对应测试和本状态记录；兄弟仓库未读取。
- 日常摘要改为只列新增 AI 资料名称；AI 身份沿用 Hub 的首分类及来源主分类均为 AI 的规则，并精确匹配观察 URL / 原文 SHA，排除 excluded URLs。无新增时中英明确说明；通用目录前言、非 AI 项和抓取/页面变化统计不再拼入摘要。原始采集证据、SHA 验证、新增判定、重试幂等和部分读取说明保留。未修改旧目录独立采集路径或历史生产数据。
- 本地 76 项相关 Python 测试通过；原环境运行 60 通过 / 16 被现有 80% 容量门拦截。重跑只在测试进程使用既有 `ensure_capacity(disk_usage=(1000,500,500))` 接缝，生产阈值和保护未改。13 项摘要 selector、Black、Ruff、compileall、diff 空白检查通过。前端 build 和 5 项 SourcePortals 测试通过；8 组中英/390及1280/混合及空列表本地浏览器 smoke 通过，模拟 API、截图已查看。
- Luna/high 实现；新鲜 Sol/high 独立审查 PASS，0 项范围内 finding。按仓库规则 commit/push/创建 PR，并只在首次发布申请一次 Copilot，约15分钟后检查反馈和当前 HEAD CI。完整回执、PR 地址及远端结果归档于本地 `reports/periodic-ai-materials-20261105/`。未授权合并或部署，当前线上旧摘要未被改写。
- 原始 checkout 仍在 `fix/gpt6-parameter-compat`，既有状态文件修改与 `.codex-tmp-agentic-rag/`、`.hermes/research/`、`diagrams/`、`graphify-out/` 四个未跟踪目录保留。

## 2026-11-05 PR #452 main integration and acceptance state

- Integrated latest main `0d75dfec4da72db8887d277e881d6d77ba86c6ed`, including PR #457. The only merge conflict was this status file; both the Issue #450 history and weekly publication record were retained. The target worker auto-merged, PR #452 editor files remain unchanged from its prior HEAD, and weekly UI files match latest main.

- PR #452 remains open. Its title/body will reference #450 without an automatic-close keyword; Issue #450 remains open because full acceptance is incomplete. China current-site editor and the saved Chinese draft are accepted with warnings retained. Real local generation, bilingual readback, ACK recovery, zero-write idempotence, and schedule gates remain pending.

- This integration step did not generate articles, deploy, or change schedules. Current-head CI must run on the merged commit.
# Issue #450 本地文章解读 — 2026-11-02

### 2026-11-04 main merge and CI import-order repair

- The current branch merged `origin/main` at `3f44b0571f32cf8eaa942ea09904dbf1e7557d45` normally in merge commit `4ada89679ead6b6cb0845955753fc0cb7e397ce9`. The only conflict was this status document; both the Issue #450 history and incoming weekly-summary entry were retained. Application/API editor files did not conflict. The incoming weekly-summary UI changes remain included.
- CI's only reported failure on the prior head was isort ordering in `ai_actuarial/api/routers/article_interpretations.py`. The two import lines were sorted; commit `b4cf77b99e71a39638a4370ec7a72423471d76ec` contains only that two-line reorder and was pushed normally.
- Post-merge checks: the FileDetail editor and incoming weekly tests passed (40 tests across three files); `npm run typecheck`, `npm run build`, `git diff --check`, and router isort/Black/Ruff/compile checks passed. Build emitted the existing large-chunk advisory. No provider, database, API, target, DAV acceptance, sync, deployment, or schedule operation was run.
- The merge commit has not yet been pushed. The successor China-only release package and live acceptance runbook are being prepared offline from this merged HEAD; the earlier R30 frozen package remains unchanged and non-deployable. Root alone performs fresh live gates and any later target operation.

### 2026-11-04 Review30 PASS and controller handoff

- Fresh independent Sol/high review30 passed the exact current implementation; its independent proof is `reports/controller-editor-review30-independent-proof.json`. The separate Jev 1.14.0 coverage result is recorded in `reports/issue450-review30/typesafe-review30-coverage-result.json` (Noul 0.89; coverage evidence only, not a substitute for review or CI).
- Cumulative local reviews: 30 completed, including 21 CHANGES_REQUESTED cycles. TypeSafe completed calls: 29. Review29 used two successful Jev calls (assessment and `repair_both`); one separate HTTP 422 occurred before model execution and counts only as request validation failure.
- R29's two receipt-recovery fixes and their synthetic regressions are described below. The isolated PostgreSQL selectors, Black, Ruff, in-memory compile, and `git diff --check` passed. No model, generation, production DB/API, target, DAV acceptance, sync, deployment, or schedule action was performed by this worker.
- Root owns the normal commit/push, current-head CI, and release-package review. This work does not authorize merge, production stage/prepare/cutover/verify, DAV acceptance, deployment, schedule enablement, or sync; the primary controller alone may perform those later actions after all gates. The Issue and PR remain open.

### 2026-11-04 Review29 reserved-call recovery receipts

- Review29 reproduced two AC-5 recovery gaps. A manual `file_url` request could hit the content-call cap before finding/recovering a same-source running draft without a body, leaving a reserved call and origin receipt active. Recovery through `retry_id` or the current daily slot could also update only the passed origin/current receipts while a linked manual receipt stayed running.
- The shared recovery transition now finds an exact current-version running draft before manual budget return, marks its reserved call interrupted, and atomically updates every linked nonterminal execution receipt. Recovery keeps prior call/attempt charges, provider seconds, source identity, and cursor; exhausted manual execution records a terminal budget receipt without starting a new call. Terminal receipts are not rewritten.
- Red/green: the three new synthetic PostgreSQL regressions failed on the prior implementation (manual slot lacked the draft identity; retry and current-round recovery left the linked manual receipt running) and passed after the repair. The focused recovery/accounting selection passed 18 tests, including retry-by-identity, manual and scheduled recovery, receipt accounting, budget exhaustion, and cursor preservation.
- Validation: Black, Ruff, in-memory Python compilation, and `git diff --check` passed. Tests used only the approved isolated loopback PostgreSQL 16 database; test processes exited and the database service was left running for Root. No real model/provider, production DB, target, sync, DAV acceptance, deployment, or schedule action occurred. The frozen Revision6 frontend was not rebuilt.
- Review29 was CHANGES_REQUESTED and is repaired by the same worker. It received the subsequent Review30 PASS above; the R29 repair itself is not described as an R29 PASS. Root owns current-head CI, normal commit/push, China-only release review, and any later live acceptance. No commit or push by this worker.

### 2026-11-04 Review28 manual-origin reservation recovery in scheduled rounds

- Review28 reproduced a manual `file_url` interruption after reservation commit, followed by a scheduled round reusing the same running draft. Scheduled execution now recovers persisted reserved calls and their active origin/attempt receipts before candidate budgeting; `_generate` also applies the shared recovery before any budget early return. Recovery reloads the persisted draft before starting a new attempt. Scheduled calls now persist their own execution receipt, while the two-call execution cap remains specific to manual receipts and the six-call scheduled-round gate remains intact.
- Red/green: both new cases failed on the prior code. With one call remaining, the pre-fix scheduled receipt showed zero calls while the ready attempt retained `[reserved, valid]` and the manual receipt remained running. With the article cap exhausted, pre-fix scheduling made zero new calls but left the manual receipt/call reserved. Both pass after the fix: the first creates a distinct ready attempt and records only its new call in the scheduled receipt; the second makes zero calls and persists the old attempt/manual receipt as interrupted without changing the two-call budget.
- Validation on the isolated PostgreSQL 16 test service: full `tests/test_article_interpretations.py` — 235 passed, 2 skipped; `tests/test_article_interpretation_english.py` — 31 passed; six focused recovery/accounting selectors — 6 passed. Black, Ruff, Python compile, and `git diff --check` pass. The frozen Revision6 browser acceptance/build asset was not rebuilt because this repair only changes backend generation accounting/recovery.
- Root reported Revision6's independent browser increment passed against the matching frozen frontend source/build. This worker did not run a browser, model/provider, production DB, target, sync, deployment, or schedule operation. The approved DAV content is still not accepted in production; its failed receipt and spent budget remain unchanged.
- Review28 status: CHANGES_REQUESTED, repaired by the same worker. Cumulative local reviews: 28; changes-requested cycles: 20. TypeSafe cumulative calls: 26, including the accepted R28 recovery and budget-early-exit decisions. Fresh Sol/high review29 and current-HEAD CI remain required; no commit or push.

### 2026-11-04 R27 recovery and explicit content-warning acceptance

- Manual `run(file_url=...)` now uses the shared reserved-call recovery transition before retrying, preserving prior attempt/call charges and receipts. Regression coverage exercises normal round, `retry_id`, and manual `file_url` entry paths.
- Only `unsupported_number` and `unlabelled_inference` are content warnings; other structural, source identity, evidence, title, author, and formula checks remain hard failures. Warning-only output completes in one call and retains the fixed warning codes/diagnostics. A failed draft is offered only to `markdown.write` users as a metadata-only candidate; the user must provide title/body and explicitly acknowledge its warnings in the existing article editor. The CAS writer checks current source identity and body hash, records an audit, preserves failed calls/receipts and budgets, and marks old English stale. No generated text is exposed by the candidate response.
- Red/green and focused checks: `tests/test_article_interpretations.py` — 233 passed, 2 skipped on the isolated PostgreSQL 16 test service; `tests/test_article_interpretation_english.py` — 31 passed; `FileDetailForm.test.tsx` — 28 passed. `npm run typecheck`, `npm run build`, targeted ESLint, Black, Ruff, Python compile, and `git diff --check` pass. Build reports only the existing large-chunk advisory.
- No real provider/model, production DB, target, synchronization, deployment, or schedule operation was run. The current approved content is not yet manually accepted in production; its earlier receipt remains failed until the reviewed code is deployed and the operator saves it through the current-source editor. English translation and cross-target ACK/sync remain outside this phase.
- Current implementation is on `codex/issue-450-local-interpretation-review25` at `eabf41452d1e4c54e8ecf2c570780dd7428b7eee` plus uncommitted changes in the scoped implementation/test files and this status file. Cumulative local reviews: 27; changes-requested cycles: 19. TypeSafe cumulative calls: 24. This is not a new reviewer PASS; fresh Sol/high review and current-HEAD CI remain required. No commit or push.

### 2026-11-04 Review26 reserved-call retry repair

- Review26 reported that retry-by-identity could reuse a running attempt after a process interruption between the reservation commit and provider completion. The fix now marks committed reserved calls and their attempt as interrupted, persists that recovery with the origin receipt, then starts the retry as a new attempt. Existing call history, content budget, origin-round accounting, and cursor are preserved.
- Red/green: `test_retry_by_identity_recovers_committed_reservation_before_ready` failed before the fix because a ready draft still had one attempt containing the reserved call; it passes after the fix with the old call interrupted, a second ready attempt, two total calls, and matching origin receipt counters. The new regression plus six existing interruption, retry, and budget selectors passed (7 passed).
- Formatting/static checks: Black, Ruff, Python compilation, and `git diff --check` pass. Tests used only the approved isolated loopback PostgreSQL test service; no production DB, provider, generation, target, sync, deployment, schedule, commit, or push operation was performed.
- Review26 status: CHANGES_REQUESTED, repaired by the same worker. Cumulative local reviews: 26; changes-requested cycles: 18. TypeSafe cumulative count: 23, including the two current anonymized assessments (R25 scope support and R26 `accept_fix`). This is not a reviewer PASS; fresh Sol/high review, current-HEAD CI, and existing live acceptance gates remain.

### 2026-11-04 CI python-symbols registered-route whitelist

- GitHub Actions run `41905460187` on `dacdae5d1c804737752c6c5530f24460e1e20e40` reported one `python-symbols` baseline finding: the manual-body update handler was classified as unused. The function is a FastAPI-decorated route, its router is registered by the application, and the endpoint is exercised in `tests/test_article_interpretations.py` around line 3727.
- Added the handler to `config/dead_code_whitelist.py` using the existing framework-registered route convention and a reason comment. No application handler or runtime behavior changed. `npm run dead-code:symbols` passed: TypeScript 0 findings; Python 0 baseline findings.
- This only verifies the local symbol gate; the new current-HEAD GitHub run remains required. No isolated PostgreSQL, production endpoint, provider, generation, sync, deployment or schedule action was run.

### 2026-11-04 Review25 独立 PASS 与 Review24 页面验收

- 新鲜独立 Sol/high 代码审查对当前 eafd 基线的完整 12 文件差异判定 PASS；未发现符合范围的 P1/P2。审查报告 `reports/issue450-editor-review4-independent-review.md`，审阅快照 SHA-256 `90FC547339EF975109B61FF1159571A87BD50AB59B63C4DFE9E04D1B18EEC384`。
- 当前 FileDetail 页面回归 27/27、`npm run typecheck`、`npm run build`、两个改动文件 ESLint、`git diff --check` 均通过。独立真实本机 API/隔离 PG/CUA 浏览器验收 `reports/local-interpretation-migration-20261102/controller-editor-independent-browser-acceptance-revision4.json` 全部 PASS：来源变化后草稿可见/可复制，保存保留 409；保存中切语言后旧英文在 commit 后隐藏并回读新语言。只操作合成夹具，0生产连接、0模型、0双端同步。
- 用户明确认可并接受最后生成的 DAV 稿件正文。这是人工编辑接受意见；生成回执仍如实记录为 `failed`、`reader_eligible=false`，两次响应的校验码分别为 `unsupported_number` 和 `unlabelled_inference`。本机未创建 ready 稿、未写生产记录或同步目标，因此不能把用户的内容认可误报为系统校验或两端接收已完成。
- 累计本地 review 25、changes-requested cycles 17；TypeSafe 累计 21。PR #452 仍 open、尚未更新到本次改动。当前尚未提交/推送；仍须对新提交核验当前 HEAD 六项 CI及既有最小 China 网站发布门，再按授权继续。

### 2026-11-04 合并最新 main，复验待跑

- 远端 `main` 已前进到 `9611c8b523f2b697e86ed074689db98da6b3f274`。Issue #450 分支用普通 merge 合入；唯一冲突为 `.hermes/project-status.md`，已保留本 Issue 与 main 上首页来源报告/AICT 的两侧记录。源代码文件均自动合并，没有强推或改写历史。合并提交 `3e8a12218b99677fde2247f8e9c293e84eddf68e`。
- PR 相对最新 main 的当前差异 17 个文件；main 侧涉及 runtime、target worker、storage 和周报/门户更新，因此 eafd 上的 Review25 PASS 和 Revision4 浏览器报告不能单独替代合并后复核。需新鲜独立审查和该新 HEAD 六项 CI。
- Revision4 页面哈希中 FileDetail、i18n 与解释格式化代码保持一致；编译产物及实际运行路径仍按合并树重建/复核。部署候选只能基于现行中国站基线叠加本次必要编辑文件，不带最新 main 的 Dashboard、周报、采集和门户改动；尚未生成或部署该候选。
- 本地合并分支尚未推送，PR #452 的远端 HEAD 仍是 eafd；未写生产、未双端同步、未启用排程。

### 2026-11-04 Review24 编辑器生命周期修复

- 来源身份变化后，若当前解读读回为空，页面仍保留并显示原编辑会话的草稿与冲突提示；复制入口保持可用。保存仍使用打开编辑时保存的 interpretation/source/body CAS 基线，409 后保留草稿。草稿另存初始正文以正确启用有改动的冲突保存按钮。
- 中文保存成功后使旧解读和在途英文读取失效，并重新读取当前语言；旧英文响应不能重新显示。文章卡片仅在语言或来源切换时折叠，正文保存后的当前语言回读保持展开。
- 红绿：两个新增 Review24 selector 在旧行为下失败（空读回丢草稿、保存后未使在途英文读取失效），修复后通过。两条新增回归及编辑保存/保存中锁定选择器共 4 passed；完整 `FileDetailForm.test.tsx` 27 passed。`npm run typecheck`、`npm run build`、针对两个改动文件的 ESLint 与 `git diff --check` 通过；build 仅有既有大 chunk advisory。Prettier 未安装，本轮未新增格式依赖。
- 未启动隔离 PG、API/Vite 服务或模型；未访问生产端、同步、部署或更改排程。此前 Review3 浏览器验收报告保留不变；本轮没有新浏览器 smoke。
- 累计本地 review 24、changes-requested cycles 17；TypeSafe 累计 21，Review24 两项修复已获 formal Judge 判定。当前改动等待 fresh Sol/high reviewer，不记录新 PASS；未提交或推送。审阅补丁/报告位于主 checkout 的 `reports/issue450-editor-review4.patch` 与 `reports/issue450-editor-review4-report.md`。

### 2026-11-04 FileDetail CAS 与英文旧claims门禁修复

- 语言切换编辑缓冲现在保留打开编辑时的 interpretation id、原始/Markdown source hash 和 expected body hash。保存始终提交此原始 CAS 基线；若另一作者在切换期间更新正文，服务端返回 409，未保存草稿保留，不会用刷新后的 hash 覆盖对方版本。
- 有 manual_edit_revision 的中文解读不再进入英文翻译 provider 调用，receipt 记录 skipped/manual_chinese_edit_requires_claim_refresh；英文 reader 对手工修订稿保持隐藏，即使旧结构化 claims 的旧译文带有看似匹配的当前正文 hash/revision。现阶段没有基于新中文正文重建 claims 的翻译流程，因此保持隐藏，不新增流程。
- Red/green：双作者+locale切换测试在旧逻辑下发送刷新后的新 body hash（而不是打开编辑时的基线），修复后发送原 hash 并保留 409 草稿；旧 claims 翻译 red 重放实际触发 1 次 fake generator 调用，reader red 测试证明匹配 metadata 的旧译文会被返回。修复后双作者 UI 测试通过；英文 runner 的零 provider 调用与 reader suppression 两个 selector 2 passed，英文模块+手工 CAS API 聚焦套件 32 passed；FileDetail Vitest 25 passed。
- 静态检查：npm run typecheck、npm run build、Black、Ruff --no-cache、Python compile 与 git diff --check 均通过。Build 只有既有 chunk-size advisory。测试仅使用提供的隔离 PG16 loopback endpoint 55441；没有生产连接、生成、目标同步、部署或排程操作。pytest/服务进程已退出，容器未停止。
- 累计本地 review 23、changes-requested cycles 16；TypeSafe 累计 19。formal Judge 与 supplemental assessment 在本轮修复请求之后完成。该修复尚待 fresh Sol/high reviewer，未记录 PASS；保留此前 review2 与独立浏览器验收记录。新补丁与报告路径为 reports/issue450-editor-review3.patch、reports/issue450-editor-review3-report.md。未提交或推送。
### 2026-11-04 FileDetail编辑并发回归修复

- 修复三项已复现问题：保存进行中禁用正文输入，避免提交后静默丢弃后续输入；编辑器的 Markdown 草稿与预览状态按当前文件缓冲，切换语言再回来可恢复，切换文件/取消/成功保存时清除；英文翻译保存通过事务条件同时匹配当前中文正文与手工编辑版本，旧翻译任务在正文被改后不能重新标为 ready，英文读取也过滤与当前正文版本不匹配的翻译。
- 英文绑定使用中文正文 SHA-256 与 manual_edit_revision；不改变英文生成预算、同步、生产状态或目标 ACK。本轮没有恢复失败的真实稿件或执行同步。
- 回归：隔离 PG16 上英文模块及手工编辑 CAS selector 合计 30 passed（仅连接 loopback 测试库）；FileDetail Vitest 24/24 passed。npm run typecheck、npm run build、Black、Ruff --no-cache、Python 源码 compile 与 git diff --check 通过。早期两个 proxy fake 测试失败发生于 URL 校验前，没有数据库连接或写入；随后以隔离 PG 中的真实 SQL 完成 30 项回归。production_connection_attempted=false，最终测试端点匹配专用 55441，未触及其他数据库；测试及服务进程已退出，未停止测试容器。
- 独立浏览器验收记录保持原样。累计本地 review 22、changes-requested 15；TypeSafe 累计 17，其中 Supplemental 22 assessment 与 formal Judge 在本轮修复请求之后完成。此结果不是新鲜独立 review PASS。补丁与检查报告：reports/issue450-editor-review2.patch、reports/issue450-editor-review2-report.md。当前未提交或推送；未做真实生成、双端写入、部署或排程操作。
- 2026-11-04 FileDetail 中文解读 Markdown 手工编辑：新增仅当前站点的 `markdown.write` API 和文章卡片编辑/预览/取消/保存/冲突提示。PG writer 在同一事务锁定来源与 ready 解读行，比较当前 file/raw/Markdown identity 和 expected body SHA；陈旧来源或正文返回 409，前端保留编辑内容。仅更新中文 body/hash，附 actor、UTC 时间、新旧正文 hash 的手工审计记录；generation attempts/round receipts/budget/cursor、标题/来源/evidence/coverage/fingerprint 和原始 Markdown 保持不变。
- 中文正文变化后将旧英文翻译标记 stale；代理英文读取也在当前本地解读有编辑 revision 时停止返回旧翻译。原 target ACK receipt 保留；编辑 revision 进入 ACK source identity 的独立 key，使 future candidate scan 将正文视为待同步，不在本轮执行同步。
- 隔离 PG `tests/test_article_interpretations.py` 228 passed / 2 skipped，包含权限拒绝、source/body CAS、persisted readback、英语 stale/proxy suppression、generation 历史与预算保持；`tests/test_local_collection_target_worker.py` 85 passed / 1 skipped，覆盖旧 ACK 保留与新 revision pending。FileDetail Vitest 22/22；TypeScript typecheck、Vite build、Black、Ruff、py_compile 均通过。Chromium loopback UI smoke（合成 API fixture）验证预览/取消/保存/英文隐藏/409 保留编辑；Vite 端口 5191 已停止。测试数据库仅使用 127.0.0.1:55441 的专用 test 服务；未运行真实模型、source generation、双端 sync、生产写入、部署或排程操作。
- 本轮改动未提交/推送，等待根安排独立审查；当前 PR/Issue 生命周期门保持不变。

- 2026-11-04 validator retry feedback: anonymous Judge `targeted_correction` is recorded at `reports/local-interpretation-migration-20261102/controller-supplemental19-retry-feedback-judge.json`. Added allowlisted second-call guidance only for `unlabelled_inference` and `article_length_requires_short_reason_or_reduction`; validator strictness, evidence requirements, prompt version, fingerprints, routes, cursors, and the two-call budgets are unchanged. Synthetic red: 4 new parameter cases failed because no targeted feedback was sent; green: the 4 correction/rejection cases plus existing numeric-correction and unsupported-claim regression passed (6 passed). Black, Ruff, py_compile, and git diff --check passed. No real model, source-support review, production DB, harness, target, or schedule operation was run; real acceptance remains incomplete. Fresh independent Sol/high review 19 PASS; the 13 synthetic boundary checks passed. Cumulative review/change-request history remains 19/13. Authorized for normal commit and push; no merge, deployment, or production operation.

- PR #452 保持 Draft；上一推送 HEAD 4603fc6 的 GitHub run 41502058426 六项检查全部通过。另一个必需 AC1/AC5 本机启动校准在旧 HEAD 上失败于 PowerShell npm 包装器参数异常；已按运行门失败记录，未伪称 CI 失败。
- 本机项目路由保持 gpt-6-luna/high。Windows launcher 修复为 PATH 中 codex.exe → codex.cmd → 原 PowerShell 回退；保留 stdin、只读沙箱和工具禁用参数，不硬编码安装版本、不改全局设置。桌面 Codex CLI 0.166.0-alpha.5.1 通过同路由 Unicode JSON 合成回显（13 秒；无数据库、应用服务器或正式预算调用）。npm shim 0.154.0 对该账号/模型组合返回 model_not_found。
- 静态验证：4 个 launcher/argv 测试通过，Black、Ruff、git diff --check 通过。独立 Sol/high review 6 PASS；匿名 TypeSafe 评估无 findings，summary coverage 0.87。当前 launcher 修复等待提交推送与新 HEAD CI。
- 远程反馈 disposition 已登记为 clean，9 个保存的 Copilot review thread unresolved 为 0；未再次请求或刷新 Copilot。尚未执行真实文章生成、双端原生读回、幂等/单边重试、部署或排程变更；未合并或启用 08:00 计划。
- 2026-11-04 真实验收诊断：本地未配置 DATABASE_URL 或 env-backed 数据库连接配置，未读取 native DB；自动审核拒绝输出由真实模型输出派生的数字 token/evidence ID，并禁止换路径绕过。最初脱敏摘要只有通用 validation；后续受限 safe-flags 仅给出固定错误类别，仍没有足够证据确认真实来源支持性。合成 validator 9 passed；真实验收仍未完成且无 ready 草稿。不得据此放宽证据校验或重试已耗尽内容版本。


### Issue #450 AC-3 sync candidate fairness — 2026-11-02

- 修复候选扫描从最旧 ready 稿重复开始的问题：在现有 rounds 表保存独立 target_sync_scan 环形位置，并用专用事务 advisory lock 串行更新。failed/unknown ACK 继续可见且可重试；失败候选之后的新稿可达，扫描环回后失败项仍会再出现。
- 扫描游标与生成 receipt/source cursor 分开；候选列表只写该专用位置，不改 draft、ACK、生成预算或游标，也不调用 generator。已 ACK locale 的跳过行为由现有同步路径保留。
- 隔离红测：旧实现连续两次均只返回 failed-0/1/2，不含 new-pending。修复后聚焦候选和未 ACK 目标重试回归 6 passed；Black、Ruff、py_compile 与 git diff --check 通过。未运行真实生成、生产或目标操作，未改排程；Copilot thread disposition 未更改。精确 snapshot manifest patch SHA 69c7f46c581042f1c2cac7d2b6e8d5ad8c4ae97f3499a73cb408d19b61c9e144 获得 fresh Sol/high review 18 PASS（累计 changes-requested cycles 13）；TypeSafe Judge 记录见 reports/local-interpretation-migration-20261102/controller-supplemental17-target-sync-cursor-judge.json。

### Issue #450 最新 main 整合 — 2026-11-03

- 已将 origin/main 的 #441 squash SHA 5a62b7da563dcecc1b74bd4e99902514e98b209b 普通合并；唯一真实冲突为 project-status 文档，保留 #450 与 #441 两侧记录。runtime 与 runtime tests 自动合并，引入已在 main 的 SOA 失效 seed/frontier 修复；无代码冲突。
- article_interpretation_english.py、article_interpretations.py、codex_environment.py、storage.py 四个 receiver 模块，以及 local_collection_target_worker.py 的 Git blob 均与合并前相同；本次未改变 receiver overlay 与 AC-3 修复。
- 隔离测试：runtime、ArticleInterpretationService、英文后续步骤和 target worker 四个测试文件共 451 passed、2 skipped（本机缺少 pg_dump/pg_restore；Linux-only process-group 测试在 Windows 跳过）。仅使用新建 loopback PG16 测试容器、mock 和 fixtures；测试后删除容器 05fc5031d846ef58717d58ab8b47d0ab0549249f06ff21e78d0917608f235b33 与匿名卷 062b7d5f1626816636d3f34f9d382870bc2104e5175cba0286db98ad9c9ce6ef，精确 inspect 确认两者不存在；Black、Ruff、py_compile、git diff --check 通过。
- Review impact: none for #450 behavior；仅吸收已进入 main 的 #441 SOA 修复。累计 review 18、changes-requested cycles 13 保持不变；未发起新 review/Judge。未运行真实模型生成、生产/目标读写、部署或排程操作；merge 暂未 commit/push，交由 controller 复核。
## Unified weekly publication local relay — 2026-11-04

- Worktree `codex/unified-weekly-publication` from `3f44b057`. China remains the only weekly generator; a local durable relay freezes the completed bilingual guide and three recommendation card projections, then applies the same snapshot/member order/guide/projection pair transactionally to China and Overseas. The relay has no generation path. The shared frontend weekly view overlays or reconstructs the three frozen cards from snapshot metadata only when their owner matches the current snapshot ID and successful guide `generated_at`; raw API/catalog reads and generator inputs remain unchanged. Frozen rows carry `first_seen` and `original_filename` so a partial home-page read can still display the canonical card; home remains capped at six rows and weekly detail remains full length. Legacy/unowned reads keep the saved guide without inventing picks when a selected URL is unavailable.
- Added `ai_actuarial.local_weekly_publication` as a production reachability entry, streamed target worker operations, focused tests and runtime instructions. Tests cover one generation call, retry after lost ACK, unchanged no-op after ACK, a newer successful same-period guide revision refreshing projections, pending delivery surviving a failure-only guide audit append, transactional failure preserving prior publication, missing/deleted recommended articles holding the old target pair and pending outbox until article redelivery, bilingual guide ordering/four-link compatibility, frozen visible projections after catalog edits, Tuesday catch-up, and pre-slot `not_due`. Frontend regressions compare complete China versus a page-failing Overseas home read in both languages, retain exactly three canonical recommendations, preserve the six-card home cap and full detail list, and keep a legacy guide when selected rows are unavailable.
- 首次 PR 反馈修复：手动 UTC 周期将 `Z` 规范为 `+00:00`，使首次查找与待同步重试使用相同周期键；全部文章分页失败时保留 unavailable 提示，但仅在快照与成功导读所有权匹配时显示三张已冻结推荐卡片，未拥有冻结投影的失败读取仍不展示卡片。运行环境必须提供非初始化 `Storage.open_existing`；正式应用前须由主控通过只读能力与默认路径验收。
- 验证：隔离 PostgreSQL 55442 上周报同步测试 10/10 通过；BuildInfo、Issue 268、Issue 434 前端测试 16/16 通过；前端构建、类型检查、Ruff、isort、Black、`py_compile`、`git diff --check` 通过。Lint 无错误（4 条现有警告）；A11y 浏览器检查通过；周报浏览器 fixture 32/32 通过且无模型调用。该 PR 反馈修复是本地审查限额耗尽后的已测试未审查修复，主控须执行当前 HEAD CI 和原生默认路径验收；本 worker 未提交或推送，也未进行生产写入。
- Focused validation: 10 PostgreSQL cases passed on the dedicated disposable `weekly_test` database; frontend weekly reader test 12/12 passed. Black, isort, Ruff, py_compile, Python dead-code files/symbol gates, CLI help/JSON contract, frontend build/typecheck/ESLint, Chromium smoke and `git diff --check` passed. `Storage` is byte-identical to `origin/main`. No production connections, model calls, live writes, schedule edits, commit or push.
- Next: final local independent review, then controller-owned frontend-only rollout, commit/PR and automation activation. The controller owns production actions.

## Latest weekly additions 客户摘要与推荐排序 — 2026-11-04

- 分支 `codex/weekly-reader-summary`，基线 main `9611c8b`。本次仅前端展示：摘要说明本周发现文章数、重点主题、三篇推荐及适读主题；标题与主题用现有本地化 metadata，选文沿用同快照已保存导读。复用现有文章卡片，推荐排前三且只展示一次；详情只对剩余文章分类。首页推荐超出前六条时读取快照其他页后排序截取，读取失败保留可用预览。
- 变更：`client/src/lib/weekly-dashboard.ts`、`WeeklyHighlightCard.tsx`、两套既有周报测试及既有浏览器smoke。未增加依赖、后端接口、数据库写入或内容生成；不合并、不部署。
- 验证：聚焦前端13项、Python展示契约6项、typecheck/build通过；lint 0错误/4既有warning，构建有既有体积提示。中英首页/详情、390/1280宽度、空/AI/失败/长摘要32组浏览器通过；另用线上7篇快照只读数据在本地8组通过，代表截图已查看。Sol/high独立只读复核PASS，无accepted findings。
- 原checkout `fix/gpt6-parameter-compat` 的状态文档修改与4个未跟踪目录保留，兄弟仓库未读取。验证证据在 `reports/weekly-reader-summary-20261104/`（忽略目录）。PR #456已创建，初始提交14cd684；Copilot只请求1次并实际完成。接受其首页补读问题：找到全部推荐即停止，后页失败保留已读成员，detail仍全量分页；补回归并通过。真实预览还将重点主题去重、采用具体关键词，缺少主题时明确提示无主题，不把标题当主题。最终fresh Sol/high review PASS（1轮需修复已修复，累计未达Judge门槛），13项/构建/类型检查及32+8浏览器回归通过。PR创建后约15分钟回读CI及远端反馈。

## 当前候选 — 首页来源入口与日报文案 — 2026-11-04

- 项目 `AI_actuarial_inforsearch`，分支 `fix/home-source-report`。首页“来源”统计卡链接到 `/source-portals`；日报按唯一网页统计查看数与可比较变化数。首次材料判定按采集时间顺序：前一日报观察或Hub结果、以及更早的当日积压Hub结果可证明URL已知；首次材料观察的同次Hub `existing` 不计新发现，`new` 或无Hub结果计一次，后续版本/重试不重复计数。带可选 `is_article: true` 的HTML文章仍计为网页查看；链接文字无效时，使用已提取的HTML标题或正文首个Markdown标题，并将标题写入文章记录和网页观察，均不可用时回退到URL文件名。通用下载提示（包括“Download the full report”）和“Read more”不会作为资料名，旧证据在日报展示时也执行同一过滤。普通导航/API网页不作资料。重复捕获与规范归并保留文章有效标题，不让被过滤的空标题覆盖；原始referrer、旧证据形状和原始采集证据保持。超过8个标题时，中文明确写出“另有N份资料”。
- 用户已授权控制器依据真实逐站采集结果更新动态展示数据库，并持续维护逐站简报；产品工作线程未写生产数据库。控制器当前冻结源码完整相关PostgreSQL套件163/163通过（日报53、来源入口21、runtime84、首页合同5），Black/isort/Ruff/Pylint errors-only/diff检查通过。未变的前端 lint（4条既有warning）、typecheck/build、Vitest13项及中英文桌面/手机首页到来源入口 browser smoke此前通过。fresh Sol/high第8轮已复核完整工作树diff并PASS，无剩余接受问题；控制器继续提交同一PR并核新HEAD CI。历史动态单独备份/预览流程已核实16个有证据的入口/日期组，尚未生产写入。
- 工作文件：`client/src/pages/Dashboard.tsx`、`client/src/pages/SourcePortals.browser-smoke.mjs`、`ai_actuarial/local_collection_runtime.py`、`ai_actuarial/source_portal_daily.py`、`tests/test_source_portal_daily.py`、`tests/test_dashboard_react_source.py`，以及本状态记录。控制器继续PR反馈复查、当前 HEAD 验证和用户已授权的历史动态刷新；本工作线程未写生产数据库。任务仅在当前仓库进行，未读取或修改兄弟仓库。

## 周报新增资料双语显示修复 — 2026-11-04

- 分支 `fix/weekly-bilingual-metadata`，PR #455。范围限周报 API 双语字段透传、首页/weekly及新导引本地渲染、缓存与必要回归。缺失包/无原摘要/本地化片段失败的既有回退均保留，模型输入、选文、校验、预算、周报成员及schema不变。
- 当前仅适配两个既有测试的字段集合与本地化调用断言；敏感字段拒绝、分组、disclosure与i18n检查保留。控制器独立验证产品源码与review3已审查版本字节相同；这次测试适配不被记为新的Sol审查PASS或新增finding。
- 控制器最终合并重跑周报相关6文件140 passed（73.49秒）；两测试独立9项及Black/isort/Ruff/diff通过。未变前端9项、typecheck/build/lint和浏览器8组证据保持。
- 前两提交完整CI仅上述2个旧断言失败，其余3128测试及全部静态检查通过；本次跟进沿用原PR等待新HEAD CI。Copilot初发仅请求一次，唯一意见已修复并解决；不重请求或开新窗口。
- 无生产写入、历史说明重建、merge或deploy；兄弟仓库未访问。原checkout既有改动保留，历史说明部署后重新生成才更新。

## AICT 旧绑定兼容修正已独立过审 — 2026-11-03

- 分支 `fix/aict-chinese-taibei`，PR #453。增加受旧绑定证明保护的确定性名称复制路径，普通新富信息仍严格要求证据；复用已有原子写入与哈希逻辑。保留64份历史注释的空首类证据，不补造引文；旧Markdown的原始/JSON绑定、结果哈希和中英文内容哈希均核验后才重绑。旧source_signature沿用原九字段导入算法的已固定值核对，不误用新四字段公式重算；新绑定按现有新公式签名。来源、日期、分类、原始CAS、删除状态和非名称数据保持。
- fresh Sol/high第10轮对四个实际变更文件PASS；183项受影响测试通过，Black/isort/Ruff/diff和Python-symbols（0 findings）通过。真实只读预检66版本/64旧绑定/2未注释全部通过，record SHA仍为3e49fd62ecfb437521a952ca7fc5bae0d10fdc6f5cb978beb851fe3c5a3cb5e3；候选清单SHA 3806ff08978a9b0dc9daf2680cd75209712d4d7791515429d05cf62c94c1bde1。原始47c7清单保留作审计。
- 前一提交d95f0d0六项CI全部成功；这次新修正仍需新HEAD CI。正文/6条目标标签/3组Ready尚未写入。最终共享规则扫描还发现国内一份已发布历史周报需改名称，快照ID、生成时间、866项成员与统计保持；只在既有一行summary_markdown上做受备份/哈希保护的更名，不重生成或发布新周报。操作脚本与实际验收记录仍放ignored报告目录，完成后由原仓库状态记实际结果。
- Copilot仅初发请求一次，旧书签意见已修复并解决；不重新请求，不合并PR，不改#450或其他服务/排程。名称专用运行快照在最终修正、CI及实际数据验收后才激活到原06/09任务。

## AICT historical name correction — CI symbol gate repair — 2026-11-03

- Project `AI_actuarial_inforsearch`, branch `fix/aict-chinese-taibei`, PR #453. Fresh review6 passed the 12 reviewed implementation/test files. The current source commit `75319e1de87e7c17500554a52e4afe997831f9d1` failed CI only at the Python dead-code-symbol check: three new `cursor.itersize` assignments were unused because each cursor already uses `fetchmany(500)`. Removed exactly those three lines; no behavior or gate changes.
- Verification after the repair: `python-symbols` passes with 0 baseline findings; `tests/test_aict_name_history_correction.py` passes 22/22 with 3 third-party warnings; Black, isort, Ruff and `git diff --check` pass. The full read-only Hub plan is byte-for-byte record-equal to the reviewed 66-record plan, with canonical record hash `3e49fd62ecfb437521a952ca7fc5bae0d10fdc6f5cb978beb851fe3c5a3cb5e3` and unchanged variant, bilingual and source-site counts.
- The full local `symbols` gate was attempted and stopped because Knip is not installed. The actual CI job's later checks were skipped behind the dead-code failure; new-HEAD CI is pending. Current no-write manifest SHA-256 is `47c7f5266ac17c962b133769f0a7d3b10d2ac3defb5021e07b9f524cad76b1fc`; original review6 baseline remains preserved at `c4a91faeef6e87b702f08ffdef8561a6550564cf8ec8b88d845ea9d0bbdf655f`.
- No Hub/target/Ready writes, deployment, scheduler changes, commit or push were performed by this worker. Reviewer7 is checking the three-line repair; parent owns the commit and new-HEAD CI gate.
## Current candidate — AICT historical text normalization — 2026-11-03

- Project `AI_actuarial_inforsearch`, branch `fix/aict-chinese-taibei`. Source Registry v3 remains applied. The shared normalizer replaces verified former English and Chinese names, including known `(AIRC)`/`(AICT)` suffixes and names adjacent to Chinese prose, while preserving ASCII letter/digit/underscore continuations. Intake applies it to article titles and Markdown before derived hashes and capture manifests are built. Visible prose, link labels and tooltip titles normalize; HTTP and valid relative Markdown destinations, reference IDs, and HTML `href`/`src` values stay intact. Raw bytes, URL identity and source keys are unchanged.
- The read-only plan/apply helper writes deterministic Content Hub correction snapshots through the existing importer and rebinds selected annotation/bilingual rows through `save_live_enrichment`. The refreshed plan selects 66 versions: 64 annotation-bound and 2 without annotations. It changes selected fields in 60 Markdown, 4 summaries, 2 titles, 1 keywords and 1 keywords-json version; 28 versions have bilingual changes across 77 language-field cells, with evidence corrections in 3 versions. Eleven `files` and eleven `catalog_items` source metadata rows have old full-name labels. New correction snapshots normalize these derived labels while preserving prior snapshot provenance. The no-write manifest is `C:/Project/AI_actuarial_inforsearch/reports/aict-name-20261103/aict-name-normalization-dry-run.json` (SHA-256 `c4a91faeef6e87b702f08ffdef8561a6550564cf8ec8b88d845ea9d0bbdf655f`); it contains IDs, URLs, hashes and bounded institution-name evidence, no article bodies. Original CAS objects and URLs stay unchanged.
- The prior exact-pattern inventory has 54 versions (71 Markdown, 3 summaries, 29 titles); the fresh shared-normalizer inventory has 62 versions (83 Markdown, 5 summaries, 3 titles, 1 keywords and 1 keywords-json). The exact current annotation-bound bilingual scan finds 28 versions and 77 cells. It includes IDs 8322 and 8345, which were outside the prior 57-version plan; 8345 is bilingual-only in the selected output. Nine IDs are newly selected versus review5 and none were removed. The manifest includes selected-field counts and hashes, plus observed name and whitespace categories. Earlier audit shows nine old-name global chunks are unbound inactive artifacts; no chunk rewrite or embedding is planned. The Ready-only follow-up covers the six target rows in `ready-only-followup-plan.md`: China `ai`/`all` and overseas `ai`; it uses `_refresh_ready(..., [])` after label receipts. Parent's read-only state is in `label-ready-before.json` and `preflight-before-live.json`.
- The target worker normalizes future Hub-derived source-site labels and exposes a scoped, backed-up operation for the six reviewed active IAA label rows. It preserves effective publisher keys and rejects deleted files. No production Hub/target writes, live apply, Ready refresh, embedding/index work, scheduler changes, deploy, commit, push or merge were performed by this worker.
- Accepted round-1/round-2 fixes keep `keywords` and `keywords_json` consistent, handle known `(AIRC)` decorations and preserve explicit-null latest fields. Round 3 adds Chinese suffix coverage and preserves Markdown relative destinations/reference IDs. Round 4 preserves current-schema file metadata, including nullable timestamps/type fields, `bytes`, and `content_type`, while changing only approved source names/text and derived bindings; prior archive metadata, URL/raw-SHA identity and CAS bytes remain unchanged. Round 5 narrows name boundaries for adjacent CJK prose and adds exact annotation-bound bilingual discovery. Regressions cover adjacent prose, bilingual-only correction/idempotence, suffixes, Markdown/HTML destinations, null/latest fields, metadata preservation, URL/CAS preservation and idempotence. The affected suites pass 168/168 with 3 third-party deprecation warnings using the disposable `aict_name_test` database. Black, isort, Ruff and `git diff --check` pass. The isolated fake-storage binding test stubs only the unrelated disk-capacity probe at 70%; production capacity gates are unchanged. Reviewer6 is reviewing the frozen implementation; no production writes, commit, push, deploy or scheduler changes.
## AICT 中英文名称更新 — 2026-11-03

- 项目 AI_actuarial_inforsearch；独立分支 fix/aict-chinese-taibei，基于 main 5a62b7d。用户指定中文“中华台北精算师协会”、英文“Actuarial Institute Of Chinese Taibei”，保留 AICT/source_key、网址及全部旧别名。中国再保险集团 2013 年第 1 期刊物有该中文称呼；中国精算师协会官网另用“中华台北精算学会”，英文 Taibei 拼写按用户明确要求。
- 已通过既有 install_registry / sync_targets / apply_source_portals 路径将 Hub、中国站、海外站字典升至版本2；29机构、118别名，hash 6c29558905c6d54cc165fd852e436920cd6398bb1e25e1a646aa5550e7855b92。两站门户各仅改 AICT 一张卡的机构名称及简介，公开接口均已回读中英文新名；30卡、其他卡片、全部历史动态和文章绑定哈希不变。重复同步均 unchanged。操作证据在原仓库 ignored reports/aict-name-20261103/apply.json，未纳入共享提交。
- 源码范围：来源字典 seed v2（保留115旧别名、追加3个新名别名）、门户元数据、采集站点名称、日报名称及目录说明；版本转换测试 fixture 独立从v1开始。78项来源/门户测试、35项日报测试、CLI help、Ruff/Black/diff检查通过。首次沙箱临时文件替换权限失败，沙箱外重跑78项全部通过；一次性独立PostgreSQL测试容器已停止自动移除。
- 本次是数据更名和源码PR，不授权合并或部署。现有冻结定时采集/日报代码仍为旧名称，后续门户同步可能回写旧卡片名；需合并并部署该名称补丁才能保证持续一致。没有切换 #450 的代码、服务或排程，没有启动真实采集/模型调用。原checkout既有脏文件与四个未跟踪目录保持。

# PR #441 合并 main 冲突整理 — 2026-11-03

- 用户要求优先处理既有 PR #441；沿用干净的 fix/soa-obsolete-seed 独立工作树，原仓库未提交内容和 #450 工作树保持原样。
- 当前 main dcad36c 的业务代码自动合并，仅项目状态文档冲突；保留双方全部记录。SOA 原有修复及独立审查记录保留；合并后完整 runtime 84/84、Black/isort/Ruff、diff 检查通过，使用独立临时 PostgreSQL；等待新 HEAD CI。没有启动真实采集、写 Hub/目标、部署或更改排程。

# 当前候选 — SOA 失效 seed 修复 — 2026-10-31

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/soa-seed-repair/AI_actuarial_inforsearch`，分支 `fix/soa-obsolete-seed`。仅本仓库：删除已确认 404 的 SOA `/research/soa-research/` registry seed；保存 frontier 修补升级至 `frontier_repair_soa_v2`，从 queue/retry_queue 移除该 URL，并保留 cursor、其他有效 frontier、文章记录及有效重试。
- 参数化 frontier 修补测试 3/3 PASS（CCA、France、SOA；SOA 用例覆盖既有 v1 marker）；Black、isort、Ruff、py_compile 与 `git diff --check` PASS。
- 仅运行离线测试和代码检查；未运行 SOA 真实采集，未写生产状态、回执、Hub 或目标。Case 仍待修复部署后的普通来源重跑，不能据此声称恢复。未提交或推送；交由 controller fresh review。

# PR #446 合入 main 准备 — 2026-11-01

- 用户已授权核对评论修复、安全性及冲突后合并 #446。合并目标已由 #444 开发分支调整到 main；隔离工作树位于本仓库 .codex-worktrees/pr-446-main-integration，分支 codex/pr-446-main-integration，从最新 main c9ce6ac 建立，未修改外部英文开发工作树或原始脏工作树。
- #444 压缩合并后造成四个产品文件的历史冲突。已逐文件确认 main 与批准的 #444 基线 efb98c0 完全相同，且相对该基线的 13 个英文功能文件与 22 个 main 新增功能文件无重叠，因此保留 #446 已测试的精确产品版本；状态文档保留双方记录。没有新增业务逻辑、强推或删除分支。
- 五条首次 Copilot 反馈均已解决，针对修复代码与回归逐项复核。精确产品字节核对及英文/中文/异步组合回归通过（228 passed / 1 skipped，84.12 秒）；只使用隔离测试 PostgreSQL、注入 generator 与 loopback，无真实 provider 或生产调用。推送原 PR 后等待当前 HEAD 六项 CI，再按用户授权合并。既有三轮审查限额后的 TESTED / UNREVIEWED 记录保持，不声称新的 reviewer PASS，不重复请求 Copilot。此次授权仅用于合并，未执行部署或生产数据操作。

# 合并准备 — PR #444 与 #445 — 2026-11-01

- 用户已明确授权先合并 #444，再将 #445 合入 main，并核验处理 Copilot 意见。#444 已 squash 合并为 bbad8a76317c96c02e6a03bb7070e334a97633b1，原 HEAD 六项 CI 全部通过，四个 Copilot 讨论已解决。
- #445 合入更新后的 main 时唯一冲突是本状态文件顶部的两组独立记录；保留双方记录，应用源码没有冲突，也不改写任一 PR 的实现。正常 merge main 到原分支后重新跑当前 HEAD 的 CI，再合并；不强推、不删分支、不部署或访问生产数据。

# 当前候选 — 来源入口列表与单入口详情 — 2026-11-01

- 项目 AI_actuarial_inforsearch，分支 codex/source-portals，继续 PR #445。本轮仅调整来源入口前端：`/source-portals` 为数据库风格四列表格，支持名称/机构/介绍搜索与每页 20 项；独立详情路径保留原动态全文、原站链接及返回时的筛选/页码。更新中英文、路由、组件测试和 Playwright smoke；未改 Database、API、采集或 schema。
- 搜索输入保留空格；标题可键盘进入详情。移动端合并机构列，简介换行，日期仍清晰显示。直接刷新详情和未知入口返回列表也已纳入验证用例。
- 最终验证：组件 Vitest 5/5、lint（仅四条已有 Hook warning）、typecheck、build、真实 Chrome 中英文桌面/手机 browser smoke 全部通过。浏览器流程覆盖搜索、分页、键盘打开详情、直接详情、返回时保留筛选/页码、空动态与未知入口。另以真实十个入口配置在 1440/768/640/390 宽度完成截图，无横向溢出或 pageerror，详情刷新正常；动态只在浏览器 mock 中演示，不是生产采集结果。前期本机进程与自动权限审核超时已恢复，未留下验证阻塞。
- 本轮 UI 首轮及最终独立 Sol/high reviewer 均 PASS，最终五个前端文件的 blob hash 已记录在忽略文件 `reports/source-portals-list-review-final.md`；原 PR 后端结论仍保持原有“最终修复已测试但未 review，不能称 PASS”的状态。完整本轮记录见忽略文件 `reports/source-portals-list-worker.md`。沿用旧的 255 项后端回归证据，本次未改后端，不重复生产验收。没有第二次 Copilot 请求、生产数据写入、合并或部署。原工作树无关改动保留；本轮提交后检查 GitHub 当前 HEAD 的 CI。

# 当前候选 — 来源入口动态 — 2026-11-01

- 项目 AI_actuarial_inforsearch，分支 codex/source-portals，PR #445。独立来源入口阅读页由固定目录卡片和真实完整采集组成；Content Hub v5 保存不可变采集与成员，服务 schema 6 展示每日最新实际采集。普通 HTML 材料和版本保留，精确目录页仅从 Database 列表、计数、分类及导出排除。
- 初始 PR 后仅发起过一次 Copilot review，五项可复现反馈经 TypeSafe Judge 接受并已修复：同日相同页面的后续真实采集按 captured_at 留存并排序；SOA AI 入口使用固定抽取来源及新比较范围；动态示例限长但 Hub 保留完整标题；忽略正文内导航/页脚且空目录不完整；CIA 带尾斜杠目录 URL 纳入精确别名。没有重开 Copilot review。
- 验证：Content Hub、采集 runtime、target worker、API、迁移和来源入口测试合计 255/255 通过（来源入口 suite 21/21）。Black、isort、Ruff、Pylint errors-only、py_compile、git diff --check 通过。测试只写隔离 PostgreSQL schema；无生产迁移、采集或 serving 写入。
- 累计完成 6 轮独立 review：此前 4 轮要求修改、review 5 PASS、PR 反馈 review 6 要求修改。TypeSafe Judge 接受最后两项有界修复；按 review 限额例外，最终改动已测试但未再 review，明确不记为 PASS。父任务负责提交推送修复、GitHub 线程处置和 CI；没有合并或部署。完整记录在忽略文件 reports/source-portals-worker.md。
## 2026-11-01 required CI import-order repair

The prior12e quality gate failed only three newly introduced isort violations. The same worker changed import ordering in the API router, English module and English tests (5 inserted/5 deleted lines, no behavior changes). Isort, Ruff, per-file Black, diff checks and the full English module20 tests passed after formatting. Functional patch validation before this formatting-only commit was223 passed/1 skipped. A new current-HEAD CI and rebuilt/reprepared candidates remain required before live cutover. No production cutover or article generation has run.

## 2026-11-01 PR446 remote feedback final tested fixes

Copilot was requested once at initial publication and completed on 12e23f8. All five in-scope findings were reproduced without provider calls and accepted by actual TypeSafe Jev 1.14.0. The same persistent worker fixed scoped one-hot terminology (including the selected paper's one-hot vectors), overlapping ordinal events, saved quotation multiplicity, native DeepSeek budget options and source currentness before each new call. Final combined current-byte suite: 223 passed, 1 skipped in 60.81s, no provider calls; English module 20 passed, focused Chinese gates and Ruff/Black/compile/diff passed.

Three cumulative independent local review rounds remain exhausted. These are tested final fixes under the explicit final-review-limit exception, not a new reviewer PASS. No fourth local review or repeated Copilot request. No merge authorization inferred. Required current-HEAD CI and real two-site article/browser/export/stability acceptance remain gates. Live China is still4a37ed4 and overseas7402626; unused12e candidates are retained and will be superseded without touching production data.

## 2026-11-01 final English release validation

Final accepted fixes: 220 passed, 1 skipped across English, Chinese interpretation and async transport suites (67.53s); no provider calls. Frontend/API/task bytes match review-3 snapshot; earlier frontend/type/lint/build checks remain applicable, release packaging rebuilds final SHA. Three independent local reviews required changes; accepted fixes were TypeSafe adjudicated and tested under the final-review-limit exception. No final reviewer PASS. Current-HEAD CI and actual C/O deployment, qualified bilingual article, browser and HTML exports remain pending.

# 当前候选 — PR444 远程审查反馈 — 2026-11-01

- 分支 `fix/interpretation-number-evidence`。Copilot 对 PR444 的4项反馈均先在隔离 PostgreSQL schema 与注入式 generator/resolver 中复现；TypeSafe Jev 1.14.0 接受全部4项，并要求同一 worker 修复与测试。证据：`reports/interpretation-number-repair-20261101/remote-feedback-assessment.json`、`typesafe-remote-input.json`、`typesafe-remote-result.json`。
- 修复 provider cleanup 后的手动重试拦截；有已保存正文时先读取草稿，仅对新生成应用 provider-call 预算，允许在原截止时间内继续链接校验；手动选择时间戳取自持久 receipt；恢复每日稿件时同时保留来源 round 调用上限，并在 reservation 时给 manual receipt 记录本次调用数。
- 新增6项回归覆盖4个反馈主题，包括手动和每日 receipt 的中断恢复。隔离数据库验证：`tests/test_article_interpretations.py` 与 `tests/test_article_interpretation_async_transport.py` 合计201 passed / 1 skipped；补丁后六项新回归再次6 passed。Ruff、Black、`py_compile`、`git diff --check` 通过。模型/provider调用0，生产数据库访问0。
- 当前补丁按第3轮最终审查限额完成的已测试修复处理；没有新增独立审查 PASS。主控负责提交、推送和 CI；本 worker 未提交或推送。

# 当前候选 — 微信解读数字证据诊断与单篇生成 — 2026-11-01

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/fix-interpretation-number-evidence/AI_actuarial_inforsearch`，分支 `fix/interpretation-number-evidence`。数字证据仍严格校验；私有诊断只含限长段落片段、证据 ID、解析 token 与缺失数量，不进入 reader DTO。第二次调用的纠正提示受原输入字符和模型上下文余量限制，不改变已保存输入。
- 现有 POST `/api/collections/run` 与 CLI 支持明确 `file_url` 单篇生成。服务复用来源、当前内容、取消、advisory lock、链接验证及内容预算；单篇 receipt 使用服务端键和 `manual` 类型，不推进每日游标；重复、旧耗尽内容、日程注入均有回归覆盖。
- 验证：`tests/test_article_interpretations.py` 192 passed / 1 skipped，`tests/test_article_interpretation_async_transport.py` 2 passed；Ruff、Black、`py_compile` 与 `git diff --check` 通过。仅使用隔离测试 PostgreSQL、注入式离线 generator 和本地 loopback fixture；没有调用生产模型或写生产数据库。独立审查及部署、真实 CAS 单篇发布和 HTML 导出由主控继续完成；本 worker 未提交或推送。
- 第3轮最终审查接受的 P2 已由同一 worker 做最终限额修复：当完整数字诊断前缀无法装入第二次调用余量时，改为不附加空洞的通用纠正提示；新增1000字符/300字节边界回归。最终聚焦反馈/预算测试 2 passed，Ruff、Black、源码 compile 通过。此改动是最终限额下的已测试未复审修复，未取得独立审查 PASS，也不再安排第4轮。`git diff --check` 在此链接工作树仍报“must be run in a work tree”；已对改动文件做尾随空白检查。OPS 最终自检7个注入场景通过，包括拒绝旧构建环境标记并保留非构建环境变量；无生产操作。本 worker 未提交或推送。

# 当前候选 — 中文文章解读阅读与导出 — 2026-10-31

- Issue #437，分支 `codex/issue-437-interpretation-reader`。只读接口只投影当前 `reader_eligible` 最新稿件的公开字段；FileDetail 仅在中文界面读取和渲染，沿用最新请求守卫，提供折叠、复制、Markdown 和内联样式 HTML 导出。成功保存 Markdown 或转换完成后清除并重读解读，保存失败保留当前稿。老稿缺少原文标题时使用当前文件标题。生成输入从有限前页结构/显式署名行携带原文作者证据，现有一次生成提示要求逐字返回且验证；link validation 将已核验姓名写入 payload references，再由读取接口/页面/导出透传。没有明确署名时为空；不读原文之外的作者、不改原文/摘要。
- 新增法国真实标题页片段隔离PG集成测试：generation 输入/输出验证、link失败后重试复用、payload references、`read_interpretations` 和 reader API 端到端；SOA前页六位署名及Acknowledgments中的R. Dale Hall/Achilles Natsis作为负例，确认不扫正文/致谢。原有测试覆盖 FileDetail 语言/键盘、读取失败、保存/转换后重读、标题回退、作者导出及 API allowlist。三篇人工审校样稿继续使用共享 formatter 语义 HTML 预览。三个国内链接由 Issue 管理端实开核对；微信编辑器访问被安全门拒绝，尚待人工粘贴核验。
- 验证：`tests/test_article_interpretations.py` 186 passed / 1 skipped；MarkdownContent 与 FileDetail focused Vitest 18 passed；`npm run typecheck`、`npm run build`、Black、Ruff、`git diff --check` 和本地浏览器 smoke 通过。完整证据在 Issue 外部 evidence 目录。测试只使用注入的离线 Generator，无真实模型调用；无迁移、发布或生产写入。worker 未提交或推送，等待 manager fresh review。
- 本地 Chromium smoke 使用隔离 API fixture：中文读取 10 次、英文 0 次，生成 POST/model call 0；复制、Markdown、HTML 的标题/正文/原文 URL/国内 URL 一致。桌面与 375px 截图及 HTML 预览截图保存在外部 `issue-437/screenshots/`；API fixture 不替代部署环境验收。微信粘贴仍待人工检查。

# 当前候选 — 意大利公开空密码 PDF 提取 — 2026-10-30

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/public-pdf-extraction/AI_actuarial_inforsearch`，分支 `fix/public-pdf-extraction`。仅修改采集 runtime、聚焦测试和 runtime 参考说明；其他仓库未读写。
- PDF 现尝试以空密码解锁；只有 pypdf 确认成功才继续提取，需用户密码的文件仍清晰报为转换失败。保留 600 页与 Markdown 大小上限。
- 新增 4 项参数化/回归用例；针对新测试 4/4 通过。runtime 文件除一项需要 `POSTGRES_TEST_URL` 的数据库测试外 82/82 通过；完整文件尝试中该测试因环境变量缺失失败。Black、isort、Ruff、Pylint errors-only、py_compile 和 `git diff --check` 通过。
- 只读核验 Italy CAS SHA-256 与指定 digest 相同（82,393 bytes）；通过 `_convert_article` 生成 12,119 字符 Markdown 并含 3 页。未运行 live config、Hub 或目标服务。
- 未提交或推送。若需完整 runtime 文件结果，请设置指向隔离 PostgreSQL 的 `POSTGRES_TEST_URL` 后重跑 `python -m pytest tests/test_local_collection_runtime.py -q --no-cov`；父任务继续 fresh review。

# 当前候选 — 日报中英文语言选项 — 2026-10-29

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-flow-report-language/AI_actuarial_inforsearch`，分支 `feat/local-flow-report-language`。仅离线日报 Markdown 支持 `--language zh|en`；默认中文；JSON 与汇总数据不受语言选项影响。
- 完成 helper/CLI 双语回归（35/35 PASS）、CLI 帮助与无效语言检查、Black、isort、compileall、`git diff --check`、skill-creator quick_validate。Oct28/29 双语真实回执+runtime 报告已生成到原项目 `reports/report-language-20261029/`，确认中文默认等于显式 zh、JSON 双语一致且输入未改变。中文相对基线仅有按要求替换的预算建议短语。
- 本轮未改采集 runtime、回执、ledger、自动化或生产状态，未提交或推送；等待独立 Sol/high review。

# 当前候选 — CI 容量错误用语修正 — 2026-10-29

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-flow-readable-report/AI_actuarial_inforsearch`，分支 `feat/readable-local-flow-report`。日报仅在容量错误明确写出 `% used` 时显示已用比例；只有阈值或语义含糊的百分比保持通用“目标容量门槛”。原 runtime 集成断言未改。
- 验证：runtime 报告集成测试 3/3、offline helper 34/34 PASS；Black、isort、Ruff、Pylint errors-only、`py_compile`、`git diff --check` PASS。Oct28/29 runtime Markdown/JSON 与已冻结 v3 输出一致；Oct28 实际已用 80.2% 仍可见。30 份回执/runtime 输入 SHA256 未变。未运行 DB runtime suite。
- 提交 `85a3faf` 对应候选通过第三轮独立 review；本轮 helper 修正发生在本地 review 轮次耗尽后，未再次独立 review，不能称最终 HEAD 获 reviewer PASS。等待父任务提交修正并重跑 required CI；本 worker 未提交或推送。

# 当前候选 — 计划未运行建议与回执缺口区分 — 2026-10-29

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-flow-readable-report/AI_actuarial_inforsearch`，分支 `feat/readable-local-flow-report`。修改限于执行摘要 advice、回归测试、本技能说明和本状态记录；不涉及 runtime、生产数据或调度。
- 计划内未运行与已尝试但无匹配回执分别给建议：前者核实是否应执行，后者核对当前回执。IABA 等 monitor-only 运行不会被误说成来源采集的回执缺口。
- 本地评审历史如实保留：增量2有一项 review CHANGES_REQUESTED；累计失败评审周期5（此前阶段3的最终限额例外仍保留）。本轮修复后尚待新的独立评审；没有声称 reviewer PASS。
- 验证：helper 34/34、Black/isort/Ruff/Pylint errors-only、`py_compile`、skill-creator quick_validate、CLI `--help` 与 `git diff --check` 通过。Oct28/29 runtime 与日期回执模式的 8 份 Markdown/JSON v3 输出均重复渲染字节一致；30 份回执/runtime 输入 SHA256 前后不变。未运行 DB runtime suite（runtime 未改）。父任务负责后续独立评审和 PR 发布；本 worker 未提交或推送，当前没有 reviewer PASS。

# 当前候选 — 执行摘要覆盖与建议修复 — 2026-10-29

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-flow-readable-report/AI_actuarial_inforsearch`，分支 `feat/readable-local-flow-report`。范围限于离线日报 helper、聚焦测试、技能说明与状态记录；未读写生产状态。
- 有 runtime-output 时，汇总只统计精确匹配的当前非预览回执；无 runtime-output 时按同日回执展示已知下载、入库/分类数量及故障，并标明当前运行覆盖未知。预览、过期回执和未匹配的当前尝试仍不计成功。转换错误沿用 `failure_point` 的转换阶段归并并去重；建议同时覆盖国内/海外 ACK、Ready/容量错误和普通来源/转换错误，且不表示已执行修复。
- 验证：offline helper 33/33 PASS；Black、isort、Ruff、Pylint errors-only、`py_compile`、skill-creator quick_validate 与 `git diff --check` PASS。Oct28/29 含 runtime 与不含 runtime 的 Markdown/JSON 八份输出均重复渲染一致；无 runtime 的Oct29仍显示119下载、41新增、25复用、40分类，并明确运行覆盖未知。30份回执/runtime输入前后SHA256不变。
- 未改采集 runtime、回执、ledger、automation、生产服务或历史人工报告；未提交或推送。父任务继续 fresh review 与 PR 后续。

# 当前候选 — 每日采集报告执行摘要 — 2026-10-29

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-flow-readable-report/AI_actuarial_inforsearch`，分支 `feat/readable-local-flow-report`。修改范围为离线日报 Markdown 渲染、helper 回归和本技能的报告合同；未读写兄弟仓库或生产状态。
- 日报开头新增四项中文执行摘要：本次精确匹配回执的完成/部分/失败数、可见下载与入库/分类/首类候选/转换数量、来源/转换/目标/运行回执缺口与预算暂停、后续建议。摘要不把预览、monitor-only、hold 或旧同日回执算成本次采集成功；当前来源、转换和目标问题分别保留，缺失数据仍显示未记录。
- 验证：离线 helper 30/30 PASS；Black、isort、Ruff、Pylint errors-only、`py_compile`、skill-creator `quick_validate.py` 与 `git diff --check` PASS。真实 Oct28 命令输出匹配回执 5/8（完成0、部分4、失败1），Oct29 为 8/8（完成0、部分7、失败1）；摘要能显示 Oct28 海外 80.2% Ready 容量门槛、国内端回执失败和3项回执缺口。两天 Markdown 与 JSON 均重复渲染一致。CLI `report --help` PASS。运行时采集源码未改，未重跑 DB runtime suite。
- 仅读取既有 Oct28/29 运行输出与回执，并记录输入 SHA256 前后校验；未改写回执、ledger、调度或报告历史。未提交或推送；父任务负责最终验收及 PR 后续。

# 当前候选 — AI 首类发布、日期回填与 legacy 证据修复 — 2026-10-28

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/ai-primary-publication/AI_actuarial_inforsearch`，分支 `fix/ai-primary-publication-dates`。仅本仓库可写；未读写兄弟仓库或生产配置。
- Hub、缓存、历史列表/count、目标 payload 和 pending retry 均按 `categories[0].key == "AI"` 决定发布；Hub reader 原样保留已存 legacy 首类空 evidence，但只有 exact Hub annotation digest 绑定的已存读/回填路径接受，新的 Hub enrichment 写入仍要求每类 1–3 条 exact quote。源日期按 `publication_date.value` 原精度写入 `files.published_time`；Hub 日期语义保留 `publication`/`revision`/`document_version`，未知日期不回退。
- 五项 PR #431 Copilot finding 经 TypeSafe Judge3 接受有界修复：cleanup 现用文件 advisory lock、exact URL/raw-SHA 与成员关系复核及单记录事务；fresh backlog rows 也经过 exact Hub refresh；soft-deleted/invisible row 走完整 reactivation；只有 raw SHA 和 Markdown 不变时才保留旧双语包；未知 Hub 日期在写入事务中只允许预检观察到的有效旧值。历史 v2 signature 仍由发送前的 exact Hub read 校验并原样保留。
- 真实 cleanup interleave 回归在隔离 PostgreSQL `55436` 上确认：并发 replacement writer 等待 cleanup 文件锁；cleanup 提交后 replacement 保持 active 且成员关系恢复。三个聚焦测试文件 `test_local_collection_runtime.py`、`test_local_collection_target_worker.py`、`test_content_hub.py` 在隔离 PostgreSQL `55436` 联跑 156/156 PASS（3 项上游 SWIG deprecation warnings）。Black、isort、Ruff、Pylint errors-only、py_compile、两个维护 CLI `--help` 和 `git diff --check` PASS。
- 本修复发生在本地 review limit 3 之后，按 Judge3 实施并验证；没有第 4 次 review，也没有声称 reviewer PASS。控制器此前已完成单独批准的 China maintenance 与幂等回放；此 worker 未写生产目标，未提交或推送。控制器负责真实维护其余批次、更新冻结状态、提交推送、当前 HEAD CI 与既有 review threads；overseas apply 仍等待容量相关批准。

# 当前候选 — SSH 静默期连接存活 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。仅此仓库；修改 `_stream_target` 单次 SSH 参数、命令契约回归和 runtime 运行说明。
- 单次 SSH 调用显式设为 `ServerAliveInterval=30`、`ServerAliveCountMax=3`。不改全局 SSH 配置，保留 `BatchMode`、`ConnectTimeout` 与原 21600 秒 subprocess timeout。keepalive 约 90 秒未获响应时走原失败路径；它不确认目标写入，成功仍需实际 worker ACK 和 Ready 回读。
- 验证：隔离 PostgreSQL `127.0.0.1:55435` 上 runtime 65/65 PASS；target worker 31/31 PASS；Ruff、Black、isort、compileall、skill-creator quick_validate 与 `git diff --check` PASS。该实现运行未连接生产或修改运行状态。
- Swiss60 中国端的远端 Ready 已由控制器只读证据确认；本地 SSH 返回/回执恢复由控制器处理。本轮未提交或推送。

# 当前候选 — 法国 memoir frontier 恢复 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。仅此仓库；涉及法国站点入口、已保存 frontier 的 v2 修补、回归及 skill 参考。
- France memoir 入口更新到 `/se-documenter/memoires/memoires-d-actuariat-4651`。迁移只移除已观察的两个失效路径与旧 `doc_id=1` 地址；未成功访问的当前列表只排到既有待处理附件之前一次。若该列表已存在，会原位提升为 depth 0；其他队列前缀、重试和文章历史保留。
- 验证：隔离 PostgreSQL `127.0.0.1:55435` 上 runtime 64/64 PASS；offline flow 19/19 PASS；Ruff、Black、isort、compileall、skill-creator quick_validate 与 `git diff --check` PASS。
- 控制器已完成 CIA、CCA、法国 live 与幂等验收；Swiss60 中国端 Ready 回读及本地回执恢复由控制器处理。本轮未运行生产采集或写入，未提交或推送。

# 当前候选 — 有界目标重试游标公平推进 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；隔离工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。范围限于文章批次 cursor、runtime 回归与本状态记录；仅此仓库。
- 普通运行在本站完整持久文章顺序中旋转 cursor，扫描32篇后只将其前缀内已选文章作为进度锚点；第一篇 deferred 会在下轮优先进入批次。全部扫描记录均被选中时锚定最后一篇。reuse/target retry24、模型8、exact URL 不推进普通 cursor 与本站 pending 计数保持不变。
- 验证：隔离 PostgreSQL `127.0.0.1:55435` 上 runtime 59/59 PASS；offline flow 19/19 PASS；Ruff、Black、isort、compileall、skill-creator quick_validate、`git diff --check` PASS。持久化回归覆盖32篇 target retry 失败、混合25篇模型失败+7篇reuse/target失败，以及逐轮恢复。
- 未运行生产采集或写入，未提交或推送。候选等待 fresh independent Sol/high review。

# 当前候选 — exact URL 捕获隔离 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；隔离工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。范围为 exact URL frontier 隔离、四 ID 请求序列回归和技能说明；仅此仓库。
- 明确传入单项 `initial_frontier` 时跳过普通保存前沿修补；CIA 两个 ID、CCA、法国 exact 重放仅捕获指定 URL 及经验证的同站重定向。普通发现仍运行旧前沿修补，正常站点 cursor 不变。
- 验证通过：runtime focused tests 57/57（隔离 PostgreSQL `127.0.0.1:55435`）、offline flow 19/19、Ruff、Black、isort、compileall、skill-creator quick_validate 和 `git diff --check`。四 ID 参数化测试各两次 exact 重放均只请求 canonical exact URL；既有普通 CIA/CCA/法国修补和 redirect 回归通过。
- 未运行生产采集或写入，未提交或推送。候选等待 fresh independent Sol/high review。

# 当前候选 — 精确 URL pending 队列口径 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。范围限于站点积压计数、回归和技能字段说明；仅此仓库，未访问/修改生产状态。
- `pending_article_count` 按本站所有 incomplete 文章减去本次实际选择数。`--exact-url` 仍只处理该 URL，并保留普通站点 cursor；所选文章后续失败、等待目标确认或 Ready 的状态仍单列。
- 验证：隔离 PostgreSQL 55435 上 runtime focused tests 53/53 PASS；offline flow tests 19/19 PASS；Ruff、Black、isort、compileall、skill-creator quick_validate 和 `git diff --check` PASS。40 篇两次 exact replay 回归确认每次只触发指定 URL、pending=39，日报从 prior 38 正确更新到 39，cursor 不变。
- 未运行生产 runtime、未提交或推送。候选等待 fresh independent Sol/high review。

# 当前候选 — 已发现公开附件优先 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；隔离工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。只处理本仓库；未访问或修改生产状态。
- 仅 CIA 两项、CCA 与法国站对 frontier 未处理后缀稳定优先已发现且通过现有公开文档规则的附件。消费前缀、cursor、visited、重试项、文章历史、HTTP cap 与请求间隔保持不变；其他站点队列顺序不变。
- 验证：runtime/PostgreSQL 隔离测试 52/52（仅 localhost:55435）、offline helper 19/19、compileall、Ruff、isort、Black（runtime 与测试）、diff check、skill-creator quick validation 均通过。
- 回归覆盖旧导航队列中第100位后的 CIA PDF、页面当轮发现附件后下一请求优先处理、30请求上限与 restart 无重抓/跳过、CCA/法国规则及 Swiss 原队列不变。
- 未运行真实生产采集或目标同步；未提交或推送。等待新的独立 Sol/high review；通过后 controller 控制 CIA 正常 discovery 重跑与附件幂等验证。

# 当前候选 — 资料队列游标恢复 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。仅此仓库；生产状态和服务未访问或修改。
- 普通批次先在本站持久文章全列表中定位并旋转现有 identity 游标，再过滤 `complete` 行；精确 URL 批次不改站点游标。扫描32、既有内容复用/目标重试24和模型补全8上限保持不变，失败项仍保留 `pending_retry` 与错误文本。
- 验证通过：runtime/PostgreSQL 隔离测试 47/47（仅 localhost:55435）、offline helper 19/19、compileall、Ruff、isort、Black（runtime 与测试文件）及 `git diff --check`。
- 40 篇/三次持久化运行回归覆盖：8篇模型超时、24篇复用完成、游标锚点完成后下一轮处理8篇新文献、失败项后续仍可重试；精确 URL 重试保留站点游标。
- 未运行生产采集/目标同步，未提交或推送。候选等待新的独立 Sol/high review；通过后 controller 安排真实 CIA、CCA、法国与瑞士试跑。

# 当前候选 — 本地来源发现与预算修复 — 2026-10-27

- 项目 `AI_actuarial_inforsearch`；隔离工作树 `C:/Users/ferry/.codex/worktrees/local-source-budget-fixes/AI_actuarial_inforsearch`，分支 `fix/local-source-discovery-budgets`。仅修改此仓库；兄弟仓库与原生产工作树均未访问/编辑。
- 当前 7 个文件覆盖安全跳过非 HTTP 链接、CIA/CCA/法国已验证入口与旧 frontier 修补、瑞士单轮 60 请求续跑、文章重用/模型配额公平、v2 阶段预算/错误和日报字段，以及技能文档与回归测试。
- 验证通过：runtime/PostgreSQL 隔离测试 46/46（仅 `127.0.0.1:55435`）、offline helper 19/19、`compileall`、Ruff、Black（runtime 与测试文件）、`git diff --check`、skill-creator `quick_validate.py`。CLI help/JSON 与幂等行为由测试覆盖。
- 尚未运行生产 CIA/CCA/France/瑞士采集；未访问生产 Hub/目标、未提交或推送。候选待新的独立 Sol/high review；通过后由 controller 安排真实站点试跑与发表。

# PR #428 main CI claim-race repair — 2026-10-26

- 项目 `AI_actuarial_inforsearch`；工作树 `reports/pr428-main-ci-worktree`，分支 `fix/pr428-main-ci-single-flight`，基于 `e3ed5c981aa7ab1d7f042998b46bb2ea93111af7`。范围限于 `ai_actuarial/storage.py`、两个周报测试文件和本状态文件；未访问兄弟仓库。
- 在 task-owned localhost:55435 PostgreSQL 上用事件屏障确定性复现未修改主分支竞争：竞争者读到同指纹 failed/空 token，暂停；另一连接 claim 并 finalize complete；竞争者恢复后旧 UPDATE 仍 claim 成功。原复现证据在 `reports/pr428-main-ci-repair-20261026/repro-untouched-main.json`。
- 修复在 UPDATE 条件排除已完成的同指纹记录；未 claim 的竞争者在事务后的回读发现该结果已完成时直接返回 complete。失败和过期租约仍可重试，不同指纹仍可重新生成，finalizer 的 claim-token 保护未变。CI 单飞测试改用仅测试配置的 10 秒 timeout、并发前预建探针连接、以及竞争 claim 返回事件；原 NOWAIT 检查与 `generator.calls == 1` 断言保留。
- 真实 PG 组合运行：`tests/test_issue_267_weekly_explanations.py` 与 `tests/test_postgres_weekly_claim.py` 31/31 PASS，覆盖 CI 失败用例、确定性完成/claim 竞争、初次 claim 排他、过期租约重试、指纹变化和过期 finalizer。精确两项回归 2/2 PASS。Black、isort、Ruff、Pylint errors-only、py_compile、diff check 均 PASS。测试仅使用隔离数据库；未调用生产数据库或服务。
- 当前候选待新一轮 fresh independent review；尚未 commit/push/创建 PR。隔离 PostgreSQL 容器 `local-runtime-tests-pg-20261025` 保持运行供复审复现。

# 当前运行候选 — 2026-10-26

- 项目 `AI_actuarial_inforsearch`；工作树 `reports/local-automation-worktree`，分支 `feat/local-collection-runtime`；当前候选含 16 个文件，兄弟仓库未访问。
- 本次候选另修复 Ready 恢复中的 embedding 选择：每个当前 URL 必须恰有一条本次 chunk 任务结果，profile 必须匹配当前 KB，chunk-set ID 必须非空且互不重复；embedding 只收到这些精确 ID 和当前 KB embedding identity。历史 ready set 不再按 URL/profile 猜选。31 项 target-worker 测试 PASS（3 项 SWIG deprecation warnings），覆盖歧义 selector、缺失/错配结果拒绝和 embedding 失败后按原生 ID 重试；Black、isort、Ruff、Pylint errors-only、py_compile、CLI help、dead-code files/symbols、diff check 均 PASS。无需数据库；本轮没有生产调用或写入。候选待独立审查。
- Hub 对外 `markdown_sha256` 表示 Markdown UTF-8 原文摘要；另带 `hub_markdown_sha256` 和 `hub_markdown_sha256_kind`。共享严格校验器独立验证存储 JSON payload 摘要，并仅接受确切的 `raw_utf8` 或 `json_payload_utf8` 绑定；两种语言必须共用 variant ID 与原始绑定。旧 fill-only projection 保留原三字段 `hub_binding` 形状。
- 双端 target fingerprint、流式输入、持久元数据和回读校验均保留上述新绑定对；原生 chunk 仍按原 Markdown UTF-8 文本计算。
- 显式声明 `openpyxl>=3.1.5,<4`，使不安装 MarkItDown extras 的 CI 环境也具备现有 XLSX 提取依赖；DOCX/PPTX/XLSX 与普通 ZIP 的识别规则保持现有测试覆盖。
- 隔离 PostgreSQL 55435 上 Hub/runtime/target focused tests 为 78/78 PASS（3 项上游 SWIG deprecation warnings）；Ruff、Black、isort、pylint errors-only、py_compile、dead-code files/symbols、CLI help、CI 过滤依赖检查和 `git diff --check` 均 PASS。
- 全量 quality gate 已启动并收集 2,558 项测试，冻结时仍在运行；结果只追加到 ignored `reports/local-runtime-20261025/implementation.json`。
- 此次修复未调用生产 Hub 或 target。此前 IAA 单篇真实生产验收记录为 receipt succeeded，Hub 双语与中国 ai/all、海外 ai Ready/query 检查均通过；该记录来自修复前 HEAD。此候选冻结等待独立审查，生产兼容只读审计由 controller 执行；未提交或推送。详情见 `reports/local-runtime-20261025/implementation.json`。此前所有历史状态如下保留。

### Target source-site provenance compatibility — 2026-10-26

- Historical v16 `source_site` values can be organization display names; new captures use registry site IDs. The target worker now preserves any nonblank source-site string exactly, keeps `null` unknown, and rejects blank/non-string values. Historical raw-blob recovery is unchanged.
- Target worker regression: CCA and AAE legacy labels plus `iaa` pass persistence, exact readback, and idempotent retry on China and Overseas profiles; `null` remains supported and malformed values fail. Focused target tests pass 24/24; Black, isort, Ruff, Pylint errors-only, py_compile, CLI help, and diff check pass.
- This repair made no production calls or writes. Candidate remains the existing 16-file scope; ready for fresh independent review and controller retry of the first five backlog records. No commit or push by this worker.

# 本地资料每日轮换与失败研究 — 2026-10-25

- 工作树 `reports/local-automation-worktree`，分支 `docs/local-collection-automation`（PR #427）；范围为 skill、离线 `plan/status/report --json`、回执/ledger合同、行为测试和 CI smoke 测试。
- 计划按 America/New_York 自然日每天 06:00 选固定六项 baseline，最多另排两个不同的失败重试；连续七日计划覆盖 32 个监控项。09:00 日报统计前一自然日。hold/monitor-only 均不冒充采集成功，实际覆盖只由逐站回执确认。
- helper 只读 v2 每日回执与可选 case ledger，不执行采集、研究、Hub/两站写入，也不创建或启用 Scheduler。生产 source、Hub、两端写入/回读及 Ready/index adapters 仍待实现与验收。
- 验证：Python 3.11；19 项单元测试、CLI help/JSON/幂等、schema 文档夹具、DST/七日覆盖/预算/重试公平/恢复语义、`py_compile`、skill-creator `quick_validate.py`、`git diff --check` 均通过。
- 失败 case 按 site/stage 跨日保留；只有对应阶段明确成功才关闭。ledger 写回 `close/supersede=closed`，其他更新动作保持 `active`；新证据保留旧研究指纹直到实际研究。fresh Sol/high review-4 PASS，无验收范围内问题；提交与远端检查以 PR #427 当前 HEAD 为准。

# 当前 PR #425：双语前台/Catalog及汇总库同步 — 2026-10-14T19:56:34+00:00

- 项目 AI_actuarial_inforsearch；分支 fix/bilingual-document-metadata，任务工作树 reports/bilingual-metadata-worktree；原 checkout 修改及四个未跟踪目录保留，兄弟仓库未访问。范围为目录 JSON/PG0003、生成与增量补齐、Storage/API/搜索/编辑、Database/FileDetail/两Catalog入口、Hub同步CLI及相关测试和指南。
- 前台列表/详情使用现有语言按钮显示中英完整元数据；编辑仅更新所选语言，另一套保留。Catalog固定输出完整中英，移除原文语言选项；分类共享规范键并按界面翻译，错误/跳过不清除已保存信息，旧local调用保留原合同。Hub导入同版本分类一致；同步按URL/原文件SHA及Markdown绑定，只补空值并报告冲突。
- Linux原始conftest/真实Git隔离快照/独立PG16：213测试与13子测试PASS；前端12测试、typecheck/build、Chrome真实渲染fixture smoke PASS。Black/isort/Ruff/compileall/diff、Python/TypeScript symbols PASS。最终fresh独立Sol/high frontend-review-3 PASS，28个变更文件哈希匹配。累计本新增范围完成3review/2FAIL，TypeSafe jev-latest/jev1.13.0的裁决已保留；最终PASS与CI各自独立，Copilot用户禁用。
- 此刻后台成功3246篇/6492条，77个正文缺口；generator45624/writer49256与3个Luna/high上下文继续运行，错误日志为空。心跳每15分钟监控；准确数量看完成ID文件，不能声称已全量完成。
- 正在自动commit/push并更新PR425；此新增范围真实新HEAD CI待运行。仅代码交付，未merge/deploy，未对正式网站数据库执行Hub sync。下一步等待当前提交全部CI与非Copilot范围内反馈；随后由用户安排合并部署与正式同步。

# Simple parallel bilingual metadata and CI hooks — 2026-10-14

- User requested one Markdown per fresh Luna/high context, three in parallel, with a separate importer and only basic field/source-ID checks. The two local scripts in reports/bilingual-metadata/simple-runner are running and have actually imported 295 document versions / 590 zh/en rows at this checkpoint.
- The generator sends up to150k characters as one complete input, chunks longer texts, reuses successful notes/outputs, and records source gaps. The writer calls the existing reviewed core API; no source-excerpt, all-table fingerprint or repeated-readback gate delays generation.
- Original source fields/CAS are retained. The pipeline is not fully complete;25versions lackMD and29nonemptyMDs are known empty-extraction placeholders. Additional unsupported bodies are recorded as gaps.
- Three Luna contexts continue independently. Minor terminal-state/gap bookkeeping repairs are undergoing the configured scoped review without stopping the running pipeline. Previous real schema failure is fixed; both scripts now produce/import real metadata.
- The existing two CI tests now use recognized setup_module/teardown_module hooks, preserving the production sunset and at/after410 checks.31focused tests andPython-symbol gatePASS; fresh review5 approved those diffs. Full local symbol gate cannotrun becauseKnip is missing; actual currentHEAD CI is the delivery gate.
- Only the two CI testfiles andthisstatus are published inthisfollow-up; operation scripts/data remainlocalignored. Copilot user-disabled. No merge or website deployment is authorized.
# 双语元数据逐篇生成与 CI 日期修复 — 2026-10-14

- 项目 AI_actuarial_inforsearch / fix/bilingual-document-metadata；PR #425。只编辑本仓库，原 checkout 已有状态修改及四个未跟踪目录保留，兄弟仓库未访问。
- 用户最新要求简化为每个 Markdown 一个 GPT-6-luna/high 新上下文，3 个并行；一个脚本产出中英文 title/summary/category/keywords，另一个持续入库。两个小型操作脚本正在 reports/bilingual-metadata 内实现，保留基本结构和文档绑定检查，使用既有核心导入器；已有结果跳过。
- 正式本地汇总库现有 53 个版本、106 条双语记录；前 52 个已额外只读检查必填字段为 0 缺失，53 的分段生成/入库已成功。8 张原来源表全行指纹及精确回读历史 PASS，9,767 原版本/9,541 原文 blob 保留；不重复这些昂贵检查。此前复杂队列已停止且保留断点。
- 9,742 版本有非空 Markdown，另 25 无 Markdown；审计发现其中 29 个非空字段其实是 MarkItDown 空响应占位，须记缺正文并跳过摘要编造。输入和原数据不修改，也不重启已由用户停止的 Docling。
- 核心存储变更独立 Sol/high PASS，CLI/队列修复 fresh runtime-review-4 PASS。最新 Linux 原始 conftest + disposable PostgreSQL 44/44 PASS，队列基本检查 15/15 PASS。线上网站未接入/未部署。
- 当前 CI 的 11 个旧兼容聊天测试失败已在干净 main2f1fcda 快照同样复现（11 failed/18 passed）；接口按原计划于 2026-10-14 00:00Z 退役。仅两份测试固定到退役前 1 秒，并新增退役当刻/之后的 410 检查；生产路由和退役日期未改。测试修复已独立 Sol/high PASS，Windows 31/31 与 Linux 联合 44/44 PASS，静态及 diff 检查通过。
- 此次推送仅两份 CI 测试和本状态，等待真实新 HEAD CI。Copilot 用户禁用。未授权合并/部署。全量双语数据尚未完成；下一步按用户要求启动简单脚本的并行逐篇生成及自动入库。

# 双语元数据试跑及入库 — 2026-10-14

- 项目 AI_actuarial_inforsearch / fix/bilingual-document-metadata。原 checkout 的已有状态修改和四个未跟踪目录保留；兄弟仓库未访问。
- 按用户授权，由 GPT-6-luna/high 新上下文直接读 Markdown。1/3/6/8 篇试跑均完成，首轮 18 个文档版本已通过；随后三批继续完成，目前共 40 个文档版本、80 条 zh/en 记录；6 篇组全文 129,567 字符约 6 分钟，8 篇组 95,417 字符约 4 分 42 秒。每批绑定版本、Markdown variant 和 JSON 字段哈希。
- 本机 D 盘正式 content_hub 已实际应用追加迁移 v2 并入库这 80 条记录，逐字段数据库回读和精确重复导入 PASS。8 张原来源表全部行指纹及行数前后相同；9,767 个版本和 9,541 个原文 blob 保持不变。原来源字段/CAS 未改。
- 可处理 Markdown 共 9,742 个版本，另 25 个没有正文，不能据标题编摘要；全量尚未完成。其余批次及断点队列正在处理，普通上下文按 6–8 篇且约 150,000 字符控制，长文需分段后汇总。
- 存储代码 fresh 独立 Sol/high 审核 PASS。Windows 常规 pytest 因既有 FAISS 全局夹具崩溃无法启动；同 13 项隔离 PG 测试 PASS，Linux 原始 conftest/真实 Git 临时快照 13/13 PASS。Black、Ruff、py_compile、CLI help、diff-check PASS；0001 迁移不变，新 0002 为 LF。
- 仅更改 content_hub、CLI、0002 迁移、聚焦测试、CONTENT_HUB 指南和本状态。网站尚未接入新表；这次完成可按版本及 zh/en 查询的数据结构，不部署网站。
- 操作证据与逐文档输出在 reports/bilingual-metadata，实际回执 initial-18-import.json 与 next-22-import.json，来源指纹 source-state-before.json，审核 review-1.md。依项目规则发布 PR，Copilot 按用户偏好禁用，仅等待真实当前提交 CI 并处理有范围的非 Copilot 反馈。

# Bilingual metadata storage — 2026-10-14

- Project `AI_actuarial_inforsearch`; branch `fix/bilingual-document-metadata`, based on
  `origin/main` at `2f1fcda34e25b5507825565a336806f268d1fee7`. The assigned worktree was clean
  before edits. Only this repository was accessed; sibling repositories and serving runtime/API
  code remain out of scope.
- Normal-tier decision: the change crosses one hub migration, the existing CLI/data module, and
  focused PostgreSQL integration coverage. The data contract and transaction path are understood;
  no runtime consumer, cross-project contract, or AI provider code is needed.
- Added migration `0002_bilingual_metadata.sql` and an offline `content-hub metadata import`
  contract for zh/en records keyed by content version and language. Imports verify both the
  Markdown text variant ID and its stored digest, use configured category keys plus `Other`,
  preserve source-attributed rows, fill blank generated fields only, and keep recipe/author
  provenance per filled field set. `show` groups metadata by version/language and `status` reports
  language counts.
- Files changed: `ai_actuarial/content_hub.py`, `ai_actuarial/cli.py`, new migration
  `ai_actuarial/content_hub_migrations/0002_bilingual_metadata.sql`, `tests/test_content_hub.py`,
  `docs/guides/CONTENT_HUB.md`, and this status note. No generated metadata was written to a live
  database; no credentials or D-drive data were accessed.
- Black, Ruff, `py_compile`, migration LF check, CLI import help, and `git diff --check` pass.
  PostgreSQL integration used only the controller's disposable test database. The stock
  `python -m pytest tests/test_content_hub.py -q` run could not set up tests because the shared
  autouse cleanup fixture imports the RAG runtime and triggers a Windows FAISS fatal exception
  (`0xc0000008`). The same 13 tests passed when run from a temporary test copy that excluded only
  that unrelated runtime fixture, retained the disposable PostgreSQL database, and cleaned its
  test schemas at session end. The first run also found sandbox `%TEMP%` permission errors, which
  were avoided by placing pytest's temporary directory under this worktree.
- The controller owns fresh independent review and publication. Current work remains uncommitted;
  there are no unrelated worktree changes.

# CI 超时调查更新 — 2026-10-12

- 分支 `fix/ci-quality-gate-progress` 已定位 PostgreSQL 测试夹具在后台 ready-data 子任务结束前删除 schema，形成应用层锁等待环；证据见 `reports/ci-investigation-20261012/root-cause.md`。
- 当前工作树只改测试清理：等待 `NativeTaskRuntime` 工作线程及其后续子线程，超时则在 DROP 前明确失败；schema DROP 增加 30 秒 lock timeout。Windows 3 项回归与 Black、isort、Ruff、`git diff --check` 均通过。
- disposable PostgreSQL Linux 最终复跑 15/15 PASS（含清理回归、quality-gate 回归、受影响 API 与 index-chain 用例）；实际旧 fixture 负对照使新回归失败，修复后通过。Fresh Sol/high 独立审核 PASS，另独立验证 Windows 8 PASS 及 Black/isort/Ruff/diff-check。Controller 将发布至 PR #424，并核对新提交实际完整 CI；原 CI run `38198724627` 与正式数据库/服务保持未触碰，部署门槛未改变。

# 第 1–3 步实际迁移已验收，发布状态见验收记录 — 2026-10-11

- 项目 AI_actuarial_inforsearch；实现分支 codex/local-content-hub，基于未合并的
  codex/full-postgresql / PR #422。原工作目录 fix/gpt6-parameter-compat 的已有
  状态修改及四个未跟踪目录保留；同级项目没有读写。
- 两站 SQLite v16 一致快照、原文/富内容/索引归档已落盘 D:/AI_actuarial_inforsearch。
  海外 1,008、中国 3,384 个归档文件已逐文件校验；Windows 特殊名称用可追溯映射保留。
- 正式本机 PG16.15：ai-actuarial-content-hub-pg16；PGDATA 在 D 的 postgres/content-hub-pg16，
  仅绑定 127.0.0.1:55434。连接、全量来源档案与 PGDATA 目录访问已限制为当前用户/System/Admin。
- 两个独立 raw_source 暂存库保留全部 42 表、195,675 行，JSON TEXT 存档保留 NUL/BLOB/rowid。
  source-stage 版本 ledger、逐表计数与内容摘要、原生 dump/隔离 restore 均 PASS；不冒充原生 42 表转换。
- content_hub 主库实际双源导入 PASS：4,141 个 file observations、3,511 个 URL/文件版本、
  8,269 个来源记录映射、28,909 个文本字段版本。全部原始元数据/文本已独立逐字段比对，
  13 个同 URL 不同原文版本均可查询；两源精确重跑后全表计数/摘要保持不变。
- 共享原文 CAS 已验证 3,356 个唯一文件；保留 137 个缺失哈希状态：136 对应删除记录，
  1 个在用历史网页捕获缺件。两份缺件已按完全相同 SHA 补回；不同的新响应没有替代旧版。
- 摘要和 Markdown 独立离线语言候选，原文不改；模型/来源/生成配方并存。
  中国站实际仍含大量英文富内容，不能按所在服务器推断中文或法域。
- 62 个 legacy artifacts 保持来源隔离，8 份 FAISS 实测 China1024 / overseas3072；不混合。
  缓存未声明的模型/切块配置及历史未知配置如实记 unknown；原始向量/切块行仍在私有全量暂存库。
- 主库原生 PG16 dump/隔离 restore PASS，9 表全部计数/内容摘要一致。D 档案保留两份来源库
  dump 和 content-hub.dump；原始文件另在 hub/cas 与原站 archives，不以数据库备份代替文件备份。
- 重点旧 CLI/import/schema/data-root 回归 116 passed；最终新功能 12 passed。Black/isort/py_compile、
  Pylint errors-only、Python 文件/符号 dead-code 与 diff-check PASS。独立 fresh Sol/high review-6 PASS（0 findings）。
  已确认问题和 AC7 验证缺口由同一 Sol/high worker 修复；TypeSafe/Jev-1.13.0 裁定三次。
  Windows Git 检出 SQL 固定 LF，已验收的 SQL/ledger 不变；CAS 哈希错误与中途源库变化的
  隔离故障回归均证明 canonical 与 raw_source 全表计数/内容摘要保持不变。
- 首次 CI 13 个旧 CLI 配置用例失败已按同顺序复现并用 5 行测试环境恢复修复。
  最终 content-hub/issue263/weekly 联动 96 passed；并发用例单独六次 PASS，未改业务代码。
  本地静态/可达性检查与 fresh review-6 PASS，修复提交的当前 HEAD CI 仍待验证。
- 本次变更：hub/source-stage 模块与 SQL migrations、CLI、tests、langdetect 依赖、操作指南和文档索引。
  本机采集/摘要/翻译 API 调用为 0；不停止或清理生产数据，不切换服务器、不合并 PR。
  现有 API/crawler/RAG 尚不消费新 hub。下一步接入本机采集，按分类/语言发布两站子集及增量同步。
- PR #423 已创建并附加（base codex/full-postgresql）；修复 HEAD 的 GitHub CI 待核对。
  创建后 15 分钟非 Copilot 反馈检查 PASS，无评论/评审/线程；
  Copilot 用户禁用。最终发布状态见 ignored reports/data-hub/github-verification.json 与 D/hub/reports/20261011。

# 执行第 1–3 步：归档与来源暂存完成，主库合并进行中 — 2026-10-11

- 用户已解除前次权限限制并明确授权继续；D 盘、Git 与本机 Docker 均可访问。
- 项目 AI_actuarial_inforsearch；实现分支 codex/local-content-hub，依赖未合并的
  codex/full-postgresql / PR #422。主目录已有改动保留；同级仓库不在范围内。
- 两站 SQLite v16 一致快照已保存到 D:/AI_actuarial_inforsearch/archives/20261011-content-hub，
  SHA、integrity 与全部 42 表行数核对通过。海外 1,008、中国 3,384 个原文/富内容/旧索引
  归档文件核对通过；5 个 Windows 不支持的原文件名用可追溯的名称映射存放。
- 新建 PG16.15 容器 ai-actuarial-content-hub-pg16；PGDATA 在 D，端口只绑定
  127.0.0.1:55434，连接设置保存在 D 的 private 目录，未写入 Git 或报告。
- 两个独立 raw_source 暂存库共 195,675 行：China 122,038 / overseas 73,637。
  JSON TEXT 行存档保留 SQLite 的 NUL/BLOB/rowid，未冒充原生 42 表转换。
  逐表行数与内容摘要、原生 dump 和隔离 restore 均通过。
- 共享原文 SHA CAS 与双源 manifest 正在准备；产品 CLI/独立 schema 的测试和审查
  仍在进行，尚未声明第 3 步完成。生产配置、采集、数据和服务均未切换或清理。
- 中英富内容按来源、内容版本和独立语言候选保存；资料采集/摘要/翻译 API 调用为 0。
  按仓库规定已完成 1 次 TypeSafe/Jev 审查裁定，裁定只接收代码与审查证据。
  旧向量来源/模型/维度/切块配置分别存档；现有 API/RAG 后续步骤再接入主库。
- 本次 review 的范围限定用户第 1–3 步；Copilot 按用户要求禁用。

# 最新工作 — PostgreSQL runtime conversion — 2026-10-11

- 项目 `AI_actuarial_inforsearch`；分支 `codex/full-postgresql`；基线
  `origin/main` / HEAD `80f497a3c50351520a88b23e5d1b68901b8c4e6b`。
  实现树为 `6c58bc61bc021387418eab3ab99565729808d68b`。代码范围 179 个路径；
  本次只增加此状态记录，工作目录变化为 180 个路径。只改本仓库，同级仓库不可读写。
- PostgreSQL 是唯一应用运行时数据库。保留原有 Storage 业务 API，以窄连接适配
  处理 DB-API 差异；迁移覆盖基础与懒初始化的 RAG、聊天 schema。并发状态通过
  PostgreSQL 事务、CAS、advisory/row locks 和 savepoints 实现。SQLite 仅保留给
  显式 schema/旧版导入流程使用。
- SQLite v16 导入器只读单个来源，要求目标 PostgreSQL 业务 schema 为空；校验
  schema、全表数据、主键/外键、序列和来源 provenance，支持同源幂等重跑并拒绝
  冲突或第二来源。它不做两站合并。版本化 schema `0001`/`0002` 支持 plan/apply；
  原生 `pg_dump`/`pg_restore` CLI 提供 backup、verify 与隔离 restore smoke。
- `DATABASE_URL` 与文件 `DATA_DIR` 独立解析。应用附件、任务历史、上传和 RAG
  产物可放在 D 盘；PostgreSQL 的 `PGDATA` 也需单独配置到 D 盘。真实 D-root
  CLI/日志/API 检查通过。Windows PostgreSQL 16.15 原生 CLI 对实际仓库 backup、
  verify、restore 和 v1→v2 升级检查通过；冻结 v16 fixture 的 42 表导入、内容、
  ID、序列、幂等和冲突检查通过。PG16 Docker 构建/HTTP smoke 与 API HTTP smoke
  也通过。证据在 ignored `reports/postgresql-assessment/` 下的
  `controller-repo-ops.json`、`controller-import-full.json`、
  `controller-cli-data-root-r2.json`、`controller-docker-smoke.json` 和
  `controller-http-smoke.json`。
- 最终 Linux 完整质量门 r6 PASS：2,461 passed、0 skipped、4 warnings、
  531.64 秒；quality JSON 为 `reports/postgresql-assessment/controller-linux-quality-r6/`，
  Black/isort/Pylint 无 violations/new/stale。四个 Python/TypeScript 文件和符号
  dead-code gates 均为零 findings，fresh Sol/high review-4 PASS。最终树未因这些
  检查发生代码改动。Copilot 按用户要求禁用；PR 发布后仍需等待当前 HEAD 的
  GitHub CI 实际通过。
- 本次只更新状态文件；不提交、不推送、不合并、不执行生产切换。生产数据尚未
  迁移，不做两站数据合并，也不搬运或清理原文档案。PostgreSQL dump 不包含原始
  文件内容；任何生产清理前必须另行归档并校验原始文件。下一步由控制器发布 PR，
  再核对该 PR 的 CI；合并和生产切换另行授权。

# 最新工作 — Docker 构建上下文与旧覆盖文件核查 — 2026-10-09

# Active work — Issue #420 offline tokenizer — 2026-10-10

- Project `AI_actuarial_inforsearch`; branch `fix/issue-420-offline-tokenizer`; scope is lazy KB tokenizer/embedding runtime construction, Docker tokenizer cache setup, and focused regressions only. Sibling repositories remain off-limits.
- `KnowledgeBaseManager.chunker` and `embedding_generator` are cached properties, preserving indexing first-access behavior while removing read-only manager-construction tokenizer work. Docker now pins a writable `/app/.tiktoken-cache`, exports it as `TIKTOKEN_CACHE_DIR`, and resolves supported built-in encodings at build time.
- Focused new regressions pass (9 tests); baseline pre-fix evidence and result are in `reports/issue-420/worker/sabotage.md`. Docker was not built or run, per task constraint. The complete existing `test_fastapi_rag_admin_endpoints.py` invocation exceeded this runner's 30-second command window after its first passing test; it remains for reviewer/CI execution.
- Follow-up verification on 2026-10-10: `python -m pytest -q tests/test_kb_manager_lazy_chunker.py tests/test_fastapi_kb_readonly_no_chunker.py` passes (9 passed). The requested persistent Codex session `01a1240d-1fa6-7d60-8148-5b95f5494924` was found but cannot resume here because the CLI cannot initialize its in-process app-server client on the managed read-only home; no sandbox/configuration bypass was attempted and no fallback session was opened. Remote-head lookup is likewise blocked by DNS resolution for github.com.
- Final local check on 2026-10-10: the same 9 focused tests pass again; Black and isort checks for the three Python files plus `git diff --check` pass. A new persistent `gpt-5.6-terra/medium` fallback was also attempted after the requested resume, but failed at the same read-only app-server initialization point, so no session last-message could be produced. The ignored #420 build/smoke evidence records a successful temporary `issue420-image:probe` build and a `--network none` tokenizer smoke; it was not rerun in this follow-up. No application-source changes were needed; only this state record is uncommitted. The current remote HEAD still cannot be refreshed because DNS cannot resolve github.com.
- Controller acceptance repair on 2026-10-10: the prior `tests/issue_420/smoke.sh` passed its Python command to the fixed API entrypoint, which ignores arguments, so it could not prove the claimed tokenizer check. The script now overrides that entrypoint with `--entrypoint python` and executes a packaged `/app/tests/issue_420/offline_tokenizer_smoke.py` under `--network none`; the probe verifies a nonempty cache, `gpt-4` mapping, and first `SemanticChunker` chunk. Dockerfile explicitly copies `./tests` into the image, and a focused source contract prevents regressions. `pytest` (10), original KB-list runtime-independence (1), shell syntax, Black, isort, and diff-check pass. This runner cannot access Docker's local socket (`operation not permitted`), so it did not build/run `issue420-image:v2`; `gh pr view 421` cannot connect to GitHub, so the requested PR-body update remains pending. No service, production image, `/opt` path, commit, push, or PR mutation occurred.
- The requested `codex exec --ephemeral -m gpt-5.6-terra -c model_reasoning_effort=medium --output-last-message reports/issue-420/worker-r3/last-message.md` was attempted after validation and exited 1 before producing the file: its in-process app-server client cannot initialize on the managed read-only home. Its exact completion content remains in the worker's final report; no workaround or alternate session was used.
- Worker-r4 acceptance repair on 2026-10-10: `smoke.sh` now creates no named container or pre-emptively deletes one. Under `--network none` it invokes the packaged probe with the Python entrypoint override. The probe resolves all seven Docker-warmed encoding names and all ten warmed model mappings before semantic chunking, so a merely nonempty but incomplete tokenizer cache cannot pass. Contract tests pass (2), prior lazy-read regressions pass (9), shell syntax / Black / isort / diff checks pass. Docker daemon access remains denied (`operation not permitted`), so the actual image build/run is not claimed. No application or Dockerfile change, commit, push, PR, merge, or production operation was performed in this worker pass.

- 项目 `AI_actuarial_inforsearch`；隔离分支 `codex/fix-docker-build-context`；
  基线 `origin/main` 为 `e9ad04c`。只处理本次三项核查及确认的构建问题，
  同级仓库不可访问。根 checkout 的既有状态修改和四个未跟踪目录保留。
- 实施评估为 simple：上下文排除规则、一个实际 Docker 回归测试和部署说明；
  使用同一个 `gpt-6-luna/medium` worker。未改应用查询、迁移或后台任务。
- 当前单 KB 与批量统计的实际 SQL 均使用关联子查询，EXPLAIN 均命中
  `idx_file_chunk_sets_latest` 覆盖索引。现有 v15/v16 与 service-token 回归
  通过；当前建表、迁移和查询保留 `token_type`。未获得服务器旧覆盖文件，
  不宣称复现原始 CTE 性能数字、文件字节一致或物理数据库列删除。
- 确认旧 `.dockerignore` 会复制嵌套环境文件、SQLite/sidecar、运行配置及
  临时工作目录。合成上下文的实际 BuildKit 导出在修复前失败、修复后通过。
  已排除这些路径，保留开发模板、配置代码、API 和前端构建输入。
- 文件范围：`.dockerignore`、`tests/test_docker_build_context.py`、
  `docs/deployment-runbook.md` 与本状态记录。已有相关回归 17 项和新增
  Docker 回归 1 项通过；Black/isort/Pylint 与 diff-check 通过。
- 独立 Sol/high 复审 PASS，无确认的范围内问题；PR 发布及当前 HEAD 的
  GitHub CI/反馈核查待完成。Copilot 按用户要求禁用。未执行生产部署、
  迁移、重启、合并或删除。
- 下一步：提交、推送并创建 PR；约 15 分钟后核查 CI 与
  非 Copilot 反馈。生产实际覆盖目录仍需由部署环境提供。

---

# 最新工作 — Issue #408 文档追问范围 — 2026-10-07 EDT

- 项目 `AI_actuarial_inforsearch`；分支 `codex/issue-408-document-scope`；
  独立 checkout `.codex-worktrees/issue-408`；最新 main 基线 `4192205`。
  范围为 Chat 请求、会话范围/恢复、直接文档上下文、错误与回归。
  同级仓库不可读写；未改生产模型路由、凭据或部署。
- 实施评估为 complex：范围跨前端请求/会话恢复、后端持久化、权限、预算和失败重试。
  已选定并始终保留 `gpt-6-sol/high` worker；审查使用 fresh `gpt-6-sol/high`。
  复用已有文档预算、Markdown 权限检查、会话 metadata 和结构化失败路径；无新增依赖。
- 根因证据：真实 Chromium 154 + Vite 5184 / 本地 API fixture 捕获到首次
  FileDetail Explain 带原文/URL，而同一会话两次普通追问都不带原文/URL/scope。
  此证据证明前端参数丢失，不代表生产模型回答。
- 修复：会话只保存最多三个 URL/name selectors；每次文档追问读取当前文档
  Markdown，并校验其与持久 scope 一致；引用来自本轮实际生成 chunks。
  UI 显示当前范围。注册用户明确清除通过 owner/permission checked DELETE；
  guest 下一请求带独立 clear 意图。切换、新建、恢复和删除重置本地待确认意图。
- 普通空 scope 继承已保存非空范围；缺原文返回可重试 `CHAT_DOCUMENT_EMPTY`，
  不进入库检索。不同范围的非显式请求返回 `CHAT_DOCUMENT_SCOPE_MISMATCH`。
  恢复失败禁发并提供重试/新建。quota/预检/传输失败保留未确认切换；成功或已接受
  scope 的结构化失败清除 switch/clear 意图，防止再次覆盖其他标签页的选择。
- 验证：完整 Python quality gate PASS，2,414 passed / 11 skipped，
  Black/isort/Pylint PASS；最后的前端修改后 Chat source guard 21/21 PASS。
  相关四个 Vitest 文件 26/26 PASS；typecheck/build PASS；lint 0 errors、
  4 条既有 Hook warnings；两个 dead-code gate 与 diff-check PASS。
  补充全量 Vitest 131/132，唯一失败为既有 FilterBar a11y 的 Status 标签测试；
  该测试、组件、Layout 默认翻译上下文和 setup 均与 origin/main 一致，超出 #408 范围。
- Chromium 生命周期 smoke PASS：12 query / 9 Markdown fetch，覆盖首次解释、
  两次追问、切换、清除、新建、恢复及失败重试、双标签 stale scope、quota 恢复、
  provider 接受范围后失败。浏览器使用本地 API/回答 fixtures；后端 TestClient
  独立捕获实际 direct/retrieved chunks、citations、持久 scope 和 retry 元数据。
  未声称生产模型或部署后验收。
- 独立审查最终 PASS（review4，无确认的范围内 finding）。此前三个可复现失败路径
  均交同一 worker 修复；累计失败两轮及三轮时分别使用 TypeSafe `jev-latest`
  （实际 `jev-1.13.0`）只读裁决，均接受最小修复和 fresh review 路由。
  本地 ignored reports/issue-408 保存原始审查、裁决与验证证据。
- 根 checkout 既有 `.hermes/project-status.md` 修改及 `.codex-tmp-agentic-rag/`、
  `.hermes/research/`、`diagrams/`、`graphify-out/` 未触碰。
- 交付：实现提交 `bbdf9fc` 已 push；PR #413 已创建并关联本任务：
  https://github.com/ferryhe/AI_actuarial_inforsearch/pull/413
  创建时间 2026-10-08 02:37:09 UTC；远端复查于 02:52:28 UTC 完成。
  实现提交六项 GitHub CI 全部 SUCCESS，PR 为 OPEN / CLEAN；inline 和一般评论均为零。
  Copilot 仅报告账户评审额度用尽，未完成评审；没有提出代码 finding，独立 Sol/high
  审查仍为 PASS。没有需要追加的范围内代码修复；远端快照在
  `reports/issue-408/remote-checkpoint.json`。本次跟进提交只记录交付验证。
  任务分支无待交产品改动。下一步审阅 PR；merge 和生产部署未授权。

# Active work — Issue #407 KB / Category loading — 2026-10-07 EDT

- Project: `AI_actuarial_inforsearch`; branch:
  `codex/issue-407-kb-category-loading`; isolated checkout:
  `.codex-worktrees/issue-407`; baseline `b867dda976f580c947850f09b75d499f73af5a63`.
  Scope is KB and Category list/API loading, focused regressions and performance
  evidence. Sibling repositories are off-limits. Root checkout and its unrelated
  modified status/untracked directories are preserved.
- Pre-implementation assessment selected a persistent Sol/high worker because
  scoped SQL aggregation must preserve binding validity and readiness metadata,
  while independent React loading/retry must preserve manifest episode authority,
  polling and permission projections. Fresh Sol/high review is PASS with no
  confirmed in-scope findings; its focused backend module passed 11/11.
  Ponytail full and karpathy-guidelines apply; graphify located the relevant code.
- The user's production read-only profiling isolates the root cause in
  `_prepare_coverage`: full service 57.29/46.62 s, coverage SQL 57.07/46.41 s.
  SQLite selects a noncovering index and visits large vector-table data pages.
  Keeping SQL logic identical while using the existing metadata covering index
  gives service 0.54–0.64 s and coverage SQL 0.35–0.45 s. These measurements
  were supplied by the user; full production output equivalence remains pending.
- Final backend scope is guarded existing-index hints, following the existing
  ops_write stats pattern. Original aggregate and source-fallback logic are
  retained. Category cards render independently of KB/Chat lookups; KB errors
  receive explicit failure/retry state. No deep vector read or external model
  call is the diagnosed cause. No index creation or schema migration is planned.
- Existing 8,704-chunk / 3,072-dimension / two-KB local baseline passed: 37 SELECTs,
  cold 190.7 ms and warm 184.3 ms, no vector JSON reads. Final same-data comparison
  gives hinted 52.2/44.4 ms versus unhinted 182.0/170.7 ms and identical complete
  8,957-byte payloads. These fixtures do not reproduce the production minute-long
  timeout and are not production-root-cause evidence.
- Production read-only samples: anonymous Category 200 / 1.057 s first and
  0.763 s repeated; anonymous KB 200 / 1.051 s first and 0.704 s repeated.
  Admin Category remained loading at 24.8 s then cards appeared by 83.1 s;
  a repeat remained loading at 23.1 s then cards appeared by 57.0 s. These are
  sparse UI observation bounds, not precise API durations or P95 estimates.
  Admin KB repeat showed two KBs by 35.9 s: 580 bound files and 14,306 chunks.
  Category search/navigation worked for guest/admin; public AI files API was
  200 / 1.002 s first and 0.947 s repeated, 35,577 bytes, 213 matching files.
- Current stage: final local quality gate PASS: 2,411 passed, 11 skipped;
  Black, isort and Pylint have zero violations. Vitest 3/3, typecheck, lint,
  build and both dead-code gates PASS. Lint has four existing Hook warnings.
  Built-bundle Chromium/API-fixture smoke PASS across guest/registered/admin,
  with category grids visible in 237–357 ms despite delayed auxiliary requests;
  search/filter and error/retry flows pass. Performance evidence and commands
  are in `docs/issue-407-performance.md`. Fresh independent review is PASS.
  The earlier interrupted review is not a failed cycle. No deployment,
  migration, production writes or post-deployment improvement is claimed.
- Delivery: PR #412 is open at
  https://github.com/ferryhe/AI_actuarial_inforsearch/pull/412
  with implementation commit `698928f`. Local checks and independent review
  are complete. GitHub checks and remote feedback are tracked on this PR;
  the 15-minute checkpoint is due at 2026-10-08 01:34 UTC.
  The task authorizes commit/push/PR, not merge or deployment. Keep #407 open
  until remaining production acceptance is verified.

# Latest work — PR #409/#410 completion repairs — 2026-10-07 UTC

- Project: `AI_actuarial_inforsearch`; branch: `codex/fix-comments-from-review-thread`;
  isolated checkout: `.codex-worktrees/pr-410`. Continue the existing stacked PRs
  from #410 head `ff4215f`; no duplicate PR or sibling-repository work.
  The user authorized repair and the order #410 into #409's branch, then #409
  into main. Branch deletion, deployment, and unrelated cleanup are excluded.
- Selected a simple Luna/medium worker for the reproduced missing `errors=[]`
  test fixture and four CI-pinned Black 26.3.1 format violations. The formatting
  preserves Python ASTs; no quality baseline or dependency lockfile changed.
- Catalog tasks pass the existing stop callback to both execution paths and
  preserve stopped metadata. Explicit-file runs count consumed outcomes and
  classified missing-URL failures; candidate-prefilter exclusions remain
  uncounted. Stopped runs without a success target retain callback progress,
  including 1/4 at 25 percent and 0/4 at zero percent. Target-based scans retain
  their successful-outcome calculations. No framework was added.
- Current focused verification: all 91 Python cases pass across Issue #406,
  task React source, task metrics, and task-stop/nonregression suites. Black,
  isort, Pylint errors-only, and diff check pass on the six touched Python files.
  TaskMetrics Vitest, frontend typecheck/build, and ESLint pass (zero errors;
  four existing Hook warnings and the existing build chunk-size advisory).
- Real Chromium smoke against the local built UI and mock API passes: category
  Insurance survives skip/overwrite/retry changes; start is 1 and target 100;
  actual checked/success/failure/skip metrics are 80/50/20/10 with an error label.
  No production requests or writes occurred.
- Fresh independent Sol/high final review is PASS with no accepted findings.
  Two earlier completed local cycles produced the AC7 repairs. TypeSafe
  jev-latest selected repair_then_review (0.98; confidence 0.97), then confirmed
  rejection of a retracted historical-row claim as scope expansion (1.0).
  Evidence is in ignored root `reports/pr409410/`; implementation stayed with
  the original Luna/medium worker. No review or CI gate was bypassed.
- The broader Windows quality gate also passed: 2,404 tests passed, 11 skipped,
  and no Black/isort/Pylint baseline differences. Its test process began before
  the final cancellation-progress repair; the final behavior is covered by the
  91 focused tests and must receive full GitHub Linux CI before merge.
- Next: commit/push this repair to #410 and require all six GitHub checks before
  each authorized merge. The
  earlier Windows sandbox FAISS/Vitest errors were environment failures; the
  final head must still receive GitHub's full Linux validation.
- Root checkout remains on `fix/gpt6-parameter-compat` with its uncommitted
  advisory status entry and four existing untracked directories preserved:
  `.codex-tmp-agentic-rag/`, `.hermes/research/`, `diagrams/`, `graphify-out/`.

# Latest work — PR #409 review-thread fixes — 2026-10-07 UTC

- Project: `AI_actuarial_inforsearch`; branch: `codex/fix-comments-from-review-thread`.
  Scope is PR #409 review `pullrequestreview-5449172841` only; sibling repositories
  remain off-limits.
- Applied all five requested fixes from that review thread only:
  checked/scanned accounting now advances per consumed worker outcome; catalog
  parameter persistence omits synthetic scan target for explicit `file_urls` runs
  and stores effective `skip_existing`; catalog failure count now renders as
  `errors` in Task metrics; and Catalog form stats reload keeps active category
  scope when option toggles retrigger loading.
- Added focused regression coverage for stop-mid-batch consumed-outcome accounting
  and explicit-file catalog parameter persistence, plus source/runtime assertions
  for metrics label and category-scoped stats reload wiring.
- Validation in this runner:
  `python -m compileall ai_actuarial/catalog_incremental.py ai_actuarial/task_runtime.py` PASS,
  `npm exec -- vitest run client/src/pages/tasks/TaskMetrics.test.tsx` PASS,
  `git diff --check` PASS.
  `python -m pytest ...` could not run because `pytest` is not installed in this environment.
- `npm ci --no-audit --no-fund` installed locked dependencies only (no manifest/lockfile edits).
- Commit `37503b2` is pushed on `codex/fix-comments-from-review-thread`; PR #410
  is open: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/410.
  Current remote feedback check shows no reviews, no review threads, and no
  PR conversation comments. Current CI run `37698134023` concluded
  `action_required` with zero jobs created.
- No production actions, deployments, or cross-repository changes were made.

# Latest work — Issue #406 catalog candidate processing — 2026-10-07 UTC

- Project: `AI_actuarial_inforsearch`; branch: `copilot/bugfix-unify-batch-processing`.
  Scope is issue #406 only; sibling repositories remain off-limits.
- Catalog batching now excludes this-run `seen_urls` in SQL before `LIMIT`,
  keeps nonzero candidate starts bounded to the chosen candidate ID, caps each
  batch by remaining successful target, and reports checked/success/failed/
  skipped counts without forcing an exhausted run to 100%.
- Catalog and Markdown automatic starts use filtered candidate coordinates;
  catalog stats and execution share category plus skip/overwrite/retry filters.
  Tasks persist only allowlisted scope/count/options, not raw payloads or
  credentials.
- Added focused catalog pagination, category, offset, accounting, stats and
  task-history regressions, plus task metrics/form assertions. Frontend
  typecheck, build, TaskMetrics Vitest, ESLint, Python compileall, diff check,
  and extracted SQLite candidate-query smokes passed. Vite reported its
  existing large-chunk warning. Python pytest is blocked in this runner
  (`No module named pytest`), and application test dependencies such as FastAPI
  are also missing.
- `npm ci` installed from the existing lockfile and reported 18 audit alerts;
  no dependency manifests or lockfiles were changed or auto-fixed.
- Commits `259f1a3` and `72361e9` were pushed to issue branch/PR #409. CodeQL
  reported zero Python alerts; JavaScript had no new changes. The latest PR CI
  run `37695605207` ended `action_required` without creating jobs; its logs
  report zero failed jobs. No review threads were present; the Code Review
  binary was unavailable in this environment.
- No production changes, deployments, or cross-repository access.

# Latest work — PR #405 CI formatting repair — 2026-10-06 EDT

- Project: `AI_actuarial_inforsearch`; branch: `fix/gpt6-parameter-compat`.
  Scope is the existing PR's CI failure; sibling repositories are off-limits.
- Failed run `37496604567` passed 2,402 Python tests (one skipped). Its only
  gate failures were Black formatting in `catalog_llm.py`, `chatbot/llm.py`,
  and `openai_capabilities.py`, plus isort spacing in the last file.
- Simple repair: ran the CI-pinned Black 26.3.1 and isort 8.0.1 on those three
  files. Their Python ASTs are identical before and after formatting.
- Verification passed: all 128 existing GPT-6/chatbot/catalog/Weekly/recovery
  regression tests; repository-wide Black/isort scans (zero violations and
  zero baseline differences); changed-file Pylint errors-only; diff check.
- Publish this repair to PR #405, then verify all six checks on its new head.
  The existing Copilot docstring suggestion is nonblocking and outside this
  CI-only repair. No merge or deployment is authorized by this task.
- Existing unrelated untracked directories remain: `.codex-tmp-agentic-rag/`,
  `.hermes/research/`, `diagrams/`, and `graphify-out/`.

# Latest work — Issue #350 knowledge-base list pagination

- Updated: 2026-10-04 EDT. Repository: AI_actuarial_inforsearch; branch:
  codex/issue-350-kb-list-pagination; baseline:
  0a2d6bf6a964104505b44c32865cb8649bf51342. Only this issue worktree is writable;
  sibling repositories remain off-limits. No production writes, deployments,
  production-data cleanup, or schema migrations were performed.
- Validity and tier: Issue #350 remains OPEN and no matching PR existed at startup.
  TypeSafe Jev chose valid (confidence 0.98; probability 0.99). Complex tier was
  selected because the work crosses KB and Chat APIs, their React consumers,
  cross-page identity, and chunk-count query behavior. Ponytail full applied.
- Implemented the shared items/total/limit/offset contract: default 50, maximum
  100, server query/category filters, normalized-title then stable-URL ordering.
  Chat can reach files beyond its former LIMIT 1000. Bounded legacy files/
  total_files/documents aliases remain for compatibility. Customer field
  projections and operator status/diagnostics are preserved. KB binding reads
  and one grouped chunk-version count query now operate on the selected page;
  no per-file COUNT query remains. Issue #273 detail behavior is preserved.
- Both React lists mount one page of 50 rows, use a common 250 ms debounce and
  AbortController cancellation, reset offsets for filters/routes, and recover
  after removal empties the last page. KB removal and Chat comparison selection
  use stable file URLs. API contract documentation and existing smoke mocks
  were updated for the new page shape and asynchronous page loading.
- Verification: `python scripts/quality_gate.py` PASS: full pytest 2,333 passed,
  11 skipped (425.82 seconds), Black/isort/Pylint checks passed with no new or
  stale baseline findings. `python -m pytest tests/test_issue_350_file_pagination.py
  --no-cov -q` PASS (4 tests; 1,101-file API fixture, stable boundaries/filtering,
  customer projection, tail past 1,000, and one grouped count query).
- `npm exec -- vitest run client/src/pages/Issue350FilePagination.test.tsx` PASS
  (5 tests; bounded rows/Remove buttons, page/URL removal, stale-filter and
  stale-route cancellation, cross-page/filter selection, and last-page recovery).
  Existing Chat #347/#351 tests passed (13). Final full `npm exec -- vitest run`
  yielded 116 passed and one unchanged baseline failure in
  client/src/components/a11y/FilterBar.test.tsx (task-filter label).
- `npm run typecheck`, `npm run lint`, `npm run build`, `npm run dead-code:check`,
  Node syntax checks, and `git diff --check` PASS. Lint has 0 errors and four
  existing Hook warnings; build retains its existing large-chunk advisory.
  Two old KB loader source guards were updated to assert the common paged
  cancellation path; focused knowledge source tests passed (36).
- Chromium commands, with the local Vite server on 127.0.0.1:5180:
  `node client/src/pages/Issue350FilePagination.browser-smoke.mjs` PASS;
  `SMOKE_URL=http://127.0.0.1:5180 node
  client/src/pages/chat/Issue351MobileDrawer.browser-smoke.mjs` PASS;
  `SMOKE_URL=http://127.0.0.1:5180 node
  client/src/pages/Knowledge.rbac.browser-smoke.mjs` PASS (five roles).
  These use local API fixtures with the real UI/API client, not production data.
  The new smoke covers 1,101 files, at most 50 DOM rows, scrolling, page changes,
  removal, search/category filtering, and stable comparison selection. Initial
  KB cold/warm first view: 2,898/456 ms; Chat: 547/457 ms. Final rerun after Vite
  compilation: KB 597/446 ms, Chat 560/470 ms. All meet cold <5 s / warm <2.5 s;
  production timing remains outside this local fixture measurement.
- Unrelated root untracked directories remain untouched: .codex-tmp-agentic-rag/,
  .hermes/research/, diagrams/, graphify-out/. The issue worktree contains only
  the scoped changes. No other project was accessed.
- PR #402 is open: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/402.
  The initial implementation commit 1d1ef7b received fresh Sol/high local review
  PASS and all six initial GitHub checks PASS. The single 15-minute feedback
  checkpoint found three confirmed in-scope Copilot threads (4179212013,
  4179212047, 4179212068): literal query search in Chat/KB and this stage record.
- Remote-feedback repair: both new query paths now escape LIKE wildcard characters
  and the escape character, with an explicit SQL ESCAPE clause. Queries containing
  percent/underscore search literal metadata; Chat's legacy keywords retains
  wildcard and comma-separated matching. Seven regression cases first reproduced
  the query problem (five failures) and now pass, alongside the four original
  pagination API cases. This status distinguishes the completed initial review
  from the pending fresh review of the feedback repair.
- Focused repair verification: `python -m pytest
  tests/test_issue_350_file_pagination.py tests/test_fastapi_chat_endpoints.py
  tests/test_issue_273_kb_detail_lightweight.py tests/test_issue_272_kb_rbac.py
  --no-cov -q` PASS (74 tests, 38.66 seconds). Changed-file `python -m black
  --check`, `python -m isort --check-only`, `python -m pylint --errors-only
  --disable=import-error`, and `git diff --check` PASS. Only two API services,
  the pagination regression test, and this status file changed in the repair;
  no frontend behavior or production data was changed.
- Current stage: PR #402 is open. Implementation ca6a140 passed fresh Sol/high
  review and all six GitHub checks. The three original findings were fixed in
  ca6a140, replied to, and their threads resolved. Merge when required checks on
  the latest status-only head pass and the final 15-minute post-push review
  window clears. This status-only head must still complete those gates; no
  additional PR, merge, or product-code change was performed in this update.

# Latest work — Issue #367 unified browser-local date/time display

- Updated: 2026-10-04 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-367-unified-date-format`; baseline `7b192bd49b435906a93631cc73be0e1f3326f709`.
  Only this repository is in scope; sibling repositories remain off-limits.
- Shared date formatting is in place for Tasks, Schedule, Weekly, Users, Token,
  and Logs. New task timestamps carry UTC offsets; legacy task history retains
  its process-local interpretation without changing stored rows. Backup mtimes
  preserve their source epoch. No account timezone model or schema change.
- Remote feedback on PR #401 found a mixed-format task-history ordering bug and
  an exact Weekly period datetime display mismatch. Both are fixed locally:
  history sorts parsed instants before limiting; Database period endpoints show
  browser-local time with a canonical UTC tooltip and retain UTC filter values.
  Weekly list/detail date-only labels remain UTC calendar dates. No #362 enum
  resolver changes were made.
- Final local verification on the six-file PR diff: 81 focused Python
  tests, 12 focused Vitest tests, New York and Shanghai browser smoke, typecheck,
  changed-file ESLint (zero errors; one existing Database hook warning), Node
  syntax check, and `git diff --check` passed. Full Vitest and accessibility
  suites each retain one unchanged baseline FilterBar label failure.
- PR #401 is Ready for review. Remote-feedback fixes were committed and pushed
  as `24d38b485710977ff8f7f96357fe59e582b71599`; mixed task-history ordering
  and exact Weekly datetime display findings are fixed. The UTC date-only
  suggestion was rejected per the period-boundary contract. All three fetched
  Copilot threads received replies and are resolved; the fresh unresolved count
  is zero. On this head, frontend, dead-code, and office-conversion checks pass;
  quality-gate and Python smoke are still running. No second feedback fetch,
  production write/deploy, or production-data cleanup occurred. Next: finish CI,
  verify merge gates, then merge and verify cleanup.
# Latest work — Issue #362 bilingual enum labels

- Updated: 2026-10-04 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-362-status-i18n-r2`; PR #400 is open as a draft and closes Issue
  #362. Only this repository is in scope; sibling repositories remain off-limits.
- The PR's first GitHub check run passed five of six checks. `quality-gate`
  exposed five stale source-contract assertions in four tests that still expected
  literal enum text after this issue moved those surfaces to the shared resolver.
  The same implementation worker updated only those tests; no product code changed.
- Local full pytest passed (2,323 passed, 11 skipped); the five previously
  failing assertions pass after formatting. Black and isort checks pass across
  Python source, tests, and configuration. The quality-gate report showed zero
  new/stale isort or Pylint findings; the unified script was initially blocked
  only by Black formatting in those four tests and will be rerun by GitHub after
  the repair is pushed.
- Next: publish the narrow check repair, wait for all required checks, mark the
  PR ready, then perform the single required remote-feedback fetch after its
  full wait window. Merge only after checks and thread state permit it.

# Active work — Issue #359 Token permissions, expiry, and usage status

- Updated: 2026-10-04 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `agent/issue-359`; baseline `7eb0d3ad6a4929544035197688a2cef11a13a649`
  (`origin/main`). This issue worktree is the only project workspace in scope;
  sibling repositories remain off-limits.
- Issue #359 is OPEN/P1. PR #399 is ready for review and closes the issue:
  https://github.com/ferryhe/AI_actuarial_inforsearch/pull/399. Commit
  `c7fcabdd59a74f3d786f687d6654edbaf391472d` passed the local Python quality gate
  (2,321 passed, 11 skipped), Vitest, Chromium, typecheck, lint, build, dead-code,
  disposable PostgreSQL, and all six GitHub checks. Independent local review and
  TypeSafe review passed.
- The post-Ready feedback fetch found four Copilot inline comments. The
  last-used timestamp write failure reproduced as an authentication 500 and is
  now fixed; 26 focused auth tests pass. TypeSafe Judge found the list group-name
  contract ambiguous under AC1/AC3. At the user's direction to evaluate and
  resolve the comments, the manager selected four canonical create groups and
  an open string group name for list metadata to preserve existing stored data.
  A v0 migration compatibility claim was reproduced as invalid. The
  stale status claim in an earlier draft of this section had no Issue
  acceptance-criteria mapping; this update corrects the project record. Focused
  backend and Settings coverage, typecheck, lint and diff checks pass. Next,
  publish the reviewed fix to PR #399; no second remote feedback window is needed.
- The issue queue heartbeat remains active: `ai-actuarial-inforsearch-issue-to-merge-queue`.
  No production data or services were touched.

# Latest work — PR #398 Caddy template isolation and redirect configuration

- Updated: 2026-10-03 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-328-caddy-compression-cache`; starting head:
  `afe4aa1f7a1c63c0db2febd154fb4de965a34188`. Only this repository was edited;
  sibling repositories remain off-limits.
- Split the standalone `Caddyfile` entrypoint from the app-only `Caddyfile.app`
  fragment, mounted at the generic `/etc/caddy/app.caddy` path. Removed the
  secondary site route and all production host literals from active Caddy
  config, tests, and deployment docs. HTTP redirect hosts now come from
  space-separated `CADDY_APP_REDIRECT_HOSTS`; the fixed HTTPS origin comes from
  `CADDY_APP_REDIRECT_ORIGIN` and Caddy appends `{uri}`. Development defaults
  are localhost; production Compose requires the app site hosts and both new
  redirect values.
- The focused deployment suite passed: 14 tests, including two fake deployment
  overrides, Caddy adapt/validate, HTTP 308 path/query preservation, unknown
  host 421, health 200, host-managed site composition, and the existing static
  cache/security-header checks. Compose config checks confirmed localhost dev
  defaults, production failure when redirect hosts are absent, and successful
  mapping of fictional production values.
- Deployment has not happened and no server values were supplied. Before any
  rollout, operations must preserve the server-local site config and validate
  the combined Caddy entrypoint; compare host/container hashes and inodes with
  active config, and recreate Caddy if the single-file mount is stale because
  reload does not refresh it. PR #398 remains open and unmerged.

# Latest work — Issue #328 missing-asset cache blocker fix

- Updated: 2026-10-03 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-328-caddy-compression-cache`; starting head:
  `011043f454ca900a0d190f797989e713fc07e463`. Only this repository was changed;
  sibling repositories were not accessed.
- The Caddy `/assets/*` handler now converts a successful HTML SPA fallback to
  404. Hashed asset paths receive one-year immutable caching only for 200/206
  responses; it strips `If-None-Match` and `If-Modified-Since` from upstream
  requests so a headerless 304 cannot bypass the fallback check. Asset redirects
  and errors receive `no-store`. Successful HTML responses across the app,
  including `/`, `/index.html`, `/index`, and `/chat`, receive `no-cache`.
- Docker-backed Caddy tests use a file-backed static HTTP server with SPA
  fallback. They prove real hashed JS/CSS files return the expected bytes and
  MIME types, missing assets that upstream serves as the homepage still return
  404 under `If-Modified-Since` and `If-None-Match` (where the upstream alone
  returns a headerless 304), redirects and errors are not cached, and SPA deep
  links serve the homepage with `no-cache`. Gzip responses and
  `Vary: Accept-Encoding` passed end to end; zstd end-to-end behavior remains
  unverified. The focused deployment suite passed (12 tests), including Caddy
  adapt/validate. Black, isort, and
  `git diff --check` passed.
- Fresh gpt-6-sol/high review passed the five Issue #328 cache criteria, including
  the conditional-304 regression. No merge or production deployment was performed.
- CI initially found the old `_CaddyHeaderUpstream` test name in the dead-code
  whitelist after replacing that fixture. The whitelist now references the real
  file-backed `_CaddyStaticUpstream`; local TypeScript and Python symbol gates
  pass with zero baseline findings.
- The first remote unified quality-gate run then exposed Python's platform
  difference in `.js` MIME labels (`text/javascript` on Linux,
  `application/javascript` on Windows); the fixture now accepts both valid labels.
- PR #398 remains open and has not been merged. No production deployment has
  been performed; Huawei/WeChat/Chrome field comparison remains for after a
  reviewed, safe deployment.

# Latest work — Issue #395 full Vitest discovery

- Updated: 2026-10-02 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-395-vitest-discovery`; baseline:
  `3565d51d2cb31f85716306900eb4235b1bcbd6d9` (`origin/main`). Only this assigned
  worktree was changed; sibling repositories were not accessed.
- Added shared test-only jsdom `matchMedia` setup and registered the eleven
  assertion-script suites as meaningful Vitest tests. The RetrievalIndicators
  source path now resolves on Windows. All six Python callers of converted suites
  use `npm exec -- vitest run` and retain their existing success checks.
- Full Vitest passed (32 files / 97 tests); accessibility passed (18 files / 71
  tests); the targeted #351/#347 tests, TypeScript, lint (0 errors; five existing
  Hook warnings), production build, and `git diff --check` passed. The full Python
  quality gate passed (2,310 passed, 10 skipped; Black, isort, and error-only
  Pylint passed). Build retains the existing chunk-size advisory.
- Fresh gpt-6-sol/high review passed all four acceptance criteria with no findings;
  TypeSafe Jev found no local review findings. Commit `f66e4f5` is published in
  Draft PR #396 (`Closes #395`). Its first `dead-code-files` run flagged the
  config-loaded setup file; `knip.json` now lists that exact entry and the local
  combined dead-code check passes. GitHub checks, remote feedback, merge, and
  scoped cleanup continue under the lifecycle evidence.

# Latest work — Issue #365 safe Markdown preview

- Updated: 2026-10-02 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-365-safe-markdown-preview`; baseline:
  `5c73d16f1f79cb12dc6a06988e5263038cde62c6` (`origin/main`). Only this repository
  was changed; sibling repositories were not accessed.
- File Preview chunks use the shared safe Markdown renderer, with a text-only
  image placeholder enabled only in File Preview. The chunk pane has a source
  view that preserves exact text; preview panes stack on mobile while keeping
  tables and code scrollable within their panes.
- The Python quality gate first exposed two stale Issue #285 source assertions
  that forbade the required File Preview renderer use. Updated those guards to
  preserve the shared renderer's safe defaults and assert File Preview's explicit
  inert-image opt-in. The full gate passed: 2,310 passed, 10 skipped, 26 warnings;
  Black, isort, and error-only Pylint passed.
- Focused File Preview tests (2), MarkdownContent assertions, TypeScript, lint
  (0 errors; 5 existing Hook warnings), production build (existing chunk-size
  advisory), dead-code gates, Chromium at 1280px/390px, overflow checks, and
  `git diff --check` passed. Fresh Sol/high review passed AC1–AC5; TypeSafe Jev
  found no review findings.
- Commit `92c52f7` was pushed in PR #393, which was marked Ready after all six
  required checks passed on that head. The single 15-minute feedback snapshot
  found one reproduced AC4 issue: long profile names clipped the mobile chunk-set
  selector. A renderer-map identity comment had no observable AC-mapped effect.
  TypeSafe accepted the selector finding and rejected the renderer-map comment.
- The selector header now wraps and constrains the control; Chromium smoke covers
  a long profile name at 1280px, 390px, and 320px. The follow-up commit
  `cf56ee8` is pushed, and all six required checks pass on that head. Both Copilot
  threads have written dispositions and are resolved, with zero unresolved.
  PR #393 was subsequently merged into `main`; this paragraph preserves the
  original checkpoint, and Issue #395 is now the latest work above.

# Latest work — Issue #351 mobile Chat layout and drawer

- Updated: 2026-10-02 EDT. Repository: `AI_actuarial_inforsearch`; branch: `codex/issue-351-chat-mobile`; baseline: `f245d0890cfad1b078edd30b01f4f9e2ff9a9474` (`origin/main`). Only this repository was edited; sibling repositories were not accessed.
- Chat now starts with its sidebar closed below 768px and open on desktop. Mobile uses an overlay drawer with backdrop, scroll lock, Escape/backdrop close, focus return, and named shared `IconButton` controls. The composer and its controls fit the requested mobile widths.
- Added an Issue #351 component regression and a real-Chromium smoke for 320/360/390/414px at 100% and 200%, including drawer actions and a visible send reply. The smoke uses deterministic backend fixtures while exercising the real Chat UI and frontend API client.
- Manager validation passed the focused Vitest regression, Chromium smoke, typecheck, lint, production build, both dead-code gates, and `git diff --check`. Build reports the existing chunk-size advisory. Fresh Sol/high review passed with no AC-mapped findings; TypeSafe Jev returned no findings.
- Implementation and local review are complete. Commit, Draft PR, required GitHub checks, remote feedback, merge, and cleanup are pending.

# Latest work — Issue #366 form accessibility and responsive controls

- Updated: 2026-10-02 EDT. Repository: AI_actuarial_inforsearch; branch: agent/issue-366. Only this worktree was used; sibling repositories were not accessed.
- Review 9 fixes are complete. Manager independently reran the affected suite and full validation: 14 a11y files / 47 tests, TypeScript, lint (0 errors; 5 existing Hook warnings), production build (existing chunk-size advisory), dead-code checks, 15-surface forms Chromium smoke including File Import and the opened Token form at 390px/200%, keyboard/focus/English-Chinese smoke, and `git diff --check`; all passed.
- File Detail mutation failures now expose action-linked alerts; File Import chooser inputs are keyboard reachable and connected to visible help; Knowledge and Token controls meet the touch target floor; the Token form reflows at mobile width and has 200% coverage.
- Review 10: Database search/filter controls now have explicit IDs, visible labels, and 44px targets. Settings provider edit/routing controls use 48px targets, and Mathpix API-key help is associated through a stable ID. Controlled red/green regressions pass; full validation passes 15 a11y files / 49 tests, TypeScript, lint (0 errors; 5 existing Hook warnings), production build (existing chunk advisory), dead-code, 16-surface Chromium forms smoke, keyboard/focus/English-Chinese smoke, and `git diff --check`. No commit, push, PR, or merge exists; Review 11 is next.
- Review 11: Confirm Delete now labels its confirmation input and provides 48px Close/Cancel/Delete targets. File Detail delete failures render `#error-confirm-delete` as an alert described only by the confirmed Delete action. Chunk Profile creation failures render `#error-profile-create` as an alert described only by Create profile. Categories/System conditional Save controls use 48px targets; the standalone 16-surface Chromium smoke now asserts visible focus in Database, Knowledge, Schedule, Web Listening, Markdown Settings, and Site Configuration and exercises a real failed File Detail confirmation delete. The excluded Close-name and heading-level claims were not changed. Controlled RED/GREEN evidence, focused real-page axe tests, all a11y tests (16 files / 52 tests), TypeScript, browser smoke, and diff check pass. Manager independently reran the full gate: 16 a11y files / 52 tests, TypeScript, lint (0 errors; 5 existing Hook warnings), production build (existing chunk advisory), dead-code, all 16 Chromium form surfaces including the failed Confirm Delete flow, and git diff --check pass. No commit, push, PR, or merge exists; fresh Review 12 is starting.
- Review 12: Site Configuration's primary Run now consumes the Tasks submit-error description. Web Listening records Draft/Validate/Materialize HTTP-200 validation errors by operation and exposes a stable alert described only by the initiating action. Database Clear search, page-jump input, and Jump use 48px mobile targets. Manager independently passed a11y tests (16 files / 55 tests), TypeScript, lint (0 errors; 5 existing Hook warnings), production build (existing chunk advisory), dead-code, 16-surface Chromium smoke, and `git diff --check`; smoke includes the Site Configuration 500 error path, Web Listening HTTP-200 validation errors, and measured Database mobile targets.
- Review 13: Prompt editors link textarea controls to visible card titles, each prompt Save has action-specific alert association, and prompt Cancel is 48px. Categories uses the actual localized crawler hint. Populated Database actions and pagination, plus Site import/list/backups states, use 48px targets and are covered in the 16-surface Chromium smoke. Manager independently reran the full gate: 16 a11y files / 58 tests, TypeScript, lint (0 errors; 5 existing Hook warnings), production build (existing chunk advisory), dead-code, populated/open-state 16-surface Chromium smoke, and diff check all pass.
- Review 14: New review reproduced four further AC3/AC4/AC5 gaps: remaining mobile targets across Database, Tasks History/modal, Pipeline, Settings, and Knowledge; duplicate `button-run-task` test IDs when failed Pipeline stages expand together; missing Pipeline Tab/focus/200% smoke for populated results; and two a11y tests excluded from configured test commands. TypeSafe marked all four valid, and the Judge selected `accept_all_core_only` (0.81 probability). The same worker is fixing these four items in the last repair cycle; one final independent Review 15 remains. No commit, push, PR, or merge exists.
# Latest work — Issue #360 Operator Knowledge RBAC alignment

- Issue #360 delivery checkpoint (2026-10-01): implementation commit `d6aaecb` is pushed on
  `agent/issue-360` in Draft PR #389 (`Closes #360`). The initial exact-head CI run passed all six
  checks; the 15-minute remote review fetch found no reviews, comments, or unresolved threads.
  Local quality gate passed (2,307 passed, 10 skipped); fresh cycle-4 Sol/high review and
  TypeSafe assessment found no acceptance-mapped findings.

- Cycle-2 review fixes: catalog-only users can load Chunk Profile choices and submit a plain KB
  create without task diagnostics; Create-and-index remains tasks-gated. The four-role matrix covers
  all 29 in-scope RAG admin/Ready Data endpoints. Chromium enters Knowledge via navigation and
  opens detail through the list for Operator/Admin. Full quality gate passed: 2,306 passed,
  10 skipped; Black, isort, and Pylint clean.

- Review-fix 1: `Create and index` is now rendered only with both `catalog.write` and
  `tasks.run`; plain KB creation remains catalog-only. The executable FastAPI mutation matrix
  covers 16 catalog/task/config endpoints for guest, registered, operator, and admin. The
  Chromium role matrix covers all protected Knowledge/KBDetail action controls plus the
  catalog-only edge. Focused suite: 73 passed. Full quality gate: 2,305 passed, 10 skipped;
  Black, isort, and Pylint have zero violations. No commit, push, or PR was created.

- Updated: 2026-10-01 UTC. Repository: `AI_actuarial_inforsearch`; branch:
  `agent/issue-360`; baseline `02da9d7cc575a724cb15e7ad2a8b88eee2a851c6`. Only this
  repository's assigned worktree was used; sibling repositories were not accessed.
- Knowledge UI and service writes now distinguish `catalog.write` for KB catalog mutations,
  `tasks.run` for indexing and per-KB Ready Data automation, and `config.write` for Chunk Profile
  and cleanup writes. The service rejects authenticated callers missing the operation's specific
  capability while preserving the legacy config-token fallback.
- Guest/registered/operator/admin mutation coverage and Operator/Admin browser smoke were added.
  Focused source/RBAC tests pass (46); Chromium smoke, typecheck, lint, production build,
  dead-code checks, and `git diff --check` pass. Full quality gate passes: 2,303 tests, 10 skipped,
  24 existing warnings; Black, isort, and Pylint report zero violations.
- Implementation and verification are complete. Fresh local review and PR creation are pending.

# Latest work — Issue #354 filtered and full catalog exports

- Updated: 2026-09-30 EDT. Repository: `AI_actuarial_inforsearch`; branch: `agent/issue-354`; baseline `d479053008c9257e182760e545bc4c320bb87983`. Only the assigned Issue worktree was edited; sibling repositories were not accessed.
- `/api/export` now uses the Database parser, active-only filtering, public projection, weekly snapshot membership, complete paged results, count header, and bounded audit detail. `/api/export/full` is capability-gated by `export.full`; deleted and internal fields each require explicit selection. Review fix 1 makes snapshot queries start from `weekly_snapshot_members`, so frozen `original_filename` and `first_seen` survive later file changes or current-row removal and drive filename search, date bounds, and first-seen sorting.
- Database now distinguishes filtered and full-admin exports by capability, uses current filter parameters, blocks filtered export when deleted records are displayed, and requires confirmation for full export. The ordinary control explicitly says “Export current filtered results” / “导出当前筛选结果”; the full-admin confirmation lists the current deleted and internal-field selections.
- Focused API/source suite: 29 passed after review fix 1. AC-4 frontend source-contract suite: 13 passed. Black, isort, `git diff --check`, TypeScript typecheck, lint, and production build passed; lint keeps five existing Hook warnings and build keeps its chunk advisory. TDD baseline/red-green evidence is in `.git/codex-issue-to-merge/evidence-354/`.
- Manager completed the Chrome CSV download row-count verification. Commit `7dca3256c3403299e4f4f5b64586ae5652a741dd` is published in Draft PR [#387](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/387) with `Closes #354`. Round 2 Sol/high review passed with no mapped findings; TypeSafe returned no findings. The first Draft CI run flagged the new FastAPI route in the dead-code whitelist. Added `api_export_full` to the existing route whitelist; the same symbol check and `git diff --check` pass locally. The repair commit and current-HEAD CI rerun are next; Ready review, remote feedback, merge, and cleanup remain pending.

# Latest work — Issue #356 canonical email-user roles

- Required-check repair: exact-head CI run `36646491306` failed only the Python symbol dead-code
  gate. The new FastAPI roles route is now registered in the repository's reviewed framework
  whitelist, and the superseded unreferenced `VALID_USER_ROLES` constant was removed. The canonical
  assignable schema, role behavior, token groups, and API/UI contracts are unchanged. Focused and
  exact dead-code validation details are recorded in the check-repair worker report.
- Updated: 2026-09-29 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-356-canonical-roles`; baseline:
  `21e4cc58a5a02d6ee55637a620128b047489cfce`. Only this assigned worktree was
  edited; sibling repositories were not accessed.
- Added the authenticated `/api/admin/roles` contract for the four assignable email-account
  roles: `registered`, `premium`, `operator`, and `admin`. The same contract drives backend
  validation and the Users menu. `guest` and legacy `operator_ai` are rejected by email-user role
  writes; the separate API Token group contract is unchanged.
- Users and Profile show bilingual role names. Stored `operator_ai` is shown as the localized
  legacy alias, exposes canonical `operator` to the Users menu, and migrates on the next role save.
  The existing atomic activity/audit path now records `old_role` and `new_role` for role changes.
- Registered and Premium descriptions explicitly state equal permissions and different daily AI
  chat quotas in English and Chinese.
- TDD red evidence: the new Issue suite failed 4/4 on the baseline for the absent schema/inventory,
  absent canonical legacy projection, hard-coded menu/missing copy, and missing endpoint. Green:
  the final Issue/auth/permission/admin-protection suite passed 52 tests and the related React
  authority/source suite passed 9 tests. Black, isort, `git diff --check`, frontend typecheck,
  lint, and production build pass; build retains the existing chunk-size advisory.
- A disposable live FastAPI + Vite browser smoke passed in Chinese and English. It showed exactly
  four localized menu choices with descriptions and no guest or legacy option. Saving the displayed
  legacy alias sent `operator`; SQLite then held `operator`, with atomic audit evidence
  `old_role=operator_ai` and `new_role=operator`. Browser console contained no app errors; only
  unrelated browser-extension warnings. Temporary services, browser tab, and smoke data were
  removed.
- Local review: fresh Sol/high reviewer PASS with no acceptance-mapped findings;
  TypeSafe review-summary coverage 0.96. Manager final validation passed 61 focused
  tests, Black, isort, `git diff --check`, frontend typecheck, lint, and build.
- Delivery: ready for the manager-owned commit, push, and Draft PR workflow. No blocker is known.

# Latest work — Issue #348 pipeline error visibility

- Updated: 2026-09-29 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-348-pipeline-ui`; baseline: `e9cdd59f432cea1539758162f91d0a3c9abbbb0a`.
  This assigned worktree is the only edited workspace; sibling repositories and `graphify-out/`
  were not accessed.
- `NativeTaskRuntime.pipeline_baton_status` keeps raw baton `round_status` and child task
  statuses while deriving compact stage statuses, counts, and a display-only
  `completed_with_errors` summary. A persisted stopped task remains stopped even when its task
  record carries the usual stop message. Existing #319 `kb_results` failures also produce a
  derived RAG failure without changing baton state. The response exposes only `error_count`,
  `failed_items`, `first_error_code`, and `first_error_summary`; detailed #368 item errors stay
  in the task log.
- Pipeline Baton renders the summary, text/icon/color failed headers, default expandable failed
  cards, a failure-only filter, item versus task error counts, a manual latest-failure log link,
  and generic Rerun wording whenever prior stage results exist. It does not retry tasks or change
  #319 continuation behavior.
- The production `PipelineBatonResults` component renders summary states, failed-stage expansion,
  failure-only filtering, and manual log callbacks. Its executable TSX regression plus focused
  Python and #319 coverage passed (106 Python tests); Black, isort, and `git diff --check` passed.
  After local dependencies were restored, typecheck and the executable TSX regression pass; lint
  passes with five pre-existing warnings and build passes with its existing chunk advisory.
- Round-2 corrections mark the valid current stage failed for an otherwise unprojected hard
  orchestration error and preserve the raw `error` round status. A link is rendered only for a
  current task ID present in task history/active tasks. Legacy catalog tasks without the #368
  `failed_items` key derive that count from an exact bounded `Catalog errors: N` message; explicit
  values, including zero, remain authoritative.
- Round-3 correction keeps earlier failed stages while also projecting a later valid current stage
  as failed for a terminal hard orchestration error. It increments the derived count only when the
  current stage was not already failed, and makes that terminal context the latest failure.
- Round-4 correction preserves ordered RAG result failures and lets a positive-output non-KB
  current task show terminal orchestration context without changing an already failed count.
- Round-5 projection maps failed advancement to its attempted target stage and overlays terminal
  RAG orchestration context while preserving raw state and prior failure records.
- Fix-5 real-transition coverage now drives scheduled markdown-launch and RAG Ready Data OSError
  failures through `PipelineBaton.tick()` and into the runtime projection.
- Round-6 repair keeps the general 100-row in-memory history cap. If the retained baton source is
  evicted, the status projection reloads only its matching durable source/child records even when
  a late child remains in memory; current active/in-memory records override older snapshots.
- Publish-gate repair moves the Issue #237 source assertion for pipeline task status/ID rendering
  to `PipelineBatonResults.tsx`, where the extracted production rendering now resides.
- Publish-gate repair makes the Results component's internal stage-task and stage interfaces
  private; the executable TSX test validates its steps through the component props type.
- Final-candidate repair adds English `Running` and Chinese `运行中` pipeline status entries;
  focused source and executable TSX coverage verifies locale presence and active-summary rendering.
- Final local gates pass on the current candidate: the Issue-focused Python suite has 112 tests;
  the executable TSX regression, typecheck, lint, production build, dead-code check, Black, isort,
  Pylint baseline, `git diff --check`, and the repository quality gate all pass. The quality gate
  ran 2,235 tests with 10 skipped. Lint retains five existing Hook warnings and the build retains
  its existing chunk-size advisory.
- An isolated real FastAPI + Vite browser smoke passed in English and Chinese at desktop and
  320x800. It verified the Daily Pipeline summary, five stage cards, failed-only filter, expanded
  settings, and authenticated API requests. The 320px viewport had no horizontal overflow
  (`bodyScrollWidth` and root scroll width both 320), and the browser console had no warnings or
  errors. Temporary services and ignored smoke data were stopped and removed.
- Final-candidate review found and repaired the missing bilingual `running` summary label. A fresh
  Sol/high follow-up raised only localization of raw child-task status tokens; TypeSafe review
  found no direct acceptance-criterion mapping, and TypeSafe Judge rejected it as out of scope
  with 0.99 probability because AC-3 covers stage headers and AC-7 preserves raw child statuses.
- Delivery is ready for the authorized commit, push, and pull request flow, followed by exact-head
  CI and the required remote-feedback window.

# 最新状态 — PR #380 与已合并的 PR #379

- Updated: 2026-09-29 EDT. Repository: `AI_actuarial_inforsearch`; branch:
  `codex/issue-375-audit-ip`, now based on `origin/main@5d8e74568eb8d44d3faed0bd80038ae598b1de26`.
  This worktree is the only workspace used; sibling repositories were not accessed.
- PR #374 / Issue #346 was aligned, all required checks passed, and PR #374 was merged as
  `119423437847aecd3a6a60c36281eec5604a967c`.
- PR #379 / Issue #377 was submitted by external contributor `mikemikimike`. Its CI initially
  reported the nested maintenance CLI as unused because `scripts/maintenance/*.py` was missing from
  `script_entry_globs`. The CLI glob fix was pushed to the contributor's maintainer-editable fork;
  all five CI jobs then passed and PR #379 merged as `5d8e74568eb8d44d3faed0bd80038ae598b1de26`.
- Issue #375 passes normalized `client_ip(request)` through the atomic admin role/active update
  path into both activity and audit rows. Storage and real FastAPI trusted-peer + XFF regressions
  read back the temporary SQLite DB. Existing #372 transaction/concurrency and #352 fail-closed
  coverage remains intact. Local quality gate passed 2,197 tests with 10 skipped; GPT-6-sol
  extra-high review passed; TypeSafe AI judged PR-stage work complete while the post-deployment
  Caddy canary and actual API DB readback remain pending. No historical NULL values were changed.
- PR #380 / Issue #375 is open. Merging latest main exposed only a status-file conflict; all code
  merges cleanly. The conflict is resolved here while retaining the #379 merge record and #380
  status. No production operation has been performed.
- Next action: verify the merged tree, commit and push the normal merge commit to PR #380, then check
  the resulting CI. Complete the Caddy canary and actual database readback after deployment.

# Latest work — Issue #376 deterministic latest chunk-set lookup

- Updated: 2026-09-14 EDT.
- Repository: `AI_actuarial_inforsearch`; branch: `agent/issue-376-kb-latest-index`;
  baseline: `origin/main@80fb03a`. Sibling repositories were not accessed.
- Added formal SQLite schema v15 migration `add_file_chunk_sets_latest_index_v15` and
  covering index `idx_file_chunk_sets_latest` on `(file_url, profile_id, updated_at DESC,
  created_at DESC, chunk_set_id DESC)`. Fresh schema, strict v14 validation, ORM metadata,
  and the legacy SQLite chunk-contract rebuild path are synchronized.
- Correlated `LIMIT 1` selectors in `Storage`, `_KBListStorageView` batch/fallback paths,
  and `StorageV2RAGMixin` now use `chunk_set_id DESC` as the final tie-breaker. Existing
  latest-any-status, dirty, and orphan semantics are unchanged; no new `ROW_NUMBER` query
  was introduced.
- Manager independently proved TDD red for all 8/8 focused Issue #376 cases. After all
  implementation and review corrections, the final full quality gate passed 2,195 tests plus
  Black, isort, and Pylint. Under Node 20.19, both dead-code files/symbols checks passed, and
  lint/typecheck/build passed with five existing hook warnings and the existing chunk advisory.
  Python smoke passed 13 + 31 + 3/3 tests.
- Manager endpoint confirmation now passes 1/1 in 2.92s. The post-review full quality gate
  passed 2,194 tests before the version-zero correction below.
- Review corrections: v15 validation now requires the named index on `file_chunk_sets` with the
  complete ordered ASC/DESC key signature, while pre-v15 sources reject both a premature named
  index and an identically shaped wrong-name impostor. Renamed-current and renamed-v14 cases were
  red before this correction; renamed, wrong-order, wrong-column, and unknown-index cases are
  green afterward. Compact coverage now includes current/stale/empty composition, multi-profile,
  multi-KB, orphan/cross-file exclusion, latest-any-status failed/building/empty rows, and the four
  required KB HTTP projections. The endpoint fixture aligns its current embedding runtime and its
  explicit 1,536-dimensional KB/index identity so list, detail, chat, and bindings isolate
  `binding_dirty`; narrow wrappers preserve each complete original source-state payload on both
  `Storage` and `_KBListStorageView` paths and override only `serving_stale=false`, so the
  independent published-stale classification cannot mask binding dirtiness.
  Final Codex review found that a legitimate `user_version=0` database with the otherwise
  current pre-v15 schema was rejected solely because it lacked the v15 latest-chunk-set index.
  The version-zero tolerant validation path now applies the exact pre-v15 index normalization
  after its pre-v13 stats-index normalization. Regression coverage proves status/plan/apply,
  seeded-data preservation, and idempotency; the existing premature named and wrong-name
  v15-shaped index cases remain invalid. The expanded Issue/schema suite passes 72 tests.
- Query-level synthetic benchmark (not a production HTTP SLA): SQLite 3.53.1 with 2,595
  `file_chunk_sets`, 1,101 bindings, and one profile, using 3 warmups plus 20 samples. Baseline
  median/p90 was 311.270/356.089 ms; candidate median/p90 was 1.009/1.071 ms. Both returned the
  identical 1,101-row result, for a 308.5x median speedup.
- Same-shaped exclusions: `Storage.list_file_chunk_sets` and the SQLAlchemy equivalent list
  all versions rather than select one latest row; embedding-service scans are chronological
  ready-set iteration; the pre-existing profile-filter `ROW_NUMBER` selector already has the
  required ID tie-breaker. The ready-only helper was updated because it is a true latest
  selector, while latest-any-status composition behavior remains unchanged.
- Validation: focused pytest uses `-o addopts=''`; repository `pytest-cov` is available. The
  manager's latest four-surface endpoint run passes 1/1 in 2.92s with the contract-preserving
  wrappers. The post-review quality gate passed 2,194 tests before the version-zero correction;
  after that correction, the 72-test Issue/schema suite passed. Black, isort, and
  `git diff --check` also pass; the final focused correction rerun passes 5 tests.
- Delivery: per Issue #376 instruction, no commit, push, PR operation, merge, or production
  modification was performed.
- Next action: manager review of the formatted, uncommitted diff and final benchmark/status copy.

# Latest work — Issue #349 CI snapshot-transaction repair

- Updated: 2026-09-14 Asia/Shanghai.
- Repository: `AI_actuarial_inforsearch`; branch: `fix/349-kb-reembed-hint`.
- Scope: only `_KBListStorageView`'s read-only agentic-ready source/publication
  projection. Sibling repositories were not accessed; the committed frontend
  RBAC assertion update was preserved.
- Fix: both `get_agentic_ready_source_state` and
  `get_agentic_ready_publication_state` explicitly begin a transaction when
  needed, so prepared list projections retain SQLite's read-snapshot contract
  at the publication lookup boundary. The list view connection closes to
  release the read transaction.
- Validation: `git diff --check`, Black, isort, and `npm run dead-code:check`
  passed. `tests/test_fastapi_rag_admin_endpoints.py::test_kb_embedded_public_projection_uses_one_sqlite_read_snapshot[list]`
  and `[detail]` both pass locally; all 181 impacted backend tests pass.
- Committed and pushed by Issue #349 manager on branch `fix/349-kb-reembed-hint`.

# Latest work — Issue #349 reviewer round-1 corrections

- Updated: 2026-09-14 Asia/Shanghai.
- Repository: `AI_actuarial_inforsearch`; branch: `fix/349-kb-reembed-hint`.
- Scope: minimal corrections for reviewer findings F1/F2 only: the shared KB reason
  contract, chat/RAG list serialization, Categories presentation/gating, focused tests,
  and this record. Sibling repositories were not accessed.
- Added `published_stale_but_servable`: compatible indexed KBs with the existing
  ready-data `serving_stale` signal retain Ask AI availability and report `ready` without
  requiring re-embedding. Both list serializers pass the existing source-state signal to
  `classify_kb_status`; no publication subsystem was added.
- Categories now displays shared non-healthy reason copy and combines its existing
  permission/dedicated-KB logic with `isAskAiAvailable` when a chat-KB status is present.
- Validation: Black, isort, `git diff --check`, and Python compilation passed. Focused
  tests passed: 49 total (`test_kb_status_reason.py`, `test_knowledge_react_source.py`,
  and the legacy chat knowledge-base endpoint test). Full chat/RAG endpoint modules exceeded
  the sandbox's 30-second command window after collection/startup. Frontend typecheck is
  blocked because root `node_modules` is absent.
- Delivery: per manager instruction, do not commit, push, or modify PR state. No untracked
  files; the listed implementation files are intentionally uncommitted for manager review.
- Next action: manager reviews and commits the narrow diff; in an environment with frontend
  dependencies, run `npm run typecheck` and the full endpoint modules before push.

# Latest work — Issue #349 KB re-embedding hint / Ask AI serving gate

- Updated: 2026-09-14 Asia/Shanghai.
- Repository: `AI_actuarial_inforsearch`; branch: `fix/349-kb-reembed-hint`.
- Scope: KB status serialization in RAG admin/chat, Knowledge/KB Detail/Chat presentation,
  focused status tests, and this record only. Sibling repositories were not accessed.
- Implemented a structured `reason` contract: `embedding_incompatible`, `content_dirty`,
  `binding_dirty`, `index_missing`, `index_building`, `publish_failed`, `serving_disabled`,
  and `healthy`. `needs_reembed` is true only for `embedding_incompatible`; the legacy
  `needs_reindex` remains an operations/backward-compatibility signal.
- Completed compatible indexes now return `serving=true`, `usable=true`, and `availability=ready`
  during content/binding maintenance. Ask AI gates on this serving state, not generic reindex work.
  The UI maps every reason in English/Chinese and keeps the existing Ready Data serving/operation
  display separate from KB Ask AI availability.
- Added `tests/test_kb_status_reason.py` covering every reason, re-embed and serving decisions,
  frontend mapping source contracts, and the all/regulation/ai generic-reindex regression.
- Verification: `python -m py_compile ai_actuarial/kb_status.py ai_actuarial/api/services/rag_admin.py ai_actuarial/api/services/chat.py` passed; `git diff --check` passed;
  `python -m pytest -q tests/test_kb_status_reason.py tests/test_knowledge_react_source.py` passed
  (46 tests). Broader focused endpoint runs were started but could not complete within this session's
  30-second command window. Existing TSX runtime and `npm run typecheck` are blocked because this
  worktree lacks `node_modules` (including `node_modules/.bin/tsx`, React, and type packages).
- Delivery: per task instruction, do not commit, push, or open a PR in this sandbox session.
- Next action: install the lockfile frontend dependencies in an authorized environment, then rerun
  the complete focused endpoint/frontend suite and review the uncommitted diff before delivery.

# Latest work — PR #344 quality-gate repair

- Updated: 2026-09-09 EDT.
- Repository: `AI_actuarial_inforsearch`; branch: `codex/fix-pr-344-checks`.
- Baseline: latest `origin/main@98af167`; PR #344 was already merged.
- Request: fix the failed checks associated with PR #344.
- CI run `34410277972` passed all 2,114 tests and four other jobs, but
  `quality-gate` failed on Pylint E1101 in `tests/test_api_logging.py`:
  full-repository inference attributed `baseFilename` to `_CapturingHandler`.
- Fix: use `getattr` without a default after the existing `FileHandler` guard.
  Missing attributes still raise; the existing path, duplicate-write, count,
  replacement-type, and unrelated-handler assertions remain unchanged.
- Changed files: `tests/test_api_logging.py` and this status entry only.
- Validation: 11 focused logging tests passed; focused Pylint, both dead-code
  gates, and `git diff --check` passed. Local full pytest: 2,103 passed, 10 skipped; one Docker test failed because
  the local Docker engine pipe is absent (also failed outside the sandbox).
  Full formatting/static scans are still running.
  The original full Pylint scan passed locally on Windows, so Linux CI on the
  repair PR is required to confirm the original CI failure is removed.
- Original PR's Copilot suggestion concerns a hypothetical future scheduler
  test ambiguity and does not explain this failure; left outside this scope.
- Preserved the pre-existing local status notes and untracked
  `.codex-tmp-agentic-rag/`, `diagrams/`, and `graphify-out/`; those are excluded
  from this commit. No sibling repository was accessed.
- Delivery: publish a follow-up PR; check exact-head CI and remote feedback
  after approximately 15 minutes. No merge was requested.
- Blockers: none. Next action: confirm all repair-PR checks pass and assess
  remote comments against this check-repair request.

---


# Project Status — Issue #338 schema v12 migration source validation

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Project\AI_actuarial_inforsearch-issue-338`
- Branch: `codex/issue-338-schema-v12-migration`
- Baseline: `origin/main@411b0d477e68b8dd1748f44139e0ad07e9cbc729`
- Issue: `#338 fix(schema): v12→v13 source validator rejects a legitimate v12 DB as invalid`
- Review state: `C:\Users\ferry\.codex\issue-to-merge\AI_actuarial_inforsearch\issue-338\review-state.json`
- Delivery stage: Draft PR #339 is Ready; the single remote-feedback window is assessed and one
  documentation-only AC-1 fix is locally validated; ready to push the final candidate
- Progress heartbeat: id `issue-338`, status `ACTIVE`, 15-minute cadence

## Issue #338 acceptance criteria

- AC-1: `_accept_version_12_source` accepts the exact genuine v12 source shape: no v13 stats
  covering indexes, no v14 `markdown_terminal_source_state` table, and the supported legacy
  `api_tokens` physical column order; it remains strict about unrelated future or malformed schema.
- AC-2: `schema_status` classifies that source as `needs_migration`, with `can_apply=true` and
  `blocked=false`, and `schema_plan` exposes the exact v12→v13→v14 migration chain.
- AC-3: `apply_schema` on an isolated genuine-v12 fixture reaches current schema v14, applies the
  v13 and v14 migrations exactly once, preserves seeded business rows and table counts, passes
  `PRAGMA foreign_key_check`, and is a no-op when repeated.
- AC-4: The same v14-signature regression is repaired for genuine v10 and v11 source shapes;
  v1–v9 and v13 remain unaffected, invalid/future-object shapes stay fail-closed, and the focused
  SQLite schema-runner suite plus repository-required checks remain green.

## Issue #338 scope, baseline evidence, and non-goals

- Worker-owned files are limited to `ai_actuarial/sqlite_schema.py`,
  `tests/test_sqlite_schema_runner.py`, the incorrect historical fixtures in
  `tests/test_issue_306_metadata_only_chunk_stats.py`,
  `tests/test_issue_266_weekly_snapshots.py`, and
  `tests/test_issue_267_weekly_explanations.py` that otherwise retain later v13/v14 objects. This
  manager owns this status record.
- Non-goals: production schema apply or deployment; server/database access; rebuilding
  `api_tokens`; per-version signature refactoring; schema registry redesign; dependency upgrades;
  sibling repositories; security frameworks; or speculative abstractions.
- The assigned worktree is clean. `HEAD`, `origin/main`, and merge-base all match the supplied
  baseline `411b0d477e68b8dd1748f44139e0ad07e9cbc729` on the assigned branch. The controller checkout
  with unrelated Issue #317 work and every sibling repository remain off-limits.
- Duplicate search found no equivalent active or closed-unmerged implementation. PR #330 is the
  v14 regression source and PR #323 is the v13 migration dependency; neither fixes #338. Remote
  heads are only `main` and unrelated `archive/flask-only-system`.
- An isolated current-schema database was converted to the genuine v12 shape, including legacy
  `api_tokens` order. Baseline `_accept_version_12_source` returned false and `schema_status`
  returned `invalid`, `blocked=true`, and `can_apply=false`, with one missing required table and
  two normalized future-index signature differences. `PRAGMA foreign_key_check` was clean.
- Blame and function history trace `_accept_version_12_source` to PR #323. PR #330 added the v14
  table and the correct v13 source validator but did not update the v12 validator to normalize that
  later table. The premise is current and delivery is classified `code-change`.
- The worker reproduced the identical PR #330 regression on genuine v10 and v11 sources: their
  validators normalize their own later weekly tables and the v13 indexes but not the v14 table.
  They are included as same-shaped AC-4 siblings; v1–v9 already tolerate the allowlisted backfill
  table and v13 already handles the v14 absence explicitly.
- Review-policy override: none; findings must be realistically reproducible and map directly to an
  acceptance criterion above. Required checks remain separate merge gates.

## Issue #338 required validation

- New regression test must show expected failure before the source fix and pass afterward.
- Focused: `python -m pytest -q tests/test_sqlite_schema_runner.py`.
- Final: `python scripts/quality_gate.py`, `npm run dead-code:files`,
  `npm run dead-code:symbols`, and `git diff --check`.
- Remote merge gates: `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke` on the exact PR head.

## Issue #338 implementation and local review

- The v12 validator now treats `markdown_terminal_source_state` as a later table, normalizes its
  legitimate absence together with the two v13 stats indexes, and rejects the table or indexes when
  they appear ahead of the recorded version. The valid-signature fast path now also checks v12.
- The same PR #330 regression was repaired explicitly for v10 and v11. No validator uses a broader
  `tolerate_backfill` path, and v1–v9/v13 behavior is unchanged.
- The regression fixture reproduces the supported legacy `api_tokens` physical order, seeds a file
  and API token, and removes exactly the v13/v14 objects from a fresh current schema. It verifies
  classification, exact plan/apply results, all pre-existing table counts, seeded rows, foreign
  keys, idempotency, and future/malformed fail-closed cases.
- TDD first failed because the genuine v12 status was `invalid` instead of `needs_migration`; the
  complete-future signature test also first failed because it bypassed source validation. Direct
  v10/v11 probes returned false before their sibling fix and true afterward.
- Fresh read-only review round 1 independently inspected the complete diff and history, ran the
  genuine v10–v13 status matrix and 78 related tests, and returned PASS with no valid finding.
- The first full quality gate exposed seven older v10/v11 migration tests whose setup still kept
  v13 indexes and the v14 table. The same worker changed only nine fixture-setup lines; no product
  assertion or explicit future-object invalid case changed. The two affected files then passed all
  59 tests, and the five-file schema combination passed all 137 tests. Because the state script had
  closed local review after PASS and the repair was setup-only, the decision log records why no new
  review round was opened.

## Issue #338 local validation so far

- Worker and manager independently ran the schema-runner, Issue #306, and Issue #322 combination:
  78 passed with only three existing SWIG deprecation warnings.
- Full `tests/test_sqlite_schema_runner.py`: 57 passed. Black/isort and `git diff --check` passed.
- The first complete quality-gate pytest run produced 2,074 passes, 10 skips, and 30 failures:
  23 frontend runtime tests lacked `node_modules` in the fresh worktree, and seven historical schema
  fixtures retained future objects. `npm ci` installed the lockfile dependencies without tracked
  changes, and the seven fixture failures were corrected as described above. A clean full rerun is
  the final evidence below; npm's existing audit notices are out of scope and caused no dependency
  change.
- The clean full `python scripts/quality_gate.py` rerun passed: 2,104 tests passed, 10 skipped, and
  Black, isort, and Pylint all passed. `npm run dead-code:files` and
  `npm run dead-code:symbols` each passed with zero baseline findings; final
  `git diff --check` passed. The five-file historical schema combination remained green at
  137 passed after the fixture correction.

## Issue #338 remote feedback and checks

- Draft PR `#339` was published from `e0a330009f9dbc4d8fecbca8edca9ef822551fc7` with exact
  `Closes #338`, then marked Ready. The single remote snapshot was fetched after 694 seconds.
- There were no human reviews, PR conversation comments, or Issue #338 comments. Copilot left two
  inline threads. The same persistent worker and manager rejected the machine-path suggestion as
  outside AC-1–AC-4: this project requires the status record and the same file already uses this
  path convention. No path content changed.
- The v12 validator docstring omitted its v14-table fail-closed contract. This maps directly to
  AC-1 and was handled with a one-line documentation-only correction; no behavior changed. The
  focused v12 selection passed 5 tests with 52 deselected, Black passed, and `git diff --check`
  passed.
- On the pre-feedback-fix head, all five remote merge gates completed successfully:
  `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and `python-smoke`.
  The same gates must complete successfully again on the final documentation-only head.

## Issue #338 blockers or decisions needed

- None.

## Issue #338 recommended next action

- Commit and push the one-line remote documentation fix plus this final status update, verify all
  five required checks on the exact final head, then merge PR #339 and verify Issue #338 closure.

# Project Status — Issue #333 content-first article lists

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\44b9\AI_actuarial_inforsearch`
- Branch: `codex/issue-333-content-first-lists`
- Baseline: `origin/main@e3f028d1f67910a98e38ae5dfb4045c8d75e6f30`
- Issue: `#333 feat(ui): make Home, Weekly, and Database article lists content-first`
- Review state: `C:\Project\AI_actuarial_inforsearch\.git\codex-issue-to-merge\issue-333.json`
- Delivery stage: local review and final validation complete; ready to create the Draft PR

## Issue #333 acceptance criteria

- AC-1: The full Home Materials, Categories, and Weekly Updates stat cards are links to
  `/database`, `/categories`, and `/weekly`, with visible hover and keyboard-focus states; Sources
  remains unchanged.
- AC-2: Home keeps the deterministic snapshot `file_count`, requests/renders at most the newest six
  preview files, and each file card shows its title, available full Category, Keywords, Summary,
  and a localized month/day date only. The original timestamp remains in semantic `time` metadata
  or a tooltip, file cards open File Detail, and missing metadata adds no empty label or placeholder.
- AC-3: The selected Weekly detail retains the existing historical master-detail flow, retrieves
  every snapshot member without a six/eight-item loss, and groups articles by the first trimmed
  non-empty semicolon-delimited Category. Unclassified items use localized Uncategorized, group
  counts are exact, and the complete original Category remains visible on each card.
- AC-4: Every Weekly category group has a keyboard-operable expand/collapse control with correct
  expanded/collapsed semantics, and every selected-week article remains reachable after grouping.
- AC-5: The Database desktop list uses a wide article-content area for title plus available
  Category, Keywords, and a bounded wrapping Summary. Outside that area it retains only Source,
  First seen, Actions, and the existing selection control; it removes the standalone Category,
  Markdown, Size, and Last seen/Date displays, and displayed dates always use `first_seen`.
- AC-6: Database filters, sorting, pagination, row navigation, preview, download, AI Explain,
  deletion/recovery paths, bulk selection, and permission behavior remain usable. Action and
  selection controls do not trigger row navigation; icon-only actions have localized accessible
  names and tooltips.
- AC-7: The Weekly files read response adds only public `category`, `keywords`, and `summary` via a
  lightweight Catalog join and does not read Markdown/body content or expose sensitive fields.
  Database declares and renders its existing public `keywords` field. Missing or malformed public
  metadata degrades without `null`, `undefined`, crashes, or visual noise.
- AC-8: Loading, empty, partial-data, and error states remain clear; added English/Chinese copy and
  short-date formats are correct; 320, 768, 1024, and 1440px layouts have no horizontal overflow,
  including long titles, keywords, summaries, and category names.
- AC-9: Focused Dashboard, Weekly, Database, Weekly API/service/storage, permissions/data-contract,
  and responsive accessibility tests pass, together with frontend lint/type-check/build, both
  dead-code gates, Python smoke, the unified quality gate, browser smoke, and desktop plus 320px
  before/after screenshots.

## Issue #333 scope, evidence, and non-goals

- Worker-owned components are the Home stat/Weekly surfaces, shared Weekly read/view helpers and
  card UI, Weekly selected-detail grouping/loading, Database article rows and `FileItem` metadata,
  the minimal Weekly public file response/service/storage projection, bilingual copy, and directly
  corresponding tests. This manager owns this status record and browser evidence.
- Non-goals: changing Category/Keywords/Summary generation or storage, database schema cleanup,
  File Detail redesign, Weekly snapshot/count/report generation, the historical-week selector,
  global layout/max-width or design-system changes, pagination/filter redesign, permission-policy
  changes, sibling repositories, dependency upgrades, security frameworks, or speculative
  abstractions.
- The worktree was clean and detached at the assigned baseline. After fetch, `HEAD`, `origin/main`,
  and merge-base all matched `e3f028d1f67910a98e38ae5dfb4045c8d75e6f30`; the pre-created
  assigned branch was then attached at that commit.
- No open/closed PR, remote branch, or matching commit references #333, its URL, or the distinctive
  content-first Home/Weekly/Database wording. The only other remote branch is the unrelated
  `archive/flask-only-system`, whose relevant diff removes the React Dashboard and Database pages.
- Baseline browser evidence with 15 disposable files and a 12-file latest snapshot showed inert
  stat cards, eight Home/Weekly rows with full year/time/time-zone dates, four selected-week files
  unreachable in Weekly, and Database desktop columns Title/Source/Category/MD/Size/Date/Actions.
  The Database date is selected from `first_seen` or `last_seen` according to the active sort.
- The Weekly service's field allowlist already names Category/Keywords/Summary, but its storage
  member query and public Pydantic model return only URL/title/original filename/first seen.
  `/api/files` already projects Category/Summary/Keywords publicly without sensitive fields.
- Review-policy override: none; only realistically reproducible findings mapped to an AC above are
  accepted.

## Issue #333 validation and artifacts

- The persistent worker implemented the content-first Home, Weekly, and Database views plus the
  narrow Weekly public metadata projection. No lifecycle actions have run yet.
- Local review round 1 accepted and fixed two AC-8 defects: a failed Weekly detail request and an
  uncached Database list failure were incorrectly rendered as empty states. Live browser failure
  injection now shows distinct localized error states while cached/partial behavior is preserved.
- Local review round 2 accepted and fixed three scoped defects: collapsed Weekly groups now retain
  their `aria-controls` target via `hidden`; the Database icon-only search-clear action has localized
  `aria-label` and `title`; and semicolon-only malformed categories no longer create visual noise.
- Local review round 3 accepted and fixed one AC-3/AC-8 copy defect: the English group count now
  uses plural-safe noun-first wording (`Articles: {count}`), with one-item and multi-item assertions.
- Manager-focused verification after round 2 passed: 57 Python tests, executable Issue #333 TSX
  assertions, TypeScript typecheck, and `git diff --check`. Browser verification at 1024px confirmed
  stable disclosure targets across collapse/reopen, the search-clear accessible name/tooltip, and
  no horizontal overflow.
- Fresh local review round 4 inspected the complete tracked/untracked candidate and passed with no
  findings. The local review cycle is closed after four rounds.
- Final candidate validation passed: unified quality gate (`2024 passed, 10 skipped`), frontend
  ESLint (0 errors; 5 existing warnings), TypeScript typecheck, production build, both dead-code
  gates (0 findings), FastAPI smoke (`13 passed`), Agentic RAG eval tests (`31 passed`), and the
  deterministic Agentic RAG smoke (`3/3 passed`). `git diff --check` also passed.
- Final live browser checks passed at 320, 768, 1024, and 1440px with exact viewport/scroll widths,
  disclosure collapse/reopen semantics, the localized search-clear accessible name/tooltip, and
  normal Home/Weekly/Database content. Final desktop and 320px screenshots were refreshed.
- Final gates are `git diff --check`, both dead-code commands, frontend ESLint/TypeScript/build,
  the three CI Python smoke commands, `python scripts/quality_gate.py`, and live browser checks at
  320, 768, 1024, and 1440px.
- Baseline screenshots are stored outside the checkout under
  `C:\Users\ferry\.codex\visualizations\2026\09\03\01a06897-4cf9-7ff2-90ed-a0b13f4104cc\issue-333-screenshots\before`.
- Current after screenshots are stored beside them under `issue-333-screenshots\after`; final
  captures will be refreshed after the candidate passes the last local review.

## Issue #333 blockers or decisions needed

- None.

## Issue #333 recommended next action

- Commit the reviewed candidate, push the task branch, and create the required Draft PR.

# Project Status — Issue #331 public HTTP redirect

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\a0f0\AI_actuarial_inforsearch`
- Branch: `codex/issue-331-http-https-redirect`
- Baseline: `origin/main@114108dd4426bdeb5b7bd93bda9b2498ebc06986`
- Issue: `#331 ops: restore public HTTP-to-HTTPS redirects for app hostnames`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/332`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-331.json`
- Delivery stage: Draft PR #332 created; preparing the reviewed head for Ready
- Progress heartbeat: id `issue-331-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #331 acceptance criteria

- AC-1: Public port 80 accepts only the two app hostnames `aiinforsearch.com` and
  `www.aiinforsearch.com` for redirect behavior and returns permanent 301/308 responses to the
  fixed canonical origin `https://www.aiinforsearch.com`.
- AC-2: The canonical redirect preserves the complete request path and query string, including
  `/database?category=AI`, and never builds `Location` from the request `Host` header.
- AC-3: Unrelated Host values on public HTTP receive a bounded non-success response and are not
  reflected into `Location`; `http://localhost:80/` continues to return 200 for the Caddy
  container health check.
- AC-4: The HTTPS application routes, application/baseline security headers, API/frontend private
  container-port posture, and non-exposed Caddy admin API remain unchanged. The
  `cross.aiactuary.cn` site block and upstream remain byte-for-byte unchanged.
- AC-5: Focused regression tests, production-shaped Caddy adaptation/validation, and
  `docker compose ... config -q` prove the listener, redirect, host-rejection, health, and
  unchanged-topology contracts before publication.
- AC-6: After review and squash merge, production is synced to the exact merge commit only after
  repository-external rollback artifacts capture the pre-change tracked Caddyfile and running
  Caddy configuration; the candidate validates before a scoped Caddy-only reload, without
  rebuilding or restarting API/frontend.
- AC-7: The running deployment passes HTTP redirects from China Telecom, China Unicom, and China
  Mobile; fixed canonical path/query and arbitrary-Host checks; HTTPS apex/www, API health,
  localhost health, all three container health states, `cross.aiactuary.cn`, and sustained Caddy
  error checks; and normal mobile plus WeChat in-app browser canaries without a redirect loop.

## Issue #331 scope, non-goals, and baseline evidence

- Worker-owned repository scope is limited to `Caddyfile`, the directly related deployment
  source tests, and documentation only where the changed tracked contract requires it. This
  manager owns `.hermes/project-status.md`.
- Sibling repositories, the primary checkout's #317 changes, issue-269, pr-324, #328,
  API/frontend business code, dependency upgrades, DNS/CDN/certificates, HTTPS apex
  canonicalization, and the `cross.aiactuary.cn` block/upstream are off-limits.
- Duplicate search across all PR titles/bodies/heads and local/remote branches found no #331 or
  equivalent public-port-80 redirect implementation. Merged PR #107 only added JSON logging and a
  loopback-only localhost health responder, so it is relevant history rather than a duplicate.
- The clean detached worktree, `HEAD`, `origin/main`, and merge-base all matched
  `114108dd4426bdeb5b7bd93bda9b2498ebc06986` before creating the assigned branch.
- Baseline public requests to both HTTP hostnames and the path/query probe failed with curl exit 7;
  HTTPS apex/www, API health, and `cross.aiactuary.cn` returned 200.
- Production-shaped `caddy adapt` showed the only port-80 listener as `127.0.0.1:80` and
  `[::1]:80`, while HTTPS listened on `:443`. Targeted blame/history traces that listener to
  merged PR #107 and finds no documented intent to reject public HTTP.
- Production-shaped `docker compose -f docker-compose.yml -f docker-compose.override.yml config
  -q` passed locally with non-secret placeholders; standalone Caddy is available through the
  pinned container image for adaptation and validation.
- Review-policy override: none. Only realistically reproducible findings mapped directly to an
  AC above are accepted.

## Issue #331 implementation and local review

- The tracked Caddy configuration disables Caddy's generated HTTP redirects and owns public port
  80 through one explicit server. `localhost` returns 200, the apex and `www` app Host values
  redirect permanently to fixed `https://www.aiinforsearch.com{uri}`, and every other Host returns
  an empty 421 without a `Location` header.
- The HTTPS application block, security-header snippets, API/frontend upstreams, and complete
  `cross.aiactuary.cn` block/upstream remain unchanged from `origin/main`. Compose continues to
  publish only Caddy 80/443; neither API/frontend nor the Caddy admin port is published.
- A production-shaped semantic test uses `caddy:2-alpine` to adapt and validate the tracked file,
  then runs only the adapted HTTP server on an isolated random loopback port. It verifies both app
  hosts, fixed canonical path/query, localhost health, arbitrary/cross Host rejection, unchanged
  HTTPS upstreams, and cleanup of the temporary container.
- TDD red evidence first found no public HTTP server on the baseline. Opening port 80 alone then
  reproduced Caddy's automatic apex redirect to `https://aiinforsearch.com/...`; the final explicit
  routing passes with fixed canonical output.
- The adapted configuration test directly asserts the HTTPS server's automatic redirect state so
  the guard against generated Host-derived redirects cannot disappear while the focused suite
  remains green.
- Local review round 1 found one valid AC-5 gap: the semantic runtime test did not directly prove
  that Caddy's automatic Host-derived redirect injection remained disabled. The persistent worker
  added the focused adapted-config assertion, reproduced the failing case by removing the guard,
  restored it, and returned the focused suite to green.
- Fresh read-only local review round 2 independently rechecked the full diff, production-shaped
  runtime, encoded path/query cases, Host values with case/ports, exact HTTPS/cross configuration,
  Compose topology, CI feasibility, and temporary-container cleanup. It passed with no valid
  #331 findings, so the local review cycle is closed after two rounds.

## Issue #331 local validation

- Focused deployment configuration suite: 9 passed, including real Caddy adapt, validate, and
  isolated runtime requests. Base and production Compose `config -q` both passed.
- Unified quality gate passed after the worktree's lockfile dependencies were installed: 2,012
  tests passed and 10 skipped; Black, isort, and Pylint passed. The earlier 20 failures were all
  missing React/tsx executables and passed before the clean full rerun.
- Both dead-code gates passed with zero findings. Frontend lint passed with zero errors and five
  existing warnings; type-check and production build passed. Python smoke passed 13 FastAPI tests,
  31 Agentic evaluation tests, and all 3 CLI evaluation cases.
- `git diff --check` passed. No temporary `issue-331-caddy-*` container remains. The npm audit's
  existing dependency findings are outside #331 and did not cause dependency changes.
- The complete current post-review diff then passed the full gate again: 2,012 tests passed and 10
  skipped; Black, isort, Pylint, both dead-code checks, frontend lint/type-check/build, all Python
  and Agentic smoke/evaluation suites, the 9 focused deployment tests, both Compose configurations,
  production-shaped Caddy validation, and `git diff --check` all passed.

## Issue #331 blockers or decisions needed

- No repository implementation blocker. Production SSH port 22 is reachable, but this host has no
  SSH config/private key and BatchMode authentication failed for the common server accounts. The
  existing in-app and Chrome browser sessions both reached the Tencent Cloud login page without an
  authenticated session. Public 17CE/443.cn probes can cover the three carrier checks after
  deployment; a real WeChat in-app canary capability has not been found. No unavailable production
  or browser result will be inferred.

## Issue #331 recommended next action

- Push this Draft PR status update, verify the PR head and exact `Closes #331` reference, then move
  PR #332 to Ready and start the single full feedback window.

# Project Status — Issue #322 Markdown terminal preflight

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\8480\AI_actuarial_inforsearch`
- Branch: `codex/issue-322-markdown-terminal-preflight`
- Baseline: `origin/main@e0645f92b867a7209af91f2ddd28027cede28778`
- Issue: `#322 fix(markdown): preflight terminal source failures before conversion`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-322.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/330`
- Delivery stage: PR #330 is Ready. Its single feedback window completed after 720.2 seconds;
  the sole valid Copilot wording fix is pending commit/push and current-head CI.
- Progress heartbeat: id `issue-322-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #322 acceptance criteria

- AC-1: A legacy binary `.ppt` is classified as `unsupported_legacy_ppt` before converter
  execution and is excluded from later automatic Markdown backlogs while its source/state is
  unchanged, unless an operator explicitly retries it.
- AC-2: A missing local source is durably classified as `repair_required` before converter
  execution and does not repeat the same scheduled conversion error.
- AC-3: A `.pdf` whose declared MIME/content kind or magic identifies HTML is durably classified
  as `invalid_source` and is not accepted solely from its extension or URL.
- AC-4: Terminal preflight outcomes remain distinct from retryable converter failures. An unchanged
  terminal source stays out of ordinary incremental selection; a verified source/state change or
  explicit operator selection makes it eligible again under one narrow rule.
- AC-5: Terminal skips have their own task counter and per-item result visibility, separate from
  successful conversions, ordinary skips, and retryable errors; they cannot falsely make a run
  successful.
- AC-6: Auto exhaustion preserves every attempted converter and its concrete failure reason in
  task details instead of only `Auto conversion failed`.
- AC-7: Valid supported sources preserve the existing incremental selection, conversion,
  persistence, and retry behavior; downstream Chunk and Embedding contracts do not change.
- AC-8: Regression tests cover legacy PPT, missing source, HTML-disguised PDF, a valid supported
  control, durable exclusion/re-entry, separate terminal statistics, and Auto failure details.

## Issue #322 baseline and duplicate evidence

- After fetch, `HEAD`, `origin/main`, and their merge-base all matched the supplied baseline
  `e0645f92b867a7209af91f2ddd28027cede28778`; the worktree was clean and detached before the
  isolated task branch was created.
- No open, closed, or merged PR matched Issue #322, its URL/number, or the distinctive terminal
  Markdown-preflight title. The remote exposes only `main`, and targeted commit history found no
  equivalent terminal source state. Closed Issue #319 changes loose-coupled stage continuation and
  does not implement Markdown source preflight or terminal eligibility.
- A temporary-database reproduction made a real OLE-header `.ppt`, a missing `.pdf`, an HTML-body
  `.pdf` with `content_type=text/html` and `content_kind=web_page`, and a valid `%PDF` control.
  The first run called a converter for the PPT, HTML PDF, and valid PDF; the HTML PDF was accepted.
  The second ordinary run selected the unchanged PPT and missing PDF again and repeated both
  failures.
- A separate runtime reproduction forced `markitdown` and `local` to fail concretely. The exposed
  Auto error was only `Auto conversion failed for control.pdf`; only the final `local` failure
  survived as the exception cause.
- `git blame` and targeted `git log -S` trace broad candidate selection and missing-file retries to
  the original May task runtime, and generic Auto exhaustion to the February/June converter work.
  No later history establishes terminal preflight as intentionally excluded, so the bug premise is
  current.

## Issue #322 scope and validation

- Worker-owned scope is limited to Markdown candidate selection/preflight, the smallest durable
  state needed for unchanged-terminal exclusion and source-change/explicit-selection re-entry,
  task result/stat visibility, Auto failure details, and directly corresponding migrations/tests.
- Likely touched surfaces are `ai_actuarial/task_runtime.py`, storage/schema code only if durable
  state requires it, the two task display-summary services, the shared frontend task metrics/types
  and bilingual label, plus focused Python/React/schema tests. Exact edits must be justified by an
  acceptance criterion; `doc_to_md/registry.py` is an inspected sibling and is edited only if the
  task contract actually routes through it.
- Required final checks: Issue-focused red/green tests, relevant Markdown/task/API/schema/frontend
  regression, `git diff --check`, both dead-code gates, frontend lint/type-check/build, the unified
  quality gate, and all three Python smoke commands from CI. Browser smoke is required if visible
  Task metrics change.
- Non-goals: LibreOffice or new converter installation, automatic source repair/redownload,
  Issue #319 pipeline redesign, downstream Chunk/Embedding changes, sibling-repository work,
  security frameworks, schema registries, or speculative abstractions.
- No unrelated uncommitted or untracked files were present at startup. Generated ignored
  `graphify-out/` data is manager-created analysis output and will not be committed.

## Issue #322 implementation and local review

- A schema-v14 `markdown_terminal_source_state` record persists `unsupported_legacy_ppt`,
  `repair_required`, or `invalid_source` together with a bounded source fingerprint. Ordinary
  selection excludes an unchanged terminal source before logical offset/limit, while explicit
  selection and verified source changes re-enter preflight.
- Task results keep downstream-ready files separate from per-item outcomes, expose an independent
  `items_terminal_skipped` metric through both API summaries and the shared Task UI, and do not
  report a terminal-only run as successful. Retryable converter failures remain eligible.
- Runtime Auto and the same-shaped converter registry now retain every attempted converter and a
  bounded concrete reason. Candidate reasons share the 800-character public budget, so later
  candidates cannot disappear from the final task detail.
- TDD first reproduced 12 failures for the original implementation gap. Local review round 1 found
  two valid defects: generic-MIME OLE `.ppt` records were omitted from the automatic candidate
  predicate, and a long Auto aggregate was truncated before all converter reasons reached the
  public task result. The same persistent worker fixed both with red/green tests.
- Fresh read-only review round 2 independently checked the full diff and returned PASS. Current
  evidence includes 11 Issue-focused tests, 324 related regression tests, schema and Pipeline Baton
  coverage, frontend TaskMetrics runtime/type checks, and `git diff --check` passing.
- The first final dead-symbol gate found one Issue-added exported-but-module-private
  `TaskFileOutcome`. The same persistent worker removed only the unnecessary `export`; the gate
  then passed with zero findings. Because this happened after round 2 PASS, a third fresh read-only
  reviewer checked the full current diff and returned supplemental PASS with no findings.

## Issue #322 final local validation

- Unified quality gate passed: 2,011 tests passed and 10 skipped, then Black, isort, and Pylint all
  passed.
- Dead-code files and symbols both passed with zero baseline findings. Frontend lint passed with
  zero errors and five existing Hook warnings; TypeScript type-check and production build passed,
  with only the existing large-chunk advisory.
- Python CI smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI
  evaluation cases. Evidence/citation/refusal rates were 1.0 and unsupported-answer rate was 0.0.
- In-app-browser smoke used an isolated temporary database and one local test token. The real Task
  History page rendered `Terminal skips: 1` for a Markdown terminal-source result, and browser
  console errors were empty. Both local services were stopped after the check; no real account or
  production data was used.
- `git diff --check` passed. CRLF notices are informational workspace conversion warnings.
- Files in scope: Markdown runtime, storage/schema, both task summary services, shared Task metric
  UI/types/i18n, same-shaped converter registry, focused Issue test, related schema/task/frontend
  regression fixtures, and this manager-owned status file. No downstream Chunk/Embedding production
  code changed.

## Issue #322 remote feedback

- PR #330 was marked Ready at head `a0474909ee11b1c5fca8cc046753b737c80161ab`.
  One complete snapshot was fetched 720.2 seconds later; there will be no second feedback fetch.
- All five required checks on that head passed. No PR conversation comment or Issue comment was
  present. Copilot left one inline comment about a failed item still reporting `Converted` progress.
- The persistent worker and manager confirmed the comment under AC-5: a canonical
  `retryable_error` must not have success-shaped visible progress. The minimal fix changes only
  `Converted markdown` to neutral `Processed markdown` and adds a public-result progress assertion.
- The new assertion failed before the fix and passed afterward. The worker also passed 131 related
  tests plus Black, isort, Python compilation, and diff checks; the manager independently reran the
  focused public-result test successfully.

## Issue #322 blockers or decisions needed

- None. Commit and push the confirmed wording fix, wait for all five required checks on the new
  exact head, then squash merge, verify Issue closure, and clean the remote branch, worktree, and
  local branch.

# Project Status — Issue #320 strict manifest validation

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\7a36\AI_actuarial_inforsearch`
- Branch: `codex/issue-320-strict-manifest-validation`
- Baseline: `origin/main@29b73be7ecf65d236570b5f9d698783a8966cb46`
- Issue: `#320 fix(manifest): reject incompatible producer payloads instead of silent zero import`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-320.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/329`
- Delivery stage: Draft PR #329 created with `Closes #320`; final status commit pending before the
  Ready transition and single 600-second feedback/CI window

## Issue #320 scope and acceptance criteria

- Accept only the exact supported legacy `web-listening-manifest.v1` object contract, with
  non-empty manifest/run/source identities and a `downloaded_assets` list. Full producer Result
  envelopes, nested manifests, unsupported schemas, missing identities, and wrong container types
  fail with stable machine-readable errors instead of succeeding with zero imported assets.
- Parse raw JSON fail-closed, including duplicate keys at any depth and non-standard numeric
  constants. Preflight every asset before any transaction: object and asset identity; absolute
  HTTP(S) URL; SHA-256 checksum; media type; non-boolean, non-negative integer byte count;
  filename; and at least one valid path field with documented precedence.
- Keep valid legacy behavior: archive the original manifest bytes exactly, retain content kind,
  preserve URL/SHA upsert behavior and path precedence, and make repeated ingestion idempotent.
- Direct ingestion, task execution, task history, and API-visible errors expose only stable codes
  and safe field metadata; malformed inputs cannot leak payload values, credentials, signed query
  strings, cookies, or local secret paths through error chains or logs.
- Non-goals: external consumer/adapter changes, producer API calls, artifact downloads, Baton or
  new lineage work, a schema registry, storage redesign, migration, or backfill. Sibling
  repositories remain off-limits.

## Issue #320 baseline and duplicate evidence

- Startup confirmed the assigned worktree on the exact supplied baseline. Final pre-publication
  fetch again confirmed `HEAD`, `origin/main`, and their merge-base at `29b73be7`.
- Baseline reproduction showed that both a full `web-listening-result.v1` envelope and a nested
  incompatible manifest returned empty IDs with `imported=0`; an unsupported schema carrying a
  manifest ID also reported `imported=0` while writing one raw-manifest row.
- Focused baseline tests passed 44 tests, confirming the defect was an untested contract gap rather
  than an already-failing implementation.
- No equivalent open/merged PR, branch, or commit was found. Merged PR #205 introduced the
  permissive legacy importer and PR #136 covers an unrelated Agentic ready-manifest registry.

## Issue #320 implementation and review

- `manifest_ingest.py` now performs strict raw parsing and complete contract validation before
  opening the write transaction, then preserves the existing valid archive/upsert/idempotency
  path. `ManifestIngestError` carries safe machine code and field details.
- `task_runtime.py` validates and decodes the manifest before constructing storage, persists the
  safe error code/details in task history, and logs contract failures without unsafe exception
  chains. The public collection-run API remains unchanged and continues to reject manifest mode.
- Focused regression coverage now exercises incompatible envelopes, unsupported schemas, duplicate
  keys, every field/type rule, late-asset atomicity, backslash and invalid-port URLs, exact raw-byte
  archival, path priority, idempotency, task/history/API propagation, and secret-safe logs.
- TDD red evidence reproduced six core failures before implementation. Local review round 1 found
  two valid acceptance-criteria defects: backslash URLs were accepted, and chained URL/file errors
  could leak sensitive values. The same persistent worker fixed both with targeted red/green tests.
  Fresh read-only review round 2 returned PASS with no findings. Focused validation passed 102
  tests; the wider related regression selection passed 201 tests.

## Issue #320 final local validation

- Unified quality gate passed: 2,000 tests passed and 10 skipped, then Black, isort, and Pylint all
  passed.
- Both dead-code gates passed with zero baseline findings. Frontend lint passed with zero errors
  and five existing Hook warnings; type-check and production build passed, with only the existing
  large-chunk advisory.
- Python smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI
  evaluation cases with evidence/citation/refusal rates at 1.0 and unsupported-answer rate at 0.0.
- `git diff --check` passed. No browser smoke is required because this change has no UI behavior.
- Files in scope: `ai_actuarial/manifest_ingest.py`, `ai_actuarial/task_runtime.py`,
  `tests/test_manifest_ingest.py`, `tests/test_issue_320_manifest_contract.py`,
  `tests/test_issue_220_immutable_guards.py`, `tests/test_fastapi_ops_read_endpoints.py`,
  `tests/test_fastapi_ops_write_endpoints.py`, and this manager-owned status file.
- No unrelated uncommitted or untracked files are present. There are no local blockers; the next
  action is to push this final status commit, mark PR #329 Ready, then perform the single required
  feedback/CI/merge/cleanup lifecycle.

# Project Status — Issue #308 inapplicable retrieval metrics

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\2378\AI_actuarial_inforsearch`
- Branch: `codex/issue-308-inapplicable-retrieval-metrics`
- Baseline: `origin/main@0cdc25fce76d9eaf21d484020ccaa223fef0f3b6`
- Issue: `#308 fix(chat): distinguish inapplicable retrieval metrics from missing score data`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-308.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/326`
- Delivery stage: Draft PR #326 created with `Closes #308`; final status commit pending before
  Ready for review

## Issue #308 scope and acceptance criteria

- AC-1: Keyword-only methods (`summaries`, `titles`, `sections`, `relations`, `formulas`,
  `tables`, and `calculation_terms`) show Keyword relevance plus Retrieval method and omit
  Semantic relevance when its canonical value is absent.
- AC-2: `vector` evidence shows Semantic relevance plus Retrieval method and omits Keyword
  relevance when its canonical value is absent.
- AC-3: A metric applicable to the method remains visible as `—` when its canonical value is
  missing, invalid, non-integer, or outside `0..100`.
- AC-4: Any present valid canonical semantic or keyword value is shown regardless of method, so
  hybrid evidence can show both.
- AC-5: Unknown methods infer no applicability and show only valid scores actually present, plus
  the safely normalized Other method badge.
- AC-6: Citation Cards and Retrieved Blocks use the same shared component and therefore the same
  rendering rules.
- AC-7: Every rendered badge remains screen-reader labeled, `whitespace-nowrap`, flex-wrapping,
  and free of horizontal overflow at 320, 768, 1024, and 1440 px.
- AC-8: Backend response fields, persistence/history, ranking, result order, thresholds, planner,
  tool selection, and retrieval APIs remain unchanged.

## Issue #308 ownership, non-goals, and validation

- Implementation ownership is limited to
  `client/src/pages/chat/RetrievalIndicators.tsx` and its focused component test. The manager owns
  this status file. `Chat.tsx` is inspected as the two-call-site contract and is edited only if the
  shared-component contract cannot satisfy AC-6.
- Sibling repositories are off-limits.
- Non-goals: adding vector scoring to Ready Data, relabeling scores, creating a combined score,
  changing any backend contract or retrieval behavior, backfilling history, adding a security
  framework, or introducing a speculative abstraction.
- Component matrix: vector-only; every keyword-only method; valid hybrid scores; applicable
  missing/invalid/out-of-range scores; all missing; and unknown method with absent, one, or both
  valid scores. Assertions cover exact visible and absent accessible labels.
- Regression matrix: the existing backend Issue #265 suite preserves Agentic raw-score and
  Standard vector-mapping contracts; frontend lint, type-check, build, real browser smoke, both
  dead-code gates, the unified quality gate, and all three Python smoke commands are required.

## Issue #308 baseline evidence

- The assigned worktree arrived clean but detached. After fetching, `HEAD`, `origin/main`, and
  their merge-base all matched the supplied baseline exactly; the manager created the isolated
  branch named above without changing files.
- Runtime server rendering reproduced both defects: `titles` with keyword score `31` rendered an
  extra `Semantic relevance: —` badge, and `vector` with semantic score `83` rendered an extra
  `Keyword relevance: —` badge.
- `git blame` and the complete path history show that PR #286 introduced the component with a
  fixed three-badge array and no later change. Issue #308 explicitly supersedes that earlier layout
  rule as a focused UX follow-up, so the report is current rather than stale or duplicate work.
- Duplicate search found no equivalent PR or branch. Merged PR #286 is the linked #265 origin and
  does not implement the new applicability distinction.

## Issue #308 implementation and validation

- The shared component now treats `vector` as semantic-applicable, the seven Ready Data methods as
  keyword-applicable, and unknown methods as having no inferred applicability. Any valid canonical
  score is still rendered regardless of method, while an applicable invalid/missing score remains
  visible as `—`.
- TDD red evidence showed the original vector-only and keyword-only cases each rendered the extra
  inapplicable `—` badge. The expanded component matrix then passed after the minimal component
  change.
- Local review completed after one fresh read-only reviewer round with no valid findings. Citation
  Cards and Retrieved Blocks were independently confirmed to pass identical fields to the same
  shared component.
- The Issue-focused component test passed. The retrieval/backend regression selection passed 143
  tests, preserving Agentic raw-score and Standard vector-mapping contracts.
- Frontend lint passed with zero errors and five existing Hook warnings; type-check and production
  build passed, with only the existing large-chunk advisory. Both dead-code gates passed with zero
  findings.
- Python smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI smoke
  cases with quality rates at 1.0.
- The unified quality gate passed: 1,882 tests passed and 10 skipped; Black, isort, and Pylint all
  passed.
- Real browser smoke used controlled local API responses in the actual Chat page. Citation Cards
  and expanded Retrieved Blocks rendered keyword-only, vector-only, applicable-missing, unknown,
  and hybrid cases identically. At 320, 768, 1024, and 1440 px, all 22 expected badges stayed
  within their containers, retained `nowrap`, wrapped as whole badges, and produced no page
  overflow or console errors. The existing narrow-screen sidebar was closed before inspecting the
  conversation content.
- Final fetch confirmed `origin/main`, branch merge-base, and the original baseline remain
  `0cdc25fce76d9eaf21d484020ccaa223fef0f3b6`.

# Project Status — Issue #307 scheduler reconciliation

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\be1a\AI_actuarial_inforsearch`
- Branch: `codex/issue-307-scheduler-reconciliation`
- Original baseline: `origin/main@0fe3101df6f3834e33b609aff3d119b70df9a274`
- Integrated main: `origin/main@25d0e0ae96a938d97636041e77a175203184237f`
- Issue: `#307 fix(tasks): reconcile configured recurring tasks with effective scheduler jobs`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-307.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/325`
- Delivery stage: PR #325 is Ready; the full 10-minute feedback window completed, all five CI
  checks passed, and two confirmed Copilot findings are fixed and locally revalidated for push
- Progress heartbeat: id `bug-issue`, status `ACTIVE`, 15-minute cadence

## Issue #307 pause checkpoint (historical)

- Pause requested after local review round 1 returned PASS with no findings. The persistent state
  file remains at `local_review_complete` with `review_count: 1` and no PR recorded.
- Completed validation: Issue-focused tests (36 passed), worker extended backend regression
  (293 passed), reviewer regression (113 passed), rendered component assertions, real browser
  smoke for registered-reader/admin controls and English/Chinese copy, dead-code file/symbol gates,
  frontend lint/type-check/build, and `python scripts/quality_gate.py`.
- Unified quality result: PASS; full pytest was 1876 passed and 10 skipped, followed by passing
  Black, isort, and Pylint baseline checks. Frontend lint retained 5 existing warnings and build
  retained the existing large-chunk advisory.
- At this historical pause point, the separate CI-equivalent `python-smoke` commands had not run
  and no Git or remote lifecycle action had occurred. Both the smoke commands and all other
  post-integration local checks have now completed below; the Git/remote lifecycle still has not
  started.
- Resume entry: from this exact worktree and branch, verify `git status`, run the three
  `python-smoke` commands from `.github/workflows/ci.yml`, review the final diff/status, then commit,
  push, open the Draft PR with `Closes #307`, mark Ready, and continue the recorded remote-feedback
  workflow.
- Preserve all current tracked implementation/test changes, the two new test files, the three
  manager-generated `graphify-out/` directories, and the Issue state file. Sibling repositories
  remain off-limits.

## Issue #307 latest-main integration

- The controller reported and the manager verified that `origin/main` advanced five commits from
  `0fe3101` to `25d0e0a` through PR #324.
- A three-way preflight found no business-code or test conflict and no untracked-path collision.
  The only conflict was this manager-owned status file.
- The branch fast-forwarded to `25d0e0a`; all #307 tracked changes and both new tests were restored
  from the recoverable stash. The three `graphify-out/` directories remained untouched.
- The status-file conflict was resolved by preserving the complete #307 record and its prior
  #306/#317 history while adding the current main record for PR #324 below.
- PR #324 changed guest-only task-option caching and unrelated pages/tests. It did not change any
  #307 production or test file, nor a hook consumed by the #307 scheduling surfaces, so local
  review round 1 remains applicable and `review_count` stays at 1.

## Issue #307 post-integration validation

- Extended scheduler/API/frontend regression: 293 passed.
- FastAPI entrypoint/native-authority smoke: 13 passed. Agentic evaluation tests: 31 passed.
  Agentic command smoke: 3/3 cases passed with all reported quality rates at 1.0.
- Frontend lint passed with 0 errors and 5 existing hook warnings; type-check and production build
  passed, with only the existing large-chunk advisory.
- Dead-code file and symbol gates passed with zero findings.
- Unified quality gate passed: 1,880 tests passed and 10 skipped; Black, isort, and Pylint passed.
- Real browser smoke passed against the integrated branch. A registered reader saw both Effective
  Scheduler Jobs and Configured Recurring Tasks, including all five expected job kinds, while add,
  reinitialize, edit, and delete controls were absent. An admin saw add, reinitialize, edit, and
  configured-task delete controls, with no direct effective/system-job delete action. English and
  Chinese desired/effective, diagnostic/recovery, read-only, and deletion-consequence copy all
  rendered correctly. The confirmation was inspected without deleting the recurrence.
- `git diff --check` passed apart from informational CRLF conversion notices. No second local review
  was needed because the integrated upstream changes did not touch or feed the reviewed #307
  surfaces.

## Issue #307 remote feedback and follow-up

- PR #325 was created as Draft, verified to contain `Closes #307`, then marked Ready. The required
  observation window ran for 635 seconds before the one permitted feedback snapshot was fetched.
- Remote CI passed `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke`; the reviewed head was `e3109b4bcab6414c5d18f1de19657f5753c21334` and GitHub
  reported the PR mergeable and clean.
- Copilot raised four inline comments. Two were confirmed and fixed: unmanaged scheduler jobs now
  retain their generated sanitized metadata so identity survives in-process list reordering; and
  `daily at H:MM` is normalized to `HH:MM` both for runtime registration and desired/effective
  reconciliation.
- The two comments about absolute paths in this internal workflow record were rejected under the
  repository review policy because they do not map to any Issue #307 acceptance criterion.
- Red evidence reproduced both accepted findings, including a 503 reconciliation failure and the
  real scheduler rejecting the API-accepted single-digit hour. Green evidence: 2/2 focused tests,
  46/46 Issue/API tests, and the manager's 295/295 extended regression passed. Black, isort, and
  `git diff --check` passed for the follow-up patch.

## Issue #307 acceptance criteria and boundaries

- AC-1: Effective scheduler status exposes a deterministic within-process `job_key` plus only
  sanitized kind, source, display name, interval, last/next run, managed, and deletable metadata.
- AC-2: Configured recurring tasks, site jobs, the global job, Pipeline Baton, and Ready Data are
  distinguishable; configured effective jobs map back to their configured task.
- AC-3: Configured-task add, update, and delete return success only after desired YAML and live
  scheduler state match; recurrence removal needs no manual Reinitialize.
- AC-4: A forced registration or reconciliation failure returns failure and restores both the
  previous YAML and the previous scheduler state.
- AC-5: Reconciliation does not stop active tasks or alter history, logs, stop behavior, or
  unrelated system jobs; system jobs have no direct delete action.
- AC-6: `tasks.view` readers can see Configured Recurring Tasks and Effective Scheduler Jobs but
  no mutation controls; direct writes remain 403 and operator/admin write flows remain valid.
- AC-7: Reinitialize remains a diagnostic/recovery action, and English/Chinese copy plus deletion
  confirmation clearly explain desired versus effective state.
- Implementation ownership is limited to `ai_actuarial/task_runtime.py`, the directly related
  FastAPI ops read/write services and routers, `client/src/pages/Tasks.tsx`,
  `client/src/pages/tasks/ScheduledTasksSection.tsx`, `client/src/hooks/use-i18n.ts`, the three
  same-shaped mutation callers `ScheduleFromTaskButton.tsx`, `WebListeningForm.tsx`, and
  `PipelineBaton.tsx`, and focused tests for those contracts. `.hermes/project-status.md` remains
  manager-owned.
- Sibling repositories are off-limits. Non-goals are schedule/timezone UX from #312, a database
  job table, a generic scheduler platform, direct system-job deletion, stopping current tasks,
  history/log/artifact deletion, APScheduler/Celery migration, and pipeline-order changes.

## Issue #307 baseline evidence

- The assigned worktree was clean; branch, `HEAD`, and supplied baseline matched exactly.
- A real `NativeTaskRuntime` reproduction showed add left only the existing 30-minute Pipeline
  Baton job, update left the old daily timer effective, and delete left the two-hour timer live
  after YAML became empty. Manual `init_scheduler()` was required after each mutation.
- `git blame` and targeted history trace the split to the original April FastAPI work: CRUD writes
  YAML and calls only `set_site_config`, while the separately exposed Reinitialize path alone calls
  `init_scheduler`. The status endpoint independently enumerates live jobs. Later changes added
  system jobs and stricter RBAC without creating an automatic reconcile contract, so the Issue is
  current and not a stale request.
- The linked #312 explicitly depends on #307 and owns only future schedule expression/timezone UX.
- Baseline CI run 33582893736 passed all five jobs at the assigned merge baseline.

## Issue #307 required validation

- Scheduler/runtime tests cover every job kind/source, stable keys, configured mapping,
  add/update/delete reconciliation, forced failure rollback, and unchanged system jobs.
- API tests cover the reader/operator/admin RBAC matrix and active/history/log/stop regressions.
- Frontend source and rendered-component tests cover read-only visibility, hidden mutations,
  bilingual copy, and deletion confirmation.
- Final validation includes focused scheduler/API/frontend tests, frontend lint/type-check/build,
  browser smoke, dead-code file/symbol checks, the unified quality gate, and Python smoke tests.

# Project Status — PR #324 guest UI permission gating

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\pr-324`
- Branch: `fix/guest-ui-permission-noise`
- Baseline merged: `origin/main@0fe3101`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/324`
- Task: review PR #324, fix its failing test gate, and evaluate Copilot feedback

## Scope and boundaries

- This repository is the only writable project workspace; sibling repositories are off-limits.
- Scope is limited to the guest UI permission behavior, the failed formatting gate, and the
  Copilot review comment on `useTaskOptions`.
- The primary checkout has unrelated user-owned changes and remains untouched. Work is isolated
  in this task worktree.

## Findings and implementation

- The original remote run passed all 1,880 pytest tests but failed the quality gate because
  `tests/test_knowledge_react_source.py` was not Black-formatted.
- Copilot's comment was confirmed: a disabled `useTaskOptions` consumer could expose module-level
  cached operator data and could retain a stale loading state.
- Disabled consumers now receive stable fallback/empty values, `loading=false`, `error=null`, and
  a request-free `refresh` function.
- A runtime TypeScript/React hook regression warms the authorized cache, expires it, mounts a
  disabled guest consumer, and verifies that no operator data or new requests escape.
- Black reformatted the original failing test file.
- The Copilot thread was answered with the fix and regression evidence.
- Latest `origin/main` was merged after it advanced through PR #323; its sole textual conflict in
  this status file was resolved in favor of the current PR #324 record.

## Local verification before latest-main merge

- New runtime regression: demonstrated the stale-data/loading failure before the hook fix and
  passed after the fix.
- Focused React source suite: 78 passed.
- Black check for the four relevant React source test files: passed.
- Frontend lint: passed with 0 errors.
- Frontend type-check: passed.
- Frontend production build: passed; only the existing Vite large-chunk advisory remained.
- Four-layer dead-code gate: passed with zero baseline findings.
- Unified quality gate: passed with 1,861 tests passed and 10 skipped; Black, isort, and Pylint
  passed.
- `git diff --check`: passed apart from informational CRLF conversion notices.
- Browser shell smoke as a signed-out user showed no operator diagnostics or console errors. The
  backend was not running, so proxied API requests returned connection-refused/500 responses;
  the runtime regression is the authoritative guest-cache check.

## Post-merge verification

- Focused React source suite: 78 passed.
- Frontend lint, type-check, production build, and four-layer dead-code gate: passed.
- Unified quality gate: 1,871 passed and 10 skipped; Black, isort, and Pylint passed.
- `git diff --check`: passed.

## Delivery state

- Fix commit `1d61054` is pushed to the PR branch.
- The Copilot reply is published at discussion comment `3910583670`.
- Post-merge local validation is complete; the new remote CI run is the remaining check at this
  snapshot.

## Preserved merged Issue #306 evidence

- PR #323 merged at `0fe3101df6f3834e33b609aff3d119b70df9a274` on 2026-09-02T02:21:06Z.
- Issue #306 closed automatically one second later.
- PR #323 passed `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke`; the post-merge main CI run 33582893736 also passed all five jobs.
- The detailed #306 implementation and validation record remains preserved below.

# Project Status — Issue #306 metadata-only Chunk & Embedding stats

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\692c\AI_actuarial_inforsearch`
- Branch: `codex/issue-306-metadata-only-stats`
- Baseline: `origin/main@1e7f5f6b1cf29e7e9c0a413e221e774d77bdeee2`
- Issue: `#306 perf(tasks): make Chunk & Embedding stats metadata-only`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-306.json`
- Delivery stage: merged through PR #323 at
  `0fe3101df6f3834e33b609aff3d119b70df9a274`; Issue #306 is closed and post-merge CI passed
- Progress heartbeat: id `bug-issue`, status `ACTIVE`, 15-minute cadence

## Issue #306 scope and boundaries

- This repository is the only writable project workspace; sibling repositories are off-limits.
- Ordinary `GET /api/chunk_generation/stats` must use aggregate metadata only and must not read
  `global_chunks.content` or `chunk_embeddings.vector_json`.
- Preserve the response shape, category filtering, embedding identity fields, and
  `first_without_chunks_index` semantics.
- Preserve deep vector-body validation for build, audit, repair, and explicit coverage paths.
- Add measured covering-index/query-plan evidence, regression guards, dimension/byte-size
  performance evidence, focused API/storage/schema checks, frontend build, and browser smoke.
- Non-goals remain caching the deep scan, changing embedding generation or serialization,
  weakening fail-closed build/audit behavior, replacing SQLite, or redesigning Tasks UI.

## Issue #306 baseline evidence

- Worktree was clean; assigned branch and `HEAD` exactly matched the supplied baseline.
- A baseline endpoint run with 3,072-dimension stored vectors called
  `Storage.embedding_coverage`, `Storage.list_chunks_for_embedding`, and
  `Storage.read_valid_chunk_embeddings` once each.
- Targeted blame/log evidence traces the deep statistics path to the persisted-embedding
  implementation; current intent already keeps metadata-only and deep validation paths separate
  for Knowledge Base detail, so Issue #306 is reproducible and not stale.

## Issue #306 current validation

- Issue-focused tests: 10 passed. The added v0 regression proves a real pre-v13 database
  without the new indexes is recognized, migrated with data preserved, and idempotent.
- Schema/API combinations: 153 schema migration checks and 42 related API/lightweight-path
  checks passed.
- Production-scale benchmark: 21,314 rows at 3,072 dimensions with about 262 MB of stored
  vector bodies; first new connection 0.02653s and 20-run warm p95 0.02172s.
- Frontend lint, type-check, production build, dead-code file/symbol gates, and the unified
  quality gate passed. Final full pytest result: 1,867 passed, 10 skipped, 0 failed;
  Black, isort, and Pylint also passed. Agentic eval smoke passed 3/3.
- Browser smoke passed on Tasks → Chunk & Embedding: stats and selected embedding identity
  rendered without a persistent loading state, the stats API returned 200, and the browser
  console had no errors.
- Local review closed after two rounds. One real v0 migration gap was fixed and independently
  revalidated. A proposed manual wrong-name index construction was rejected under the repository
  review policy because no supported create or migration path can produce it and Issue #306 does
  not require compatibility with manual schema tampering.

## Prior project status (Issue #317 historical record)

# Project Status — Issue #317 dead-code and unified quality gates

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch\.codex-tmp-agentic-rag`
- Branch: `codex/issue-317-dead-code-detection`
- Baseline: `origin/main@bd6f47f`
- Task: implement Issue #317 and the requested unified pytest/Black/isort/Pylint gate

## Scope and boundaries

- This repository is the only writable workspace.
- Sibling repositories are off-limits.
- The work covers TypeScript and Python file reachability, symbol detection,
  reviewed exceptions, shrink-only baselines, local hooks, CI, reports, and
  contributor documentation.
- CI only reports and blocks; it never deletes or rewrites source files.

## Implementation state

- PR #318 is open: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/318`.
- Added production-first Knip and AST module-reachability checks, followed by
  Knip/ESLint and Vulture symbol checks.
- Production and test entries are separate. Constant dynamic imports require a
  reasoned allowlist, and stale entries fail the gate.
- Added a statically validated Vulture whitelist for FastAPI routes, Pydantic
  validators, middleware hooks, and pytest fixtures.
- Added normalized `path + kind + symbol` dead-code baselines. New findings,
  stale findings, and all 100%-confidence Vulture findings fail; maintenance
  updates can only shrink the baseline.
- Classified the initial baseline: 9 TypeScript files, 5 Python modules, 28
  TypeScript symbols, and 93 Python symbols. Reviewed cleanups have since
  reduced all dead-file findings to zero and all symbol findings to 17 Python
  compatibility/test items.
- Added the requested unified quality gate: full pytest plus non-mutating
  Black, isort, and Pylint checks, with an exact shrink-only compatibility
  baseline for existing formatter/linter debt. Pytest failures cannot be
  baselined.
- Added pre-commit/pre-push hooks, ordered CI jobs, text/JSON artifacts,
  top-level commands, watch mode, and investigation/cleanup documentation.
- Removed confirmed unused TypeScript locals/imports and corrected narrow test
  contracts exposed by the new full-suite gate.
- The first PR #318 run passed file/symbol, frontend, and Python smoke jobs. Its
  full Linux gate exposed one POSIX path-normalization bug, two FastAPI 0.141
  route-introspection assumptions, five Linux symlink-path assertions, and
  four platform-dependent static-baseline entries. These were fixed narrowly:
  publication slots remain atomic while failed rollback audit fields advance,
  staging is reverified immediately after digesting, and optional marker
  Pylint findings are deterministically suppressed at their exact call sites.
- Copilot's one actionable review finding was confirmed and fixed: the
  synthetic commit-failure context manager now executes the transaction body,
  raises during exit, and delegates rollback to the real transaction manager.
- The second Linux run passed four jobs but showed that four symlink rollback
  assertions scrubbed audit fields from the direct publication projections,
  not from the same fields mirrored in the nested manifest projection. The
  helper now removes only those four audit keys recursively while comparing
  every other field, with a platform-independent regression for that shape.
- Historical cleanup now proceeds one directory at a time, with focused tests,
  the complete gate, and one path-specific commit per directory. The first
  completed directory is `config/`: Black/isort formatting was applied, the
  Pydantic path validator was explicitly marked as a classmethod, and the
  output-format validation was made type-explicit for Pylint.
- The second completed directory is `scripts/`. Eleven Python scripts received
  only Black/isort formatting; no behavior, dead-code decision, or script entry
  point was changed.
- The third completed directory is `ai_actuarial/agentic_rag/`. Graphify
  confirmed that its primary modules connect to runtime/API consumers and
  dedicated tests, so seven historical files received only Black/isort
  formatting and no file or symbol was removed.
- The fourth completed directory is `ai_actuarial/api/middleware/`. Its single
  implementation file is directly exercised by FastAPI auth and ops tests, so
  it received only Black/isort formatting and no file or symbol was removed.
- The fifth completed directory is `ai_actuarial/models/`. Both the package
  exports and `ApiToken` model have direct runtime/storage consumers and
  dedicated tests, so both files received only Black/isort formatting.
- The sixth completed directory is `ai_actuarial/security/`. Both production
  files are imported by crawler, listening-rule, and API-service paths and are
  covered by URL-safety and integration tests, so both files received only
  Black/isort formatting and no symbol was removed.
- The seventh completed directory is `ai_actuarial/services/`. The package
  export and token-encryption implementation have direct runtime, API, and
  diagnostic consumers plus dedicated integration tests, so both files
  received only Black/isort formatting and no symbol was removed.
- The eighth completed directory is `ai_actuarial/processors/`. Unlike the
  earlier directories, all three Python modules were production-unreachable,
  had no code or test callers, and were already classified `remove` in the
  reviewed dead-code baseline. The three modules and their inaccurate README
  were deleted rather than reformatted.
- The ninth completed directory is `ai_actuarial/collectors/`. Current source
  and exact repository search confirmed that `AdhocCollector` had no runtime,
  test, export, or dynamic caller; its stale Graphify edge pointed to an import
  no longer present in the current CLI. The orphan module and its README claim
  were deleted, two unused imports were removed, and the five reachable
  collector implementations were formatted. The exported
  `CollectionConfig.auto_download` constructor field was retained because
  Issue #317 forbids deleting a public API solely from static-analysis output.
- The tenth completed directory is the direct files under `ai_actuarial/api/`
  (excluding its separately reviewed subdirectories). `app.py`, `deps.py`, and
  `route_inventory.py` were formatted. The `deps.py` email-session selection
  now uses an explicit typed branch instead of a conditional expression,
  preserving behavior while removing its Pylint E1136 false inference. The
  reported `block_retired_api_fallback` symbol remains because its FastAPI
  decorator registers the framework route at runtime.
- The eleventh completed directory is `ai_actuarial/chatbot/`. Seven reachable
  implementation files and the package exports were formatted. Six confirmed
  unused public symbols plus the private `_extract_citations` helper used only
  by a removed method were deleted. No test imported or exercised those
  symbols, so no test was deleted; all tests covering retained chatbot behavior
  remain. `QueryRouter.select_kbs` remains because its source explicitly marks
  it as a backward-compatible alias, and the public configuration fields remain
  part of the configuration contract.
- The twelfth completed directory is `ai_actuarial/rag/`. All ten modules have
  production or test consumers, so no module was deleted. Ten confirmed unused
  baseline symbols were removed, along with four additional helpers or
  attributes that exact caller analysis and the cleanup itself showed were
  unreachable. `RAGConfig.chunk_strategy` remains because YAML, environment,
  migration, documentation, and tests establish it as a public configuration
  contract. The one test dedicated to proving the removed
  `_soft_delete_file_vectors` helper was not called was deleted with that
  helper; all retained RAG behavior remains covered.

## Acceptance results

- Unified quality gate: passed. Pytest reported 1,880 passed and 10 skipped;
  Black, isort, and Pylint exactly matched the current reviewed baselines at
  159 files, 99 files, and 19 error identities respectively.
- Dead-code gate: passed with 9/1 file findings and 28/72 symbol findings,
  exactly matching the classified baseline and with no 100%-confidence
  Vulture finding.
- Dead-code and quality-gate unit tests: 11 passed as part of the full suite.
- Flaky schema-validator isolation regression: passed five consecutive focused
  runs and then passed in the full suite.
- Frontend ESLint: passed with six existing React dependency warnings and no
  errors.
- Frontend TypeScript check: passed.
- Frontend production build: passed; Vite emitted only the existing large
  chunk advisory.
- Clean lockfile install: `npm ci` passed. npm reported nine dependency audit
  findings (2 low, 1 moderate, 6 high); dependency/security upgrades are
  outside Issue #317.
- Pre-commit config validation, CI YAML parsing, CLI `--help`, and
  `git diff --check`: passed.
- Post-CI focused regression: 6 passed and 5 Windows symlink skips. Static
  baselines now match exactly at 213 Black files, 142 isort files, and 22
  Pylint identities; the dead-code gate remains exact.
- After the Copilot fix, its focused regression passed, then the complete
  unified quality gate passed again with 1,880 passed and 10 skipped; the
  dead-code gate also remained exact at 9/5 files and 28/93 symbols.
- After the nested-audit assertion fix, its focused regression passed. Static
  baselines remain exact at 213/142/22 with no new or stale entries, and the
  dead-code gate remains exact at 9/5 files and 28/93 symbols. Final Linux CI
  run 33456929109 passed all five jobs; its unified gate reported 1,891 tests
  passed, including the four original symlink tests, then passed Black, isort,
  and Pylint.
- `config/` focused validation passed: Black, isort, and Pylint reported no
  findings; 36 tests passed and 1 platform-specific test skipped.
- The complete unified quality gate passed after the `config/` cleanup with
  1,881 tests passed and 10 skipped. Its reviewed baseline shrank only for this
  directory, from 213/142/22 to 210 Black files, 140 isort files, and 20 Pylint
  identities.
- The complete dead-code gate also passed unchanged at 9/5 file findings and
  28/93 symbol findings.
- Path-specific commit `fc814fa` was pushed to PR #318. CI run 33460353038
  passed all five jobs: both dead-code layers, frontend, Python smoke, and the
  complete Linux quality gate. No new review comment was added.
- `scripts/` focused validation passed: Black, isort, and Pylint reported no
  findings; 80 tests passed and 1 platform-specific test skipped.
- The complete unified quality gate passed after the `scripts/` cleanup with
  1,881 tests passed and 10 skipped. The reviewed baseline shrank only for this
  directory, from 210/140/20 to 200 Black files, 132 isort files, and 20 Pylint
  identities. The complete dead-code gate remained exact at 9/5 files and
  28/93 symbols.
- Path-specific commit `c601182` was pushed to PR #318 and all five remote CI
  jobs passed with no new review feedback.
- `ai_actuarial/agentic_rag/` focused validation passed: Black, isort, and
  Pylint reported no findings, and all 94 dedicated tests passed.
- The complete unified quality gate passed after the `agentic_rag/` cleanup
  with 1,881 tests passed and 10 skipped. The reviewed baseline shrank only for
  this directory, from 200/132/20 to 193 Black files, 127 isort files, and 20
  Pylint identities. The complete dead-code gate remained exact at 9/5 files
  and 28/93 symbols.
- The machine's existing global Black cache caused high-CPU CLI stalls for the
  changed files. Black's API verified them immediately; the official CLI and
  complete gate then passed with an isolated temporary `BLACK_CACHE_DIR`.
- Remote commit `5356248` contains the exact `agentic_rag/` tree and passed all
  five PR #318 jobs in CI run 33467686369. GitHub authentication and the branch
  update used a task-scoped temporary credential because the sandbox cannot
  replace the invalid user-level GitHub CLI credential.
- `ai_actuarial/api/middleware/` focused validation passed: Black, isort, and
  Pylint reported no gate findings, and all 27 direct FastAPI tests passed.
- The temporary clone initially lacked its ignored root `node_modules`, so 16
  TypeScript subprocess tests could not start. `npm ci` restored the pinned
  dependencies, all 16 focused tests passed, and the complete pytest rerun then
  passed with 1,881 tests and 10 platform skips.
- The full static gate passed after the `middleware/` cleanup at 192 Black
  files, 126 isort files, and 20 Pylint identities, with zero new or stale
  entries. The complete dead-code gate remained exact at 9/5 files and 28/93
  symbols.
- Remote commit `b2c0d92` contains the exact `middleware/` tree. CI run
  33470766007 passed all five jobs, including the 6m27s Linux quality gate, and
  no new Review or Copilot comment was added.
- `ai_actuarial/models/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 23 model/storage integration tests passed.
- The complete pytest suite passed after the `models/` cleanup with 1,881 tests
  and 10 platform skips. The full static gate passed at 190 Black files, 124
  isort files, and 20 Pylint identities, with zero new or stale entries. The
  dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `2fff76c` contains the exact `models/` tree. CI run
  33472039867 passed all five jobs, including the 7m30s Linux quality gate, and
  no new Review or Copilot comment was added.
- `ai_actuarial/security/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 70 URL-safety and direct-consumer tests
  passed.
- The complete pytest suite passed after the `security/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 188 Black files,
  123 isort files, and 20 Pylint identities, with zero new or stale entries.
  The complete dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `0699b47` contains the exact `security/` tree. CI run
  33473548630 passed all five jobs, including the 11m04s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/services/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 120 token-encryption and direct-consumer
  tests passed.
- The complete pytest suite passed after the `services/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 186 Black files,
  122 isort files, and 20 Pylint identities, with zero new or stale entries.
  The complete dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `4bc201e` contains the exact `services/` tree. CI run
  33475164224 passed all five jobs, including the 7m05s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/processors/` focused validation found no remaining Python
  caller, compiled the repository successfully, and passed all 23 catalog,
  collector, and dead-code-gate regression tests.
- The complete pytest suite passed after removing `processors/` with 1,881
  tests and 10 platform skips. The full static gate passed at 184 Black files,
  121 isort files, and 20 Pylint identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/5 files and 28/93 symbols to 9/2
  files and 28/89 symbols.
- Remote commit `a7c502e` contains the exact `processors/` tree. CI run
  33476666119 passed all five jobs, including the 7m51s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/collectors/` compiled successfully, had no remaining
  `AdhocCollector` reference, passed Black and isort, and passed all 253 tests
  in the ten directly importing collector modules or their runtime consumers.
- The complete pytest suite passed after the `collectors/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 178 Black files,
  116 isort files, and 20 Pylint error identities, with zero new or stale
  entries. The dead-code gate shrank exactly from 9/2 files and 28/89 symbols
  to 9/1 files and 28/88 symbols.
- Remote commit `915fc4d` contains the exact `collectors/` tree. CI run
  33511516566 passed all five jobs, including the 7m48s Linux quality gate,
  and no new Review or Copilot comment was added.
- The direct `ai_actuarial/api/` files compiled successfully and passed Black,
  isort, and a zero-error focused Pylint scan. All 407 directly importing tests
  completed with 400 passed and 7 platform skips.
- The complete pytest suite passed after the direct `api/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 175 Black files,
  114 isort files, and 19 Pylint error identities, with zero new or stale
  entries. The dead-code gate remained exact at 9/1 files and 28/88 symbols.
- Remote commit `bf2d2a0` contains the exact direct `ai_actuarial/api/` cleanup.
  CI run 33513870640 passed all five jobs, including the 7m35s Linux quality
  gate, and no new Review or Copilot comment was added.
- `ai_actuarial/chatbot/` compiled successfully and passed Black, isort, and a
  zero-error focused Pylint scan. All 176 chatbot and direct-consumer tests
  passed. No dedicated test existed for any removed symbol, so no corresponding
  test removal was required.
- The complete pytest suite passed after the `chatbot/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 168 Black files,
  107 isort files, and 19 Pylint error identities, with zero new or stale
  entries. The dead-code gate shrank exactly from 9/1 files and 28/88 symbols
  to 9/1 files and 28/82 symbols.
- Remote commit `675c2b5` contains the exact `ai_actuarial/chatbot/` cleanup.
  CI run 33530581036 passed all five jobs, including the 8m02s Linux quality
  gate, and no new Review or Copilot comment was added.
- `ai_actuarial/rag/` compiled successfully and passed Black, isort, and a
  zero-error focused Pylint scan. The 24 directly importing test files completed
  with 646 passed and 8 platform skips after the one obsolete test was removed.
- The complete pytest suite passed after the `rag/` cleanup with 1,880 tests
  and 10 platform skips. The full static gate passed at 159 Black files, 99
  isort files, and 19 Pylint error identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/1 files and 28/82 symbols to 9/1
  files and 28/72 symbols.
- Remote commit `fdac797` contains the exact `ai_actuarial/rag/` cleanup. CI
  run 33534463645 passed all five jobs, including the 7m56s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/api/routers/` compiled successfully and all 15 route modules
  were confirmed as registered FastAPI production modules. The 15 directly
  related test files completed with 393 passed and 8 platform skips.
- `WeeklySnapshotFilesModel.truncated` is a live Pydantic response field, not
  dead code: the service populates it and endpoint tests assert it. An exact
  whitelist reference now records that framework contract; no source field or
  test was removed.
- The complete pytest suite passed after the router cleanup with 1,880 tests
  and 10 platform skips. The full static gate passed at 146 Black files, 91
  isort files, and 19 Pylint error identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/1 files and 28/72 symbols to 9/1
  files and 28/71 symbols.
- Remote commit `a71e984` contains the exact `ai_actuarial/api/routers/`
  cleanup. CI run 33537947899 passed all five jobs, including the 6m53s Linux
  quality gate, and no new Review or Copilot comment was added.
- `ai_actuarial/api/services/` compiled successfully. Seven confirmed dead
  baseline symbols and two resulting private orphans were removed; no test was
  dedicated to those deleted definitions, so no test removal was required.
- The provider-credential write and environment-import paths now pass
  `status_code=503` correctly when token encryption is unavailable instead of
  raising `TypeError`. A regression covers both HTTP entry points. The ready
  source gate also uses an explicit mapping check, removing a Pylint inference
  false positive without changing its behavior.
- The 12 directly related service test files completed with 462 passed and 9
  platform skips. The complete pytest suite passed with 1,881 tests and 10
  platform skips. The full static gate passed at 129 Black files, 81 isort
  files, and 16 Pylint error identities, with zero new or stale entries. The
  dead-code gate shrank exactly from 9/1 files and 28/71 symbols to 9/1 files
  and 28/64 symbols.
- Remote commit `cbd933b` contains the exact `ai_actuarial/api/services/`
  cleanup. CI run 33539534698 passed all five jobs, including the 6m47s Linux
  quality gate, and no new Review or Copilot comment was added.
- `client/src/components/` no longer contains the unreachable
  `LoadingSkeleton.tsx`. `transformMarkdownUrl` remains live inside
  `MarkdownContent.tsx` but is no longer exported solely for tests; the direct
  helper assertions were removed while the component-level link and hostile
  input coverage was retained.
- The focused component checks passed: both TypeScript dead-code ratchets,
  ESLint, the three Markdown content source tests, frontend type-check, and the
  production build. The complete pytest suite passed with 1,881 tests and 10
  platform skips, and the full unified quality gate passed at 129 Black files,
  81 isort files, and 16 Pylint error identities. The dead-code gate shrank
  exactly from 9/1 files and 28/64 symbols to 8/1 files and 27/64 symbols.
- Remote commit `182d0c0` contains the exact `client/src/components/` cleanup.
  CI run 33540711906 passed all five jobs, including the 13m42s Linux quality
  gate, and no new Review or Copilot comment was added.
- `client/src/hooks/` no longer contains the completely unreferenced
  `use-api-query.ts`. The two live task-option result shapes remain in use but
  are now private implementation types instead of unused public exports.
- The hooks directory passed ESLint, the 27 task React source tests, frontend
  type-check, and the production build. The complete pytest suite passed with
  1,881 tests and 10 platform skips, and the full unified quality gate passed
  at 129 Black files, 81 isort files, and 16 Pylint error identities. The
  dead-code gate shrank exactly from 8/1 files and 27/64 symbols to 7/1 files
  and 25/64 symbols.
- Remote commit `f80d52d` contains the exact `client/src/hooks/` cleanup. CI
  run 33542287174 passed all five jobs, including the 7m35s Linux quality gate,
  and no new Review or Copilot comment was added.
- `client/src/lib/` now exposes only externally consumed contracts. Two unused
  navigation helpers and the test-only knowledge-list authority helper were
  removed; the duplicate ready-data route helper was consolidated under the
  request name. Live helpers and data shapes that are internal to their module
  remain implemented but are no longer exported.
- Tests were updated to exercise the public ready-data merge helper and native
  URL parsing. The one runtime test segment dedicated only to the removed
  authority helper was deleted; the surrounding current behavior tests remain.
  All 77 focused tests, ESLint, frontend type-check, and the production build
  passed. The complete pytest suite passed with 1,881 tests and 10 platform
  skips, and the unified quality gate passed at 129/81/16. The dead-code gate
  shrank exactly from 7/1 files and 25/64 symbols to 7/1 files and 7/64 symbols.
- Remote commit `8beb8d8` contains the exact `client/src/lib/` cleanup. CI run
  33543437722 passed all five jobs, including the 7m41s Linux quality gate, and
  no new Review or Copilot comment was added.
- Five unreachable historical page implementations were removed from
  `client/src/pages/`: `FeatureUnavailable`, `NativeFileDetail`, `NativeLogs`,
  `NativeSettings`, and `NativeTasks`. The live chat route selection type is
  now private to its module.
- Test constants and assertions that read the deleted native file/task pages
  were removed while current FileDetail, FilePreview, task metrics, Markdown,
  and chat route coverage was retained. All 41 focused tests, directory ESLint,
  frontend type-check, and the production build passed. The complete pytest
  suite passed with 1,881 tests and 10 platform skips, and the unified quality
  gate passed at 129/81/16. The dead-code gate shrank exactly from 7/1 files
  and 7/64 symbols to 2/1 files and 6/64 symbols.
- Remote commit `77e54a9` contains the exact `client/src/pages/` cleanup. CI
  run 33544476773 passed all five jobs, and no new review comment was added.
- `client/src/pages/tasks/` no longer contains the unreachable
  `FolderBrowser.tsx` or its unreachable barrel `index.ts`. Three live
  implementation details remain in use but are no longer exported, and three
  duplicate schedule types with no caller were removed. The negative test
  proving that browser uploads do not use the retired folder browser remains
  because it covers current behavior.
- The task-page cleanup passed 32 focused source/runtime tests, directory
  ESLint, frontend type-check, and the production build. One full-suite source
  assertion was corrected to inspect the shared `TaskMetrics` implementation
  instead of relying on a removed re-export comment; its focused rerun passed.
- The complete pytest suite then passed with 1,881 tests and 10 platform skips,
  and the unified quality gate passed at 129/81/16. The dead-code gate shrank
  exactly from 2/1 files and 6/64 symbols to 0/1 files and 0/64 symbols, so the
  TypeScript historical dead-code baseline is now empty.
- Remote commit `0bbda30` contains the exact `client/src/pages/tasks/`
  cleanup. CI run 33547151953 passed all five jobs, including the complete
  Linux quality gate, and no new review comment was added.
- The exported `CollectionConfig.auto_download` dataclass field was retained as
  a public constructor contract and added to the statically validated exact
  whitelist. No source or test was deleted. All 112 directly related collector
  tests passed, and Black, isort, and Pylint passed for the touched whitelist
  and collector base files.
- The complete pytest suite passed with 1,881 tests and 10 platform skips, and
  the unified quality gate passed at 129/81/16. The dead-code gate shrank
  exactly from 0/1 files and 0/64 symbols to 0/1 files and 0/63 symbols.
- Remote commit `1a792e0` contains the exact collector public-contract
  classification. CI run 33549779936 passed all five jobs, including the
  complete Linux quality gate, and no new review comment was added.
- The final unreachable Python module `ai_actuarial/pipeline_config.py` was
  deleted. Its 20-test dedicated file and four tests in the immutable-guards
  suite that imported only that module were deleted with it; the live manifest
  schema-version ingestion traceability test remains.
- The pipeline-config cleanup compiled successfully, passed all 44 retained
  focused tests, and left no repository reference to the deleted module. The
  complete pytest suite passed with 1,857 tests and 10 platform skips. The
  unified quality gate passed after shrinking to 127 Black files, 80 isort
  files, and 16 Pylint identities. Both TypeScript and Python dead-file
  baselines are now empty; symbol findings remain 0/63.

## Files changed

- Gate implementation/config: `scripts/dead_code_gate.py`,
  `scripts/quality_gate.py`, `knip.json`, `eslint.config.mjs`, `pyproject.toml`,
  `package.json`, lockfile, development requirements, and both baselines.
- Framework review: `config/dead_code_whitelist.py`.
- Automation: `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.
- Documentation: `docs/dead-code.md`, docs index, and both root READMEs.
- Focused cleanup/tests: affected React files, small Python unused-argument
  cleanups, gate tests, and narrow full-suite contract corrections.
- First historical directory cleanup: `config/__init__.py`,
  `config/settings.py`, `config/yaml_config.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Second historical directory cleanup: eleven formatted Python files under
  `scripts/` and the matching removals from `quality-gate-baseline.json`.
- Third historical directory cleanup: seven formatted Python files under
  `ai_actuarial/agentic_rag/` and the matching removals from
  `quality-gate-baseline.json`.
- Fourth historical directory cleanup:
  `ai_actuarial/api/middleware/rate_limit.py` and the matching removals from
  `quality-gate-baseline.json`.
- Fifth historical directory cleanup: `ai_actuarial/models/__init__.py`,
  `ai_actuarial/models/api_token.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Sixth historical directory cleanup: `ai_actuarial/security/__init__.py`,
  `ai_actuarial/security/url_safety.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Seventh historical directory cleanup: `ai_actuarial/services/__init__.py`,
  `ai_actuarial/services/token_encryption.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Eighth historical directory cleanup: deleted the unreachable
  `ai_actuarial/processors/` package and its inaccurate README, then removed
  exactly three module and four method findings from `dead-code-baseline.json`
  plus the three matching formatter paths from `quality-gate-baseline.json`.
- Ninth historical directory cleanup: deleted
  `ai_actuarial/collectors/adhoc.py`, removed its inaccurate README section and
  two dead-code findings, removed two unused imports, formatted the five
  reachable collector implementations, and removed their eleven matching
  formatter paths from `quality-gate-baseline.json`.
- Tenth historical directory cleanup: formatted `ai_actuarial/api/app.py`,
  `ai_actuarial/api/deps.py`, and `ai_actuarial/api/route_inventory.py`, made
  the authentication type narrowing explicit, and removed their six matching
  Black/isort/Pylint entries from `quality-gate-baseline.json`.
- Eleventh historical directory cleanup: formatted all eight Python files under
  `ai_actuarial/chatbot/`, removed six confirmed unused public symbols and one
  private helper, reclassified the explicit `select_kbs` compatibility alias,
  and removed the matching dead-code and formatter baseline entries. No test
  file or test case was removed because none corresponded to the deleted code.
- Twelfth historical directory cleanup: formatted the nine historical Python
  files under `ai_actuarial/rag/`, removed ten reviewed dead-code baseline
  symbols plus four exact or cascading orphans, deleted the single test tied to
  the removed immutable-index helper, and removed the matching dead-code and
  formatter baseline entries.
- Thirteenth historical directory cleanup: formatted all 15 files under
  `ai_actuarial/api/routers/`, added the precise Pydantic response-field
  whitelist for `WeeklySnapshotFilesModel.truncated`, and removed its stale
  dead-code entry plus the 21 matching formatter baseline entries.
- Fourteenth historical directory cleanup: formatted all 17 files under
  `ai_actuarial/api/services/`, removed seven reviewed dead-code baseline
  symbols plus two cascading private orphans, fixed three Pylint identities,
  added the two-entry-point encryption failure regression, and removed the
  matching dead-code and 27 formatter/linter baseline entries.
- Fifteenth historical directory cleanup: deleted the unreachable
  `client/src/components/LoadingSkeleton.tsx`, made the live Markdown URL
  transformer private, removed only its direct test-only import and assertions,
  and removed the matching two TypeScript dead-code baseline entries.
- Sixteenth historical directory cleanup: deleted the unreachable
  `client/src/hooks/use-api-query.ts`, made two live task-option interfaces
  private, and removed the matching three TypeScript dead-code baseline entries.
- Seventeenth historical directory cleanup: removed three confirmed dead
  `client/src/lib/` functions, consolidated a duplicate ready-data request
  export, made fourteen live implementation details private, updated the one
  cross-directory caller and focused tests, and removed the matching eighteen
  TypeScript dead-code baseline entries.
- Eighteenth historical directory cleanup: deleted five unreachable legacy
  files under `client/src/pages/`, made the live chat route selection type
  private, removed only the test constants and assertions tied to the deleted
  pages, and removed the matching six TypeScript dead-code baseline entries.
- Nineteenth historical directory cleanup: deleted the unreachable
  `client/src/pages/tasks/FolderBrowser.tsx` and barrel `index.ts`, removed
  three unused exports and three unused duplicate schedule types, corrected
  one source-contract test to inspect the real shared metrics component, and
  removed the final eight TypeScript dead-code baseline entries.
- Twentieth historical directory cleanup: retained the public exported
  `CollectionConfig.auto_download` constructor field, recorded its exact
  compatibility reference in the validated whitelist, and removed its stale
  Python dead-code baseline entry without changing source or tests.
- Twenty-first historical directory cleanup: deleted the unreachable
  `ai_actuarial/pipeline_config.py` module and its 24 module-only tests,
  formatted the touched immutable-guards test while preserving its live
  manifest traceability case, and removed the final Python dead-file baseline
  plus the matching Black/isort baseline entries.
- Twenty-second historical directory cleanup: formatted all 31 direct Python
  files under `ai_actuarial/`, deleted 20 confirmed-unused root symbols plus one
  cascading legacy weekly-summary reader, retained 27 framework/public
  contracts through exact validated whitelist references, and narrowed seven
  SQLAlchemy/Pydantic Pylint suppressions to their individual call sites. No
  test was removed because none was dedicated to the deleted code. Focused
  tests passed 132/1, the full suite passed 1857/10, the dead-code gate passed
  at 0 files/17 symbols, and the quality baseline fell from 127/80/16 to
  96/60/9.
- Twenty-third historical directory cleanup: retained the nested
  `block_retired_api_fallback` FastAPI 410 route in `ai_actuarial/api/app.py`
  and added its exact source-level framework reference. Focused tests passed
  20/20; after one host-resource-abnormal test run was stopped and isolated,
  the unchanged historical file passed 83/83 and a clean full rerun passed
  1857/10 plus Black, isort, and Pylint. The dead-code symbol baseline fell
  from 17 to 16; the quality baseline remains 96/60/9. The first remote
  quality-gate attempt hit a concurrent-test race in an unrelated historical
  schema test; the failed job rerun passed without source changes, and all five
  remote CI jobs are green.
- Twenty-fourth historical directory cleanup: retained six public exported
  `ChatbotConfig` fields loaded from environment/YAML settings plus the
  explicit `QueryRouter.select_kbs` compatibility alias, recording each as an
  exact validated whitelist reference. No production code or tests were
  removed. Focused tests passed 115/115, the full suite passed 1857/10 plus
  Black, isort, and Pylint, and the dead-code symbol baseline fell from 16 to
  9; the quality baseline remains 96/60/9. All five remote CI jobs passed.
- Twenty-fifth historical directory cleanup: retained the public
  `RAGConfig.chunk_strategy` field loaded from environment/YAML settings and
  recorded its exact validated whitelist reference. No production code or
  tests were removed. Focused tests passed 41/41, the full suite passed 1857/10
  plus Black, isort, and Pylint, and the dead-code symbol baseline fell from 9
  to 8; the quality baseline remains 96/60/9. All five remote CI jobs passed.
- Twenty-sixth historical directory cleanup: formatted all six Python files
  under `tests/agentic_rag/` (five Black and two isort baseline identities) and
  strengthened `test_evaluate_single_pass` to verify the fake retriever
  receives the query and `top_k`. No tests were removed. Focused tests passed
  102/102, the full suite passed 1857/10 plus Black, isort, and Pylint, the
  dead-code symbol baseline fell from 8 to 6, and the quality baseline fell
  from 96/60/9 to 91/58/9. All five remote CI jobs passed.
- Twenty-seventh historical directory cleanup: formatted the two historical
  Python test files under `tests/unit/`, removing two Black and two isort
  baseline identities. No code or tests were removed. Focused tests passed
  40/40, the full suite passed 1857/10 plus Black, isort, and Pylint, the
  dead-code baseline remains 0 files/6 symbols, and the quality baseline fell
  from 91/58/9 to 89/56/9. All five remote CI jobs passed.
- Twenty-eighth and final historical directory cleanup: formatted all 105
  direct Python files under `tests/` (89 historical Black and 56 isort baseline
  identities), resolved all nine Pylint identities, removed six unused test
  symbols without deleting any test case, strengthened the API-token timestamp
  assertion, and isolated the mutating schema-validator test from background
  database activity. Focused tests passed 319/7, the full suite passed 1857/10,
  independent semantic and mechanical reviews found no issues, and both the
  dead-code and quality baselines are now completely empty: 0 files/0 symbols
  and 0/0/0 respectively. All five remote CI jobs passed. PR #318 is clean and
  mergeable; the only review thread was an older Copilot finding already fixed
  and acknowledged before this final cleanup.

## Working tree notes

- Existing untracked `diagrams/` and `graphify-out/` remain user-owned,
  untouched, and excluded from the commit.
- Generated `reports/`, coverage output, build output, and installed
  dependencies are ignored.

## Blockers or decisions needed

- No implementation or local validation blocker.
- Merge is not authorized by the current request; publication stops at an open
  PR unless explicit merge authorization is given.

## Recommended next action

- Report the completed directory-by-directory cleanup and leave the clean,
  mergeable PR #318 open. Merge only after explicit authorization.

# Project Status — Issue #319 loose-coupled incremental stages

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\e680\AI_actuarial_inforsearch`
- Branch: `codex/issue-319-loose-coupled-stages`
- Baseline: `origin/main@ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`
- Issue: `#319 fix(pipeline): continue loose-coupled incremental stages after partial success`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-319.json`
- Delivery stage: remote feedback assessed; one confirmed contract fix validated; follow-up push pending

## Issue #319 acceptance criteria

- AC-1: Production-shaped Markdown `status=error` with `items_downloaded=2` launches Catalog
  exactly once while preserving the Markdown task's original status, errors, counters, result,
  and log.
- AC-2: Scheduled, Markdown, Catalog, Chunk, and Embedding all use the same terminal decision
  matrix: `completed/error + successful outputs > 0` advances once; `completed + 0` completes as
  a clean no-op; `error + 0` ends in error; `stopped` ends stopped; missing task or hard exception
  ends in error.
- AC-3: Catalog launches from its saved/default incremental configuration without predecessor
  `file_urls` and may select its normal historical uncataloged/outdated backlog.
- AC-4: Chunk launches from its saved/default incremental configuration without predecessor
  Markdown `files` and may select its normal historical Markdown-ready backlog.
- AC-5: Embedding launches without predecessor `chunk_set_ids` or `file_urls`; a minimal
  module-owned selector-free incremental backlog mode computes its own eligible ready chunk-set
  backlog and is available through both manual/API and Baton launches.
- AC-6: Given the same saved/default module configuration, Baton and manual launches resolve
  equivalent runtime parameters and work-selection behavior; raw frontend payload equality is not
  required.
- AC-7: Existing skipped, reused, retry-eligible, and historical backlog behavior remains owned by
  each module; skipped work is not reinterpreted as a predecessor handoff artifact.
- AC-8: Repeated ordinary ticks do not launch a next stage or subtask twice.
- AC-9: Current indexable KBs are enumerated in stable order across `manual`, `category`, and `all`
  modes; zero KBs completes cleanly.
- AC-10: One failed KB Index or Ready Data task is recorded and does not block later KBs; any
  stopped KB subtask stops the whole round immediately and launches no later KB.
- AC-11: If relay reaches the end, `round_status=completed` means orchestration completed and does
  not rewrite any individual task outcome.
- AC-12: Baton state remains compact: current stage/task plus existing KB summary only; no copied
  per-item errors, partial-evidence schema, or source-task mutation.
- AC-13: Existing standalone/manual task APIs, forms, saved/default configuration, module logs,
  status semantics, and Ready Data/KB behavior remain unchanged except for the shared Embedding
  selector-free backlog mode required by AC-5.
- AC-14: Existing Baton/runtime tests, the full stage matrix, production-shape Markdown regression,
  selector-absence and historical-backlog regressions, manual/Baton equivalence, KB failure/stop
  paths, duplicate-tick behavior, and all repository-required checks pass.

## Issue #319 stage decision matrix

| Task outcome | Successful output count | Baton result |
| --- | ---: | --- |
| `completed` | `> 0` | Launch the next module's normal incremental task once |
| `error` | `> 0` | Preserve the task error and launch the next module once |
| `completed` | `0` | Complete the round as a clean no-op |
| `error` | `0` | End the round as `error` |
| `stopped` | any | End the round as `stopped` |
| missing task or hard exception | unknown / `0` | End the round as `error` |

## Issue #319 scope and non-goals

- Owned production scope: `ai_actuarial/pipeline_baton.py`; minimal shared runtime/API/Embedding
  wiring only where AC-5/AC-6 requires it. Focused Baton/runtime/API/domain tests are in scope.
  Pipeline status/UI copy changes are conditional on observable wording changes.
- Sibling repositories and the primary checkout's Issue #317 changes are off-limits.
- No predecessor file/hash/chunk-set handoff, frozen cohort, global lineage, new publication
  transaction, DAG, retry/resume/checkpoint/lease framework, automatic retry, crawler change,
  module redesign, or suppression/rewriting of task errors.
- Review-policy override: none. Findings must be realistically reproducible and map directly to
  an AC above.

## Issue #319 baseline and history evidence

- The assigned worktree was clean and detached at the supplied baseline. After fetch, `HEAD`,
  `origin/main`, and their merge-base all remained exactly `ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`;
  the isolated branch above was then created.
- A production-shaped no-edit reproduction showed Markdown `error + items_downloaded=2` leaves
  `round_status=error` and starts no Catalog task. Existing #292 Scheduled partial-success tests
  still pass.
- The same baseline reproduction showed Catalog receives predecessor `file_urls`, Chunk receives
  predecessor Markdown `files`, and Embedding receives predecessor `chunk_set_ids`.
- `git blame` and `git log -S` trace the general terminal behavior to the original Baton, the
  Scheduled-only exception to merged PR #292, and all three exact selector injections to commit
  `7a175050` (`feat: persist chunk embeddings`). The original #179 Baton regression explicitly
  asserted independent tasks without output handoff before that commit changed the contract.
- Duplicate search across open/closed/merged PRs, local/remote branches, and commit messages found
  no equivalent #319 work. Merged PR #292 covers Scheduled only and is not a duplicate.

## Issue #319 implementation state

- Baton now uses `items_downloaded` as the single authoritative successful-output count for all
  five non-KB phases. Partial errors advance once, clean zero-output completions stop cleanly,
  zero-output errors fail, stopped tasks halt, and missing tasks or hard orchestration failures fail.
- Catalog and Chunk now launch their normal saved/default incremental backlog without predecessor
  selectors. Baton no longer persists copied Markdown file evidence.
- Embedding now exposes a selector-free `incremental` mode owned by the embedding module. It
  resolves the current server identity first, scans ready chunk sets in stable order, validates
  chunk-set stability, and selects sets containing missing or invalid embeddings while preserving
  existing reuse and repair behavior.
- Manual/API, Baton, Tasks, and scheduled Chunk & Embedding composition use the same selector-free
  Embedding mode. File Detail retains its explicit single-file `chunk_set_ids` scope.
- Scheduled composition and Tasks both retain their existing empty Chunk-result guard. Reused
  stable chunk sets still launch selector-free Embedding so historical missing/invalid coverage can
  be repaired.
- KB Index/Ready Data preserves stable `manual`/`category`/`all` enumeration: one KB error is
  recorded and later KBs continue; a stopped KB task halts the round immediately.

## Issue #319 local review

- Round 1 found and fixed a scheduled-composition regression where reused stable chunk sets had
  `items_downloaded=0` and incorrectly skipped Embedding. The fix gates on non-empty stable
  `result.chunk_sets` and still launches only `incremental: true`.
- Round 2 found and fixed the matching Tasks regression where an empty Chunk result could launch an
  unrelated global Embedding backlog. Tasks now keeps the non-empty result guard without handing
  the IDs to Embedding.
- Round 3 used a fresh read-only reviewer and passed with no reproducible #319 finding. The final
  reviewer independently ran 96 focused tests.

## Issue #319 verification

- TDD red baseline for the new focused file: 18 product failures and 15 passes after correcting
  three test-fixture defects; final focused file: 33 passes.
- Final related Baton/runtime/API/CLI/UI suite: 102 passes; broader related suite previously passed
  151 tests plus 40 Embedding/Chunk domain tests.
- Unified quality gate: 1916 passed, 10 skipped; Black, isort, and Pylint passed. The first attempt
  was stopped after the pytest process reached 23.6 GB and left 0.1 GB host memory; a clean isolated
  rerun used normal memory and passed without source changes.
- Dead-code file and symbol gates: 0 findings. Frontend lint: 0 errors and five existing warnings;
  typecheck and production build passed.
- Python smoke: FastAPI 13 passed; Agentic RAG eval 31 passed; eval CLI passed all 3 cases with full
  evidence/citation/refusal metrics.
- `git diff --check` passed. No visible form, layout, or wording changed, so browser visual smoke was
  not required; the changed request contract is covered by source tests, typecheck, and build.
- After final fetch, `HEAD`, `origin/main`, and their merge-base remain
  `ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`.

## Issue #319 remote feedback

- PR #327 was marked Ready at head `02a085339a64ddd9b7d131e897c0b33ff3f2497b`. The single
  feedback window ran for 680.49 seconds before one complete snapshot was fetched.
- All five required remote checks passed. No human review, PR comment, or Issue comment was
  present. Copilot left two inline comments.
- The first Copilot comment was confirmed: selector-free `incremental` accepted and echoed a
  `profile_id` that it did not apply. The minimal fix rejects `incremental + profile_id` at both
  the API launch boundary and the Embedding selection boundary; it does not add profile-filter
  semantics or change Baton's `{incremental: true}` payload.
- The second Copilot comment was rejected under the repository review policy. It proposed loading
  chunk IDs before content as a performance optimization but provided no reproducible functional,
  workflow, data-contract, or error-handling failure mapped to #319.
- The confirmed fix failed two new tests before implementation, then passed them. Manager reran the
  final Embedding/API/Baton/UI combination with 169 passes; the focused #319 file now has 35 passes.

## Issue #319 working tree notes

- Scoped production changes are limited to Pipeline Baton, Embedding selection/runtime/API wiring,
  and the Tasks request path. Scoped test changes cover the matrix, storage backlog, API/manual
  parity, scheduled/Tasks empty and reused results, and KB error/stop behavior.
- The new untracked `tests/test_issue_319_loose_coupled_pipeline.py` is an intentional scoped test
  file and will be included in the commit. Generated reports, coverage, build output, and installed
  dependencies are ignored.
- No unrelated local change is present. Sibling repositories and the primary checkout's Issue #317
  changes remain unread and untouched.

## Issue #319 blockers or decisions needed

- No implementation, review, validation, or publication blocker.

## Issue #319 recommended next action

- Commit and push the confirmed remote contract fix, allow required checks to rerun, reply to both
  captured Copilot threads with the accepted/rejected disposition, then merge once the updated head
  is green.
# Project Status — Issue #334 Recategory dry-run UI

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\3632\AI_actuarial_inforsearch`
- Branch: `codex/issue-334-recategory-dry-run-ui`
- Baseline: `origin/main@73215789cc6202add89d808ab35d5c430fa1ef0a`
- Issue: `#334 bug(ui): show Recategory dry-run results and place it before Catalog`
- Review state: `C:\Project\AI_actuarial_inforsearch\.git\codex-issue-to-merge\issue-334.json`
- Delivery stage: PR #335 is Ready; the single remote-feedback snapshot was assessed and its one
  valid localization fix passed focused validation; preparing the follow-up commit and current-head
  checks before merge
- Progress heartbeat: id `issue-334-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #334 acceptance criteria

- AC-1: A completed `recategory` history task whose `metadata.dry_run` is exactly true shows a
  human-readable Dry Run Result in the Task History detail/log dialog, sourced from the history
  task metadata so the same result remains visible after refresh.
- AC-2: When changes exist, the result accurately shows whether recategorization is needed and
  lists every removed and added category with its corresponding `removed_impact` or
  `added_impact` article count in a quickly scannable layout.
- AC-3: When `needs_recategory` is false and no category changes exist, the result shows an
  explicit localized no-changes state instead of an empty block.
- AC-4: Missing, incomplete, legacy, or wrong-shaped metadata degrades safely: ineligible tasks
  do not show the result, incomplete eligible results render only safe values, and no `null`,
  `undefined`, or task-detail crash reaches the user.
- AC-5: The result is read-only and offers no implicit Apply action or data mutation; the existing
  Recategory Plan/Apply algorithms and task execution contracts remain unchanged.
- AC-6: Re-categorize appears before Catalog in the Run Task cards and Scheduled Task type list;
  the Task History type filter gains Re-categorize before Catalog. Recategory remains independent
  and is not added to the automatic Pipeline.
- AC-7: All added user-facing copy is complete in English and Chinese, and category names, counts,
  lists, and the empty state fit without horizontal overflow at desktop and 320px widths.
- AC-8: Focused frontend regression tests cover change, no-change, missing/incomplete metadata,
  eligibility, and all three ordering contracts; the frontend checks, repository quality/dead-code
  gates, Python smoke gates, and desktop plus 320px browser smoke pass.

## Issue #334 scope, baseline evidence, and non-goals

- Code-change delivery is required. A baseline reproduction failed all five probes: the Run Task
  order and Scheduled Task order put Re-categorize after Catalog, Task History omits the filter
  option, `HistoryTask` has no metadata field, and the detail dialog has no dry-run rendering.
- The clean worktree started detached at the supplied baseline; `HEAD`, `origin/main`, and their
  merge-base all matched `73215789cc6202add89d808ab35d5c430fa1ef0a` before switching to the
  pre-created assigned branch at that same commit.
- PR #202 added the Recategory backend and appended basic Run/Scheduled UI entries. Its body and
  commit history describe task wiring but no dry-run history result UI or intended ordering.
  PR #201 only added taxonomy-state support, so neither is equivalent to Issue #334.
- Worker-owned files are limited to the Tasks history/detail and task-type ordering surfaces,
  bilingual task copy, and directly corresponding frontend tests. A small dedicated result
  component is allowed if it is the narrowest complete implementation. This manager owns this
  project-status record.
- Non-goals: backend result storage or API changes, `plan_recategory()` or Apply algorithm changes,
  taxonomy/Catalog/KB sync changes, Pipeline execution or dependency changes, automatic Plan-to-
  Apply behavior, sibling repositories, dependency upgrades, security frameworks, or speculative
  abstractions.
- Review-policy override: none; the default scoped review policy applies unchanged.

## Issue #334 blockers or decisions needed

- None.

## Issue #334 implementation and local review

- The Task History detail/log dialog now renders a dedicated read-only Dry Run Result only for
  completed Recategory plans with `metadata.dry_run === true`. It shows the plan decision,
  removed/added categories, safe per-category impact counts, the explicit no-change state, and an
  unavailable state for incomplete eligible metadata.
- Runtime guards accept only plain-object metadata, non-empty category strings, and non-negative
  integer counts. Missing, legacy, wrong-shaped, or ineligible metadata cannot render `null` or
  `undefined` and cannot break the rest of the task detail.
- Re-categorize now precedes Catalog in Run Task, Scheduled Task, and Task History filter order;
  the filter includes the previously missing option. Pipeline definitions remain unchanged.
- English and Chinese result copy is complete. Long names wrap, long lists are vertically bounded,
  and the result contains no Apply button or other mutation control.
- The Task History type filter now uses the existing English/Chinese task-type translations for
  every concrete option, eliminating the mixed-language dropdown identified during remote review.
- TDD reproduced three expected pre-fix failures, then the Issue suite passed all three tests.
  The worker inspected all same-shaped user-facing selectors plus desktop/mobile history paths;
  Logs, task-specific forms, and Pipeline were explicitly excluded with acceptance-mapped reasons.
- Fresh read-only review round 1 independently inspected the complete diff and tests and passed
  with no valid findings. Its only residual was the required changed-result browser evidence, which
  was completed after review without a code change.
- The first unified quality-gate invocation passed all 2,025 tests but stopped on Black/isort
  formatting of the new Python test. The same worker made only the formatter-required test-layout
  change; focused tests and formatter checks passed. The state record explains why this mechanical,
  behavior-neutral edit did not reopen local review.

## Issue #334 final local validation

- Focused Issue/task-history regression: 36 passed. Recategory/API regression: 34 passed. Scheduled
  Tasks and Task Metrics React runtime assertions passed. `git diff --check` passed.
- Unified quality gate passed on the complete post-format diff: 2,015 passed and 10 skipped; Black,
  isort, and error-only Pylint passed.
- Both dead-code gates passed with zero findings. Frontend lint passed with zero errors and five
  existing unrelated Hook warnings; TypeScript and the production build passed, with only the
  existing large-chunk advisory.
- Python smoke passed 13 FastAPI tests, 31 Agentic evaluation tests, and all 3 CLI evaluation cases;
  evidence, citation, and refusal rates were 1.0 and unsupported-answer rate was 0.
- Live browser smoke used disposable local data. Desktop and 320px both showed the changed result,
  the long removed category with impact 1, all 15 added categories with impact 0, bounded vertical
  scrolling, zero horizontal overflow, and zero result buttons. A page refresh preserved the same
  history result. The previously verified no-change result showed the explicit empty state.
- The first post-feedback CI run passed four jobs and all 2,025 tests except one older source
  assertion that expected the now-replaced hard-coded RAG filter label. The same worker updated only
  that assertion to the localized option; the exact test and the Issue suite passed locally.
- Disposable local browser servers were stopped after validation. No production operation ran.

## Issue #334 recommended next action

- Commit and push the validated remote-feedback fix to PR #335, require all checks to pass on that
  exact head, then merge and complete Issue, branch, worktree, and heartbeat cleanup.
# Project Status — Issue #312 schedule presets

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\257d\AI_actuarial_inforsearch`
- Branch: `codex/issue-312-schedule-presets`
- Baseline: `origin/main@146028ac8258550f54953c9343b0fd01062c4de3`
- Issue: `#312 feat(schedule): add frequency, run-time, and timezone presets`
- State file: `C:\Project\AI_actuarial_inforsearch\.git\codex-issue-to-merge\issue-312.json`
- Delivery stage: implementation and six-round local review complete; final local gates pass and
  the branch is ready for commit, push, and draft PR publication

## Issue #312 acceptance criteria

- AC-1: Scheduled-task create/edit UI exposes only Every N minutes, Every N hours, Daily at
  `HH:MM`, and Weekly on Monday at `HH:MM`, showing only the quantity, run-time, and timezone
  fields relevant to the selected form.
- AC-2: Add/update APIs accept only the four canonical structured forms; invalid or non-positive N,
  invalid/non-canonical `HH:MM`, extra tokens, unknown timezones, and unsupported interval/timezone
  combinations return 400 without changing configured or effective scheduler state.
- AC-3: Rolling minute/hour schedules have no timezone and reject a supplied timezone. Newly saved
  daily/weekly fixed-time schedules require exactly `UTC` or `Asia/Shanghai`, persist a canonical
  interval plus timezone, and round-trip through reads and the UI.
- AC-4: `weekly at HH:MM` registers an effective Monday job at the selected timezone through the
  existing #307 reconciliation path; no second apply or scheduler mutation mechanism is added.
- AC-5: Existing `daily`, `weekly`, and fixed-time tasks without a timezone retain their prior
  process-local behavior and stored shape across read, edit-without-schedule-change, restart, and
  reinitialize until a structured schedule is explicitly saved.
- AC-6: UTC and Asia/Shanghai fixed-time schedules preserve their wall-clock meaning and are tested
  across UTC/CST cross-day and Monday boundaries.
- AC-7: `weekly_summary` remains locked to the previous complete UTC ISO week and its fixed-time
  schedule remains UTC; the UI/status also shows the equivalent Asia/Shanghai wall time.
- AC-8: Effective fixed-time job status includes unambiguous timezone/offset information and
  serialized last/next timestamps carry an offset; naive runtime values are never labeled UTC.
- AC-9: English/Chinese copy, focused backend/frontend/runtime tests, create/edit round trips,
  frontend lint/typecheck/build, browser smoke, dead-code gates, Python smoke, and the repository
  quality gate pass.

## Issue #312 scope, evidence, and non-goals

- Owned production scope is the narrow shared scheduled-task expression contract, scheduled-task
  add/update persistence and #307 reconciliation comparison, runtime registration/status, the
  Scheduled Tasks create/edit UI and same-shaped direct scheduled-task creation UI where required,
  bilingual copy, and directly corresponding tests. This manager owns this status record.
- Dependency #307 is closed by merged PR #325. Its desired/effective reconciliation, rollback,
  job identity, and RBAC implementation are reused and must not be duplicated.
- Non-goals: cron or a generic builder; arbitrary weekdays; monthly/yearly/holiday rules;
  distributed scheduling, catch-up, or misfire policy; site/default schedule redesign; Pipeline
  Baton frequency changes; reconciliation/RBAC redesign; dependency upgrades; sibling repositories;
  security frameworks; or speculative abstractions.
- The isolated worktree was clean and detached at startup. After fetch, `HEAD`, `origin/main`, the
  assigned branch, and their merge-base all matched the supplied baseline exactly; the branch was
  then attached without changing tracked files.
- A fresh audit found no open/closed PR, remote branch, or commit matching #312, schedule/timezone
  presets, `weekly at`, or `Asia/Shanghai`; duplicate-work-audit is recorded as `proceed`.
- Baseline source and runtime probes confirm a free-text interval field, no `weekly at` validation
  or registration, ignored daily `at_timezone`, non-canonical single-digit time acceptance, no
  persisted timezone, and naive-looking status timestamps. Delivery shape is `code-change`.
- Review-policy override: none. Only realistically reproducible functionality, workflow,
  data-contract, or error-handling findings mapped directly to an AC above are accepted.

## Issue #312 required validation

- Parser/API matrix for every accepted and rejected interval/timezone combination, including
  state-preserving 400 failures and canonical persisted output.
- Legacy fixtures for read, edit without schedule fields, restart, reinitialize, and process-local
  `daily`/`weekly`/no-timezone behavior.
- Real and fallback scheduler registration, #307 add/update reconciliation and rollback regression,
  Monday semantics, UTC/Asia-Shanghai cross-day boundaries, offset-bearing status, and Weekly
  Summary previous-complete-UTC-week/CST-equivalent tests.
- Scheduled Tasks and direct-create UI create/edit round trips, conditional field visibility,
  weekly-summary locking, bilingual copy, and desktop plus 320px browser smoke.
- Focused backend/frontend suites, `git diff --check`, frontend lint/typecheck/build, both dead-code
  gates, all three Python CI smoke commands, and `python scripts/quality_gate.py`.

## Issue #312 implementation and local review

- Added one shared schedule-preset contract for strict structured writes and bounded legacy runtime
  parsing. Rolling schedules omit timezone; fixed schedules persist only `UTC` or `Asia/Shanghai`.
- Scheduled-task writes validate before mutation, preserve unchanged legacy schedule fields, and use
  the existing #307 reconciliation/rollback path for effective jobs.
- Runtime registration supports Monday weekly-at schedules, selected fixed timezones, offset-bearing
  status, process-local legacy status, and the previous-complete-UTC-week Weekly Summary contract.
- Scheduled Tasks and direct-create UI now expose the four structured forms with bilingual copy.
  Legacy fixed/no-timezone tasks show process-local state until explicit conversion; legacy
  non-weekly Weekly Summary schedules show their real cadence read-only with an explicit Weekly UTC
  migration action.
- Six fresh read-only review rounds were completed. Accepted findings covered legacy task-type edits,
  invalid equivalent-time display, baseline-valid legacy whitespace/leading zeros, Weekly Summary
  timezone compatibility/type transitions, legacy Weekly Summary UI truthfulness, and ordinary
  legacy process-local UI truthfulness. The same persistent worker fixed each accepted finding.
  Round 6 returned full PASS with no valid Issue #312 findings.
- Post-review isort normalization and removal of four test-only helper exports were behavior-neutral
  gate cleanups by the same worker; state decisions record why functional review did not reopen.

## Issue #312 final local validation

- Unified quality gate: PASS on the final code, with 2,099 passed, 10 skipped, plus Black, isort, and
  error-only Pylint.
- Focused schedule/API/runtime/UI regression: 161 passed. Final React-source/Issue suite: 104 passed.
  Both executable TSX component suites and TypeScript typecheck passed.
- Frontend lint passed with zero errors and five pre-existing unrelated Hook warnings. Production
  build passed with only the existing large-chunk advisory.
- File and symbol dead-code gates passed with zero baseline findings. `git diff --check` passed.
- CI smoke passed 13 FastAPI tests, 31 Agentic evaluation tests, and all 3 CLI evaluation cases;
  evidence, citation, and refusal rates were 1.0 and unsupported-answer rate was 0.
- Disposable browser smoke passed in English and Chinese at desktop and 320px. It verified explicit
  process-local legacy display, direct canonical UTC conversion, offset/timezone status, read-only
  legacy Weekly Summary cadence, explicit Weekly UTC conversion, and Shanghai-equivalent copy.
  Browser services and temporary data were stopped and removed afterward.

## Issue #312 blockers or decisions needed

- None.

## Issue #312 recommended next action

- Commit and push the validated branch, create a draft PR with `Closes #312`, mark it ready, observe
  the full remote-feedback window, assess the single feedback snapshot, require checks on the exact
  head, then merge and complete Issue/branch/worktree cleanup.

## Issue #377 current work

- Updated: 2026-09-27 Asia/Shanghai.
- Repository: `AI_actuarial_inforsearch`; branch: `fix/issue-377-legacy-bindings`.
- `resolve_kb_bound_chunks` now performs one detect/heal pass for KBs with no persisted bindings:
  it selects the latest ready chunk set per member under the selected profile, repairs a missing
  profile only when exactly one valid profile covers every member, writes warning/audit events,
  persists `kb_chunk_bindings`, and then re-enters the existing strict #238 contract. Partial or
  malformed binding sets remain fail-closed.
- Added idempotent `scripts/maintenance/reconcile_legacy_kb_bindings.py`, dry-run by default with
  `--apply` for writes, plus three Issue #377 regression tests.
- Focused validation passed 31 tests (`#377` plus `#238`) and 130 related Ready Data/file mutation
  tests. Targeted Black/isort/error-only Pylint and `git diff --check` passed. The full quality gate
  ran 2,198 tests: 2,166 passed and 32 failed because the Python image lacks npm/docker/tsx and one
  path-sensitive source test assumes the original checkout path; no touched Python test failed.

---

- Round 2 (2026-09-14): refreshed the UI list after successful role and active-state mutations so active-admin protection uses server-current data; added the role-transition count regression; focused pytest (7) and Python compilation passed, while the frontend build remains blocked by absent node_modules.

- Updated: 2026-09-14 Asia/Shanghai.
- Repository: `AI_actuarial_inforsearch`; branch: `fix/357-user-self-protection`.
- Scope: guard user role and active-state mutations, user-management UI affordances,
  focused regression coverage, and this status record only. Sibling repositories and
  production data were not accessed.
- Implementation: `Storage.update_user_with_admin_protection` uses one `BEGIN IMMEDIATE`
  transaction for target lookup, active email-admin count, state update, and audit writes.
  It prevents an email-session admin from removing their own active-admin status and
  prevents every principal type from removing the last active email admin. Inactive
  admins do not count. The service turns blocked requests into HTTP 409 responses.
- Audit: both blocked and successful changes are written to `audit_events` and the
  target user's activity history. `detail` is a compact JSON object with operator kind
  and stable ID, target user ID, operation, result, and reason; it contains no
  credential, password, or session value.
- UI: unsafe self/last-admin role choices and disable actions are disabled with an
  explanatory visible reason in English and Chinese. Backend enforcement remains authoritative.
- Recovery: added `docs/runbooks/admin-break-glass.md` with offline DB and controlled
  bootstrap recovery, backup, validation, rollback, audit, and secret-rotation guidance.
- Validation: `python -m pytest -q --no-cov tests/test_user_self_protection.py` passed
  (6); `python -m py_compile ai_actuarial/storage.py ai_actuarial/api/services/auth.py
  tests/test_user_self_protection.py` and `git diff --check` passed. The frontend build
  could not run because `node_modules/.bin/vite` is absent in this worktree.
- Delivery: staging/commit failed because Git metadata is outside the writable workspace:
  `/opt/ai_actuarial_inforsearch/.git/worktrees/fix-357-user-self-protection/index.lock`
  cannot be created on its read-only filesystem. No commit or push was possible.

# Latest work — Issue #352 trusted proxy client IP

- Updated: 2026-09-14; project: `AI_actuarial_inforsearch`.
- Branch: `fix/352-auth-client-ip`; clean starting baseline: `d1f885b` (`origin/main`).
- Scope: shared client-IP resolver, config/startup, anonymous rate-limit fallback,
  production environment guidance, focused resolver/auth/chat tests, and this status.
- Explicit `TRUSTED_PROXY_CIDRS` gates forwarded headers. Missing or invalid lists
  fail closed with an application-startup warning. TRUST_PROXY=false keeps the raw
  socket peer. Trusted chains peel right to left, normalize IPv4/IPv6/mapped IPv6,
  and reject malformed or oversized chains (32 hops; bounded header length).
- Uvicorn's built-in header rewriting is disabled in run_server so the resolver
  receives the real socket peer. Custom Uvicorn launches must use --no-proxy-headers.
- Production operators must supply their actual Caddy address or isolated proxy
  network CIDRs; no trust is enabled implicitly and no production data was read.
- Validation: `python -m pytest -q --no-cov tests/test_client_ip.py -k
  'not clients_behind_same_proxy'`: 36 passed, 3 deselected.
- Full focused command: `PYTHONPATH=. timeout 180 python /tmp/issue352_pytest.py
  -q --no-cov tests/test_client_ip.py tests/test_fastapi_auth_endpoints.py
  tests/test_fastapi_chat_endpoints.py tests/test_api_logging.py`: 110 passed.
  The temporary runner schedules a 10ms asyncio heartbeat because native TestClient
  hangs even for an empty FastAPI app in this sandbox; repository code is unmodified
  by the workaround. Native full pytest was interrupted at the reproduced hang.
- `python -m py_compile` on all seven changed Python files and `git diff --check`: passed.
- Deployment-source suite: 8 passed, 1 blocked/failing because docker run exits 126.
  Optional Black check unavailable: No module named black.
- Additional real registration-endpoint isolation assertions passed:
  `PYTHONPATH=. timeout 60 python /tmp/issue352_pytest.py -q --no-cov
  tests/test_fastapi_auth_endpoints.py::test_fastapi_auth_rate_limit_uses_trusted_forwarded_ip`
  (1 passed after the final test edit).
- Delivery blocked: `git add` failed creating the worktree index.lock under
  `/opt/ai_actuarial_inforsearch/.git/worktrees/fix-352-auth-client-ip` with
  "Read-only file system". No commit, push, PR, or remote-review wait was possible.
  GitHub read also failed: error connecting to api.github.com.
- All ten scoped files remain uncommitted; tests/test_client_ip.py is untracked.
- Resume with writable Git metadata and GitHub connectivity: stage the ten scoped
  files, commit `fix(auth): resolve client IP behind trusted proxies (#352)`, then
  `git push -u origin fix/352-auth-client-ip` and create a PR closing #352.
- No unrelated local changes or sibling repository access. No deployment performed.
- Next: commit/push/create PR, then inspect checks and remote comments after about
  15 minutes; rerun normal focused pytest in an environment with working TestClient.

---

# Latest work — PR #344 quality-gate repair
# Latest work — PR #344 quality-gate repair

- Updated: 2026-09-09 EDT.
- Repository: `AI_actuarial_inforsearch`; branch: `codex/fix-pr-344-checks`.
- Baseline: latest `origin/main@98af167`; PR #344 was already merged.
- Request: fix the failed checks associated with PR #344.
- CI run `34410277972` passed all 2,114 tests and four other jobs, but
  `quality-gate` failed on Pylint E1101 in `tests/test_api_logging.py`:
  full-repository inference attributed `baseFilename` to `_CapturingHandler`.
- Fix: use `getattr` without a default after the existing `FileHandler` guard.
  Missing attributes still raise; the existing path, duplicate-write, count,
  replacement-type, and unrelated-handler assertions remain unchanged.
- Changed files: `tests/test_api_logging.py` and this status entry only.
- Validation: 11 focused logging tests passed; focused Pylint, both dead-code
  gates, and `git diff --check` passed. Local full pytest: 2,103 passed, 10 skipped; one Docker test failed because
  the local Docker engine pipe is absent (also failed outside the sandbox).
  Full formatting/static scans are still running.
  The original full Pylint scan passed locally on Windows, so Linux CI on the
  repair PR is required to confirm the original CI failure is removed.
- Original PR's Copilot suggestion concerns a hypothetical future scheduler
  test ambiguity and does not explain this failure; left outside this scope.
- Preserved the pre-existing local status notes and untracked
  `.codex-tmp-agentic-rag/`, `diagrams/`, and `graphify-out/`; those are excluded
  from this commit. No sibling repository was accessed.
- Delivery: publish a follow-up PR; check exact-head CI and remote feedback
  after approximately 15 minutes. No merge was requested.
- Blockers: none. Next action: confirm all repair-PR checks pass and assess
  remote comments against this check-repair request.

---


# Project Status — Issue #338 schema v12 migration source validation

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Project\AI_actuarial_inforsearch-issue-338`
- Branch: `codex/issue-338-schema-v12-migration`
- Baseline: `origin/main@411b0d477e68b8dd1748f44139e0ad07e9cbc729`
- Issue: `#338 fix(schema): v12→v13 source validator rejects a legitimate v12 DB as invalid`
- Review state: `C:\Users\ferry\.codex\issue-to-merge\AI_actuarial_inforsearch\issue-338\review-state.json`
- Delivery stage: Draft PR #339 is Ready; the single remote-feedback window is assessed and one
  documentation-only AC-1 fix is locally validated; ready to push the final candidate
- Progress heartbeat: id `issue-338`, status `ACTIVE`, 15-minute cadence

## Issue #338 acceptance criteria

- AC-1: `_accept_version_12_source` accepts the exact genuine v12 source shape: no v13 stats
  covering indexes, no v14 `markdown_terminal_source_state` table, and the supported legacy
  `api_tokens` physical column order; it remains strict about unrelated future or malformed schema.
- AC-2: `schema_status` classifies that source as `needs_migration`, with `can_apply=true` and
  `blocked=false`, and `schema_plan` exposes the exact v12→v13→v14 migration chain.
- AC-3: `apply_schema` on an isolated genuine-v12 fixture reaches current schema v14, applies the
  v13 and v14 migrations exactly once, preserves seeded business rows and table counts, passes
  `PRAGMA foreign_key_check`, and is a no-op when repeated.
- AC-4: The same v14-signature regression is repaired for genuine v10 and v11 source shapes;
  v1–v9 and v13 remain unaffected, invalid/future-object shapes stay fail-closed, and the focused
  SQLite schema-runner suite plus repository-required checks remain green.

## Issue #338 scope, baseline evidence, and non-goals

- Worker-owned files are limited to `ai_actuarial/sqlite_schema.py`,
  `tests/test_sqlite_schema_runner.py`, the incorrect historical fixtures in
  `tests/test_issue_306_metadata_only_chunk_stats.py`,
  `tests/test_issue_266_weekly_snapshots.py`, and
  `tests/test_issue_267_weekly_explanations.py` that otherwise retain later v13/v14 objects. This
  manager owns this status record.
- Non-goals: production schema apply or deployment; server/database access; rebuilding
  `api_tokens`; per-version signature refactoring; schema registry redesign; dependency upgrades;
  sibling repositories; security frameworks; or speculative abstractions.
- The assigned worktree is clean. `HEAD`, `origin/main`, and merge-base all match the supplied
  baseline `411b0d477e68b8dd1748f44139e0ad07e9cbc729` on the assigned branch. The controller checkout
  with unrelated Issue #317 work and every sibling repository remain off-limits.
- Duplicate search found no equivalent active or closed-unmerged implementation. PR #330 is the
  v14 regression source and PR #323 is the v13 migration dependency; neither fixes #338. Remote
  heads are only `main` and unrelated `archive/flask-only-system`.
- An isolated current-schema database was converted to the genuine v12 shape, including legacy
  `api_tokens` order. Baseline `_accept_version_12_source` returned false and `schema_status`
  returned `invalid`, `blocked=true`, and `can_apply=false`, with one missing required table and
  two normalized future-index signature differences. `PRAGMA foreign_key_check` was clean.
- Blame and function history trace `_accept_version_12_source` to PR #323. PR #330 added the v14
  table and the correct v13 source validator but did not update the v12 validator to normalize that
  later table. The premise is current and delivery is classified `code-change`.
- The worker reproduced the identical PR #330 regression on genuine v10 and v11 sources: their
  validators normalize their own later weekly tables and the v13 indexes but not the v14 table.
  They are included as same-shaped AC-4 siblings; v1–v9 already tolerate the allowlisted backfill
  table and v13 already handles the v14 absence explicitly.
- Review-policy override: none; findings must be realistically reproducible and map directly to an
  acceptance criterion above. Required checks remain separate merge gates.

## Issue #338 required validation

- New regression test must show expected failure before the source fix and pass afterward.
- Focused: `python -m pytest -q tests/test_sqlite_schema_runner.py`.
- Final: `python scripts/quality_gate.py`, `npm run dead-code:files`,
  `npm run dead-code:symbols`, and `git diff --check`.
- Remote merge gates: `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke` on the exact PR head.

## Issue #338 implementation and local review

- The v12 validator now treats `markdown_terminal_source_state` as a later table, normalizes its
  legitimate absence together with the two v13 stats indexes, and rejects the table or indexes when
  they appear ahead of the recorded version. The valid-signature fast path now also checks v12.
- The same PR #330 regression was repaired explicitly for v10 and v11. No validator uses a broader
  `tolerate_backfill` path, and v1–v9/v13 behavior is unchanged.
- The regression fixture reproduces the supported legacy `api_tokens` physical order, seeds a file
  and API token, and removes exactly the v13/v14 objects from a fresh current schema. It verifies
  classification, exact plan/apply results, all pre-existing table counts, seeded rows, foreign
  keys, idempotency, and future/malformed fail-closed cases.
- TDD first failed because the genuine v12 status was `invalid` instead of `needs_migration`; the
  complete-future signature test also first failed because it bypassed source validation. Direct
  v10/v11 probes returned false before their sibling fix and true afterward.
- Fresh read-only review round 1 independently inspected the complete diff and history, ran the
  genuine v10–v13 status matrix and 78 related tests, and returned PASS with no valid finding.
- The first full quality gate exposed seven older v10/v11 migration tests whose setup still kept
  v13 indexes and the v14 table. The same worker changed only nine fixture-setup lines; no product
  assertion or explicit future-object invalid case changed. The two affected files then passed all
  59 tests, and the five-file schema combination passed all 137 tests. Because the state script had
  closed local review after PASS and the repair was setup-only, the decision log records why no new
  review round was opened.

## Issue #338 local validation so far

- Worker and manager independently ran the schema-runner, Issue #306, and Issue #322 combination:
  78 passed with only three existing SWIG deprecation warnings.
- Full `tests/test_sqlite_schema_runner.py`: 57 passed. Black/isort and `git diff --check` passed.
- The first complete quality-gate pytest run produced 2,074 passes, 10 skips, and 30 failures:
  23 frontend runtime tests lacked `node_modules` in the fresh worktree, and seven historical schema
  fixtures retained future objects. `npm ci` installed the lockfile dependencies without tracked
  changes, and the seven fixture failures were corrected as described above. A clean full rerun is
  the final evidence below; npm's existing audit notices are out of scope and caused no dependency
  change.
- The clean full `python scripts/quality_gate.py` rerun passed: 2,104 tests passed, 10 skipped, and
  Black, isort, and Pylint all passed. `npm run dead-code:files` and
  `npm run dead-code:symbols` each passed with zero baseline findings; final
  `git diff --check` passed. The five-file historical schema combination remained green at
  137 passed after the fixture correction.

## Issue #338 remote feedback and checks

- Draft PR `#339` was published from `e0a330009f9dbc4d8fecbca8edca9ef822551fc7` with exact
  `Closes #338`, then marked Ready. The single remote snapshot was fetched after 694 seconds.
- There were no human reviews, PR conversation comments, or Issue #338 comments. Copilot left two
  inline threads. The same persistent worker and manager rejected the machine-path suggestion as
  outside AC-1–AC-4: this project requires the status record and the same file already uses this
  path convention. No path content changed.
- The v12 validator docstring omitted its v14-table fail-closed contract. This maps directly to
  AC-1 and was handled with a one-line documentation-only correction; no behavior changed. The
  focused v12 selection passed 5 tests with 52 deselected, Black passed, and `git diff --check`
  passed.
- On the pre-feedback-fix head, all five remote merge gates completed successfully:
  `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and `python-smoke`.
  The same gates must complete successfully again on the final documentation-only head.

## Issue #338 blockers or decisions needed

- None.

## Issue #338 recommended next action

- Commit and push the one-line remote documentation fix plus this final status update, verify all
  five required checks on the exact final head, then merge PR #339 and verify Issue #338 closure.

# Project Status — Issue #333 content-first article lists

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\44b9\AI_actuarial_inforsearch`
- Branch: `codex/issue-333-content-first-lists`
- Baseline: `origin/main@e3f028d1f67910a98e38ae5dfb4045c8d75e6f30`
- Issue: `#333 feat(ui): make Home, Weekly, and Database article lists content-first`
- Review state: `C:\Project\AI_actuarial_inforsearch\.git\codex-issue-to-merge\issue-333.json`
- Delivery stage: local review and final validation complete; ready to create the Draft PR

## Issue #333 acceptance criteria

- AC-1: The full Home Materials, Categories, and Weekly Updates stat cards are links to
  `/database`, `/categories`, and `/weekly`, with visible hover and keyboard-focus states; Sources
  remains unchanged.
- AC-2: Home keeps the deterministic snapshot `file_count`, requests/renders at most the newest six
  preview files, and each file card shows its title, available full Category, Keywords, Summary,
  and a localized month/day date only. The original timestamp remains in semantic `time` metadata
  or a tooltip, file cards open File Detail, and missing metadata adds no empty label or placeholder.
- AC-3: The selected Weekly detail retains the existing historical master-detail flow, retrieves
  every snapshot member without a six/eight-item loss, and groups articles by the first trimmed
  non-empty semicolon-delimited Category. Unclassified items use localized Uncategorized, group
  counts are exact, and the complete original Category remains visible on each card.
- AC-4: Every Weekly category group has a keyboard-operable expand/collapse control with correct
  expanded/collapsed semantics, and every selected-week article remains reachable after grouping.
- AC-5: The Database desktop list uses a wide article-content area for title plus available
  Category, Keywords, and a bounded wrapping Summary. Outside that area it retains only Source,
  First seen, Actions, and the existing selection control; it removes the standalone Category,
  Markdown, Size, and Last seen/Date displays, and displayed dates always use `first_seen`.
- AC-6: Database filters, sorting, pagination, row navigation, preview, download, AI Explain,
  deletion/recovery paths, bulk selection, and permission behavior remain usable. Action and
  selection controls do not trigger row navigation; icon-only actions have localized accessible
  names and tooltips.
- AC-7: The Weekly files read response adds only public `category`, `keywords`, and `summary` via a
  lightweight Catalog join and does not read Markdown/body content or expose sensitive fields.
  Database declares and renders its existing public `keywords` field. Missing or malformed public
  metadata degrades without `null`, `undefined`, crashes, or visual noise.
- AC-8: Loading, empty, partial-data, and error states remain clear; added English/Chinese copy and
  short-date formats are correct; 320, 768, 1024, and 1440px layouts have no horizontal overflow,
  including long titles, keywords, summaries, and category names.
- AC-9: Focused Dashboard, Weekly, Database, Weekly API/service/storage, permissions/data-contract,
  and responsive accessibility tests pass, together with frontend lint/type-check/build, both
  dead-code gates, Python smoke, the unified quality gate, browser smoke, and desktop plus 320px
  before/after screenshots.

## Issue #333 scope, evidence, and non-goals

- Worker-owned components are the Home stat/Weekly surfaces, shared Weekly read/view helpers and
  card UI, Weekly selected-detail grouping/loading, Database article rows and `FileItem` metadata,
  the minimal Weekly public file response/service/storage projection, bilingual copy, and directly
  corresponding tests. This manager owns this status record and browser evidence.
- Non-goals: changing Category/Keywords/Summary generation or storage, database schema cleanup,
  File Detail redesign, Weekly snapshot/count/report generation, the historical-week selector,
  global layout/max-width or design-system changes, pagination/filter redesign, permission-policy
  changes, sibling repositories, dependency upgrades, security frameworks, or speculative
  abstractions.
- The worktree was clean and detached at the assigned baseline. After fetch, `HEAD`, `origin/main`,
  and merge-base all matched `e3f028d1f67910a98e38ae5dfb4045c8d75e6f30`; the pre-created
  assigned branch was then attached at that commit.
- No open/closed PR, remote branch, or matching commit references #333, its URL, or the distinctive
  content-first Home/Weekly/Database wording. The only other remote branch is the unrelated
  `archive/flask-only-system`, whose relevant diff removes the React Dashboard and Database pages.
- Baseline browser evidence with 15 disposable files and a 12-file latest snapshot showed inert
  stat cards, eight Home/Weekly rows with full year/time/time-zone dates, four selected-week files
  unreachable in Weekly, and Database desktop columns Title/Source/Category/MD/Size/Date/Actions.
  The Database date is selected from `first_seen` or `last_seen` according to the active sort.
- The Weekly service's field allowlist already names Category/Keywords/Summary, but its storage
  member query and public Pydantic model return only URL/title/original filename/first seen.
  `/api/files` already projects Category/Summary/Keywords publicly without sensitive fields.
- Review-policy override: none; only realistically reproducible findings mapped to an AC above are
  accepted.

## Issue #333 validation and artifacts

- The persistent worker implemented the content-first Home, Weekly, and Database views plus the
  narrow Weekly public metadata projection. No lifecycle actions have run yet.
- Local review round 1 accepted and fixed two AC-8 defects: a failed Weekly detail request and an
  uncached Database list failure were incorrectly rendered as empty states. Live browser failure
  injection now shows distinct localized error states while cached/partial behavior is preserved.
- Local review round 2 accepted and fixed three scoped defects: collapsed Weekly groups now retain
  their `aria-controls` target via `hidden`; the Database icon-only search-clear action has localized
  `aria-label` and `title`; and semicolon-only malformed categories no longer create visual noise.
- Local review round 3 accepted and fixed one AC-3/AC-8 copy defect: the English group count now
  uses plural-safe noun-first wording (`Articles: {count}`), with one-item and multi-item assertions.
- Manager-focused verification after round 2 passed: 57 Python tests, executable Issue #333 TSX
  assertions, TypeScript typecheck, and `git diff --check`. Browser verification at 1024px confirmed
  stable disclosure targets across collapse/reopen, the search-clear accessible name/tooltip, and
  no horizontal overflow.
- Fresh local review round 4 inspected the complete tracked/untracked candidate and passed with no
  findings. The local review cycle is closed after four rounds.
- Final candidate validation passed: unified quality gate (`2024 passed, 10 skipped`), frontend
  ESLint (0 errors; 5 existing warnings), TypeScript typecheck, production build, both dead-code
  gates (0 findings), FastAPI smoke (`13 passed`), Agentic RAG eval tests (`31 passed`), and the
  deterministic Agentic RAG smoke (`3/3 passed`). `git diff --check` also passed.
- Final live browser checks passed at 320, 768, 1024, and 1440px with exact viewport/scroll widths,
  disclosure collapse/reopen semantics, the localized search-clear accessible name/tooltip, and
  normal Home/Weekly/Database content. Final desktop and 320px screenshots were refreshed.
- Final gates are `git diff --check`, both dead-code commands, frontend ESLint/TypeScript/build,
  the three CI Python smoke commands, `python scripts/quality_gate.py`, and live browser checks at
  320, 768, 1024, and 1440px.
- Baseline screenshots are stored outside the checkout under
  `C:\Users\ferry\.codex\visualizations\2026\09\03\01a06897-4cf9-7ff2-90ed-a0b13f4104cc\issue-333-screenshots\before`.
- Current after screenshots are stored beside them under `issue-333-screenshots\after`; final
  captures will be refreshed after the candidate passes the last local review.

## Issue #333 blockers or decisions needed

- None.

## Issue #333 recommended next action

- Commit the reviewed candidate, push the task branch, and create the required Draft PR.

# Project Status — Issue #331 public HTTP redirect

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\a0f0\AI_actuarial_inforsearch`
- Branch: `codex/issue-331-http-https-redirect`
- Baseline: `origin/main@114108dd4426bdeb5b7bd93bda9b2498ebc06986`
- Issue: `#331 ops: restore public HTTP-to-HTTPS redirects for app hostnames`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/332`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-331.json`
- Delivery stage: Draft PR #332 created; preparing the reviewed head for Ready
- Progress heartbeat: id `issue-331-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #331 acceptance criteria

- AC-1: Public port 80 accepts only the two app hostnames `aiinforsearch.com` and
  `www.aiinforsearch.com` for redirect behavior and returns permanent 301/308 responses to the
  fixed canonical origin `https://www.aiinforsearch.com`.
- AC-2: The canonical redirect preserves the complete request path and query string, including
  `/database?category=AI`, and never builds `Location` from the request `Host` header.
- AC-3: Unrelated Host values on public HTTP receive a bounded non-success response and are not
  reflected into `Location`; `http://localhost:80/` continues to return 200 for the Caddy
  container health check.
- AC-4: The HTTPS application routes, application/baseline security headers, API/frontend private
  container-port posture, and non-exposed Caddy admin API remain unchanged. The
  `cross.aiactuary.cn` site block and upstream remain byte-for-byte unchanged.
- AC-5: Focused regression tests, production-shaped Caddy adaptation/validation, and
  `docker compose ... config -q` prove the listener, redirect, host-rejection, health, and
  unchanged-topology contracts before publication.
- AC-6: After review and squash merge, production is synced to the exact merge commit only after
  repository-external rollback artifacts capture the pre-change tracked Caddyfile and running
  Caddy configuration; the candidate validates before a scoped Caddy-only reload, without
  rebuilding or restarting API/frontend.
- AC-7: The running deployment passes HTTP redirects from China Telecom, China Unicom, and China
  Mobile; fixed canonical path/query and arbitrary-Host checks; HTTPS apex/www, API health,
  localhost health, all three container health states, `cross.aiactuary.cn`, and sustained Caddy
  error checks; and normal mobile plus WeChat in-app browser canaries without a redirect loop.

## Issue #331 scope, non-goals, and baseline evidence

- Worker-owned repository scope is limited to `Caddyfile`, the directly related deployment
  source tests, and documentation only where the changed tracked contract requires it. This
  manager owns `.hermes/project-status.md`.
- Sibling repositories, the primary checkout's #317 changes, issue-269, pr-324, #328,
  API/frontend business code, dependency upgrades, DNS/CDN/certificates, HTTPS apex
  canonicalization, and the `cross.aiactuary.cn` block/upstream are off-limits.
- Duplicate search across all PR titles/bodies/heads and local/remote branches found no #331 or
  equivalent public-port-80 redirect implementation. Merged PR #107 only added JSON logging and a
  loopback-only localhost health responder, so it is relevant history rather than a duplicate.
- The clean detached worktree, `HEAD`, `origin/main`, and merge-base all matched
  `114108dd4426bdeb5b7bd93bda9b2498ebc06986` before creating the assigned branch.
- Baseline public requests to both HTTP hostnames and the path/query probe failed with curl exit 7;
  HTTPS apex/www, API health, and `cross.aiactuary.cn` returned 200.
- Production-shaped `caddy adapt` showed the only port-80 listener as `127.0.0.1:80` and
  `[::1]:80`, while HTTPS listened on `:443`. Targeted blame/history traces that listener to
  merged PR #107 and finds no documented intent to reject public HTTP.
- Production-shaped `docker compose -f docker-compose.yml -f docker-compose.override.yml config
  -q` passed locally with non-secret placeholders; standalone Caddy is available through the
  pinned container image for adaptation and validation.
- Review-policy override: none. Only realistically reproducible findings mapped directly to an
  AC above are accepted.

## Issue #331 implementation and local review

- The tracked Caddy configuration disables Caddy's generated HTTP redirects and owns public port
  80 through one explicit server. `localhost` returns 200, the apex and `www` app Host values
  redirect permanently to fixed `https://www.aiinforsearch.com{uri}`, and every other Host returns
  an empty 421 without a `Location` header.
- The HTTPS application block, security-header snippets, API/frontend upstreams, and complete
  `cross.aiactuary.cn` block/upstream remain unchanged from `origin/main`. Compose continues to
  publish only Caddy 80/443; neither API/frontend nor the Caddy admin port is published.
- A production-shaped semantic test uses `caddy:2-alpine` to adapt and validate the tracked file,
  then runs only the adapted HTTP server on an isolated random loopback port. It verifies both app
  hosts, fixed canonical path/query, localhost health, arbitrary/cross Host rejection, unchanged
  HTTPS upstreams, and cleanup of the temporary container.
- TDD red evidence first found no public HTTP server on the baseline. Opening port 80 alone then
  reproduced Caddy's automatic apex redirect to `https://aiinforsearch.com/...`; the final explicit
  routing passes with fixed canonical output.
- The adapted configuration test directly asserts the HTTPS server's automatic redirect state so
  the guard against generated Host-derived redirects cannot disappear while the focused suite
  remains green.
- Local review round 1 found one valid AC-5 gap: the semantic runtime test did not directly prove
  that Caddy's automatic Host-derived redirect injection remained disabled. The persistent worker
  added the focused adapted-config assertion, reproduced the failing case by removing the guard,
  restored it, and returned the focused suite to green.
- Fresh read-only local review round 2 independently rechecked the full diff, production-shaped
  runtime, encoded path/query cases, Host values with case/ports, exact HTTPS/cross configuration,
  Compose topology, CI feasibility, and temporary-container cleanup. It passed with no valid
  #331 findings, so the local review cycle is closed after two rounds.

## Issue #331 local validation

- Focused deployment configuration suite: 9 passed, including real Caddy adapt, validate, and
  isolated runtime requests. Base and production Compose `config -q` both passed.
- Unified quality gate passed after the worktree's lockfile dependencies were installed: 2,012
  tests passed and 10 skipped; Black, isort, and Pylint passed. The earlier 20 failures were all
  missing React/tsx executables and passed before the clean full rerun.
- Both dead-code gates passed with zero findings. Frontend lint passed with zero errors and five
  existing warnings; type-check and production build passed. Python smoke passed 13 FastAPI tests,
  31 Agentic evaluation tests, and all 3 CLI evaluation cases.
- `git diff --check` passed. No temporary `issue-331-caddy-*` container remains. The npm audit's
  existing dependency findings are outside #331 and did not cause dependency changes.
- The complete current post-review diff then passed the full gate again: 2,012 tests passed and 10
  skipped; Black, isort, Pylint, both dead-code checks, frontend lint/type-check/build, all Python
  and Agentic smoke/evaluation suites, the 9 focused deployment tests, both Compose configurations,
  production-shaped Caddy validation, and `git diff --check` all passed.

## Issue #331 blockers or decisions needed

- No repository implementation blocker. Production SSH port 22 is reachable, but this host has no
  SSH config/private key and BatchMode authentication failed for the common server accounts. The
  existing in-app and Chrome browser sessions both reached the Tencent Cloud login page without an
  authenticated session. Public 17CE/443.cn probes can cover the three carrier checks after
  deployment; a real WeChat in-app canary capability has not been found. No unavailable production
  or browser result will be inferred.

## Issue #331 recommended next action

- Push this Draft PR status update, verify the PR head and exact `Closes #331` reference, then move
  PR #332 to Ready and start the single full feedback window.

# Project Status — Issue #322 Markdown terminal preflight

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\8480\AI_actuarial_inforsearch`
- Branch: `codex/issue-322-markdown-terminal-preflight`
- Baseline: `origin/main@e0645f92b867a7209af91f2ddd28027cede28778`
- Issue: `#322 fix(markdown): preflight terminal source failures before conversion`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-322.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/330`
- Delivery stage: PR #330 is Ready. Its single feedback window completed after 720.2 seconds;
  the sole valid Copilot wording fix is pending commit/push and current-head CI.
- Progress heartbeat: id `issue-322-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #322 acceptance criteria

- AC-1: A legacy binary `.ppt` is classified as `unsupported_legacy_ppt` before converter
  execution and is excluded from later automatic Markdown backlogs while its source/state is
  unchanged, unless an operator explicitly retries it.
- AC-2: A missing local source is durably classified as `repair_required` before converter
  execution and does not repeat the same scheduled conversion error.
- AC-3: A `.pdf` whose declared MIME/content kind or magic identifies HTML is durably classified
  as `invalid_source` and is not accepted solely from its extension or URL.
- AC-4: Terminal preflight outcomes remain distinct from retryable converter failures. An unchanged
  terminal source stays out of ordinary incremental selection; a verified source/state change or
  explicit operator selection makes it eligible again under one narrow rule.
- AC-5: Terminal skips have their own task counter and per-item result visibility, separate from
  successful conversions, ordinary skips, and retryable errors; they cannot falsely make a run
  successful.
- AC-6: Auto exhaustion preserves every attempted converter and its concrete failure reason in
  task details instead of only `Auto conversion failed`.
- AC-7: Valid supported sources preserve the existing incremental selection, conversion,
  persistence, and retry behavior; downstream Chunk and Embedding contracts do not change.
- AC-8: Regression tests cover legacy PPT, missing source, HTML-disguised PDF, a valid supported
  control, durable exclusion/re-entry, separate terminal statistics, and Auto failure details.

## Issue #322 baseline and duplicate evidence

- After fetch, `HEAD`, `origin/main`, and their merge-base all matched the supplied baseline
  `e0645f92b867a7209af91f2ddd28027cede28778`; the worktree was clean and detached before the
  isolated task branch was created.
- No open, closed, or merged PR matched Issue #322, its URL/number, or the distinctive terminal
  Markdown-preflight title. The remote exposes only `main`, and targeted commit history found no
  equivalent terminal source state. Closed Issue #319 changes loose-coupled stage continuation and
  does not implement Markdown source preflight or terminal eligibility.
- A temporary-database reproduction made a real OLE-header `.ppt`, a missing `.pdf`, an HTML-body
  `.pdf` with `content_type=text/html` and `content_kind=web_page`, and a valid `%PDF` control.
  The first run called a converter for the PPT, HTML PDF, and valid PDF; the HTML PDF was accepted.
  The second ordinary run selected the unchanged PPT and missing PDF again and repeated both
  failures.
- A separate runtime reproduction forced `markitdown` and `local` to fail concretely. The exposed
  Auto error was only `Auto conversion failed for control.pdf`; only the final `local` failure
  survived as the exception cause.
- `git blame` and targeted `git log -S` trace broad candidate selection and missing-file retries to
  the original May task runtime, and generic Auto exhaustion to the February/June converter work.
  No later history establishes terminal preflight as intentionally excluded, so the bug premise is
  current.

## Issue #322 scope and validation

- Worker-owned scope is limited to Markdown candidate selection/preflight, the smallest durable
  state needed for unchanged-terminal exclusion and source-change/explicit-selection re-entry,
  task result/stat visibility, Auto failure details, and directly corresponding migrations/tests.
- Likely touched surfaces are `ai_actuarial/task_runtime.py`, storage/schema code only if durable
  state requires it, the two task display-summary services, the shared frontend task metrics/types
  and bilingual label, plus focused Python/React/schema tests. Exact edits must be justified by an
  acceptance criterion; `doc_to_md/registry.py` is an inspected sibling and is edited only if the
  task contract actually routes through it.
- Required final checks: Issue-focused red/green tests, relevant Markdown/task/API/schema/frontend
  regression, `git diff --check`, both dead-code gates, frontend lint/type-check/build, the unified
  quality gate, and all three Python smoke commands from CI. Browser smoke is required if visible
  Task metrics change.
- Non-goals: LibreOffice or new converter installation, automatic source repair/redownload,
  Issue #319 pipeline redesign, downstream Chunk/Embedding changes, sibling-repository work,
  security frameworks, schema registries, or speculative abstractions.
- No unrelated uncommitted or untracked files were present at startup. Generated ignored
  `graphify-out/` data is manager-created analysis output and will not be committed.

## Issue #322 implementation and local review

- A schema-v14 `markdown_terminal_source_state` record persists `unsupported_legacy_ppt`,
  `repair_required`, or `invalid_source` together with a bounded source fingerprint. Ordinary
  selection excludes an unchanged terminal source before logical offset/limit, while explicit
  selection and verified source changes re-enter preflight.
- Task results keep downstream-ready files separate from per-item outcomes, expose an independent
  `items_terminal_skipped` metric through both API summaries and the shared Task UI, and do not
  report a terminal-only run as successful. Retryable converter failures remain eligible.
- Runtime Auto and the same-shaped converter registry now retain every attempted converter and a
  bounded concrete reason. Candidate reasons share the 800-character public budget, so later
  candidates cannot disappear from the final task detail.
- TDD first reproduced 12 failures for the original implementation gap. Local review round 1 found
  two valid defects: generic-MIME OLE `.ppt` records were omitted from the automatic candidate
  predicate, and a long Auto aggregate was truncated before all converter reasons reached the
  public task result. The same persistent worker fixed both with red/green tests.
- Fresh read-only review round 2 independently checked the full diff and returned PASS. Current
  evidence includes 11 Issue-focused tests, 324 related regression tests, schema and Pipeline Baton
  coverage, frontend TaskMetrics runtime/type checks, and `git diff --check` passing.
- The first final dead-symbol gate found one Issue-added exported-but-module-private
  `TaskFileOutcome`. The same persistent worker removed only the unnecessary `export`; the gate
  then passed with zero findings. Because this happened after round 2 PASS, a third fresh read-only
  reviewer checked the full current diff and returned supplemental PASS with no findings.

## Issue #322 final local validation

- Unified quality gate passed: 2,011 tests passed and 10 skipped, then Black, isort, and Pylint all
  passed.
- Dead-code files and symbols both passed with zero baseline findings. Frontend lint passed with
  zero errors and five existing Hook warnings; TypeScript type-check and production build passed,
  with only the existing large-chunk advisory.
- Python CI smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI
  evaluation cases. Evidence/citation/refusal rates were 1.0 and unsupported-answer rate was 0.0.
- In-app-browser smoke used an isolated temporary database and one local test token. The real Task
  History page rendered `Terminal skips: 1` for a Markdown terminal-source result, and browser
  console errors were empty. Both local services were stopped after the check; no real account or
  production data was used.
- `git diff --check` passed. CRLF notices are informational workspace conversion warnings.
- Files in scope: Markdown runtime, storage/schema, both task summary services, shared Task metric
  UI/types/i18n, same-shaped converter registry, focused Issue test, related schema/task/frontend
  regression fixtures, and this manager-owned status file. No downstream Chunk/Embedding production
  code changed.

## Issue #322 remote feedback

- PR #330 was marked Ready at head `a0474909ee11b1c5fca8cc046753b737c80161ab`.
  One complete snapshot was fetched 720.2 seconds later; there will be no second feedback fetch.
- All five required checks on that head passed. No PR conversation comment or Issue comment was
  present. Copilot left one inline comment about a failed item still reporting `Converted` progress.
- The persistent worker and manager confirmed the comment under AC-5: a canonical
  `retryable_error` must not have success-shaped visible progress. The minimal fix changes only
  `Converted markdown` to neutral `Processed markdown` and adds a public-result progress assertion.
- The new assertion failed before the fix and passed afterward. The worker also passed 131 related
  tests plus Black, isort, Python compilation, and diff checks; the manager independently reran the
  focused public-result test successfully.

## Issue #322 blockers or decisions needed

- None. Commit and push the confirmed wording fix, wait for all five required checks on the new
  exact head, then squash merge, verify Issue closure, and clean the remote branch, worktree, and
  local branch.

# Project Status — Issue #320 strict manifest validation

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\7a36\AI_actuarial_inforsearch`
- Branch: `codex/issue-320-strict-manifest-validation`
- Baseline: `origin/main@29b73be7ecf65d236570b5f9d698783a8966cb46`
- Issue: `#320 fix(manifest): reject incompatible producer payloads instead of silent zero import`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-320.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/329`
- Delivery stage: Draft PR #329 created with `Closes #320`; final status commit pending before the
  Ready transition and single 600-second feedback/CI window

## Issue #320 scope and acceptance criteria

- Accept only the exact supported legacy `web-listening-manifest.v1` object contract, with
  non-empty manifest/run/source identities and a `downloaded_assets` list. Full producer Result
  envelopes, nested manifests, unsupported schemas, missing identities, and wrong container types
  fail with stable machine-readable errors instead of succeeding with zero imported assets.
- Parse raw JSON fail-closed, including duplicate keys at any depth and non-standard numeric
  constants. Preflight every asset before any transaction: object and asset identity; absolute
  HTTP(S) URL; SHA-256 checksum; media type; non-boolean, non-negative integer byte count;
  filename; and at least one valid path field with documented precedence.
- Keep valid legacy behavior: archive the original manifest bytes exactly, retain content kind,
  preserve URL/SHA upsert behavior and path precedence, and make repeated ingestion idempotent.
- Direct ingestion, task execution, task history, and API-visible errors expose only stable codes
  and safe field metadata; malformed inputs cannot leak payload values, credentials, signed query
  strings, cookies, or local secret paths through error chains or logs.
- Non-goals: external consumer/adapter changes, producer API calls, artifact downloads, Baton or
  new lineage work, a schema registry, storage redesign, migration, or backfill. Sibling
  repositories remain off-limits.

## Issue #320 baseline and duplicate evidence

- Startup confirmed the assigned worktree on the exact supplied baseline. Final pre-publication
  fetch again confirmed `HEAD`, `origin/main`, and their merge-base at `29b73be7`.
- Baseline reproduction showed that both a full `web-listening-result.v1` envelope and a nested
  incompatible manifest returned empty IDs with `imported=0`; an unsupported schema carrying a
  manifest ID also reported `imported=0` while writing one raw-manifest row.
- Focused baseline tests passed 44 tests, confirming the defect was an untested contract gap rather
  than an already-failing implementation.
- No equivalent open/merged PR, branch, or commit was found. Merged PR #205 introduced the
  permissive legacy importer and PR #136 covers an unrelated Agentic ready-manifest registry.

## Issue #320 implementation and review

- `manifest_ingest.py` now performs strict raw parsing and complete contract validation before
  opening the write transaction, then preserves the existing valid archive/upsert/idempotency
  path. `ManifestIngestError` carries safe machine code and field details.
- `task_runtime.py` validates and decodes the manifest before constructing storage, persists the
  safe error code/details in task history, and logs contract failures without unsafe exception
  chains. The public collection-run API remains unchanged and continues to reject manifest mode.
- Focused regression coverage now exercises incompatible envelopes, unsupported schemas, duplicate
  keys, every field/type rule, late-asset atomicity, backslash and invalid-port URLs, exact raw-byte
  archival, path priority, idempotency, task/history/API propagation, and secret-safe logs.
- TDD red evidence reproduced six core failures before implementation. Local review round 1 found
  two valid acceptance-criteria defects: backslash URLs were accepted, and chained URL/file errors
  could leak sensitive values. The same persistent worker fixed both with targeted red/green tests.
  Fresh read-only review round 2 returned PASS with no findings. Focused validation passed 102
  tests; the wider related regression selection passed 201 tests.

## Issue #320 final local validation

- Unified quality gate passed: 2,000 tests passed and 10 skipped, then Black, isort, and Pylint all
  passed.
- Both dead-code gates passed with zero baseline findings. Frontend lint passed with zero errors
  and five existing Hook warnings; type-check and production build passed, with only the existing
  large-chunk advisory.
- Python smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI
  evaluation cases with evidence/citation/refusal rates at 1.0 and unsupported-answer rate at 0.0.
- `git diff --check` passed. No browser smoke is required because this change has no UI behavior.
- Files in scope: `ai_actuarial/manifest_ingest.py`, `ai_actuarial/task_runtime.py`,
  `tests/test_manifest_ingest.py`, `tests/test_issue_320_manifest_contract.py`,
  `tests/test_issue_220_immutable_guards.py`, `tests/test_fastapi_ops_read_endpoints.py`,
  `tests/test_fastapi_ops_write_endpoints.py`, and this manager-owned status file.
- No unrelated uncommitted or untracked files are present. There are no local blockers; the next
  action is to push this final status commit, mark PR #329 Ready, then perform the single required
  feedback/CI/merge/cleanup lifecycle.

# Project Status — Issue #308 inapplicable retrieval metrics

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\2378\AI_actuarial_inforsearch`
- Branch: `codex/issue-308-inapplicable-retrieval-metrics`
- Baseline: `origin/main@0cdc25fce76d9eaf21d484020ccaa223fef0f3b6`
- Issue: `#308 fix(chat): distinguish inapplicable retrieval metrics from missing score data`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-308.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/326`
- Delivery stage: Draft PR #326 created with `Closes #308`; final status commit pending before
  Ready for review

## Issue #308 scope and acceptance criteria

- AC-1: Keyword-only methods (`summaries`, `titles`, `sections`, `relations`, `formulas`,
  `tables`, and `calculation_terms`) show Keyword relevance plus Retrieval method and omit
  Semantic relevance when its canonical value is absent.
- AC-2: `vector` evidence shows Semantic relevance plus Retrieval method and omits Keyword
  relevance when its canonical value is absent.
- AC-3: A metric applicable to the method remains visible as `—` when its canonical value is
  missing, invalid, non-integer, or outside `0..100`.
- AC-4: Any present valid canonical semantic or keyword value is shown regardless of method, so
  hybrid evidence can show both.
- AC-5: Unknown methods infer no applicability and show only valid scores actually present, plus
  the safely normalized Other method badge.
- AC-6: Citation Cards and Retrieved Blocks use the same shared component and therefore the same
  rendering rules.
- AC-7: Every rendered badge remains screen-reader labeled, `whitespace-nowrap`, flex-wrapping,
  and free of horizontal overflow at 320, 768, 1024, and 1440 px.
- AC-8: Backend response fields, persistence/history, ranking, result order, thresholds, planner,
  tool selection, and retrieval APIs remain unchanged.

## Issue #308 ownership, non-goals, and validation

- Implementation ownership is limited to
  `client/src/pages/chat/RetrievalIndicators.tsx` and its focused component test. The manager owns
  this status file. `Chat.tsx` is inspected as the two-call-site contract and is edited only if the
  shared-component contract cannot satisfy AC-6.
- Sibling repositories are off-limits.
- Non-goals: adding vector scoring to Ready Data, relabeling scores, creating a combined score,
  changing any backend contract or retrieval behavior, backfilling history, adding a security
  framework, or introducing a speculative abstraction.
- Component matrix: vector-only; every keyword-only method; valid hybrid scores; applicable
  missing/invalid/out-of-range scores; all missing; and unknown method with absent, one, or both
  valid scores. Assertions cover exact visible and absent accessible labels.
- Regression matrix: the existing backend Issue #265 suite preserves Agentic raw-score and
  Standard vector-mapping contracts; frontend lint, type-check, build, real browser smoke, both
  dead-code gates, the unified quality gate, and all three Python smoke commands are required.

## Issue #308 baseline evidence

- The assigned worktree arrived clean but detached. After fetching, `HEAD`, `origin/main`, and
  their merge-base all matched the supplied baseline exactly; the manager created the isolated
  branch named above without changing files.
- Runtime server rendering reproduced both defects: `titles` with keyword score `31` rendered an
  extra `Semantic relevance: —` badge, and `vector` with semantic score `83` rendered an extra
  `Keyword relevance: —` badge.
- `git blame` and the complete path history show that PR #286 introduced the component with a
  fixed three-badge array and no later change. Issue #308 explicitly supersedes that earlier layout
  rule as a focused UX follow-up, so the report is current rather than stale or duplicate work.
- Duplicate search found no equivalent PR or branch. Merged PR #286 is the linked #265 origin and
  does not implement the new applicability distinction.

## Issue #308 implementation and validation

- The shared component now treats `vector` as semantic-applicable, the seven Ready Data methods as
  keyword-applicable, and unknown methods as having no inferred applicability. Any valid canonical
  score is still rendered regardless of method, while an applicable invalid/missing score remains
  visible as `—`.
- TDD red evidence showed the original vector-only and keyword-only cases each rendered the extra
  inapplicable `—` badge. The expanded component matrix then passed after the minimal component
  change.
- Local review completed after one fresh read-only reviewer round with no valid findings. Citation
  Cards and Retrieved Blocks were independently confirmed to pass identical fields to the same
  shared component.
- The Issue-focused component test passed. The retrieval/backend regression selection passed 143
  tests, preserving Agentic raw-score and Standard vector-mapping contracts.
- Frontend lint passed with zero errors and five existing Hook warnings; type-check and production
  build passed, with only the existing large-chunk advisory. Both dead-code gates passed with zero
  findings.
- Python smoke passed: 13 FastAPI authority tests, 31 Agentic evaluation tests, and all 3 CLI smoke
  cases with quality rates at 1.0.
- The unified quality gate passed: 1,882 tests passed and 10 skipped; Black, isort, and Pylint all
  passed.
- Real browser smoke used controlled local API responses in the actual Chat page. Citation Cards
  and expanded Retrieved Blocks rendered keyword-only, vector-only, applicable-missing, unknown,
  and hybrid cases identically. At 320, 768, 1024, and 1440 px, all 22 expected badges stayed
  within their containers, retained `nowrap`, wrapped as whole badges, and produced no page
  overflow or console errors. The existing narrow-screen sidebar was closed before inspecting the
  conversation content.
- Final fetch confirmed `origin/main`, branch merge-base, and the original baseline remain
  `0cdc25fce76d9eaf21d484020ccaa223fef0f3b6`.

# Project Status — Issue #307 scheduler reconciliation

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\be1a\AI_actuarial_inforsearch`
- Branch: `codex/issue-307-scheduler-reconciliation`
- Original baseline: `origin/main@0fe3101df6f3834e33b609aff3d119b70df9a274`
- Integrated main: `origin/main@25d0e0ae96a938d97636041e77a175203184237f`
- Issue: `#307 fix(tasks): reconcile configured recurring tasks with effective scheduler jobs`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-307.json`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/325`
- Delivery stage: PR #325 is Ready; the full 10-minute feedback window completed, all five CI
  checks passed, and two confirmed Copilot findings are fixed and locally revalidated for push
- Progress heartbeat: id `bug-issue`, status `ACTIVE`, 15-minute cadence

## Issue #307 pause checkpoint (historical)

- Pause requested after local review round 1 returned PASS with no findings. The persistent state
  file remains at `local_review_complete` with `review_count: 1` and no PR recorded.
- Completed validation: Issue-focused tests (36 passed), worker extended backend regression
  (293 passed), reviewer regression (113 passed), rendered component assertions, real browser
  smoke for registered-reader/admin controls and English/Chinese copy, dead-code file/symbol gates,
  frontend lint/type-check/build, and `python scripts/quality_gate.py`.
- Unified quality result: PASS; full pytest was 1876 passed and 10 skipped, followed by passing
  Black, isort, and Pylint baseline checks. Frontend lint retained 5 existing warnings and build
  retained the existing large-chunk advisory.
- At this historical pause point, the separate CI-equivalent `python-smoke` commands had not run
  and no Git or remote lifecycle action had occurred. Both the smoke commands and all other
  post-integration local checks have now completed below; the Git/remote lifecycle still has not
  started.
- Resume entry: from this exact worktree and branch, verify `git status`, run the three
  `python-smoke` commands from `.github/workflows/ci.yml`, review the final diff/status, then commit,
  push, open the Draft PR with `Closes #307`, mark Ready, and continue the recorded remote-feedback
  workflow.
- Preserve all current tracked implementation/test changes, the two new test files, the three
  manager-generated `graphify-out/` directories, and the Issue state file. Sibling repositories
  remain off-limits.

## Issue #307 latest-main integration

- The controller reported and the manager verified that `origin/main` advanced five commits from
  `0fe3101` to `25d0e0a` through PR #324.
- A three-way preflight found no business-code or test conflict and no untracked-path collision.
  The only conflict was this manager-owned status file.
- The branch fast-forwarded to `25d0e0a`; all #307 tracked changes and both new tests were restored
  from the recoverable stash. The three `graphify-out/` directories remained untouched.
- The status-file conflict was resolved by preserving the complete #307 record and its prior
  #306/#317 history while adding the current main record for PR #324 below.
- PR #324 changed guest-only task-option caching and unrelated pages/tests. It did not change any
  #307 production or test file, nor a hook consumed by the #307 scheduling surfaces, so local
  review round 1 remains applicable and `review_count` stays at 1.

## Issue #307 post-integration validation

- Extended scheduler/API/frontend regression: 293 passed.
- FastAPI entrypoint/native-authority smoke: 13 passed. Agentic evaluation tests: 31 passed.
  Agentic command smoke: 3/3 cases passed with all reported quality rates at 1.0.
- Frontend lint passed with 0 errors and 5 existing hook warnings; type-check and production build
  passed, with only the existing large-chunk advisory.
- Dead-code file and symbol gates passed with zero findings.
- Unified quality gate passed: 1,880 tests passed and 10 skipped; Black, isort, and Pylint passed.
- Real browser smoke passed against the integrated branch. A registered reader saw both Effective
  Scheduler Jobs and Configured Recurring Tasks, including all five expected job kinds, while add,
  reinitialize, edit, and delete controls were absent. An admin saw add, reinitialize, edit, and
  configured-task delete controls, with no direct effective/system-job delete action. English and
  Chinese desired/effective, diagnostic/recovery, read-only, and deletion-consequence copy all
  rendered correctly. The confirmation was inspected without deleting the recurrence.
- `git diff --check` passed apart from informational CRLF conversion notices. No second local review
  was needed because the integrated upstream changes did not touch or feed the reviewed #307
  surfaces.

## Issue #307 remote feedback and follow-up

- PR #325 was created as Draft, verified to contain `Closes #307`, then marked Ready. The required
  observation window ran for 635 seconds before the one permitted feedback snapshot was fetched.
- Remote CI passed `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke`; the reviewed head was `e3109b4bcab6414c5d18f1de19657f5753c21334` and GitHub
  reported the PR mergeable and clean.
- Copilot raised four inline comments. Two were confirmed and fixed: unmanaged scheduler jobs now
  retain their generated sanitized metadata so identity survives in-process list reordering; and
  `daily at H:MM` is normalized to `HH:MM` both for runtime registration and desired/effective
  reconciliation.
- The two comments about absolute paths in this internal workflow record were rejected under the
  repository review policy because they do not map to any Issue #307 acceptance criterion.
- Red evidence reproduced both accepted findings, including a 503 reconciliation failure and the
  real scheduler rejecting the API-accepted single-digit hour. Green evidence: 2/2 focused tests,
  46/46 Issue/API tests, and the manager's 295/295 extended regression passed. Black, isort, and
  `git diff --check` passed for the follow-up patch.

## Issue #307 acceptance criteria and boundaries

- AC-1: Effective scheduler status exposes a deterministic within-process `job_key` plus only
  sanitized kind, source, display name, interval, last/next run, managed, and deletable metadata.
- AC-2: Configured recurring tasks, site jobs, the global job, Pipeline Baton, and Ready Data are
  distinguishable; configured effective jobs map back to their configured task.
- AC-3: Configured-task add, update, and delete return success only after desired YAML and live
  scheduler state match; recurrence removal needs no manual Reinitialize.
- AC-4: A forced registration or reconciliation failure returns failure and restores both the
  previous YAML and the previous scheduler state.
- AC-5: Reconciliation does not stop active tasks or alter history, logs, stop behavior, or
  unrelated system jobs; system jobs have no direct delete action.
- AC-6: `tasks.view` readers can see Configured Recurring Tasks and Effective Scheduler Jobs but
  no mutation controls; direct writes remain 403 and operator/admin write flows remain valid.
- AC-7: Reinitialize remains a diagnostic/recovery action, and English/Chinese copy plus deletion
  confirmation clearly explain desired versus effective state.
- Implementation ownership is limited to `ai_actuarial/task_runtime.py`, the directly related
  FastAPI ops read/write services and routers, `client/src/pages/Tasks.tsx`,
  `client/src/pages/tasks/ScheduledTasksSection.tsx`, `client/src/hooks/use-i18n.ts`, the three
  same-shaped mutation callers `ScheduleFromTaskButton.tsx`, `WebListeningForm.tsx`, and
  `PipelineBaton.tsx`, and focused tests for those contracts. `.hermes/project-status.md` remains
  manager-owned.
- Sibling repositories are off-limits. Non-goals are schedule/timezone UX from #312, a database
  job table, a generic scheduler platform, direct system-job deletion, stopping current tasks,
  history/log/artifact deletion, APScheduler/Celery migration, and pipeline-order changes.

## Issue #307 baseline evidence

- The assigned worktree was clean; branch, `HEAD`, and supplied baseline matched exactly.
- A real `NativeTaskRuntime` reproduction showed add left only the existing 30-minute Pipeline
  Baton job, update left the old daily timer effective, and delete left the two-hour timer live
  after YAML became empty. Manual `init_scheduler()` was required after each mutation.
- `git blame` and targeted history trace the split to the original April FastAPI work: CRUD writes
  YAML and calls only `set_site_config`, while the separately exposed Reinitialize path alone calls
  `init_scheduler`. The status endpoint independently enumerates live jobs. Later changes added
  system jobs and stricter RBAC without creating an automatic reconcile contract, so the Issue is
  current and not a stale request.
- The linked #312 explicitly depends on #307 and owns only future schedule expression/timezone UX.
- Baseline CI run 33582893736 passed all five jobs at the assigned merge baseline.

## Issue #307 required validation

- Scheduler/runtime tests cover every job kind/source, stable keys, configured mapping,
  add/update/delete reconciliation, forced failure rollback, and unchanged system jobs.
- API tests cover the reader/operator/admin RBAC matrix and active/history/log/stop regressions.
- Frontend source and rendered-component tests cover read-only visibility, hidden mutations,
  bilingual copy, and deletion confirmation.
- Final validation includes focused scheduler/API/frontend tests, frontend lint/type-check/build,
  browser smoke, dead-code file/symbol checks, the unified quality gate, and Python smoke tests.

# Project Status — PR #324 guest UI permission gating

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\pr-324`
- Branch: `fix/guest-ui-permission-noise`
- Baseline merged: `origin/main@0fe3101`
- PR: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/324`
- Task: review PR #324, fix its failing test gate, and evaluate Copilot feedback

## Scope and boundaries

- This repository is the only writable project workspace; sibling repositories are off-limits.
- Scope is limited to the guest UI permission behavior, the failed formatting gate, and the
  Copilot review comment on `useTaskOptions`.
- The primary checkout has unrelated user-owned changes and remains untouched. Work is isolated
  in this task worktree.

## Findings and implementation

- The original remote run passed all 1,880 pytest tests but failed the quality gate because
  `tests/test_knowledge_react_source.py` was not Black-formatted.
- Copilot's comment was confirmed: a disabled `useTaskOptions` consumer could expose module-level
  cached operator data and could retain a stale loading state.
- Disabled consumers now receive stable fallback/empty values, `loading=false`, `error=null`, and
  a request-free `refresh` function.
- A runtime TypeScript/React hook regression warms the authorized cache, expires it, mounts a
  disabled guest consumer, and verifies that no operator data or new requests escape.
- Black reformatted the original failing test file.
- The Copilot thread was answered with the fix and regression evidence.
- Latest `origin/main` was merged after it advanced through PR #323; its sole textual conflict in
  this status file was resolved in favor of the current PR #324 record.

## Local verification before latest-main merge

- New runtime regression: demonstrated the stale-data/loading failure before the hook fix and
  passed after the fix.
- Focused React source suite: 78 passed.
- Black check for the four relevant React source test files: passed.
- Frontend lint: passed with 0 errors.
- Frontend type-check: passed.
- Frontend production build: passed; only the existing Vite large-chunk advisory remained.
- Four-layer dead-code gate: passed with zero baseline findings.
- Unified quality gate: passed with 1,861 tests passed and 10 skipped; Black, isort, and Pylint
  passed.
- `git diff --check`: passed apart from informational CRLF conversion notices.
- Browser shell smoke as a signed-out user showed no operator diagnostics or console errors. The
  backend was not running, so proxied API requests returned connection-refused/500 responses;
  the runtime regression is the authoritative guest-cache check.

## Post-merge verification

- Focused React source suite: 78 passed.
- Frontend lint, type-check, production build, and four-layer dead-code gate: passed.
- Unified quality gate: 1,871 passed and 10 skipped; Black, isort, and Pylint passed.
- `git diff --check`: passed.

## Delivery state

- Fix commit `1d61054` is pushed to the PR branch.
- The Copilot reply is published at discussion comment `3910583670`.
- Post-merge local validation is complete; the new remote CI run is the remaining check at this
  snapshot.

## Preserved merged Issue #306 evidence

- PR #323 merged at `0fe3101df6f3834e33b609aff3d119b70df9a274` on 2026-09-02T02:21:06Z.
- Issue #306 closed automatically one second later.
- PR #323 passed `dead-code-files`, `dead-code-symbols`, `quality-gate`, `frontend-check`, and
  `python-smoke`; the post-merge main CI run 33582893736 also passed all five jobs.
- The detailed #306 implementation and validation record remains preserved below.

# Project Status — Issue #306 metadata-only Chunk & Embedding stats

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\692c\AI_actuarial_inforsearch`
- Branch: `codex/issue-306-metadata-only-stats`
- Baseline: `origin/main@1e7f5f6b1cf29e7e9c0a413e221e774d77bdeee2`
- Issue: `#306 perf(tasks): make Chunk & Embedding stats metadata-only`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-306.json`
- Delivery stage: merged through PR #323 at
  `0fe3101df6f3834e33b609aff3d119b70df9a274`; Issue #306 is closed and post-merge CI passed
- Progress heartbeat: id `bug-issue`, status `ACTIVE`, 15-minute cadence

## Issue #306 scope and boundaries

- This repository is the only writable project workspace; sibling repositories are off-limits.
- Ordinary `GET /api/chunk_generation/stats` must use aggregate metadata only and must not read
  `global_chunks.content` or `chunk_embeddings.vector_json`.
- Preserve the response shape, category filtering, embedding identity fields, and
  `first_without_chunks_index` semantics.
- Preserve deep vector-body validation for build, audit, repair, and explicit coverage paths.
- Add measured covering-index/query-plan evidence, regression guards, dimension/byte-size
  performance evidence, focused API/storage/schema checks, frontend build, and browser smoke.
- Non-goals remain caching the deep scan, changing embedding generation or serialization,
  weakening fail-closed build/audit behavior, replacing SQLite, or redesigning Tasks UI.

## Issue #306 baseline evidence

- Worktree was clean; assigned branch and `HEAD` exactly matched the supplied baseline.
- A baseline endpoint run with 3,072-dimension stored vectors called
  `Storage.embedding_coverage`, `Storage.list_chunks_for_embedding`, and
  `Storage.read_valid_chunk_embeddings` once each.
- Targeted blame/log evidence traces the deep statistics path to the persisted-embedding
  implementation; current intent already keeps metadata-only and deep validation paths separate
  for Knowledge Base detail, so Issue #306 is reproducible and not stale.

## Issue #306 current validation

- Issue-focused tests: 10 passed. The added v0 regression proves a real pre-v13 database
  without the new indexes is recognized, migrated with data preserved, and idempotent.
- Schema/API combinations: 153 schema migration checks and 42 related API/lightweight-path
  checks passed.
- Production-scale benchmark: 21,314 rows at 3,072 dimensions with about 262 MB of stored
  vector bodies; first new connection 0.02653s and 20-run warm p95 0.02172s.
- Frontend lint, type-check, production build, dead-code file/symbol gates, and the unified
  quality gate passed. Final full pytest result: 1,867 passed, 10 skipped, 0 failed;
  Black, isort, and Pylint also passed. Agentic eval smoke passed 3/3.
- Browser smoke passed on Tasks → Chunk & Embedding: stats and selected embedding identity
  rendered without a persistent loading state, the stats API returned 200, and the browser
  console had no errors.
- Local review closed after two rounds. One real v0 migration gap was fixed and independently
  revalidated. A proposed manual wrong-name index construction was rejected under the repository
  review policy because no supported create or migration path can produce it and Issue #306 does
  not require compatibility with manual schema tampering.

## Prior project status (Issue #317 historical record)

# Project Status — Issue #317 dead-code and unified quality gates

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch\.codex-tmp-agentic-rag`
- Branch: `codex/issue-317-dead-code-detection`
- Baseline: `origin/main@bd6f47f`
- Task: implement Issue #317 and the requested unified pytest/Black/isort/Pylint gate

## Scope and boundaries

- This repository is the only writable workspace.
- Sibling repositories are off-limits.
- The work covers TypeScript and Python file reachability, symbol detection,
  reviewed exceptions, shrink-only baselines, local hooks, CI, reports, and
  contributor documentation.
- CI only reports and blocks; it never deletes or rewrites source files.

## Implementation state

- PR #318 is open: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/318`.
- Added production-first Knip and AST module-reachability checks, followed by
  Knip/ESLint and Vulture symbol checks.
- Production and test entries are separate. Constant dynamic imports require a
  reasoned allowlist, and stale entries fail the gate.
- Added a statically validated Vulture whitelist for FastAPI routes, Pydantic
  validators, middleware hooks, and pytest fixtures.
- Added normalized `path + kind + symbol` dead-code baselines. New findings,
  stale findings, and all 100%-confidence Vulture findings fail; maintenance
  updates can only shrink the baseline.
- Classified the initial baseline: 9 TypeScript files, 5 Python modules, 28
  TypeScript symbols, and 93 Python symbols. Reviewed cleanups have since
  reduced all dead-file findings to zero and all symbol findings to 17 Python
  compatibility/test items.
- Added the requested unified quality gate: full pytest plus non-mutating
  Black, isort, and Pylint checks, with an exact shrink-only compatibility
  baseline for existing formatter/linter debt. Pytest failures cannot be
  baselined.
- Added pre-commit/pre-push hooks, ordered CI jobs, text/JSON artifacts,
  top-level commands, watch mode, and investigation/cleanup documentation.
- Removed confirmed unused TypeScript locals/imports and corrected narrow test
  contracts exposed by the new full-suite gate.
- The first PR #318 run passed file/symbol, frontend, and Python smoke jobs. Its
  full Linux gate exposed one POSIX path-normalization bug, two FastAPI 0.141
  route-introspection assumptions, five Linux symlink-path assertions, and
  four platform-dependent static-baseline entries. These were fixed narrowly:
  publication slots remain atomic while failed rollback audit fields advance,
  staging is reverified immediately after digesting, and optional marker
  Pylint findings are deterministically suppressed at their exact call sites.
- Copilot's one actionable review finding was confirmed and fixed: the
  synthetic commit-failure context manager now executes the transaction body,
  raises during exit, and delegates rollback to the real transaction manager.
- The second Linux run passed four jobs but showed that four symlink rollback
  assertions scrubbed audit fields from the direct publication projections,
  not from the same fields mirrored in the nested manifest projection. The
  helper now removes only those four audit keys recursively while comparing
  every other field, with a platform-independent regression for that shape.
- Historical cleanup now proceeds one directory at a time, with focused tests,
  the complete gate, and one path-specific commit per directory. The first
  completed directory is `config/`: Black/isort formatting was applied, the
  Pydantic path validator was explicitly marked as a classmethod, and the
  output-format validation was made type-explicit for Pylint.
- The second completed directory is `scripts/`. Eleven Python scripts received
  only Black/isort formatting; no behavior, dead-code decision, or script entry
  point was changed.
- The third completed directory is `ai_actuarial/agentic_rag/`. Graphify
  confirmed that its primary modules connect to runtime/API consumers and
  dedicated tests, so seven historical files received only Black/isort
  formatting and no file or symbol was removed.
- The fourth completed directory is `ai_actuarial/api/middleware/`. Its single
  implementation file is directly exercised by FastAPI auth and ops tests, so
  it received only Black/isort formatting and no file or symbol was removed.
- The fifth completed directory is `ai_actuarial/models/`. Both the package
  exports and `ApiToken` model have direct runtime/storage consumers and
  dedicated tests, so both files received only Black/isort formatting.
- The sixth completed directory is `ai_actuarial/security/`. Both production
  files are imported by crawler, listening-rule, and API-service paths and are
  covered by URL-safety and integration tests, so both files received only
  Black/isort formatting and no symbol was removed.
- The seventh completed directory is `ai_actuarial/services/`. The package
  export and token-encryption implementation have direct runtime, API, and
  diagnostic consumers plus dedicated integration tests, so both files
  received only Black/isort formatting and no symbol was removed.
- The eighth completed directory is `ai_actuarial/processors/`. Unlike the
  earlier directories, all three Python modules were production-unreachable,
  had no code or test callers, and were already classified `remove` in the
  reviewed dead-code baseline. The three modules and their inaccurate README
  were deleted rather than reformatted.
- The ninth completed directory is `ai_actuarial/collectors/`. Current source
  and exact repository search confirmed that `AdhocCollector` had no runtime,
  test, export, or dynamic caller; its stale Graphify edge pointed to an import
  no longer present in the current CLI. The orphan module and its README claim
  were deleted, two unused imports were removed, and the five reachable
  collector implementations were formatted. The exported
  `CollectionConfig.auto_download` constructor field was retained because
  Issue #317 forbids deleting a public API solely from static-analysis output.
- The tenth completed directory is the direct files under `ai_actuarial/api/`
  (excluding its separately reviewed subdirectories). `app.py`, `deps.py`, and
  `route_inventory.py` were formatted. The `deps.py` email-session selection
  now uses an explicit typed branch instead of a conditional expression,
  preserving behavior while removing its Pylint E1136 false inference. The
  reported `block_retired_api_fallback` symbol remains because its FastAPI
  decorator registers the framework route at runtime.
- The eleventh completed directory is `ai_actuarial/chatbot/`. Seven reachable
  implementation files and the package exports were formatted. Six confirmed
  unused public symbols plus the private `_extract_citations` helper used only
  by a removed method were deleted. No test imported or exercised those
  symbols, so no test was deleted; all tests covering retained chatbot behavior
  remain. `QueryRouter.select_kbs` remains because its source explicitly marks
  it as a backward-compatible alias, and the public configuration fields remain
  part of the configuration contract.
- The twelfth completed directory is `ai_actuarial/rag/`. All ten modules have
  production or test consumers, so no module was deleted. Ten confirmed unused
  baseline symbols were removed, along with four additional helpers or
  attributes that exact caller analysis and the cleanup itself showed were
  unreachable. `RAGConfig.chunk_strategy` remains because YAML, environment,
  migration, documentation, and tests establish it as a public configuration
  contract. The one test dedicated to proving the removed
  `_soft_delete_file_vectors` helper was not called was deleted with that
  helper; all retained RAG behavior remains covered.

## Acceptance results

- Unified quality gate: passed. Pytest reported 1,880 passed and 10 skipped;
  Black, isort, and Pylint exactly matched the current reviewed baselines at
  159 files, 99 files, and 19 error identities respectively.
- Dead-code gate: passed with 9/1 file findings and 28/72 symbol findings,
  exactly matching the classified baseline and with no 100%-confidence
  Vulture finding.
- Dead-code and quality-gate unit tests: 11 passed as part of the full suite.
- Flaky schema-validator isolation regression: passed five consecutive focused
  runs and then passed in the full suite.
- Frontend ESLint: passed with six existing React dependency warnings and no
  errors.
- Frontend TypeScript check: passed.
- Frontend production build: passed; Vite emitted only the existing large
  chunk advisory.
- Clean lockfile install: `npm ci` passed. npm reported nine dependency audit
  findings (2 low, 1 moderate, 6 high); dependency/security upgrades are
  outside Issue #317.
- Pre-commit config validation, CI YAML parsing, CLI `--help`, and
  `git diff --check`: passed.
- Post-CI focused regression: 6 passed and 5 Windows symlink skips. Static
  baselines now match exactly at 213 Black files, 142 isort files, and 22
  Pylint identities; the dead-code gate remains exact.
- After the Copilot fix, its focused regression passed, then the complete
  unified quality gate passed again with 1,880 passed and 10 skipped; the
  dead-code gate also remained exact at 9/5 files and 28/93 symbols.
- After the nested-audit assertion fix, its focused regression passed. Static
  baselines remain exact at 213/142/22 with no new or stale entries, and the
  dead-code gate remains exact at 9/5 files and 28/93 symbols. Final Linux CI
  run 33456929109 passed all five jobs; its unified gate reported 1,891 tests
  passed, including the four original symlink tests, then passed Black, isort,
  and Pylint.
- `config/` focused validation passed: Black, isort, and Pylint reported no
  findings; 36 tests passed and 1 platform-specific test skipped.
- The complete unified quality gate passed after the `config/` cleanup with
  1,881 tests passed and 10 skipped. Its reviewed baseline shrank only for this
  directory, from 213/142/22 to 210 Black files, 140 isort files, and 20 Pylint
  identities.
- The complete dead-code gate also passed unchanged at 9/5 file findings and
  28/93 symbol findings.
- Path-specific commit `fc814fa` was pushed to PR #318. CI run 33460353038
  passed all five jobs: both dead-code layers, frontend, Python smoke, and the
  complete Linux quality gate. No new review comment was added.
- `scripts/` focused validation passed: Black, isort, and Pylint reported no
  findings; 80 tests passed and 1 platform-specific test skipped.
- The complete unified quality gate passed after the `scripts/` cleanup with
  1,881 tests passed and 10 skipped. The reviewed baseline shrank only for this
  directory, from 210/140/20 to 200 Black files, 132 isort files, and 20 Pylint
  identities. The complete dead-code gate remained exact at 9/5 files and
  28/93 symbols.
- Path-specific commit `c601182` was pushed to PR #318 and all five remote CI
  jobs passed with no new review feedback.
- `ai_actuarial/agentic_rag/` focused validation passed: Black, isort, and
  Pylint reported no findings, and all 94 dedicated tests passed.
- The complete unified quality gate passed after the `agentic_rag/` cleanup
  with 1,881 tests passed and 10 skipped. The reviewed baseline shrank only for
  this directory, from 200/132/20 to 193 Black files, 127 isort files, and 20
  Pylint identities. The complete dead-code gate remained exact at 9/5 files
  and 28/93 symbols.
- The machine's existing global Black cache caused high-CPU CLI stalls for the
  changed files. Black's API verified them immediately; the official CLI and
  complete gate then passed with an isolated temporary `BLACK_CACHE_DIR`.
- Remote commit `5356248` contains the exact `agentic_rag/` tree and passed all
  five PR #318 jobs in CI run 33467686369. GitHub authentication and the branch
  update used a task-scoped temporary credential because the sandbox cannot
  replace the invalid user-level GitHub CLI credential.
- `ai_actuarial/api/middleware/` focused validation passed: Black, isort, and
  Pylint reported no gate findings, and all 27 direct FastAPI tests passed.
- The temporary clone initially lacked its ignored root `node_modules`, so 16
  TypeScript subprocess tests could not start. `npm ci` restored the pinned
  dependencies, all 16 focused tests passed, and the complete pytest rerun then
  passed with 1,881 tests and 10 platform skips.
- The full static gate passed after the `middleware/` cleanup at 192 Black
  files, 126 isort files, and 20 Pylint identities, with zero new or stale
  entries. The complete dead-code gate remained exact at 9/5 files and 28/93
  symbols.
- Remote commit `b2c0d92` contains the exact `middleware/` tree. CI run
  33470766007 passed all five jobs, including the 6m27s Linux quality gate, and
  no new Review or Copilot comment was added.
- `ai_actuarial/models/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 23 model/storage integration tests passed.
- The complete pytest suite passed after the `models/` cleanup with 1,881 tests
  and 10 platform skips. The full static gate passed at 190 Black files, 124
  isort files, and 20 Pylint identities, with zero new or stale entries. The
  dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `2fff76c` contains the exact `models/` tree. CI run
  33472039867 passed all five jobs, including the 7m30s Linux quality gate, and
  no new Review or Copilot comment was added.
- `ai_actuarial/security/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 70 URL-safety and direct-consumer tests
  passed.
- The complete pytest suite passed after the `security/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 188 Black files,
  123 isort files, and 20 Pylint identities, with zero new or stale entries.
  The complete dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `0699b47` contains the exact `security/` tree. CI run
  33473548630 passed all five jobs, including the 11m04s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/services/` focused validation passed: Black, isort, and Pylint
  reported no gate findings, and all 120 token-encryption and direct-consumer
  tests passed.
- The complete pytest suite passed after the `services/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 186 Black files,
  122 isort files, and 20 Pylint identities, with zero new or stale entries.
  The complete dead-code gate remained exact at 9/5 files and 28/93 symbols.
- Remote commit `4bc201e` contains the exact `services/` tree. CI run
  33475164224 passed all five jobs, including the 7m05s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/processors/` focused validation found no remaining Python
  caller, compiled the repository successfully, and passed all 23 catalog,
  collector, and dead-code-gate regression tests.
- The complete pytest suite passed after removing `processors/` with 1,881
  tests and 10 platform skips. The full static gate passed at 184 Black files,
  121 isort files, and 20 Pylint identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/5 files and 28/93 symbols to 9/2
  files and 28/89 symbols.
- Remote commit `a7c502e` contains the exact `processors/` tree. CI run
  33476666119 passed all five jobs, including the 7m51s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/collectors/` compiled successfully, had no remaining
  `AdhocCollector` reference, passed Black and isort, and passed all 253 tests
  in the ten directly importing collector modules or their runtime consumers.
- The complete pytest suite passed after the `collectors/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 178 Black files,
  116 isort files, and 20 Pylint error identities, with zero new or stale
  entries. The dead-code gate shrank exactly from 9/2 files and 28/89 symbols
  to 9/1 files and 28/88 symbols.
- Remote commit `915fc4d` contains the exact `collectors/` tree. CI run
  33511516566 passed all five jobs, including the 7m48s Linux quality gate,
  and no new Review or Copilot comment was added.
- The direct `ai_actuarial/api/` files compiled successfully and passed Black,
  isort, and a zero-error focused Pylint scan. All 407 directly importing tests
  completed with 400 passed and 7 platform skips.
- The complete pytest suite passed after the direct `api/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 175 Black files,
  114 isort files, and 19 Pylint error identities, with zero new or stale
  entries. The dead-code gate remained exact at 9/1 files and 28/88 symbols.
- Remote commit `bf2d2a0` contains the exact direct `ai_actuarial/api/` cleanup.
  CI run 33513870640 passed all five jobs, including the 7m35s Linux quality
  gate, and no new Review or Copilot comment was added.
- `ai_actuarial/chatbot/` compiled successfully and passed Black, isort, and a
  zero-error focused Pylint scan. All 176 chatbot and direct-consumer tests
  passed. No dedicated test existed for any removed symbol, so no corresponding
  test removal was required.
- The complete pytest suite passed after the `chatbot/` cleanup with 1,881
  tests and 10 platform skips. The full static gate passed at 168 Black files,
  107 isort files, and 19 Pylint error identities, with zero new or stale
  entries. The dead-code gate shrank exactly from 9/1 files and 28/88 symbols
  to 9/1 files and 28/82 symbols.
- Remote commit `675c2b5` contains the exact `ai_actuarial/chatbot/` cleanup.
  CI run 33530581036 passed all five jobs, including the 8m02s Linux quality
  gate, and no new Review or Copilot comment was added.
- `ai_actuarial/rag/` compiled successfully and passed Black, isort, and a
  zero-error focused Pylint scan. The 24 directly importing test files completed
  with 646 passed and 8 platform skips after the one obsolete test was removed.
- The complete pytest suite passed after the `rag/` cleanup with 1,880 tests
  and 10 platform skips. The full static gate passed at 159 Black files, 99
  isort files, and 19 Pylint error identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/1 files and 28/82 symbols to 9/1
  files and 28/72 symbols.
- Remote commit `fdac797` contains the exact `ai_actuarial/rag/` cleanup. CI
  run 33534463645 passed all five jobs, including the 7m56s Linux quality gate,
  and no new Review or Copilot comment was added.
- `ai_actuarial/api/routers/` compiled successfully and all 15 route modules
  were confirmed as registered FastAPI production modules. The 15 directly
  related test files completed with 393 passed and 8 platform skips.
- `WeeklySnapshotFilesModel.truncated` is a live Pydantic response field, not
  dead code: the service populates it and endpoint tests assert it. An exact
  whitelist reference now records that framework contract; no source field or
  test was removed.
- The complete pytest suite passed after the router cleanup with 1,880 tests
  and 10 platform skips. The full static gate passed at 146 Black files, 91
  isort files, and 19 Pylint error identities, with zero new or stale entries.
  The dead-code gate shrank exactly from 9/1 files and 28/72 symbols to 9/1
  files and 28/71 symbols.
- Remote commit `a71e984` contains the exact `ai_actuarial/api/routers/`
  cleanup. CI run 33537947899 passed all five jobs, including the 6m53s Linux
  quality gate, and no new Review or Copilot comment was added.
- `ai_actuarial/api/services/` compiled successfully. Seven confirmed dead
  baseline symbols and two resulting private orphans were removed; no test was
  dedicated to those deleted definitions, so no test removal was required.
- The provider-credential write and environment-import paths now pass
  `status_code=503` correctly when token encryption is unavailable instead of
  raising `TypeError`. A regression covers both HTTP entry points. The ready
  source gate also uses an explicit mapping check, removing a Pylint inference
  false positive without changing its behavior.
- The 12 directly related service test files completed with 462 passed and 9
  platform skips. The complete pytest suite passed with 1,881 tests and 10
  platform skips. The full static gate passed at 129 Black files, 81 isort
  files, and 16 Pylint error identities, with zero new or stale entries. The
  dead-code gate shrank exactly from 9/1 files and 28/71 symbols to 9/1 files
  and 28/64 symbols.
- Remote commit `cbd933b` contains the exact `ai_actuarial/api/services/`
  cleanup. CI run 33539534698 passed all five jobs, including the 6m47s Linux
  quality gate, and no new Review or Copilot comment was added.
- `client/src/components/` no longer contains the unreachable
  `LoadingSkeleton.tsx`. `transformMarkdownUrl` remains live inside
  `MarkdownContent.tsx` but is no longer exported solely for tests; the direct
  helper assertions were removed while the component-level link and hostile
  input coverage was retained.
- The focused component checks passed: both TypeScript dead-code ratchets,
  ESLint, the three Markdown content source tests, frontend type-check, and the
  production build. The complete pytest suite passed with 1,881 tests and 10
  platform skips, and the full unified quality gate passed at 129 Black files,
  81 isort files, and 16 Pylint error identities. The dead-code gate shrank
  exactly from 9/1 files and 28/64 symbols to 8/1 files and 27/64 symbols.
- Remote commit `182d0c0` contains the exact `client/src/components/` cleanup.
  CI run 33540711906 passed all five jobs, including the 13m42s Linux quality
  gate, and no new Review or Copilot comment was added.
- `client/src/hooks/` no longer contains the completely unreferenced
  `use-api-query.ts`. The two live task-option result shapes remain in use but
  are now private implementation types instead of unused public exports.
- The hooks directory passed ESLint, the 27 task React source tests, frontend
  type-check, and the production build. The complete pytest suite passed with
  1,881 tests and 10 platform skips, and the full unified quality gate passed
  at 129 Black files, 81 isort files, and 16 Pylint error identities. The
  dead-code gate shrank exactly from 8/1 files and 27/64 symbols to 7/1 files
  and 25/64 symbols.
- Remote commit `f80d52d` contains the exact `client/src/hooks/` cleanup. CI
  run 33542287174 passed all five jobs, including the 7m35s Linux quality gate,
  and no new Review or Copilot comment was added.
- `client/src/lib/` now exposes only externally consumed contracts. Two unused
  navigation helpers and the test-only knowledge-list authority helper were
  removed; the duplicate ready-data route helper was consolidated under the
  request name. Live helpers and data shapes that are internal to their module
  remain implemented but are no longer exported.
- Tests were updated to exercise the public ready-data merge helper and native
  URL parsing. The one runtime test segment dedicated only to the removed
  authority helper was deleted; the surrounding current behavior tests remain.
  All 77 focused tests, ESLint, frontend type-check, and the production build
  passed. The complete pytest suite passed with 1,881 tests and 10 platform
  skips, and the unified quality gate passed at 129/81/16. The dead-code gate
  shrank exactly from 7/1 files and 25/64 symbols to 7/1 files and 7/64 symbols.
- Remote commit `8beb8d8` contains the exact `client/src/lib/` cleanup. CI run
  33543437722 passed all five jobs, including the 7m41s Linux quality gate, and
  no new Review or Copilot comment was added.
- Five unreachable historical page implementations were removed from
  `client/src/pages/`: `FeatureUnavailable`, `NativeFileDetail`, `NativeLogs`,
  `NativeSettings`, and `NativeTasks`. The live chat route selection type is
  now private to its module.
- Test constants and assertions that read the deleted native file/task pages
  were removed while current FileDetail, FilePreview, task metrics, Markdown,
  and chat route coverage was retained. All 41 focused tests, directory ESLint,
  frontend type-check, and the production build passed. The complete pytest
  suite passed with 1,881 tests and 10 platform skips, and the unified quality
  gate passed at 129/81/16. The dead-code gate shrank exactly from 7/1 files
  and 7/64 symbols to 2/1 files and 6/64 symbols.
- Remote commit `77e54a9` contains the exact `client/src/pages/` cleanup. CI
  run 33544476773 passed all five jobs, and no new review comment was added.
- `client/src/pages/tasks/` no longer contains the unreachable
  `FolderBrowser.tsx` or its unreachable barrel `index.ts`. Three live
  implementation details remain in use but are no longer exported, and three
  duplicate schedule types with no caller were removed. The negative test
  proving that browser uploads do not use the retired folder browser remains
  because it covers current behavior.
- The task-page cleanup passed 32 focused source/runtime tests, directory
  ESLint, frontend type-check, and the production build. One full-suite source
  assertion was corrected to inspect the shared `TaskMetrics` implementation
  instead of relying on a removed re-export comment; its focused rerun passed.
- The complete pytest suite then passed with 1,881 tests and 10 platform skips,
  and the unified quality gate passed at 129/81/16. The dead-code gate shrank
  exactly from 2/1 files and 6/64 symbols to 0/1 files and 0/64 symbols, so the
  TypeScript historical dead-code baseline is now empty.
- Remote commit `0bbda30` contains the exact `client/src/pages/tasks/`
  cleanup. CI run 33547151953 passed all five jobs, including the complete
  Linux quality gate, and no new review comment was added.
- The exported `CollectionConfig.auto_download` dataclass field was retained as
  a public constructor contract and added to the statically validated exact
  whitelist. No source or test was deleted. All 112 directly related collector
  tests passed, and Black, isort, and Pylint passed for the touched whitelist
  and collector base files.
- The complete pytest suite passed with 1,881 tests and 10 platform skips, and
  the unified quality gate passed at 129/81/16. The dead-code gate shrank
  exactly from 0/1 files and 0/64 symbols to 0/1 files and 0/63 symbols.
- Remote commit `1a792e0` contains the exact collector public-contract
  classification. CI run 33549779936 passed all five jobs, including the
  complete Linux quality gate, and no new review comment was added.
- The final unreachable Python module `ai_actuarial/pipeline_config.py` was
  deleted. Its 20-test dedicated file and four tests in the immutable-guards
  suite that imported only that module were deleted with it; the live manifest
  schema-version ingestion traceability test remains.
- The pipeline-config cleanup compiled successfully, passed all 44 retained
  focused tests, and left no repository reference to the deleted module. The
  complete pytest suite passed with 1,857 tests and 10 platform skips. The
  unified quality gate passed after shrinking to 127 Black files, 80 isort
  files, and 16 Pylint identities. Both TypeScript and Python dead-file
  baselines are now empty; symbol findings remain 0/63.

## Files changed

- Gate implementation/config: `scripts/dead_code_gate.py`,
  `scripts/quality_gate.py`, `knip.json`, `eslint.config.mjs`, `pyproject.toml`,
  `package.json`, lockfile, development requirements, and both baselines.
- Framework review: `config/dead_code_whitelist.py`.
- Automation: `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.
- Documentation: `docs/dead-code.md`, docs index, and both root READMEs.
- Focused cleanup/tests: affected React files, small Python unused-argument
  cleanups, gate tests, and narrow full-suite contract corrections.
- First historical directory cleanup: `config/__init__.py`,
  `config/settings.py`, `config/yaml_config.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Second historical directory cleanup: eleven formatted Python files under
  `scripts/` and the matching removals from `quality-gate-baseline.json`.
- Third historical directory cleanup: seven formatted Python files under
  `ai_actuarial/agentic_rag/` and the matching removals from
  `quality-gate-baseline.json`.
- Fourth historical directory cleanup:
  `ai_actuarial/api/middleware/rate_limit.py` and the matching removals from
  `quality-gate-baseline.json`.
- Fifth historical directory cleanup: `ai_actuarial/models/__init__.py`,
  `ai_actuarial/models/api_token.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Sixth historical directory cleanup: `ai_actuarial/security/__init__.py`,
  `ai_actuarial/security/url_safety.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Seventh historical directory cleanup: `ai_actuarial/services/__init__.py`,
  `ai_actuarial/services/token_encryption.py`, and the matching removals from
  `quality-gate-baseline.json`.
- Eighth historical directory cleanup: deleted the unreachable
  `ai_actuarial/processors/` package and its inaccurate README, then removed
  exactly three module and four method findings from `dead-code-baseline.json`
  plus the three matching formatter paths from `quality-gate-baseline.json`.
- Ninth historical directory cleanup: deleted
  `ai_actuarial/collectors/adhoc.py`, removed its inaccurate README section and
  two dead-code findings, removed two unused imports, formatted the five
  reachable collector implementations, and removed their eleven matching
  formatter paths from `quality-gate-baseline.json`.
- Tenth historical directory cleanup: formatted `ai_actuarial/api/app.py`,
  `ai_actuarial/api/deps.py`, and `ai_actuarial/api/route_inventory.py`, made
  the authentication type narrowing explicit, and removed their six matching
  Black/isort/Pylint entries from `quality-gate-baseline.json`.
- Eleventh historical directory cleanup: formatted all eight Python files under
  `ai_actuarial/chatbot/`, removed six confirmed unused public symbols and one
  private helper, reclassified the explicit `select_kbs` compatibility alias,
  and removed the matching dead-code and formatter baseline entries. No test
  file or test case was removed because none corresponded to the deleted code.
- Twelfth historical directory cleanup: formatted the nine historical Python
  files under `ai_actuarial/rag/`, removed ten reviewed dead-code baseline
  symbols plus four exact or cascading orphans, deleted the single test tied to
  the removed immutable-index helper, and removed the matching dead-code and
  formatter baseline entries.
- Thirteenth historical directory cleanup: formatted all 15 files under
  `ai_actuarial/api/routers/`, added the precise Pydantic response-field
  whitelist for `WeeklySnapshotFilesModel.truncated`, and removed its stale
  dead-code entry plus the 21 matching formatter baseline entries.
- Fourteenth historical directory cleanup: formatted all 17 files under
  `ai_actuarial/api/services/`, removed seven reviewed dead-code baseline
  symbols plus two cascading private orphans, fixed three Pylint identities,
  added the two-entry-point encryption failure regression, and removed the
  matching dead-code and 27 formatter/linter baseline entries.
- Fifteenth historical directory cleanup: deleted the unreachable
  `client/src/components/LoadingSkeleton.tsx`, made the live Markdown URL
  transformer private, removed only its direct test-only import and assertions,
  and removed the matching two TypeScript dead-code baseline entries.
- Sixteenth historical directory cleanup: deleted the unreachable
  `client/src/hooks/use-api-query.ts`, made two live task-option interfaces
  private, and removed the matching three TypeScript dead-code baseline entries.
- Seventeenth historical directory cleanup: removed three confirmed dead
  `client/src/lib/` functions, consolidated a duplicate ready-data request
  export, made fourteen live implementation details private, updated the one
  cross-directory caller and focused tests, and removed the matching eighteen
  TypeScript dead-code baseline entries.
- Eighteenth historical directory cleanup: deleted five unreachable legacy
  files under `client/src/pages/`, made the live chat route selection type
  private, removed only the test constants and assertions tied to the deleted
  pages, and removed the matching six TypeScript dead-code baseline entries.
- Nineteenth historical directory cleanup: deleted the unreachable
  `client/src/pages/tasks/FolderBrowser.tsx` and barrel `index.ts`, removed
  three unused exports and three unused duplicate schedule types, corrected
  one source-contract test to inspect the real shared metrics component, and
  removed the final eight TypeScript dead-code baseline entries.
- Twentieth historical directory cleanup: retained the public exported
  `CollectionConfig.auto_download` constructor field, recorded its exact
  compatibility reference in the validated whitelist, and removed its stale
  Python dead-code baseline entry without changing source or tests.
- Twenty-first historical directory cleanup: deleted the unreachable
  `ai_actuarial/pipeline_config.py` module and its 24 module-only tests,
  formatted the touched immutable-guards test while preserving its live
  manifest traceability case, and removed the final Python dead-file baseline
  plus the matching Black/isort baseline entries.
- Twenty-second historical directory cleanup: formatted all 31 direct Python
  files under `ai_actuarial/`, deleted 20 confirmed-unused root symbols plus one
  cascading legacy weekly-summary reader, retained 27 framework/public
  contracts through exact validated whitelist references, and narrowed seven
  SQLAlchemy/Pydantic Pylint suppressions to their individual call sites. No
  test was removed because none was dedicated to the deleted code. Focused
  tests passed 132/1, the full suite passed 1857/10, the dead-code gate passed
  at 0 files/17 symbols, and the quality baseline fell from 127/80/16 to
  96/60/9.
- Twenty-third historical directory cleanup: retained the nested
  `block_retired_api_fallback` FastAPI 410 route in `ai_actuarial/api/app.py`
  and added its exact source-level framework reference. Focused tests passed
  20/20; after one host-resource-abnormal test run was stopped and isolated,
  the unchanged historical file passed 83/83 and a clean full rerun passed
  1857/10 plus Black, isort, and Pylint. The dead-code symbol baseline fell
  from 17 to 16; the quality baseline remains 96/60/9. The first remote
  quality-gate attempt hit a concurrent-test race in an unrelated historical
  schema test; the failed job rerun passed without source changes, and all five
  remote CI jobs are green.
- Twenty-fourth historical directory cleanup: retained six public exported
  `ChatbotConfig` fields loaded from environment/YAML settings plus the
  explicit `QueryRouter.select_kbs` compatibility alias, recording each as an
  exact validated whitelist reference. No production code or tests were
  removed. Focused tests passed 115/115, the full suite passed 1857/10 plus
  Black, isort, and Pylint, and the dead-code symbol baseline fell from 16 to
  9; the quality baseline remains 96/60/9. All five remote CI jobs passed.
- Twenty-fifth historical directory cleanup: retained the public
  `RAGConfig.chunk_strategy` field loaded from environment/YAML settings and
  recorded its exact validated whitelist reference. No production code or
  tests were removed. Focused tests passed 41/41, the full suite passed 1857/10
  plus Black, isort, and Pylint, and the dead-code symbol baseline fell from 9
  to 8; the quality baseline remains 96/60/9. All five remote CI jobs passed.
- Twenty-sixth historical directory cleanup: formatted all six Python files
  under `tests/agentic_rag/` (five Black and two isort baseline identities) and
  strengthened `test_evaluate_single_pass` to verify the fake retriever
  receives the query and `top_k`. No tests were removed. Focused tests passed
  102/102, the full suite passed 1857/10 plus Black, isort, and Pylint, the
  dead-code symbol baseline fell from 8 to 6, and the quality baseline fell
  from 96/60/9 to 91/58/9. All five remote CI jobs passed.
- Twenty-seventh historical directory cleanup: formatted the two historical
  Python test files under `tests/unit/`, removing two Black and two isort
  baseline identities. No code or tests were removed. Focused tests passed
  40/40, the full suite passed 1857/10 plus Black, isort, and Pylint, the
  dead-code baseline remains 0 files/6 symbols, and the quality baseline fell
  from 91/58/9 to 89/56/9. All five remote CI jobs passed.
- Twenty-eighth and final historical directory cleanup: formatted all 105
  direct Python files under `tests/` (89 historical Black and 56 isort baseline
  identities), resolved all nine Pylint identities, removed six unused test
  symbols without deleting any test case, strengthened the API-token timestamp
  assertion, and isolated the mutating schema-validator test from background
  database activity. Focused tests passed 319/7, the full suite passed 1857/10,
  independent semantic and mechanical reviews found no issues, and both the
  dead-code and quality baselines are now completely empty: 0 files/0 symbols
  and 0/0/0 respectively. All five remote CI jobs passed. PR #318 is clean and
  mergeable; the only review thread was an older Copilot finding already fixed
  and acknowledged before this final cleanup.

## Working tree notes

- Existing untracked `diagrams/` and `graphify-out/` remain user-owned,
  untouched, and excluded from the commit.
- Generated `reports/`, coverage output, build output, and installed
  dependencies are ignored.

## Blockers or decisions needed

- No implementation or local validation blocker.
- Merge is not authorized by the current request; publication stops at an open
  PR unless explicit merge authorization is given.

## Recommended next action

- Report the completed directory-by-directory cleanup and leave the clean,
  mergeable PR #318 open. Merge only after explicit authorization.

# Project Status — Issue #319 loose-coupled incremental stages

- Updated: 2026-09-02 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\e680\AI_actuarial_inforsearch`
- Branch: `codex/issue-319-loose-coupled-stages`
- Baseline: `origin/main@ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`
- Issue: `#319 fix(pipeline): continue loose-coupled incremental stages after partial success`
- State file: `C:\Users\ferry\.codex\issue-to-merge-state\AI_actuarial_inforsearch\issue-319.json`
- Delivery stage: remote feedback assessed; one confirmed contract fix validated; follow-up push pending

## Issue #319 acceptance criteria

- AC-1: Production-shaped Markdown `status=error` with `items_downloaded=2` launches Catalog
  exactly once while preserving the Markdown task's original status, errors, counters, result,
  and log.
- AC-2: Scheduled, Markdown, Catalog, Chunk, and Embedding all use the same terminal decision
  matrix: `completed/error + successful outputs > 0` advances once; `completed + 0` completes as
  a clean no-op; `error + 0` ends in error; `stopped` ends stopped; missing task or hard exception
  ends in error.
- AC-3: Catalog launches from its saved/default incremental configuration without predecessor
  `file_urls` and may select its normal historical uncataloged/outdated backlog.
- AC-4: Chunk launches from its saved/default incremental configuration without predecessor
  Markdown `files` and may select its normal historical Markdown-ready backlog.
- AC-5: Embedding launches without predecessor `chunk_set_ids` or `file_urls`; a minimal
  module-owned selector-free incremental backlog mode computes its own eligible ready chunk-set
  backlog and is available through both manual/API and Baton launches.
- AC-6: Given the same saved/default module configuration, Baton and manual launches resolve
  equivalent runtime parameters and work-selection behavior; raw frontend payload equality is not
  required.
- AC-7: Existing skipped, reused, retry-eligible, and historical backlog behavior remains owned by
  each module; skipped work is not reinterpreted as a predecessor handoff artifact.
- AC-8: Repeated ordinary ticks do not launch a next stage or subtask twice.
- AC-9: Current indexable KBs are enumerated in stable order across `manual`, `category`, and `all`
  modes; zero KBs completes cleanly.
- AC-10: One failed KB Index or Ready Data task is recorded and does not block later KBs; any
  stopped KB subtask stops the whole round immediately and launches no later KB.
- AC-11: If relay reaches the end, `round_status=completed` means orchestration completed and does
  not rewrite any individual task outcome.
- AC-12: Baton state remains compact: current stage/task plus existing KB summary only; no copied
  per-item errors, partial-evidence schema, or source-task mutation.
- AC-13: Existing standalone/manual task APIs, forms, saved/default configuration, module logs,
  status semantics, and Ready Data/KB behavior remain unchanged except for the shared Embedding
  selector-free backlog mode required by AC-5.
- AC-14: Existing Baton/runtime tests, the full stage matrix, production-shape Markdown regression,
  selector-absence and historical-backlog regressions, manual/Baton equivalence, KB failure/stop
  paths, duplicate-tick behavior, and all repository-required checks pass.

## Issue #319 stage decision matrix

| Task outcome | Successful output count | Baton result |
| --- | ---: | --- |
| `completed` | `> 0` | Launch the next module's normal incremental task once |
| `error` | `> 0` | Preserve the task error and launch the next module once |
| `completed` | `0` | Complete the round as a clean no-op |
| `error` | `0` | End the round as `error` |
| `stopped` | any | End the round as `stopped` |
| missing task or hard exception | unknown / `0` | End the round as `error` |

## Issue #319 scope and non-goals

- Owned production scope: `ai_actuarial/pipeline_baton.py`; minimal shared runtime/API/Embedding
  wiring only where AC-5/AC-6 requires it. Focused Baton/runtime/API/domain tests are in scope.
  Pipeline status/UI copy changes are conditional on observable wording changes.
- Sibling repositories and the primary checkout's Issue #317 changes are off-limits.
- No predecessor file/hash/chunk-set handoff, frozen cohort, global lineage, new publication
  transaction, DAG, retry/resume/checkpoint/lease framework, automatic retry, crawler change,
  module redesign, or suppression/rewriting of task errors.
- Review-policy override: none. Findings must be realistically reproducible and map directly to
  an AC above.

## Issue #319 baseline and history evidence

- The assigned worktree was clean and detached at the supplied baseline. After fetch, `HEAD`,
  `origin/main`, and their merge-base all remained exactly `ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`;
  the isolated branch above was then created.
- A production-shaped no-edit reproduction showed Markdown `error + items_downloaded=2` leaves
  `round_status=error` and starts no Catalog task. Existing #292 Scheduled partial-success tests
  still pass.
- The same baseline reproduction showed Catalog receives predecessor `file_urls`, Chunk receives
  predecessor Markdown `files`, and Embedding receives predecessor `chunk_set_ids`.
- `git blame` and `git log -S` trace the general terminal behavior to the original Baton, the
  Scheduled-only exception to merged PR #292, and all three exact selector injections to commit
  `7a175050` (`feat: persist chunk embeddings`). The original #179 Baton regression explicitly
  asserted independent tasks without output handoff before that commit changed the contract.
- Duplicate search across open/closed/merged PRs, local/remote branches, and commit messages found
  no equivalent #319 work. Merged PR #292 covers Scheduled only and is not a duplicate.

## Issue #319 implementation state

- Baton now uses `items_downloaded` as the single authoritative successful-output count for all
  five non-KB phases. Partial errors advance once, clean zero-output completions stop cleanly,
  zero-output errors fail, stopped tasks halt, and missing tasks or hard orchestration failures fail.
- Catalog and Chunk now launch their normal saved/default incremental backlog without predecessor
  selectors. Baton no longer persists copied Markdown file evidence.
- Embedding now exposes a selector-free `incremental` mode owned by the embedding module. It
  resolves the current server identity first, scans ready chunk sets in stable order, validates
  chunk-set stability, and selects sets containing missing or invalid embeddings while preserving
  existing reuse and repair behavior.
- Manual/API, Baton, Tasks, and scheduled Chunk & Embedding composition use the same selector-free
  Embedding mode. File Detail retains its explicit single-file `chunk_set_ids` scope.
- Scheduled composition and Tasks both retain their existing empty Chunk-result guard. Reused
  stable chunk sets still launch selector-free Embedding so historical missing/invalid coverage can
  be repaired.
- KB Index/Ready Data preserves stable `manual`/`category`/`all` enumeration: one KB error is
  recorded and later KBs continue; a stopped KB task halts the round immediately.

## Issue #319 local review

- Round 1 found and fixed a scheduled-composition regression where reused stable chunk sets had
  `items_downloaded=0` and incorrectly skipped Embedding. The fix gates on non-empty stable
  `result.chunk_sets` and still launches only `incremental: true`.
- Round 2 found and fixed the matching Tasks regression where an empty Chunk result could launch an
  unrelated global Embedding backlog. Tasks now keeps the non-empty result guard without handing
  the IDs to Embedding.
- Round 3 used a fresh read-only reviewer and passed with no reproducible #319 finding. The final
  reviewer independently ran 96 focused tests.

## Issue #319 verification

- TDD red baseline for the new focused file: 18 product failures and 15 passes after correcting
  three test-fixture defects; final focused file: 33 passes.
- Final related Baton/runtime/API/CLI/UI suite: 102 passes; broader related suite previously passed
  151 tests plus 40 Embedding/Chunk domain tests.
- Unified quality gate: 1916 passed, 10 skipped; Black, isort, and Pylint passed. The first attempt
  was stopped after the pytest process reached 23.6 GB and left 0.1 GB host memory; a clean isolated
  rerun used normal memory and passed without source changes.
- Dead-code file and symbol gates: 0 findings. Frontend lint: 0 errors and five existing warnings;
  typecheck and production build passed.
- Python smoke: FastAPI 13 passed; Agentic RAG eval 31 passed; eval CLI passed all 3 cases with full
  evidence/citation/refusal metrics.
- `git diff --check` passed. No visible form, layout, or wording changed, so browser visual smoke was
  not required; the changed request contract is covered by source tests, typecheck, and build.
- After final fetch, `HEAD`, `origin/main`, and their merge-base remain
  `ae3e4e689c1bcdbd0c80982f8abaafa7e0af73e9`.

## Issue #319 remote feedback

- PR #327 was marked Ready at head `02a085339a64ddd9b7d131e897c0b33ff3f2497b`. The single
  feedback window ran for 680.49 seconds before one complete snapshot was fetched.
- All five required remote checks passed. No human review, PR comment, or Issue comment was
  present. Copilot left two inline comments.
- The first Copilot comment was confirmed: selector-free `incremental` accepted and echoed a
  `profile_id` that it did not apply. The minimal fix rejects `incremental + profile_id` at both
  the API launch boundary and the Embedding selection boundary; it does not add profile-filter
  semantics or change Baton's `{incremental: true}` payload.
- The second Copilot comment was rejected under the repository review policy. It proposed loading
  chunk IDs before content as a performance optimization but provided no reproducible functional,
  workflow, data-contract, or error-handling failure mapped to #319.
- The confirmed fix failed two new tests before implementation, then passed them. Manager reran the
  final Embedding/API/Baton/UI combination with 169 passes; the focused #319 file now has 35 passes.

## Issue #319 working tree notes

- Scoped production changes are limited to Pipeline Baton, Embedding selection/runtime/API wiring,
  and the Tasks request path. Scoped test changes cover the matrix, storage backlog, API/manual
  parity, scheduled/Tasks empty and reused results, and KB error/stop behavior.
- The new untracked `tests/test_issue_319_loose_coupled_pipeline.py` is an intentional scoped test
  file and will be included in the commit. Generated reports, coverage, build output, and installed
  dependencies are ignored.
- No unrelated local change is present. Sibling repositories and the primary checkout's Issue #317
  changes remain unread and untouched.

## Issue #319 blockers or decisions needed

- No implementation, review, validation, or publication blocker.

## Issue #319 recommended next action

- Commit and push the confirmed remote contract fix, allow required checks to rerun, reply to both
  captured Copilot threads with the accepted/rejected disposition, then merge once the updated head
  is green.
# Project Status — Issue #334 Recategory dry-run UI

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\3632\AI_actuarial_inforsearch`
- Branch: `codex/issue-334-recategory-dry-run-ui`
- Baseline: `origin/main@73215789cc6202add89d808ab35d5c430fa1ef0a`
- Issue: `#334 bug(ui): show Recategory dry-run results and place it before Catalog`
- Review state: `C:\Project\AI_actuarial_inforsearch\.git\codex-issue-to-merge\issue-334.json`
- Delivery stage: PR #335 is Ready; the single remote-feedback snapshot was assessed and its one
  valid localization fix passed focused validation; preparing the follow-up commit and current-head
  checks before merge
- Progress heartbeat: id `issue-334-delivery-progress`, status `ACTIVE`, 15-minute cadence

## Issue #334 acceptance criteria

- AC-1: A completed `recategory` history task whose `metadata.dry_run` is exactly true shows a
  human-readable Dry Run Result in the Task History detail/log dialog, sourced from the history
  task metadata so the same result remains visible after refresh.
- AC-2: When changes exist, the result accurately shows whether recategorization is needed and
  lists every removed and added category with its corresponding `removed_impact` or
  `added_impact` article count in a quickly scannable layout.
- AC-3: When `needs_recategory` is false and no category changes exist, the result shows an
  explicit localized no-changes state instead of an empty block.
- AC-4: Missing, incomplete, legacy, or wrong-shaped metadata degrades safely: ineligible tasks
  do not show the result, incomplete eligible results render only safe values, and no `null`,
  `undefined`, or task-detail crash reaches the user.
- AC-5: The result is read-only and offers no implicit Apply action or data mutation; the existing
  Recategory Plan/Apply algorithms and task execution contracts remain unchanged.
- AC-6: Re-categorize appears before Catalog in the Run Task cards and Scheduled Task type list;
  the Task History type filter gains Re-categorize before Catalog. Recategory remains independent
  and is not added to the automatic Pipeline.
- AC-7: All added user-facing copy is complete in English and Chinese, and category names, counts,
  lists, and the empty state fit without horizontal overflow at desktop and 320px widths.
- AC-8: Focused frontend regression tests cover change, no-change, missing/incomplete metadata,
  eligibility, and all three ordering contracts; the frontend checks, repository quality/dead-code
  gates, Python smoke gates, and desktop plus 320px browser smoke pass.

## Issue #334 scope, baseline evidence, and non-goals

- Code-change delivery is required. A baseline reproduction failed all five probes: the Run Task
  order and Scheduled Task order put Re-categorize after Catalog, Task History omits the filter
  option, `HistoryTask` has no metadata field, and the detail dialog has no dry-run rendering.
- The clean worktree started detached at the supplied baseline; `HEAD`, `origin/main`, and their
  merge-base all matched `73215789cc6202add89d808ab35d5c430fa1ef0a` before switching to the
  pre-created assigned branch at that same commit.
- PR #202 added the Recategory backend and appended basic Run/Scheduled UI entries. Its body and
  commit history describe task wiring but no dry-run history result UI or intended ordering.
  PR #201 only added taxonomy-state support, so neither is equivalent to Issue #334.
- Worker-owned files are limited to the Tasks history/detail and task-type ordering surfaces,
  bilingual task copy, and directly corresponding frontend tests. A small dedicated result
  component is allowed if it is the narrowest complete implementation. This manager owns this
  project-status record.
- Non-goals: backend result storage or API changes, `plan_recategory()` or Apply algorithm changes,
  taxonomy/Catalog/KB sync changes, Pipeline execution or dependency changes, automatic Plan-to-
  Apply behavior, sibling repositories, dependency upgrades, security frameworks, or speculative
  abstractions.
- Review-policy override: none; the default scoped review policy applies unchanged.

## Issue #334 blockers or decisions needed

- None.

## Issue #334 implementation and local review

- The Task History detail/log dialog now renders a dedicated read-only Dry Run Result only for
  completed Recategory plans with `metadata.dry_run === true`. It shows the plan decision,
  removed/added categories, safe per-category impact counts, the explicit no-change state, and an
  unavailable state for incomplete eligible metadata.
- Runtime guards accept only plain-object metadata, non-empty category strings, and non-negative
  integer counts. Missing, legacy, wrong-shaped, or ineligible metadata cannot render `null` or
  `undefined` and cannot break the rest of the task detail.
- Re-categorize now precedes Catalog in Run Task, Scheduled Task, and Task History filter order;
  the filter includes the previously missing option. Pipeline definitions remain unchanged.
- English and Chinese result copy is complete. Long names wrap, long lists are vertically bounded,
  and the result contains no Apply button or other mutation control.
- The Task History type filter now uses the existing English/Chinese task-type translations for
  every concrete option, eliminating the mixed-language dropdown identified during remote review.
- TDD reproduced three expected pre-fix failures, then the Issue suite passed all three tests.
  The worker inspected all same-shaped user-facing selectors plus desktop/mobile history paths;
  Logs, task-specific forms, and Pipeline were explicitly excluded with acceptance-mapped reasons.
- Fresh read-only review round 1 independently inspected the complete diff and tests and passed
  with no valid findings. Its only residual was the required changed-result browser evidence, which
  was completed after review without a code change.
- The first unified quality-gate invocation passed all 2,025 tests but stopped on Black/isort
  formatting of the new Python test. The same worker made only the formatter-required test-layout
  change; focused tests and formatter checks passed. The state record explains why this mechanical,
  behavior-neutral edit did not reopen local review.

## Issue #334 final local validation

- Focused Issue/task-history regression: 36 passed. Recategory/API regression: 34 passed. Scheduled
  Tasks and Task Metrics React runtime assertions passed. `git diff --check` passed.
- Unified quality gate passed on the complete post-format diff: 2,015 passed and 10 skipped; Black,
  isort, and error-only Pylint passed.
- Both dead-code gates passed with zero findings. Frontend lint passed with zero errors and five
  existing unrelated Hook warnings; TypeScript and the production build passed, with only the
  existing large-chunk advisory.
- Python smoke passed 13 FastAPI tests, 31 Agentic evaluation tests, and all 3 CLI evaluation cases;
  evidence, citation, and refusal rates were 1.0 and unsupported-answer rate was 0.
- Live browser smoke used disposable local data. Desktop and 320px both showed the changed result,
  the long removed category with impact 1, all 15 added categories with impact 0, bounded vertical
  scrolling, zero horizontal overflow, and zero result buttons. A page refresh preserved the same
  history result. The previously verified no-change result showed the explicit empty state.
- The first post-feedback CI run passed four jobs and all 2,025 tests except one older source
  assertion that expected the now-replaced hard-coded RAG filter label. The same worker updated only
  that assertion to the localized option; the exact test and the Issue suite passed locally.
- Disposable local browser servers were stopped after validation. No production operation ran.

## Issue #334 recommended next action

- Commit and push the validated remote-feedback fix to PR #335, require all checks to pass on that
  exact head, then merge and complete Issue, branch, worktree, and heartbeat cleanup.
# Project Status — Issue #312 schedule presets

- Updated: 2026-09-03 EDT
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\257d\AI_actuarial_inforsearch`
- Branch: `codex/issue-312-schedule-presets`
- Baseline: `origin/main@146028ac8258550f54953c9343b0fd01062c4de3`
- Issue: `#312 feat(schedule): add frequency, run-time, and timezone presets`
- State file: `C:\Project\AI_actuarial_inforsearch\.git\codex-issue-to-merge\issue-312.json`
- Delivery stage: implementation and six-round local review complete; final local gates pass and
  the branch is ready for commit, push, and draft PR publication

## Issue #312 acceptance criteria

- AC-1: Scheduled-task create/edit UI exposes only Every N minutes, Every N hours, Daily at
  `HH:MM`, and Weekly on Monday at `HH:MM`, showing only the quantity, run-time, and timezone
  fields relevant to the selected form.
- AC-2: Add/update APIs accept only the four canonical structured forms; invalid or non-positive N,
  invalid/non-canonical `HH:MM`, extra tokens, unknown timezones, and unsupported interval/timezone
  combinations return 400 without changing configured or effective scheduler state.
- AC-3: Rolling minute/hour schedules have no timezone and reject a supplied timezone. Newly saved
  daily/weekly fixed-time schedules require exactly `UTC` or `Asia/Shanghai`, persist a canonical
  interval plus timezone, and round-trip through reads and the UI.
- AC-4: `weekly at HH:MM` registers an effective Monday job at the selected timezone through the
  existing #307 reconciliation path; no second apply or scheduler mutation mechanism is added.
- AC-5: Existing `daily`, `weekly`, and fixed-time tasks without a timezone retain their prior
  process-local behavior and stored shape across read, edit-without-schedule-change, restart, and
  reinitialize until a structured schedule is explicitly saved.
- AC-6: UTC and Asia/Shanghai fixed-time schedules preserve their wall-clock meaning and are tested
  across UTC/CST cross-day and Monday boundaries.
- AC-7: `weekly_summary` remains locked to the previous complete UTC ISO week and its fixed-time
  schedule remains UTC; the UI/status also shows the equivalent Asia/Shanghai wall time.
- AC-8: Effective fixed-time job status includes unambiguous timezone/offset information and
  serialized last/next timestamps carry an offset; naive runtime values are never labeled UTC.
- AC-9: English/Chinese copy, focused backend/frontend/runtime tests, create/edit round trips,
  frontend lint/typecheck/build, browser smoke, dead-code gates, Python smoke, and the repository
  quality gate pass.

## Issue #312 scope, evidence, and non-goals

- Owned production scope is the narrow shared scheduled-task expression contract, scheduled-task
  add/update persistence and #307 reconciliation comparison, runtime registration/status, the
  Scheduled Tasks create/edit UI and same-shaped direct scheduled-task creation UI where required,
  bilingual copy, and directly corresponding tests. This manager owns this status record.
- Dependency #307 is closed by merged PR #325. Its desired/effective reconciliation, rollback,
  job identity, and RBAC implementation are reused and must not be duplicated.
- Non-goals: cron or a generic builder; arbitrary weekdays; monthly/yearly/holiday rules;
  distributed scheduling, catch-up, or misfire policy; site/default schedule redesign; Pipeline
  Baton frequency changes; reconciliation/RBAC redesign; dependency upgrades; sibling repositories;
  security frameworks; or speculative abstractions.
- The isolated worktree was clean and detached at startup. After fetch, `HEAD`, `origin/main`, the
  assigned branch, and their merge-base all matched the supplied baseline exactly; the branch was
  then attached without changing tracked files.
- A fresh audit found no open/closed PR, remote branch, or commit matching #312, schedule/timezone
  presets, `weekly at`, or `Asia/Shanghai`; duplicate-work-audit is recorded as `proceed`.
- Baseline source and runtime probes confirm a free-text interval field, no `weekly at` validation
  or registration, ignored daily `at_timezone`, non-canonical single-digit time acceptance, no
  persisted timezone, and naive-looking status timestamps. Delivery shape is `code-change`.
- Review-policy override: none. Only realistically reproducible functionality, workflow,
  data-contract, or error-handling findings mapped directly to an AC above are accepted.

## Issue #312 required validation

- Parser/API matrix for every accepted and rejected interval/timezone combination, including
  state-preserving 400 failures and canonical persisted output.
- Legacy fixtures for read, edit without schedule fields, restart, reinitialize, and process-local
  `daily`/`weekly`/no-timezone behavior.
- Real and fallback scheduler registration, #307 add/update reconciliation and rollback regression,
  Monday semantics, UTC/Asia-Shanghai cross-day boundaries, offset-bearing status, and Weekly
  Summary previous-complete-UTC-week/CST-equivalent tests.
- Scheduled Tasks and direct-create UI create/edit round trips, conditional field visibility,
  weekly-summary locking, bilingual copy, and desktop plus 320px browser smoke.
- Focused backend/frontend suites, `git diff --check`, frontend lint/typecheck/build, both dead-code
  gates, all three Python CI smoke commands, and `python scripts/quality_gate.py`.

## Issue #312 implementation and local review

- Added one shared schedule-preset contract for strict structured writes and bounded legacy runtime
  parsing. Rolling schedules omit timezone; fixed schedules persist only `UTC` or `Asia/Shanghai`.
- Scheduled-task writes validate before mutation, preserve unchanged legacy schedule fields, and use
  the existing #307 reconciliation/rollback path for effective jobs.
- Runtime registration supports Monday weekly-at schedules, selected fixed timezones, offset-bearing
  status, process-local legacy status, and the previous-complete-UTC-week Weekly Summary contract.
- Scheduled Tasks and direct-create UI now expose the four structured forms with bilingual copy.
  Legacy fixed/no-timezone tasks show process-local state until explicit conversion; legacy
  non-weekly Weekly Summary schedules show their real cadence read-only with an explicit Weekly UTC
  migration action.
- Six fresh read-only review rounds were completed. Accepted findings covered legacy task-type edits,
  invalid equivalent-time display, baseline-valid legacy whitespace/leading zeros, Weekly Summary
  timezone compatibility/type transitions, legacy Weekly Summary UI truthfulness, and ordinary
  legacy process-local UI truthfulness. The same persistent worker fixed each accepted finding.
  Round 6 returned full PASS with no valid Issue #312 findings.
- Post-review isort normalization and removal of four test-only helper exports were behavior-neutral
  gate cleanups by the same worker; state decisions record why functional review did not reopen.

## Issue #312 final local validation

- Unified quality gate: PASS on the final code, with 2,099 passed, 10 skipped, plus Black, isort, and
  error-only Pylint.
- Focused schedule/API/runtime/UI regression: 161 passed. Final React-source/Issue suite: 104 passed.
  Both executable TSX component suites and TypeScript typecheck passed.
- Frontend lint passed with zero errors and five pre-existing unrelated Hook warnings. Production
  build passed with only the existing large-chunk advisory.
- File and symbol dead-code gates passed with zero baseline findings. `git diff --check` passed.
- CI smoke passed 13 FastAPI tests, 31 Agentic evaluation tests, and all 3 CLI evaluation cases;
  evidence, citation, and refusal rates were 1.0 and unsupported-answer rate was 0.
- Disposable browser smoke passed in English and Chinese at desktop and 320px. It verified explicit
  process-local legacy display, direct canonical UTC conversion, offset/timezone status, read-only
  legacy Weekly Summary cadence, explicit Weekly UTC conversion, and Shanghai-equivalent copy.
  Browser services and temporary data were stopped and removed afterward.

## Issue #312 blockers or decisions needed

- None.

## Issue #312 recommended next action

- Commit and push the validated branch, create a draft PR with `Closes #312`, mark it ready, observe
  the full remote-feedback window, assess the single feedback snapshot, require checks on the exact
  head, then merge and complete Issue/branch/worktree cleanup.
# Latest work — Issue #355 accessible icon buttons

- Updated: 2026-09-29 EDT. Repository: `AI_actuarial_inforsearch`; worktree:
  `C:\Users\ferry\.codex\worktrees\issue-355-a11y-buttons\AI_actuarial_inforsearch`;
  branch: `codex/issue-355-a11y-buttons`; baseline:
  `fbda2bba66b1c4c0bb87bbe4870d1777e2bb6a85`. Sibling repositories were not accessed.
- Added one required-label `IconButton` convention with an exact 44px minimum hit area and a
  visible `focus-visible` ring. Layout, Chat, File Preview, Settings, Tasks, Scheduled Tasks, and
  Sites now use localized action names; dangerous and object actions include their target.
- Provider/search/category/token, scheduled-task/site, and backup destructive prompts or labels
  identify the same target. Existing API calls, permissions, and mutation behavior are unchanged.
- The desktop Sidebar no longer renders a hidden mobile close control. Mobile navigation test IDs
  are prefixed, so open desktop/mobile navigation instances do not duplicate `data-testid` values.
  Closing the mobile drawer restores focus to its opener.
- Added Vitest + Testing Library + axe DOM coverage and a durable Playwright Core smoke using the
  installed Chrome. Baseline red failed because the CSS-hidden desktop close button remained in the
  DOM. Green: 3 DOM/axe tests pass; Chrome at 390x844 verifies Tab focus styling, Enter open, Space
  close, exact 44px controls, focus recovery, unique test IDs, and English/Chinese names.
- Final validation: 128 related Python tests pass; related TSX assertion scripts pass; typecheck,
  build, both dead-code gates, and `git diff --check` pass. ESLint passes with five pre-existing Hook
  warnings. Build retains the existing large-chunk advisory.
- No blocker is known. The manager should run fresh Sol/high review, then use the authorized
  commit/push/PR workflow if review passes.

## Issue #355 local review round 1 correction

- Updated: 2026-09-29 EDT. Accepted AC-2 finding F1 is fixed: the active-task stop control now
  passes the selected task display name into the existing confirmation, with task ID fallback when
  the display name is empty. English and Chinese confirmation text interpolate the same target as
  the dangerous action. API route, permission check, cancellation, and stop behavior are unchanged.
- Added an executable `Tasks` DOM regression covering English, Chinese, and empty-name ID fallback.
  Baseline red received `Stop this task?` when the control named `Stop task Rebuild SOA`; green is
  3/3. The complete a11y suite is 6/6.
- Related Scheduled Tasks, task metrics, and task error assertion scripts pass. Typecheck, lint,
  production build, and `git diff --check` pass. Lint retains five pre-existing Hook warnings and
  build retains the existing large-chunk advisory.
- No Escape behavior was added because it belongs to excluded Issue #351 scope. No blocker is
  known. The manager should run a fresh Sol/high review.

## Issue #355 local review round 2 correction

- Applied the TypeSafe Jev `apply_shared_task_target` decision. `TaskCard` now derives one stable
  target from the trimmed display name with task ID fallback, then uses it for view-log and stop
  accessible names and callback arguments. The stop button and its confirmation therefore stay
  identical for empty and whitespace-only names.
- Executable red evidence could not find the required `Stop task task-42` role/name for an empty
  task name. Green coverage now passes empty and whitespace fallbacks plus the existing English and
  Chinese named-task cases: a11y suite 7/7. Typecheck and `git diff --check` pass.
- No #366 or #351 behavior was added. No blocker is known; run a fresh Sol/high review.

## Issue #355 local review round 3 correction

- Applied the Jev `add_targeted_save_name` decision. The Settings search-engine credential save
  IconButton now has a dedicated localized name containing the current engine display name in
  English and Chinese. Existing save logic, disabled state, API call, and permissions are unchanged.
- New Testing Library coverage renders the real Settings search tab, opens the Brave Search
  credential editor, and finds the save control by its localized role/name. Baseline red exposed
  only `Save` / `保存`; green a11y coverage is 9/9. Typecheck and `git diff --check` pass.
- No #366 or #351 behavior was added. No blocker is known; run a fresh Sol/high review.

## Issue #355 required-check repair 1

- Updated the single stale source-contract assertion in `tests/test_tasks_react_source.py` to
  require the AC-2 task target argument and task-ID fallback in the existing stop confirmation.
  Production code was not changed.
- Focused contract test passes 1/1. The complete quality gate passes with 2239 tests passed, 10
  skipped, followed by clean Black, isort, and error-only Pylint checks. The a11y suite passes 9/9
  and `git diff --check` passes.
- Final manager smoke passes in installed Chrome at 390x844 for Tab, Enter, Space, visible focus,
  44px controls, focus recovery, unique test IDs, and English/Chinese names. The disposable Vite
  server was stopped after the run.
- No blocker is known. The manager can proceed with the exact-head required-check workflow.

## Issue #361 — permission-aware logs

- Updated: 2026-09-30. Project AI_actuarial_inforsearch; task branch agent/issue-361,
  based on d4056faed3316074474c53a3ca077187d78c935f.
- Logs.tsx now gates the system-log panel, global controls, and /api/logs/global
  request on logs.system.read. Task-log readers land on expanded task history.
  Registered/operator browser traces had 0 global-log requests; admin retained the
  global log load, search, level filter, and refresh.
- Added client/src/pages/Logs.browser-smoke.mjs with real Chromium request assertions
  for registered, operator, and admin. The backend /api/logs/global permission remains
  logs.system.read; the separate Tasks page already guarded its global-log action.
- Local validation passed: 22 focused Logs/permission tests, 8 backend ops-read tests,
  TypeScript typecheck, ESLint (five existing warnings), production build (existing
  chunk-size advisory), Chromium smoke, and git diff --check.
- Fresh Sol/high local review 1 passed with no acceptance-mapped findings. TypeSafe
  Jev-1.13.0 review coverage probability was 0.88; no findings were supplied.
- Draft PR #386 was opened with Closes #361. This entry records the pre-Ready
  checkpoint; required GitHub checks and the single remote-feedback window remain
  the next lifecycle gates.

## Issue #347 — bounded direct-document AI Explain

- Updated: 2026-09-30. Task branch `agent/issue-347`, based on
  `497d0ea1b941ac1954cd2c5f4b2170d6f716a8e7`.
- Direct-document AI Explain now budgets the complete active-model prompt and
  output reserve, retries once after a context rejection, and persists safe
  failed-turn metadata for Chat History retry. Standard RAG keeps its existing
  request path.
- Focused validation passed: backend 124, React 4, React source contracts 23,
  TypeScript, build, Python formatting/compile, and dead-code checks. Local
  Chrome passed File Detail → AI Explain → Chat → History reload with an
  isolated database and stub provider. Lint passed with five existing Hook
  warnings; the build emitted the existing chunk-size advisory.
- The full `scripts/quality_gate.py` run was manually interrupted after late
  same-Issue edits appeared during pytest collection; it has no final exit code
  and is not a passing result. The late edits were preserved, but their source
  could not be attributed from the worker session; the independent review will
  inspect the complete diff. No out-of-scope source change is visible.
- Next: complete a fresh local review, then proceed through the PR checks and
  the authorized single remote-feedback window.

### Verification update — 2026-09-30

- Third-round fixes are complete. Manager re-ran the focused backend suites:
  114 passed; the two React suites: 5 passed; typecheck, lint, build, dead-code,
  Black, isort, and `git diff --check` passed. Lint reports five existing Hook
  warnings; build reports the existing large-bundle advisory.
- Local Playwright smoke passed File Detail → AI Explain → Chat → History reload.
  The API returned 200, included the canonical file citation, made two stub
  provider calls, and recorded 3,719 prompt tokens + 1,000 output reserve
  within the 8,000-token window. No API failures occurred; one static resource
  returned 404 in the browser console.
- `scripts/quality_gate.py` remains manually interrupted from the earlier run;
  it has no final exit code and is not recorded as passing.
- Round 4, scoped to the accepted `CHAT_PROVIDER_AUTH` UI/History regression, is
  complete. TypeSafe/Judge rejected a request to add provider identity to budget
  logs and accepted only localized, nonretryable failed-turn rendering.
- Manager re-ran the relevant backend selection: 11 passed; both React suites:
  7 passed; typecheck, lint, build, dead-code, and diff check passed. Existing
  five Hook warnings and bundle-size advisory remain.
- Next: finish the fresh fifth local review, then continue the authorized PR
  checks and remote-feedback window.

### Local review limit reached — 2026-09-30

- The cumulative Issue #347 candidate completed 15 fresh Sol/high local review
  rounds. Round 15 did not pass, so the strict issue-to-merge gate stopped the
  task before commit, push, PR, merge, Issue closure, or cleanup.
- The remaining reproduced defect is the production configuration loader's
  `SitesConfigError` path. `query_chat()` catches `ValueError` only, so a missing
  or malformed authoritative production configuration escapes before the real
  user turn, structured `CHAT_PROVIDER_AUTH` response, IDs, History state, or
  guest session cookie are created.
- The final reviewer ran 252 focused Python tests, 14 React tests, TypeScript
  typecheck, and diff check successfully. Real production-loader and exact
  `query_chat()` probes reproduced the remaining failure. TypeSafe marked it
  valid and in scope; the Judge selected the scoped fix.
- The worktree and `agent/issue-347` branch remain intact with all uncommitted
  Issue changes for recovery. No PR exists and Issue #347 remains open.
- Blocker: the configured 15-round review limit is exhausted without the
  required reviewer PASS. A controller or user decision is required before any
  additional repair/review cycle can be authorized.
- Final required CI gate check: `npm run dead-code:symbols` fails because the
  Python symbol gate reports a new `ai_actuarial/config.py | unused variable |
  EXPOSE_ERROR_DETAILS` finding. TypeScript symbols pass. No baseline or source
  change was made for this gate after the review limit was reached.

### Authorized extra round and final gate stop — 2026-10-01

- The user authorized exactly one additional scoped repair and one fresh
  Sol/high review. The worker caught concrete `SitesConfigError` at the existing
  configuration gate, added a real missing-authoritative-config regression, and
  removed the unused `Settings.EXPOSE_ERROR_DETAILS` symbol. The exact
  `dead-code:symbols` check then passed with zero TypeScript/Python findings.
- Fresh review round 16 passed all nine Issue criteria. TypeSafe review coverage
  probability was 0.96 with no findings. Real missing/malformed production
  config, canonical/deprecated Agentic, and FastAPI/Vite/Chrome File Detail →
  Chat → History checks passed.
- The required full `scripts/quality_gate.py` subsequently failed: full pytest
  reported 1 failure, 2,298 passed, and 10 skipped; the failure was
  `test_default_generator_enforces_timeout_and_one_sdk_transport_attempt` in the
  Issue #267 suite. Pylint also reported a new #347-path E1102 at
  `ai_actuarial/api/services/chat.py` (`query_chat`: `generate is not callable`).
- The user-authorized exception required an immediate stop if any required gate
  remained failed. No further fix/review, commit, push, PR, merge, Issue closure,
  or cleanup was performed. Branch and managed worktree remain intact.

### Quality-gate repair authorization — 2026-10-01

- The user separately authorized repair of the two remaining required-gate
  failures, with no additional Sol reviewer and TypeSafe as the completion judge.
- The stale Issue #267 assertion now matches the stable safe upstream-provider
  message while retaining timeout, retry, and one-transport-attempt checks.
  The two direct-document dynamic `generate` calls now pass through a typed
  callable helper, preserving their runtime guards, fallback, and single retry.
- Exact checks passed: Issue #267 target 1/1, chat.py error-only Pylint with an
  empty result, and 66 focused tests. The final full `scripts/quality_gate.py`
  exited 0: 2,299 passed, 10 skipped; Black, isort, and error-only Pylint passed.
- TypeSafe Jev selected `both_complete` with probability 0.94. Local gates are
  now complete; the next authorized step is commit, push, and Draft PR.

### PR #388 checkpoint — 2026-10-01

- Committed the complete Issue #347 candidate as `8cd9a6b` and pushed
  `agent/issue-347`. Draft PR #388 includes `Closes #347`.
- Local publication gates are complete: full quality gate 2,299 passed / 10
  skipped with Black, isort, and error-only Pylint green; dead-code symbols and
  files are green; the final TypeSafe gate-repair judgment is `both_complete`.
- Next: push this status checkpoint, mark PR Ready, wait the required remote
  review window, then evaluate current-head checks and all fetched feedback.

### PR #388 remote-feedback repair — 2026-10-01

- The one Ready-window snapshot found all six checks green and three Copilot
  threads. TypeSafe accepted the chained traceback leak and deprecated 400→503
  misclassification; a focused probe confirmed the ambiguous hardcoded context
  error type.
- The scoped repair removes chained-cause traceback logging from the Agentic
  fallback, preserves deprecated missing-KB validation as 400 while keeping
  missing/not-ready registry states as safe retryable 503, and logs the actual
  caught context exception type.
- Focused tests passed 3/3, relevant backend tests 119/119, and the full quality
  gate passed with 2,301 tests passed / 10 skipped plus clean Black, isort, and
  error-only Pylint. TypeSafe judged all three remote items resolved.
- Next: push the remote-fix commit, resolve the three review threads, wait for
  the new-head CI checks, then merge if every gate remains green.

### Issue #360 review-fix cycle 3 — 2026-10-01

- Fixed accepted F1: catalog-only KB detail now retains catalog editing state (`kb_mode`, chunk profile id/name, embedding identity key) while guest/registered retain the customer projection and task diagnostics remain `tasks.run`-only. KBDetail loads the authorized profile list for catalog managers and omits unset profile/identity values on a name-only save.
- Fixed accepted F2: Chromium RBAC smoke asserts the detail embedding mismatch re-embed button is absent for guest/registered/catalog-only and present for Operator/Admin.
- Added real FastAPI catalog-only create → profile read/detail → name update → chunk binding coverage. Focused tests: 50 passed. Browser smoke: passed for five role shapes.
- Final `python scripts/quality_gate.py`: PASS, 2,307 passed / 10 skipped; Black, isort, and error-only Pylint passed. Evidence is saved under Issue #360 external evidence as `review-fix-3-*`.
- At cycle-3 completion the implementation was uncommitted; it was later committed as `d6aaecb`
  and published in Draft PR #389.

### Issue #366 Review 14 implementation — 2026-10-02

- Completed the accepted mobile target sweep for Database export/filter actions, Tasks
  history/log/pagination controls, Pipeline failures, Settings editor cancellation,
  Knowledge manual rows, and task-log refresh. Pipeline Run controls now receive a
  stage-qualified test id, avoiding duplicates when failed stages are expanded.
- `npm run test:a11y` now includes `FormFields.test.tsx` and
  `SchedulePresetFields.a11y.test.tsx`; the 18-file suite executes both.
- The standalone 390px Chromium form smoke now uses populated failed Pipeline data and
  verifies targets, Tab-visible focus, 200% text, and unique ids/test ids. It also
  measures Database export/filter controls and Settings provider/search Cancel actions.
- No commit, push, PR, merge, or sibling-repository access was performed.

### Issue #366 Review 14 fix validation — 2026-10-02

- Manager independently re-ran `npm run test:a11y` (18 files / 62 tests),
  `npx tsc --noEmit`, `npm run lint` (0 errors; 5 existing hook warnings),
  `npm run build` (pass; existing large-chunk advisory),
  `npm run dead-code:check`, both Chromium browser smokes, and `git diff --check`;
  all passed.
- The forms smoke covered 16 surfaces at 390px, including populated Pipeline
  failures, 44px targets, keyboard focus, unique ids/test ids, and 200% text.
- Review 15 is the final independent review. No commit, push, PR, or merge yet.

### Issue #366 final local review result — 2026-10-02

- Review 15 returned CHANGES REQUIRED on two reproduced gaps: undersized mobile
  targets in Settings, Chinese Knowledge, and File Detail error state (AC3), plus
  visually hidden-only labels on scoped Settings, File Detail, and Markdown
  Conversion fields (AC1). Manager source inspection confirmed both.
- TypeSafe assessed both as valid/in-scope (coverage 0.91); the Judge selected
  `accept_both_and_block` with 0.95 confidence. The configured reviewer did not
  pass within the strict 15-review limit.
- Blocked: no further fix/review cycle or PR preparation. All Issue #366 changes
  remain uncommitted on `agent/issue-366`; sibling repositories were untouched.
- Evidence: external Issue #366 evidence folder, `local-review-15.txt`,
  `local-review-15.typesafe-v2.json`, and `review-15.judge-result.json`.

### Issue #366 Review 15 authorized repair — 2026-10-02

- The user authorized a narrow repair without another independent review. Settings AI
  route add/edit controls, Chinese Knowledge Create KB, and File Detail's not-found
  Back action now use 48px targets. The Knowledge Select all control discovered while
  exercising the same create state also now has a 48px usable target.
- Categories new/category-keyword labels are visible, AI-filter keywords uses its visible
  heading via `aria-labelledby`, and File Detail/Markdown Conversion editors have visible
  associated labels. The standalone browser smoke now opens the Settings add/edit route,
  runs Knowledge in Chinese, checks File Detail's missing-file state, and verifies label
  boxes are actually visible.
- Validation passed: 18 a11y test files / 64 tests; TypeScript; lint with five existing
  Hook warnings only; build with existing chunk advisory; dead-code; both Chromium smokes;
  and `git diff --check`. No commit, push, PR, merge, or sibling-repository access occurred.

#### Review 15 controlled visible-label RED/GREEN evidence

- A reversible probe changed the visible Categories new-category label back to `sr-only`.
  The 390px standalone form smoke then failed its Settings visible-label bounding-box check
  (`width: 1`, `height: 1`) at `forms.browser-smoke.mjs:187`. The exact source was restored.
- A second reversible probe changed the File Detail Markdown and Markdown Conversion tool-model
  labels back to `sr-only`. Their focused a11y tests failed the explicit non-`sr-only` label
  assertions. Both exact sources were restored.
- Restored green checks: focused Settings/File Detail/Markdown Conversion/Knowledge suite
  passed (4 files / 32 tests); full standalone form smoke passed all 17 records at 390px;
  `git diff --check` passed. Raw outputs are in the external Issue #366 evidence folder as
  `review-15-f2-settings-red.txt`, `review-15-f2-editors-red.txt`, and
  `review-15-f2-green.txt`.

### Issue #366 TypeSafe repair gate — 2026-10-02

- At the user's explicit direction, no further independent reviewer was started.
  The same worker repaired the two final findings and the manager reran full gates.
- TypeSafe Judge selected `all_resolved` (probability 0.64; confidence 0.45) from
  the current source inspection, exact 390px smoke assertions, visible-label tests,
  controlled RED/GREEN evidence, and manager validation report.
- The lifecycle script refuses to record a fix or PR because its strict gate still
  requires a configured-reviewer PASS and all 15 review slots are used. No reviewer
  PASS was fabricated; the user explicitly authorized the TypeSafe-only exception.
- PR #390 was published and marked Ready under that instruction. The remote
  monitoring snapshot and follow-up are recorded below. No merge is authorized here.

### PR #390 tracking — 2026-10-02

- Commit `54fef1a` was pushed on `agent/issue-366`; PR #390 was created as Draft
  and marked Ready for review. It closes #366. Related PR #385 for #355 is merged.
- The user explicitly authorized the TypeSafe-only gate after the local review
  limit. TypeSafe selected `all_resolved`; no configured-reviewer PASS was recorded
  or implied. The strict lifecycle script cannot record PR publication without that
  reviewer PASS, so the explicit override and PR URL are retained in its decision log.
- No merge was performed. Next: check current-head CI and remote reviews/Copilot
  comments about 15 minutes after Ready, then disposition only confirmed in-scope items.
- Snapshot at 2026-10-02 09:03 UTC, head `54fef1a`: five checks passed and
  `quality-gate` was pending; no review, inline, or conversation comments were present.
- The formal 15-minute remote snapshot was captured at about 09:17 UTC; see the
  follow-up section below for current dispositions and validation.

### PR #390 remote feedback follow-up — 2026-10-02

- The 15-minute snapshot was captured at about 09:17 UTC on head
  `08f7c9166a4d28f2d97ebd2eb95d6ac3180f3146`. Five required checks passed; `quality-gate`
  failed on a stale `RagIndexForm` source assertion. The same worker updated the assertion,
  and its focused test passed (1 test); the correction is not yet committed or pushed.
- Copilot left ten unresolved inline threads, one review summary, and no PR conversation
  comments. The Issue has one older coordination comment; related PR #385 for #355 is merged.
- The same Issue worker classified every remote item against #366’s acceptance criteria
  and applied the confirmed in-scope fixes. No independent reviewer was started.
- The old checkpoint saying PR creation was still pending has been corrected. The remote
  feedback has since been assessed by TypeSafe and fixed by the same worker; see the final
  completion entry below. No merge is authorized.

### PR #390 required-check repair — 2026-10-02

- The only failed `quality-gate` check at head `08f7c9166a4d28f2d97ebd2eb95d6ac3180f3146`
  was a stale source assertion in `tests/test_tasks_react_source.py`. It expected the old
  two-prop `RagIndexForm` invocation, while Issue #366 correctly adds the optional
  `errorDescribedBy` accessibility prop.
- The assertion now verifies the complete current invocation. Focused verification:
  `python -m pytest tests/test_tasks_react_source.py::test_tasks_page_restores_rag_indexing_task_form`
  passed (1 test). No commit, push, or PR mutation was performed; wait for the manager's
  remote-review snapshot before acting on any Copilot feedback.

### PR #390 remote-feedback coverage follow-up — 2026-10-02

- Added direct regression coverage for File Detail stale mutation errors, the short File Detail
  category target, and Scheduled Task delete-confirm Cancel. Reversible RED probes failed as
  expected; restored focused RTL/axe passed (2 files / 11 tests), the full standalone 390px
  form smoke passed all 17 records, TypeScript passed, and `git diff --check` passed.
- No commit, push, PR mutation, or sibling-repository access occurred. The manager-owned status
  history correction remains outside this worker's code changes.

### PR #390 remote-feedback repair and TypeSafe completion — 2026-10-02

- The remote TypeSafe assessment accepted seven in-scope AC2/AC3 findings and rejected three
  out-of-scope comments. The same Issue worker fixed the seven findings and the stale source
  assertion that caused the prior `quality-gate` failure; no independent reviewer was started.
- TypeSafe Judge case `issue-366-pr-390-remote-fix-completion` selected `all_resolved` at
  09:44 UTC (probability 0.81, confidence 0.71). Its evidence packet and result are saved in
  the external Issue #366 evidence folder. The explicit user-authorized decision is recorded
  in the append-only lifecycle decision log; no reviewer PASS was fabricated.
- Current-patch validation passed: `npm run test:a11y` (18 files / 70 tests), TypeScript,
  lint (0 errors; five existing Hook warnings), build (existing chunk advisory), 390px Chromium
  form smoke (17 surfaces), the focused RagIndexForm pytest (1 test), and `git diff --check`.
- Initial remote-feedback fixes were pushed as `62ab38a85a9957896aa47a1a6ae861846c941efb`.
  On that head, five required checks passed and `quality-gate` failed only on Black formatting
  in `tests/test_tasks_react_source.py`; the test suite completed. The same worker made the
  one-line formatting correction. Manager reruns of Black, the focused pytest, and
  `git diff --check` passed. The correction was pushed as `e46ef973d5b3acce8600e4c89d4b552a8878be2a`;
  all six required checks then passed, including `quality-gate` (8m33s).
- All ten fetched inline threads now have written dispositions and are resolved; the required
  post-resolution query reported zero unresolved threads. No new feedback fetch or review was
  started. This project-status entry records the code-head check result; the follow-up commit
  contains only this tracking update. No merge is authorized.

### Issue #363 implementation — 2026-10-02

- On `codex/issue-363-prod-meta-docs`, production now omits native FastAPI docs,
  detailed health requires `logs.system.read`, and migration diagnostics use that
  permission only in production. Public `/api/health` remains unchanged.
- Regression coverage passed for development/test docs plus production anonymous/admin
  behavior (10 entrypoint tests); the related auth and canonical-role suites passed
  (34 tests), and the migration-caller suite passed (279 passed, 7 skipped).
  Independent gpt-6-sol/high review and TypeSafe coverage both passed. PR/merge
  lifecycle state is tracked in the external Issue #363 lifecycle evidence.

### Issue #353 verification blocked — 2026-10-02

- The reviewed Caddy changes remain on `codex/issue-353-csp-security-headers`. Fresh reviewer and TypeSafe review passed after one fix cycle. The final-tree focused deployment suite had previously passed 12 tests before the host restart.
- The later full `python scripts/quality_gate.py` run collected 2,323 tests but ended incomplete; the raw log shows progress only through 99%, then `python -m black --check ai_actuarial scripts tests config` exited with native code `3221226091` (`0xC000026B`). The outer quality-gate exit code was 2. This is not a formatting result. The report files under `reports/quality-gate` are stale from 19:53 and were not updated by this run.
- Windows Event 2004 at 20:34 reported low virtual memory and listed `python.exe` PID 62068 consuming 98,483,150,848 bytes. Event 1074 recorded an unplanned restart at 20:47; Event 6006 recorded the Event Log service stopping. Microsoft maps `0xC000026B` to `STATUS_DLL_INIT_FAILED_LOGOFF`, consistent with process startup during shutdown. No matching Python/Black Application Error records or current-run dump were found.
- After restart, the changed-file Black check passed. A focused deployment pytest rerun reported 8 passed and 4 Docker-dependent failures because the Docker Desktop engine pipe was unavailable. Docker Desktop was started once, but `docker info` still could not connect. Current samples showed about 11.7 GB free physical memory and 19.6 GB free virtual memory; the prior test process peak working set is unavailable because it exited.
- The full gate was not rerun after the low-virtual-memory event. Production AC-4 and AC-8 also remain unverified, so no commit, PR, deployment, or merge was made. Resume after Docker is available and the test host has enough commit-memory headroom for the full gate; capture production Caddy dump/mount/SHA and rollback evidence before any production operation.
- Raw failure output, resource events, and stale report copies are saved in the external Issue #353 evidence directory.
- The post-restart focused pytest updated ignored `.coverage` and `htmlcov` outputs around 21:09; they describe that focused run, not the incomplete full suite.

### Issue #353 grouped quality-gate recovery — 2026-10-02

- Docker recovered at version 29.8.1; the final-tree focused deployment suite passed all 12 tests.
- Ran all 130 discovered test files in 26 sequential pytest groups of five with coverage appended. All 2,323 collected items completed: 2,313 passed, 10 skipped, 0 failed, 0 errors. The combined coverage report is 82%; the summary and logs are stored in the external Issue #353 evidence directory.
- Full static components passed separately: Black checked 269 files with no changes, isort exited 0, and pylint returned an empty error list. The single-process scripts/quality_gate.py run remains incomplete and is not reported as passed.
- Production AC-4 and AC-8 remain blocked pending the live Caddy dump/matcher/mount/deployed SHA, production HTTP/browser evidence, and verified rollback evidence. No commit, PR, deployment, or merge was made.

### Issue #353 Draft PR opened — 2026-10-02

- Draft PR #397: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/397
- Commit e822b656 contains the reviewed Caddy/header changes and regression tests. Full pytest coverage passed in 26 sequential groups (2,313 passed, 10 skipped); Black, isort, and pylint component checks passed separately.
- The single-process scripts/quality_gate.py run remains incomplete; its components are documented in the PR and external delivery evidence.
- PR stays in draft for the user's real-machine validation. Production AC-4/AC-8 evidence and rollback validation remain pending. Do not merge or deploy until those results are reviewed.

### Issue #353 PR #397 Linux CI repair — 2026-10-02

- The 15-minute PR check found five passing checks and one failing quality-gate check. Its pytest run had 2,320 passing tests and three failures, all parameterizations of the new Caddy request test. In GitHub Actions Linux Docker, the Caddy container could not resolve host.docker.internal, so requests returned 502.
- Fixed the test setup to add Docker's host-gateway mapping only on Linux. Windows Docker Desktop keeps its built-in host.docker.internal route.
- Local validation passed: tests/test_deployment_config_source.py (12 passed), Black (1 file unchanged), isort (exit 0), and pylint (empty error list).
- The PR review query returned no reviews, inline threads, or conversation comments. PR #397 remains Draft while the CI reruns and the user performs real-machine validation; production AC-4/AC-8 and rollback evidence remain pending.

### Issue #353 PR #397 required checks passed — 2026-10-02

- After the Linux Docker host-gateway test fix, commit ae71cb8 passed all six GitHub CI checks. The quality-gate completed in 9m33s; the other five checks also passed.
- The 15-minute PR feedback query returned no reviews, inline threads, or conversation comments.
- PR #397 remains Draft for the user's real-machine validation. Production AC-4/AC-8 evidence and rollback verification remain pending; no merge or deployment was performed.
- This entry records the result for code commit ae71cb8; this status-only update does not change the tested code.

### Issue #362 implementation — 2026-10-04

- On `codex/issue-362-status-i18n-r2` at baseline `375cb901`, added one shared
  frontend enum label resolver and role-gated collapsed diagnostics. Knowledge,
  Tasks, Logs, Users and Settings now use it for their scoped status, task type,
  item error, role, knowledge base mode/profile/reason and credential values.
  Existing bilingual `tasks.type.*`, role, KB reason, mode/profile and credential
  status translations are reused; API/backend enums were not changed.
- The targeted regression was red on baseline: `completed` was untranslated and
  the unknown `private_type` appeared in visible text and a `data-testid`. The
  focused bilingual semantic suite now passes. The Chromium Logs smoke passes
  for registered/operator/admin, confirms unknown values are hidden from
  registered users and operator/admin diagnostics stay collapsed, and verifies
  Chinese-to-English switching for known and fallback labels.
- Focused Vitest passed (4 files / 8 tests); TypeScript passed; lint had zero
  errors and five pre-existing React Hook warnings; build passed with the
  existing large-chunk advisory; both dead-code gates and `git diff --check`
  passed. Changes remain uncommitted in this worktree; no push, PR, merge or
  production access was performed by the implementation worker.
- Same-shaped UI sites inspected: scheduled task types and PipelineBaton task
  status/error code displays are included. `TaskMetrics` uses task enums only
  for calculations; Categories filters KB reasons against the known reason
  list before translation; task prose summaries and arbitrary system log lines
  are not enum label surfaces, so these remain unchanged. At the initial implementation checkpoint, Issue #362 remained OPEN pending independent review.
- Review-1 fixes: `FilterBar` now uses the shared status/type resolver and a
  localized All Status label while retaining API option values; `queued`,
  `stopping`, `embedding_generation`, and `ready_data_build` have bilingual
  labels and semantic coverage. Logs diagnostic summaries stop click bubbling;
  Chromium smoke expands both details and verifies no task-log modal opens.
- Follow-up checks passed: focused Vitest (5 files / 9 tests), TypeScript,
  lint (0 errors, 5 existing Hook warnings), production build (existing chunk
  advisory), dead-code checks, and `git diff --check`. The real Logs Chromium
  smoke passed. An optional second-page `/tasks` Chromium navigation did not
  complete with this smoke's API fixture; FilterBar labels/options are covered
  by the focused component test. No API/backend enum changes; no commit/push/PR.
- Review-2 fixes: token creation role choices now use the shared bilingual resolver while retaining canonical `registered`, `premium`, `operator`, and `admin` values; the Settings Chromium smoke checks both locales and submitted values. Pipeline Baton summary and stage status now use the shared status resolver, including bilingual `idle` and `completed_with_errors` labels, with unknown raw codes visible only in collapsed Operator/Admin diagnostics outside the stage toggle button. Semantic tests cover both locales, fallback, and diagnostic gating; Chromium smoke confirms disclosure interaction does not toggle the stage or open the task-log modal.
- Round-2 validation passed: focused Vitest (3 files / 9 tests), Settings and Pipeline Baton Chromium smokes, Logs Chromium smoke, TypeScript, lint (0 errors; 5 existing Hook warnings), production build (existing large-chunk advisory), both dead-code gates, and `git diff --check`. Work remains uncommitted; no API/backend enum changes and no commit/push/PR.
- Review-3 fix: Pipeline Baton now sanitizes structured launch-failure summaries on the latest-failure, stage-failure, and task-error surfaces. The real `index_launch_failed` response renders a bilingual message that retains the knowledge-base ID; its error code is included in the shared mapping. Operator/Admin can expand collapsed diagnostics to inspect the original code and response summary, while customer roles see neither raw value. No API fields or backend behavior changed.
- Added bilingual component regression coverage using the #348 response shape (`latest_failure` plus `stages[].failures[]`) and extended the real Pipeline Baton Chromium smoke. It passed for registered/operator/admin, checks Chinese-to-English switching, customer redaction, diagnostic disclosure, and confirms clicking diagnostics does not toggle a stage or open a task-log modal. Focused Vitest passed (2 files / 5 tests); typecheck, lint (0 errors / 5 existing Hook warnings), build (existing chunk advisory), dead-code checks and diff check passed.
- Review-4 fix: existing API token list badges now use the shared bilingual role resolver for canonical groups while preserving stored API values. Historical group codes fall back to `Unknown status` / `未知状态`; raw values are hidden from customer roles and available to Operators/Admins only in collapsed diagnostics. The create form and submitted `group_name` values are unchanged.
- Added semantic coverage for all four canonical stored roles in both locales, historical-code gating, and preserved create values. The Settings Chromium smoke now asserts role badges for registered/premium/operator/admin in both locales, toggles language in the real page, and verifies a legacy code is safely diagnosed while collapsed. Focused Vitest (1 file / 7 tests), Settings Chromium smoke, typecheck, lint (0 errors / 5 existing Hook warnings), build (existing chunk advisory), and diff check passed.
- Review-5 fix: Pipeline Baton now recognizes only the four listed Ready Data prefixes (`build_failure`, `publish_failure`, `stale_snapshot`, `invalid_selector`) at the start of a structured failure summary when the projected error code is empty. Customer surfaces show a bilingual generic Ready Data failure message; source summaries remain available only in collapsed Operator/Admin diagnostics. Other prose is not sanitized. API/backend values were not changed.
- Added bilingual semantic coverage for all four prefixes using empty `first_error_code` projection fields, plus a Chromium fixture for `build_failure` covering registered/operator/admin fallback, language switching, collapsed diagnostics, and interaction. Focused Vitest passed (1 file / 4 tests), Pipeline Chromium smoke, typecheck, lint (0 errors / 5 existing Hook warnings), build (existing large-chunk advisory), dead-code gates, and diff check passed.
- Independent local review 6 passed all six Issue acceptance criteria with no accepted findings; TypeSafe assessment also returned no findings. The reviewer independently passed 24 focused frontend/caller tests, 25 backend Pipeline tests, typecheck, diff check, and real Chromium smokes for Knowledge, Tasks/Pipeline, Logs, Users, and Settings.
- Final manager validation passed: Vitest (8 files/24 tests), Pipeline Baton pytest (25), typecheck, lint (0 errors; 5 existing warnings), production build (existing chunk advisory), dead-code checks, and Logs/Settings/Pipeline Chromium smokes. Issue #362 remains OPEN; PR #400 has moved from Draft to Ready for review after all required checks passed.
- Remote-feedback F1 fix: added shared bilingual `error_code` labels for
  `orchestration_error`, `invalid_index_result`, `ready_launch_failed`, and
  `error`; API enum values remain unchanged. Regression was red before mapping
  (`orchestration_error` resolved to `Unknown status`) and green afterward.
  Focused Vitest passed (3 files/7 tests); Pipeline Chromium smoke passed for
  registered/operator/admin with all four labels in Chinese and English.
  Manager revalidation passed typecheck, lint (0 errors; 5 existing warnings),
  production build (existing large-chunk advisory), and diff check. PR #400
  remains Ready for review. The fix was committed and pushed as
  `95c52029ee0fc85bc04f4001a04ef94224918db7`; all six required checks passed
  on that head and all four inline review threads are resolved. F2-F5 were not
  implemented. Merge is pending final head verification.

### Issue #364 runtime provenance — assessment — 2026-10-04

- Issue #364 is still OPEN. The assigned worktree is `codex/issue-364-runtime-provenance`, based on current `origin/main` `24a07096ba597c4835d354d5d576618d4de12d93`; startup status was clean.
- Pre-implementation evidence confirms API and metrics still report fixed `0.1.0`; Docker labels and build args already carry SHA/time/source; `deploy_update.sh` currently rebuilds only the API before writing the release record; Vite produces the static frontend in `dist/public`; and protected detailed health/metrics routes already require `logs.system.read`.
- Selected `complex` / `senior_worker` because the accepted change spans the API, Vite/admin UI, OCI digest handoff, Compose, deployment/release recording, and cross-layer tests. Validation will cover safe public/protected projections, build-time frontend identity and mismatch reporting, post-build digest and release-record consistency, local Compose/deploy flows, frontend build, and focused plus repository checks.
- Router evidence needs an explicit correction: this repository's AGENTS.md specifies `gpt-6-sol/high` for a complex senior worker, while the initial per-Issue runtime snapshot selected `gpt-6.1-sol/high`. The first agent using the latter was interrupted before editing; the implementation worker must use the AGENTS.md route. Do not change shared runtime preferences to resolve it.
- Related Issue #313 remains OPEN as a separate production config rollout. #364 will expose only a safe config hash/source identifier and will not perform #313's migration. Production canary, rollback, writes, deployment, and data cleanup remain prohibited; any live-only acceptance evidence must be reported as pending rather than claimed.


### Issue #364 runtime provenance — non-production implementation checkpoint — 2026-10-04

- Project `AI_actuarial_inforsearch`, branch `codex/issue-364-runtime-provenance`,
  baseline/current uncommitted HEAD `24a07096ba597c4835d354d5d576618d4de12d93`.
  Only this issue worktree was edited; sibling repositories remain off-limits.
  No production writes/configuration/credentials, deployment, backup/restore,
  cleanup, canary/rollback, commit/push/PR/merge were performed by the worker.
- Added validated build-info ENV projections with one `release_manifest_id`,
  public short SHA/release and authenticated `logs.system.read` details/metrics.
  Config provenance reuses the current authoritative file contract and exposes
  only logical source/hash. Metrics no longer returns a credential-bearing
  storage connection URI. #313 configuration rollout remains separate.
- API labels/ENV and Vite/static frontend share the release ID. Production
  frontend rebuilds in its image and serves `/opt/frontend`; Settings gives a
  bilingual nonblocking mismatch/unavailable warning. Deployment builds both
  images, verifies matching labels in release-record, reads digests after build,
  and passes the API digest at runtime before starting both services.
- Final focused validation passed: 57 Python tests (7 provenance tests), 3 Vitest
  cases, frontend build, Chromium English/Chinese identity mismatch/return
  fixture, typecheck, lint (4 existing warnings), all dead-code gates, actual
  frontend Docker build and container artifact checks, API Dockerfile build
  check, actual Compose fixture config, and diff check. Full Vitest: 119 pass,
  one unchanged FilterBar task-label failure.
- Full `python scripts/quality_gate.py` exited 1: the worker terminated its own
  pytest child after whole-process RSS reached 24,035,385,344 bytes during an
  unchanged #263 call. Full pytest is incomplete; no full-suite PASS is claimed.
  Whole-repo Black (273 files), isort and Pylint all passed with zero findings.
  The precise #263 test independently passed in 1.88 seconds, exit 0; this does
  not prove a full retry is safe. Manager paused further full/#263 testing under
  resource limits; code and fixtures are fixed for review.
- Complete report/logs: `reports/issue-364-evidence/worker-implementation.md`.
  Production observations/canary/rollback remain unverified gates. Next: fresh
  independent review and manager decision on full-suite/CI validation before
  the authorized PR lifecycle. All scoped code remains uncommitted.

### Issue #364 runtime provenance — review round 1 — 2026-10-04

- Implementation worker: `/root/issue_364_manager/issue364_worker_corrected` (`gpt-6-sol/high`), completed. Manager: `/root/issue_364_manager`. Fresh reviewer: `/root/issue_364_manager/issue364_fresh_reviewer_1` (`gpt-6-sol/high`), completed.
- Reviewer report: `reports/issue-364-evidence/reviewer-round-1.md`. Result: PASS, no actionable findings. It independently inspected the complete tracked/untracked diff and relevant tests.
- TypeSafe `jev-latest` assessment succeeded (`jev-1.13.0`): review-summary coverage probability 0.96, no candidate findings. Input is `reports/issue-364-evidence/typesafe-review-round-1-input.json`; output is the ignored project-local `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-364-typesafe-review.json`.
- Reviewer bounded checks: Issue #364 Python 7/7, BuildInfo Vitest 3/3, auth/entrypoint 2/2, `git diff --check` passed. Worker final focused suite: Python 57 passed, frontend 3 passed, typecheck/build/Compose/frontend Docker/browser smoke and static checks passed as detailed in `reports/issue-364-evidence/worker-implementation.md`.
- Full `python scripts/quality_gate.py` remains incomplete/exit 1: the worker stopped its own pytest process after aggregate RSS reached 24,035,385,344 bytes around the existing #263 test; full pytest did not pass. Full Vitest has the separately documented pre-existing FilterBar task-label failure (119 passed, 1 failed). No rerun was started.
- No production deployment, canary, rollback, or #313 configuration rollout occurred. Those production acceptance items remain UNVERIFIED and are not claimed as passed.
- Review-cycle lifecycle state was not backfilled: the earlier external state file is left untouched under the project boundary, and historical transitions will not be fabricated. This note plus immutable agent reports, Git state, and TypeSafe result provide current in-repository evidence. The incomplete full gate and unverified production acceptance remain merge blockers; after focused validation and local review PASS, manager may prepare a PR for independent GitHub CI/review under the user's existing authorization.

### Issue #364 runtime provenance — Draft PR opened — 2026-10-04

- Committed and pushed scoped implementation as `0bbf110b7409317b26aee8c414737ec92b5dcd5b` on `codex/issue-364-runtime-provenance`.
- Draft PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/403 (`Closes #364`). PR #403 is intentionally kept Draft. GitHub check `dead-code-files` was pending at initial observation; other check jobs had not yet appeared. Worktree was clean after push.
- No deployment/production action occurred. Do not merge while the full required CI result is unknown/incomplete or production canary/rollback acceptance remains unverified and unauthorized.

### Issue #364 runtime provenance — initial GitHub CI and feedback check — 2026-10-04

- Initial GitHub CI completed on PR #403 HEAD `039167624d376eaf85d4b126849d5b0c741879c7`: `quality-gate` PASS (9m43s), `frontend-check` PASS, `python-smoke` PASS, `dead-code-files` PASS, `dead-code-symbols` PASS, `office-conversion-smoke` PASS.
- At the approximately 15-minute check after Draft PR creation, pull request reviews, PR/Issue comments, and inline review threads were all empty; unresolved thread count was 0. The PR remains Draft, so Ready-for-review remote-feedback timing has not started.
- Local full quality gate remains recorded as incomplete due to resource termination; GitHub CI is the independent full-gate result for its current HEAD. Production canary/rollback and #313 rollout remain unverified and not authorized. No merge or production action.

### Issue #364 runtime provenance — latest PR head checks — 2026-10-04

- After the project-status PR note commit, PR #403 head `6bf4fa574b107af62a8bf0121a3cfad0412c9999` completed all required GitHub checks successfully. `quality-gate` passed in 9m41s; frontend-check, python-smoke, dead-code-files, dead-code-symbols, and office-conversion-smoke also passed.
- PR #403 remains Draft/OPEN. Initial review/comment/thread fetch was empty. Ready-for-review timer has not started. Worktree is clean at the recorded checked commit.
- No live production canary, rollback, deployment, or #313 configuration rollout was authorized or performed; no merge.

# Issue #313 no-op Settings save preflight — 2026-10-05

- On `codex/issue-313-noop-save` in the managed Issue #313 worktree. Only this
  repository was accessed; sibling repositories, production writes/deployments,
  production credentials/data, and cleanup of backups were out of scope.
- `update_ai_models_config` now loads model discovery only when a submitted
  provider/model differs from its saved value. Unchanged legacy models can
  round-trip during discovery outages; changed routes retain discovery checks.
  Settings omits `credential_id` on a no-op edit when the saved credential has
  `credential_error`, while an explicit empty string still clears it. Weekly
  route inheritance and prompt/runtime settings are unchanged.
- Focused Python validation passed: `python -m pytest
  tests/test_fastapi_ops_write_endpoints.py tests/test_issue_267_weekly_explanations.py
  tests/test_settings_react_source.py --no-cov -q` (66 passed). Focused Settings
  Vitest passed (19 tests), `npm run typecheck`, focused ESLint, Black, isort,
  and `git diff --check` passed. `npm ci --no-audit --no-fund` was used to
  install locked dependencies in this worktree because node_modules was absent.
- Implementation remains uncommitted for independent fresh review. No PR,
  production operation, or production data access occurred.

- Follow-up review added the effective-default route case: when persisted
  `provider`/`model` are absent, the legacy GET defaults round-trip without model
  discovery and without materializing those fields. The Python focused suite was
  rerun after this fix: 67 passed across ops write endpoints, Weekly explanation
  behavior, and Settings source guards. Black, isort, and `git diff --check` pass.

- Follow-up: `/api/config/ai-routing` now runs static model capability validation
  only when the effective provider or model changes. It uses route defaults for
  comparison and preserves missing route sections on a no-op save. Regressions
  prove an existing Chat route using an embeddings-only model can round-trip,
  changing it to another incompatible model still returns 400, and default
  routes stay unmaterialized. Final focused Python suite: 69 passed; Black,
  isort, and `git diff --check` passed.

- Fresh-review fixes: AI routing comparison now treats explicit `null`/empty
  provider/model fields as the runtime GET defaults, preserving an unresolved
  credential ID on a no-op round-trip and avoiding a false indexed-embeddings
  rebuild. Settings now shows routes with `credential_error` even when
  `configured` is false; unchanged save omits the unresolved ID. Regressions
  cover real GET→POST for Chat null fields and Embeddings empty fields with an
  indexed KB, as well as the configured-false UI row/edit/save flow. Final
  focused validation: Python suite 70 passed, Settings Vitest 19 passed,
  TypeScript and focused ESLint passed; Black/isort/diff checks passed.

- Second Sol review follow-up: TypeSafe Jev adjudicated the credential-default
  round-trip finding as `fix` (P(fix)=0.97, confidence 0.96). Settings now uses
  existing `raw_config` presence to distinguish an explicit credential from a
  provider's resolved default. No-op and model-only edits omit inherited
  credentials; explicit selection sends the ID and explicit clearing sends an
  empty string. The configured-false credential-error route remains visible and
  editable. Added Vitest coverage for omission, explicit selection, explicit
  clearing, and unresolved route editing. Final checks: Python focused suite
  70 passed; Settings Vitest 22 passed; typecheck, focused ESLint, Black,
  isort, and `git diff --check` passed.

- Third fresh-review scope decision: Jev chose `reject_scope` (probability 0.99,
  confidence 0.98) for clearing legacy `provider_credential_id`. That behavior is
  outside Issue #313's no-op round-trip and credential-preservation acceptance
  criteria and predates this change, so no code was broadened.

- Canary-precondition scope decision: Jev chose `synthetic_canary` (probability
  0.97, confidence 0.96). Keep the UI change out of scope; if a browser canary
  route is hidden, use only an isolated canary DB with a synthetic default
  provider credential matching the copied route identity, a fake secret, and
  network egress disabled. Never copy the production credential DB.

- Follow-up: Jev selected `fix` for the legacy chatbot `llm_provider` no-op drift
  (probability/confidence 1.00). `update_ai_routing` now compares against the
  existing runtime resolver, preserving unresolved credential identity when a
  GET-resolved DeepSeek route is posted unchanged. Changed provider behavior is
  covered and remains active. The focused Python suite passed (71 tests).

### Issue #313 application prerequisite — PR #404 review gate — 2026-10-05

- Project `AI_actuarial_inforsearch`, branch `codex/issue-313-noop-save`;
  application source commit `cccd3fcbdbf0822ba2fabe9fb85751561f0d4349`.
  PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/404.
  The PR references #313 without closing it because the operational canary,
  rollout, provenance, observation and rollback acceptance remains open.
- Fresh independent `gpt-6-sol/high` review completed with PASS. Final focused
  validation was 71 Python tests and 22 Settings Vitest tests, plus typecheck,
  focused ESLint, Black, isort and diff check. All six GitHub CI jobs passed on
  the application source commit, including the full quality gate.
- PR opened Ready at 17:29:17 UTC. The 17:46 UTC remote-feedback check found
  Copilot review `5418335718` recommending approval with no findings, no other
  feedback and zero inline threads. No correction was requested. The generic
  suggestion to install a review skill was outside the acceptance criteria.
- TypeSafe `jev-latest` resolved to `jev-1.13.0`: final local review-summary
  coverage 0.94 and remote review-summary coverage 0.83, both with no candidate
  findings. Inputs/results are preserved in the project-approved ignored
  `.codex-worktrees/issue-313-noop-evidence` directory outside this worktree.
  Historical lifecycle records were not fabricated or backfilled. No message
  was sent to another task during this heartbeat.
- This status-only commit must pass required GitHub checks before merge; the
  remote-feedback timestamp is retained. The fixed application source SHA above
  is available for an isolated server canary build, but no new image digest or
  server-side acceptance is claimed. Use an exact production config copy, an
  independent v15 DB, synthetic credentials only when required, blocked egress,
  real auth/CSRF and unchanged Settings save followed by canary restart/recreate.
- No production write, deployment, service restart or data/backup cleanup was
  performed. This historical checkpoint was superseded by controller-confirmed #313
  acceptance at 2026-10-08 06:31 UTC. #364/PR #403 closeout is now in progress;
  #364 production canary/rollback remain an independent authorization gate.

### Catalog settings and task error file links — 2026-10-08

- Complex implementation tier: three user-requested surfaces cross Catalog
  scheduling, Settings state, task history persistence/API permissions, and
  FileDetail request identity. Work is on `codex/catalog-settings-error-links`
  in the isolated worktree. Only this repository was accessed; siblings,
  production writes, credentials and deployment are out of scope.
- Catalog hides the first-candidate control/statistic while new tasks submit
  `scan_start_index=1`; existing settings-mode values, filters, targets and
  candidate count remain. Settings runtime flags use a 44px semantic switch
  target and remain local until the existing save action. Task errors resolve
  file URL hashes to unique active numeric IDs, persist those IDs through
  normalization/finalization, and re-resolve them on authorized API reads;
  FileDetail loads by ID before issuing requests with the authorized URL.
  No producer traversal, success-counting or schedule logic was changed.
- Focused checks passed: `python -m pytest
  tests/test_issue_368_task_item_errors.py tests/test_fastapi_read_endpoints.py
  tests/test_tasks_react_source.py tests/test_file_detail_react_source.py -q`
  (72 passed); Vitest for CatalogForm, TaskErrors and Settings.tokens (11 passed).
  The controller's mocked browser smoke passed at 390px and 1280px. The parent
  also reports typecheck, lint, build and dead-code gates passed. The shared
  read-only DB had no rows in `files`, so no production file-ID examples were
  claimed as verified. Implementation remains uncommitted for fresh review.
- The controller-owned `client/src/pages/tasks/CatalogSettingsErrors.browser-smoke.mjs`
  is untracked in this worktree and was not edited by the implementation worker.

- Fresh independent `gpt-6-sol/high` review PASS with no accepted findings; reviewer independently passed 72 Python and 11 Vitest cases. Stable Chromium smoke rerun passed at 390px/1280px. Black repair was format-only with unchanged ASTs. Full local quality gate is running; controller will publish the tested branch and check remote feedback about 15 minutes after PR creation. No merge or deployment is authorized.

### PR #403 main conflict resolution — 2026-10-05

- Branch `codex/issue-364-runtime-provenance` merged `origin/main`
  `4cffa39677a124b5446328038d22bce2b653d8a1`. The sole manual conflict was
  this append-only status file; both #364 and #313 histories were retained.
  Settings code merged automatically, preserving BuildInfo and no-op credential
  handling. No additional application behavior was changed.
- Focused integration checks passed: 78 Python tests covering build info,
  Settings writes, Weekly behavior and source guards; 25 Vitest tests covering
  BuildInfo and Settings credentials; TypeScript typecheck and staged diff check.
- Pre-existing uncommitted status notes were backed up and stashed separately;
  they are excluded from this merge commit and will be restored after push.
- PR #403 is currently Ready/OPEN. This conflict repair does not satisfy pending
  #313 operational acceptance or authorize #364 merge/canary/production rollout.
  No production action was performed; new-head GitHub CI must finish separately.

### Issue #364 / PR #403 closeout — 2026-10-08

- Assigned branch `codex/issue-364-closeout`, isolated worktree `issue-364-closeout`.
  Manager integrated old PR head `46b2248` into main baseline `381ac1d`; only
  this append-only status file conflicted. Both main and old PR histories remain.
- Same complex Sol/high worker; three reproduced Copilot findings and AC5
  manifest-versus-config digest correction are in scope. Production writes,
  canary/rollback and sibling repositories are outside worker authorization.
- Regression-first checkpoint: 8 closeout cases failed on the old PR behavior.
  Implementation and focused verification are in progress. Lifecycle commit,
  push and GitHub actions belong to the manager.

### Issue #364 / PR #403 — final local review snapshot — 2026-10-08

- Integrated old PR head `46b2248` into baseline `381ac1d`; the sole status-file conflict is resolved and both histories are preserved. Final code changes remain uncommitted in `codex/issue-364-closeout`.
- Final focused Python suite: 50 passed, with three existing SWIG deprecation warnings. Native local Docker Compose + Buildx default-provenance rehearsal passed and recorded actual API/frontend manifest digests `sha256:05a5d7194a0e4eabc27b210b73ed681e596562d73d48f7b17a12424339f0635d` and `sha256:c286d33c64bfbaa8b2756e4a8c22037312942670cc0919ddf857b1cbd2ed4687`; optional config digest was absent and honestly recorded as unknown. Frontend build, typecheck, lint, 3/3 BuildInfo tests, bilingual browser smoke, dead-code/style checks and `git diff --check` passed.
- Fresh independent gpt-6-sol/high review round 2 passed with no accepted findings. Jev 1.13.0 TypeSafe assessment returned no findings; its review-summary coverage probability was 0.94. The sidecar records one verified historical review plus this completed current review; no lifecycle timestamps or feedback fetches were fabricated.
- Final-head GitHub required checks and isolated production-host paired-release canary/rollback remain pending. The local rehearsal is not production evidence. No live production deployment, restart, config write, or database write was performed.
- Detailed logs and review artifacts are retained at `C:/Project/AI_actuarial_inforsearch/.codex-worktrees/issue364-closeout-evidence`. The cross-store server import path remains to be validated before any isolated host canary; server is classic overlay2 while local builder uses the containerd store.

### Issue #364 / PR #403 — final acceptance repair — 2026-10-08

- Final independent review reproduced one AC5/AC8 gap: raw Bake metadata may omit config digest while classic Docker exposes only the config ID. Earlier isolated R3 canary used separately derived metadata and did not cover that normal deployment handoff.
- Same complex Sol/high worker is repairing only recovery metadata binding, meaningful direct/real-shell regressions and runbook. Native Buildx history content verifies root index/manifest/config hashes before accepting the classic config ID; raw metadata and true OCI digest remain unchanged. No frontend/API runtime changes or live production operation.
- Root's native12-blob chain and default helper four-image checks passed against actual original raw metadata and fresh classic inspect. Full create-release-record/native classic-producer evidence, final focused/static checks, fresh independent PASS and new-head checks remain required. Prior0001 CI/R3 evidence stays historical; no new acceptance or publication is claimed here.
- Final repair checks: focused four-file Python suite56 passed/22.58s with three existing SWIG warnings; Black/isort/Pylint errors-only, CLI help and diff checks passed. Full create_release_record with untouched original A/B raw metadata, default real Buildx content reading and fresh classic inspect passed in an owned local fake-config/DB fixture. Server tiny native-producer compatibility and fresh independent review/new-head checks remain pending; source/tests are frozen for those gates.
- The actual default Docker28/classic producer then exposed config-only metadata (`containerimage.digest == containerimage.config.digest == Id`); its CLI had wrongly accepted that as manifest. The explicit default-driver Docker archive exporter is unsupported. A separately owned, pinned native docker-container builder has now produced real distinct manifest/config IDs, normal raw records and native missing-config-copy checks on the same classic host, with default builder/live container/config identity unchanged. This proves only tiny-producer compatibility, not full application build capacity.
- Narrow follow-up uses a project named docker-container builder with per-command selection and create/reuse/bootstrap failure gates; first creation requires explicit full-build memory/CPU budgets and uses pinned official BuildKit image plus persistent state volume. Recovery rejects config-only digests/root documents. Moby regression-first three expected failures now pass in the21-case closeout subset; extended shell workflow, final focused/static/native replay and fresh review/new-head checks are in progress. No daemon/store/global builder change, live deployment, worker server action, commit or push.
- Final producer-repair focused suite63 passed/33.53s with three existing SWIG warnings; seven static/CLI/shell/diff checks all exit0. Latest recovery SHA25644e1afbf...9b90116 actual classic-host CLI replay passed named original and native missing-config-copy cases; both default Moby config-only cases exit1 with no output record. Owned builder stopped with state/cache retained. Functional source/tests/deploy/docs are frozen for fresh independent review and new-head checks; scratch compatibility and a separate baseline-context off-host build do not establish live/full-app server capacity.

### Issue #364 / PR #403 — final repair PASS — 2026-10-08

- Fresh independent Sol/high review round5 PASS, no in-scope finding; TypeSafe jev1.13 review coverage0.79/findings empty. Cumulative completed5/failed2; prior required Judges retained.
- Final focused63 PASS/33.53s, Black/isort/Pylint/diff/host help/Git Bash syntax checks passed. Named native classic producer and current recovery helper preserve actual OCI manifest/config IDs; actual default config-only producer is rejected before record/startup.
- Offhost complete API/frontend baseline001 Docker build/load succeeded under configured1GiB/1CPU; current helper pairedrecord and4native content proofs passed. Original optional-field validator BLOCK is preserved and corrected by independent postvalidation; no fullbuildpeak/productioncapacity or repairheadbuild is claimed.
- Historical isolated R3 app canary/rollback and new producer/recovery proof cover unchanged runtime behavior. No live cutover; owned builders stopped, state/cache/images retained. Copilot user-disabled. Commit/push and actual new-head6CI remain next delivery gates.

### PR #425 bilingual catalog metadata and Content Hub sync — 2026-10-14

- Complex implementation continues on `fix/bilingual-document-metadata` in the managed worktree. Scope is this repository only; sibling repositories, private DB configuration, live Content Hub synchronization, deployment, and generator/writer process control remain outside this work. No commit or push was made by the worker.
- Catalog metadata now carries complete zh/en packages in nullable `bilingual_metadata_json` through PostgreSQL migration 0003, catalog generation/parsing, incremental backfill eligibility, Storage/API reads and writes, manual language-targeted edits, canonical-category handling, and six JSON-path search fields. Existing legacy metadata fields remain available. Frontend catalog entry points request bilingual output by default; Database and FileDetail display the complete selected package using the global language, fall back as a whole to legacy values, and edit through the selected language only when that package is complete.
- Added `content-hub metadata sync-catalog` as a read-only-Hub / existing-Storage-target operation. It matches exact URL and original file SHA, verifies version/Markdown-variant bindings, fills only missing target fields, emits JSON counters, rejects a target sharing the Hub database, and is documented. No live data sync was run.
- Frontend tests passed: `npm exec vitest run --config ./vitest.config.ts client/src/components/a11y/FileDetailForm.test.tsx client/src/pages/tasks/CatalogForm.test.tsx` (2 files, 12 tests); `npm run typecheck`; `npm run build` (Vite reported the existing large-chunk advisory). Backend targeted catalog runtime tests passed (6 tests); mocked sync scenarios passed (2), including read-only, same-database rejection, source-hash/variant binding, and idempotent rerun. SQLite legacy search and fill-only merge checks passed. CLI `--help`, compileall, Black check, Ruff check, and `git diff --check` passed. No paid model API was called.
- Parent-owned Linux PostgreSQL integration run, final browser smoke for Database/FileDetail language switching and both bilingual Catalog entry points, and fresh independent review remain pending. Current browser-smoke fields: Catalog request uses `output_language: "bilingual"`; language-targeted `/api/files/update` sends `lang: "zh"` or `"en"` only for a complete selected package. Relevant IDs are `button-catalog`, `button-submit-catalog`, `text-catalog-language-mode`, `button-edit`, `button-save`, `input-title`, `input-summary`, and `input-keywords`.
- Focused Linux test command for the parent: `python -m pytest tests/test_bilingual_catalog_sync.py tests/test_file_edit.py tests/test_fastapi_file_mutations.py tests/test_catalog_runtime.py tests/test_content_hub.py -q`. The working tree remains uncommitted for parent review and final verification.

### PR #425 candidate-count regression repair — 2026-10-14

- The controller's Linux PostgreSQL run found that an existing legacy catalog row was counted as a local candidate. `Storage.upsert_catalog_item` stores `sha256` and `pipeline_version`, while the incremental candidate SQL only considered `file_sha256` and `catalog_version`; the newer nullable aliases were therefore mistaken for missing metadata.
- Updated batch count, batch selection, and explicit-URL skip checks to fall back to the legacy SHA/version columns whenever the incremental aliases are null or blank. Bilingual completeness remains an additional predicate only for AI/frontend work, so legacy local catalog rows stay idempotently skipped while AI rows without complete zh/en packages can be regenerated.
- Extended `test_ai_candidates_require_both_language_packages_but_local_contract_does_not` to cover candidate count, batch selection, and explicit-URL skip behavior for a legacy-only row, plus bilingual candidate inclusion. An isolated SQLite smoke passed for legacy alias count and batch selection; Black, Ruff, compileall, and `git diff --check` passed. Windows pytest was not used because this suite requires the controller's isolated Linux PostgreSQL fixtures.
- The previously reported Linux run was 45 passed / 1 failed. Parent should rerun the failing case with `python -m pytest tests/test_file_edit.py::TestFileEdit::test_ai_candidates_require_both_language_packages_but_local_contract_does_not -q`, followed by the same five-file Linux suite before independent review. Source remains uncommitted.

- 主控最终联合验证：Linux原始conftest/真实Git隔离快照/独立PostgreSQL16，上述五文件46/46 PASS。Chrome真实渲染 + API fixture：Database中英标题/摘要/关键词切换，FileDetail选定语言编辑与英文保留、旧单语fallback编辑，FileDetail/Tasks两个Catalog默认双语并无原语言选项，全PASS。fresh独立Sol/high frontend-review-1正在审查；此新范围尚未发布。

### PR #425 frontend review 1 repair — 2026-10-14

- Fresh independent frontend review round 1 had one accepted in-scope finding; cumulative failed frontend-review cycles: 1. No TypeSafe Judge is needed at this point. The controller's five-file Linux PostgreSQL suite (46/46) and browser smoke had passed before this repair.
- Fixed shared-category consistency in both local catalog write paths. When a recatalog changes the canonical category, an existing zh/en package receives the same category while retaining its title, summary, keywords, and other package fields. Hub merge now returns `conflict` without changing fields when nonempty legacy and package categories disagree or zh/en target categories disagree. A consistent existing target category wins; Hub fills only missing package categories and cannot replace a nonempty target category. Added sequence regressions covering both upserts, target disagreements, incoming Hub category disagreement, and repeated sync idempotency.
- Fixed two reproduced check failures: `isort` ordering in `catalog_incremental.py` and `test_file_edit.py`, and the PostgreSQL schema-plan expected migration list now includes `0003_bilingual_catalog_metadata.sql` while retaining an exact version-to-file assertion.
- Direct SQLite sequence tests passed for both catalog upsert paths, category-conflict detection, and fill-only/idempotent Hub merge. `python -m isort --check-only ai_actuarial/catalog_incremental.py tests/test_file_edit.py`, Black check, Ruff, compileall, and `git diff --check` all passed. The isolated Linux PostgreSQL targeted cases and fresh Sol/high review are pending controller rerun. No private DB, external sync, or process control was used; this work remains uncommitted.

### PR #425 GPT-6 fixture and recovery schema compatibility — 2026-10-14

- Applied only test-fixture compatibility updates in `tests/test_gpt6_parameter_compat.py` and `tests/test_production_recovery.py`; no production module or baseline changed. Catalog temperature cases now return a valid bilingual zh/en package with natural-language values and the same canonical `Other` category. Category-confirm cases retain the original `belongs` response. Azure GPT-5 temperature cases use the same valid catalog response, preserving all temperature and token-parameter assertions.
- Production recovery backup and release-record tests now compare recorded schema versions exactly with `POSTGRES_SCHEMA_VERSION`, preserving the backup/release contract checks.
- Directly ran all 16 catalog/category temperature-matrix combinations and both Azure GPT-5 cases (18 total): passed. isort, Black, Ruff, compileall, and `git diff --check` passed. Linux PostgreSQL-backed recovery tests and the full parameter-compatibility file remain for controller rerun. No database mutation, real sync, paid API call, or pipeline control occurred; changes remain uncommitted.
- Follow-up symbol-gate repair: removed the unreferenced `BILINGUAL_FIELDS` constant from `ai_actuarial/bilingual_metadata.py` without adding a baseline or whitelist. `python scripts/dead_code_gate.py python-symbols --report-dir reports/bilingual-metadata/python-symbols-final` passed with 0 baseline findings. Isort, Black, Ruff, compileall, and `git diff --check` remain passing.

### PR #425 review 2 category-consistency repairs — 2026-10-14

- Implemented the two accepted fresh-review findings without changing UI or sync scope. Catalog Storage and incremental upserts now retain existing bilingual packages and their shared category when a run errors, skips, or has no successful canonical category; successful nonempty category updates still synchronize both language-package category values.
- Content Hub metadata validation rejects same-version zh/en category disagreement. Import locks each referenced content version, checks existing sibling categories before writing, and rejects incoming conflicts before any row is changed. The integrated PostgreSQL regression snapshots all Hub tables around a mismatched single-language import against an existing sibling, then verifies matching fill and idempotent repeat.
- Direct SQLite sequence verification passed for both catalog write paths across error, skipped, and empty-category outcomes (6 sequences). Direct validator check passed. Black, isort, Ruff, compileall, `git diff --check`, and Python symbol dead-code gate passed (0 baseline findings). PostgreSQL integration remains for the controller's Linux run; no frontend check was repeated because no UI files changed.
- Changes remain uncommitted on `fix/bilingual-document-metadata`. No private DB access, real Content Hub sync, paid model call, or process control was performed. Controller should run the touched catalog and Content Hub Linux tests, then fresh independent review.

<!-- current-bilingual-review-context -->
### Current bilingual catalog delivery context
Project AI_actuarial_inforsearch; worktree reports/bilingual-metadata-worktree; branch fix/bilingual-document-metadata. Only this repository is in scope; sibling repositories off limits. Website databases and offline Content Hub are separate; sync is explicit. No merge, deployment or formal sync was performed.
Current feature stores zh/en title/summary/category/keywords. Database and FileDetail show/edit selected complete language package with a whole legacy fallback. AI Catalog produces both languages; frontend has no original-language selector. Shared classification and fill-only/version-bound Hub sync retain saved information, errors/skips retain existing packages, and old local/legacy calls remain valid including opaque raw category text. Canonical display/category normalization belongs at rendering, not destructive rewriting of opaque legacy input. Error branches must have defined metadata defaults.
Current branch head 4f030be has uncommitted small catalog/Storage variable defaults and raw category preservation plus Database source-contract assertions adapting to localized rendering/AI-explain filename fallback; actual frontend source is unchanged. Validation is Linux isolated PG with original conftest and real Git snapshot. New result will be reports/bilingual-metadata/frontend-ci-fix-validation.json. Existing frontend12/typecheck/build/Chrome fixture and Python/TypeScript symbol checks passed; no UI changes follow those runs. Pylint errors-only for touched modules and other static checks passed. Reviewers must not stop/restart generator45624/writer49256 or three independent Luna contexts.
<!-- /current-bilingual-review-context -->

### PR #425 Linux regression repair — 2026-10-14

- Fixed two existing-write-contract regressions found by the controller's 213-test Linux run. `Storage.upsert_catalog_item` now initializes bilingual JSON from the existing row (or `None`), so successful legacy recataloging without a bilingual package remains valid. A first-time skipped item retains its supplied category in both Storage and incremental upserts; existing rows still preserve their saved category/package on failure or skip.
- Direct SQLite checks passed for a legacy refresh without bilingual JSON, new skipped rows through both writers, and preservation of existing bilingual metadata after a failed recatalog. Black, isort, Ruff, compileall, and `git diff --check` passed. No test assertions or UI code changed; controller should rerun the same Linux 213-test suite.

### PR #425 CI regression repair — 2026-10-14

- Updated the two Database source-contract checks to follow the bilingual render path: AI explain uses localized metadata and canonical display-name fallback, and row normalization uses `metadata.category` while summary text keeps its public-text normalizer. Route-state, filename fallback, and category-specific behavior remain asserted. The source test file passed (8 tests).
- Preserved opaque legacy category text in Storage and incremental catalog upserts while using `.strip()` only to decide whether a category is nonempty. Shared zh/en package categories continue to receive the same input value. Direct SQLite raw-category and skipped-row preservation checks passed.
- Initialized bilingual metadata locals in `_upsert_catalog_row` and `_process_single_row` to cover error/skip/local branches. Pylint errors-only on both touched production modules passed. Black, isort, Ruff, compileall, and `git diff --check` passed. Linux database cases remain for controller rerun; no UI source, private DB, live sync, or process was touched.

### CI compatibility patch verified — 2026-10-14T20:28:03+00:00

- 当前HEAD4f030be完整CI的2495PASS/3testsFAIL及2Pylint错误已最小修复：两个前台源码合同断言适配localized metadata/canonical filename fallback；成功写入不再strip旧category原文；metadata默认值显式初始化。没有改UI运行源码、全局CI或baseline。
- Linux隔离PG联合223测试/13子测试PASS；唯一Node包装在无npm依赖的Python镜像无法启动，同一Vitest目标已于本机1/1PASS。已补CI同款Pylint errors-only两模块PASS；Black/isort/Ruff/compileall/diffPASS。fresh独立Sol/high frontend-ci-review-4 PASS。随后自动推送并等待实际新HEAD全部CI；旧head质量门FAIL不作新headPASS。
# 当前运行端实现 — 2026-10-25

- 当前 worker 在独立工作树 `reports/local-automation-worktree` / `feat/local-collection-runtime` 实现用户已授权的本机流程：32 项 bounded adapter；Hub v3 `live_capture`/URL+raw SHA 版本及现有 exclusion；双语 25 类与三语义日期 enrich；两目标独立写入、原生 profile-specific chunk/embed/index/Ready；state/CAS/frontier 与 v2 receipt restart recovery。
- 现有 offline helper 和 06:00/09:00 automation 合同保留。该变更不自动启用 Scheduler，不用旧全量替换脚本；只触碰本仓库。本阶段禁止生产 Hub/服务写入，待 fresh review PASS 后由 controller 使用真实 IAA 新版本和 CAS secondary-AI 跑 pilot。
+ 当前代码修复包括 target AI serving bucket readback、单文章写入/Ready ledger 与 chunk failure vs Ready-only retry 区别，并修正 Hub ingest 后模型失败的分阶段回执计数和实际下载数。`tests/test_local_collection_runtime.py` 与 `tests/test_local_collection_target_worker.py` 12/12、独立 PostgreSQL `tests/test_content_hub.py` 17/17；dead-code files/symbols、Pylint -E、Ruff、Black、isort、py_compile、CLI help/plan JSON、skill-creator validate、`git diff --check` 通过。CI python-smoke 显式纳入三组本地流程/Hub 测试。
- 既有 AI backlog 有 449 unique URLs；历史现有 primary-only 322 个 target 不代表完整覆盖。源 bytes 缺失与旧多版本歧义保持 pending/deferred，不计为同步完成。
- Controller 的真实只读 `preflight --remote` 已核对两端 China ai+all Qwen1024、Overseas ai OpenAI3072、容量低于80%；仅 Hub v3 尚待显式迁移。未写生产 Hub/服务。代码冻结，等待 fresh Sol/high review；通过后由 controller 使用 IAA 新版本与 CAS secondary-AI 进行实际验收。

### Runtime review repairs R1–R4 — 2026-10-25

- 修复 Ready-only 重试回执误计 pending、preview 失败/部分完成仍返回 0、IAA organization chart 误收及 AI governance 研究论文误挡、target source_site 丢失四项 review finding。目标来源现在精确回读；没有来源记录的历史内容保留空值，不标成 `content-hub`。
- 独立 PostgreSQL 55435 上聚焦 36/36 PASS；Black、isort、Ruff、Pylint errors-only、py_compile、dead-code files/symbols、`git diff --check` 均 PASS。生产 Hub 和服务端没有写入；隔离 PG 容器留给 fresh reviewer 复现。已冻结工作树，等待 controller 启动新的 Sol/high review。


### Local collection runtime independent review 2 — 2026-10-26

- Fresh review verdict: CHANGES_REQUESTED. Three reproducible P2 issues are recorded in `reports/local-runtime-20261025/review-2.json`: parser retry items are skipped after being marked visited; CAA/Australia bootstrap errors can leave no v2 receipt; and exact-URL same-host redirects can report success without Hub processing.
- Verification: 36 focused Hub/runtime/target tests and 19 existing offline helper tests pass; `git diff --check origin/main` passes. No production Hub/target writes or real source previews were performed. Same implementation worker should repair the three findings before fresh review.

### AI-first publication and article-date projection — 2026-10-28

- Scoped to `fix/ai-primary-publication-dates` in this repository; sibling repositories remain off-limits. Hub and target eligibility now require `categories[0].key == "AI"` and matching source primary metadata. Secondary categories and exact evidence remain in ordered Hub enrichment. Historical listing/counts, cache preparation, stale local flags, queued retries, and target-payload validation share the same rule.
- Added exact, one-target `cleanup-targets` audit/apply support for non-AI-first records. It verifies URL/raw SHA/Hub evidence, removes only native target memberships/catalog visibility, retains source/CAS data, clears pending chunk URLs, and persists index/Ready retries. A capacity-blocked target stops before retirement.
- Added `backfill-target-metadata` for existing records only. It verifies exact target URL/SHA/Markdown and Hub bindings, categories, dates, and memberships; merges only `hub_enrichment`, projects verified publication dates at source precision, preserves unknown legacy target dates and bilingual packages, and never transfers source bytes or invokes chunk/embed/Ready. It persists pending KB refresh state for the later cleanup pass to rebuild once per KB.
- Updated the skill's main instructions plus local-actuarial-flow runtime/workflow references with AI-first semantics, date projection rules, and both maintenance manifest/CLI contracts. UI/API sorting was not changed.
- Validation: all three scoped files (`test_local_collection_target_worker.py`, `test_local_collection_runtime.py`, and `test_content_hub.py`) passed against an isolated PostgreSQL instance: `141 passed`. Python compilation, Black, isort, Ruff, Pylint errors-only, CLI `--help`, and `git diff --check` passed. The only warnings are three existing SWIG deprecations from the embedding-selector test.
- No production Hub/catalog write, commit, push, PR, or deployment was performed by this worker. Parent owns fresh review and the approved target maintenance run.

### Readable local-flow daily report — 2026-10-29

- Scope: `feat/readable-local-flow-report` in this repository only. Runtime receipts now record elapsed time, request/page/link observations, collected content types, conversion/enrichment outcomes, AI-first identities, and China/overseas acknowledgement and Ready identity sets. Redirect hops remain included in the production request budget. The worker's `ready_status=not_required` is recorded as not confirmed Ready and does not close a case or erase earlier confirmed Ready identities without explicit invalidation evidence.
- The offline helper accepts optional v2 telemetry and same-date `run-daily` output, preserves missing legacy fields as unknown, and keeps JSON/default and `--json` compatible. Runtime attempts are paired with receipts only when receipt ID, attempt number, and run status match. A previous same-day receipt remains visible as historical totals while the current missing receipt and runtime error are shown; this does not create a receipt or close a case.
- Retry telemetry totals and identity sets are cumulative only when that field exists in every attempt. Missing fields and IDs remain unknown even when later retries provide them. Already-acknowledged target IDs are retained on no-work passes, while Ready IDs require an exact validated target acknowledgement with explicit `ready_pending=false`.
- Markdown shows known partial HTML/PDF/other totals with receipt coverage, plus per-site request/download/Hub/conversion/AI-first/target progress. Missing AI-first telemetry stays unknown and old candidate counts retain the legacy label; old AI counts are not used to claim no sync is needed. Monitor-only results, current monitor errors, and planned checks without runtime evidence appear in a separate section outside collection totals.
- Source counts distinguish successful page/interface reads (including directory and search data) from discovered and queued link candidates. Specific source errors remain visible beside request-budget pauses; detailed diagnostics stay in JSON.
- Updated the `local-actuarial-flow` skill and references for the isolated web-listening 3.3.0 executable and manual local-only exploration boundaries. No scheduler, production fetch policy, source state, historical receipt, Hub, target, ledger, or automation configuration was changed.
- Validation: `test_local_flow.py` passed 26/26. `tests/test_local_collection_runtime.py` last passed 79/79 on the isolated PostgreSQL test DB at port 55436; it was not rerun in this helper-only pass. New helper regressions cover partial file-type totals, per-site conversion and AI-first counts with legacy unknowns, monitor results/errors, and planned monitor checks without runtime evidence. CLI Markdown reruns were deterministic: Oct 28 showed 131 requests / 88 downloads across 5/8 matched receipts; Oct 29 showed 224 requests / 119 downloads across 8/8, with 41 new versions, 25 reused and 40 classified. The Oct 25 receipt-only render showed a planned monitor check without execution evidence. CLI JSON and `--help`, Black, isort, Ruff, Pylint errors-only, `py_compile`, and `git diff --check` passed.
- No commit, push, historical receipt rewrite, Hub/target write, production fetch, or automation change was made. The Oct 28/29 JSON inputs were read only; their saved outputs were not modified.

# 当前候选 — CAS 数字证据误报修复 — 2026-11-01

- 基于实际 CAS 单篇失败 receipt 中保存的两段限长诊断和 E6/E7/E8 原文，复现四类解析误报：二元技术术语被识别为元、训练/测试集括号内逗号样本数与无逗号数量类型不一致、数据集训练/测试期间缺少年份上下文，以及“一种”泛指短语被识别为精确计数。原始失败 receipt 的两次模型调用未重置或改写；未保留完整模型回复。
- 共享解析器只增加限定技术词上下文、训练/测试样本量标记、数据集期间年份上下文和“一种”泛指处理。回归保留 2 元货币、明确“只有一种”/“两种”计数、无上下文逗号字面值与小数、一般四位数字计数及普通 from/to 数值范围的严格校验。新增真实诊断两段的 validator 用例及负例。
- 验证：`tests/test_article_interpretations.py` 与 `tests/test_article_interpretation_async_transport.py` 合计 203 passed / 1 skipped；使用仓库专用隔离 PostgreSQL，并对本机 loopback 测试连接启用授权访问。Ruff、逐文件 Black 检查、`py_compile`、`git diff --check` 通过。完整日志 `reports/interpretation-number-repair-20261101/numeric-followup-focused-tests-elevated.log`。
- 这是累计本地审查第 3 轮限额后的已测试最终修复；没有新的独立审查 PASS，也不安排第 4 轮。主控负责提交、推送、当前 HEAD CI 和后续实际生成验收；此 worker 未提交、未推送、未调用模型/provider，且未访问生产数据库。

# 当前候选 — 英文文章解读集成 — 2026-11-01

- English feature worktree `C:/Users/ferry/.codex/worktrees/english-article-interpretations/AI_actuarial_inforsearch` 已合入 PR444 的数字解析修复。仅澄清翻译提示：日期作为 claims 中的事实必须保留；publication date、source、URL、references、citation marker 与 kind label 等额外元数据由应用代码提供。未改预算、UI 或其他提示内容。
- 使用隔离 PostgreSQL 与本机 loopback 授权验证 English/Chinese/async 三个后端测试文件：218 passed / 1 skipped / 1 failed。唯一失败 `test_native_task_stop_history_and_restart` 在合并套件时复现；单独在当前代码及只读加载的 clean numeric baseline efb98c 上均通过。两者相同的旧 finalize 路径先移除 active task、后追加 job_history.jsonl，测试会在 active 列表清空后立即重读文件；English stage 在该测试的 local/stopped 路径不执行。记录为基线任务历史落盘竞态，不改 unrelated runtime code。日志位于外部 `reports/interpretation-number-repair-20261101/english/`。
- English prompt regression、Ruff、逐文件 Black、`py_compile` 与 `git diff --check` 通过。UI 文件未改；此前21项 UI/type/lint/build 检查的输入字节保持不变。后续 fresh review3 应包含冻结的 English 源码与 English 两站 OPS 资产。未调用 provider 或生产系统；主控负责最终 CI 与部署验收。
- 最终检查补充：为避免测试在 `active_tasks` 清空、但历史文件尚未追加完成时立刻重读，停止/重启回归现在通过 `threading.Event` 等待原始 `append_history_to_disk` 返回；此改动仅在测试中，运行时代码未改。最新完整组合运行中，该历史测试已通过，但本机 async transport 测试的第二个 slot 偶发失败（218 passed、1 skipped、1 failed）；相同测试在 17 项定向运行中通过。保留两份日志并记录为尚未解释的组合运行失败，不宣称组合套件全绿。移除了仅逐字镜像提示词的回归；15 项 English 行为测试、停止/重启测试和 async transport 测试合计 17 passed。Ruff、逐文件 Black、`py_compile` 与 `git diff --check` 通过。此后不再改 English 源码；fresh review3 应以当前源码和 OPS 资产为准。
- 两站 OPS 资产位于外部报告目录 `reports/interpretation-number-repair-20261101/english/ops/`：固定中国 4a / 海外 740 基线及候选 GAN 论文 C3677/O1107 与双站原文、Markdown SHA；海外预检禁止英语生成和启用的解读计划，运行时仅启用只读代理。新增离线故障注入自检覆盖不活动计时器、设置失败恢复原计时器、watchdog 保留/安全取消，共 7 项通过。Ruff、逐文件 Black、`py_compile` 通过；npm 可执行路径解析检查成功。没有 Docker、SSH、生产或 provider 操作；fresh review3 尚待主控执行。
- 主控诊断发现 async transport 组合失败来自真实 AsyncOpenAI 首次懒加载占用两秒合成调用期限。回归现在在计时前创建、访问并关闭真实 SDK 的 `.chat.completions` 资源，且断言预热没有发出 loopback 请求；生产运行时代码和既有两秒期限、取消、串行及服务端请求断言均未改。Ruff、逐文件 Black、`py_compile` 和 `git diff --check` 通过；定向测试待主控对当前完整测试集重跑。
- Final review 3 的四项已接受问题已完成最后限额内修复：英文数字比较保留次序、重复次数及精度，仅把完整匹配的中文年月日、英文月份日期和 ISO 日期归一为一个日期事件；源引号内容及重复次数必须保留，且新增引号仍须有源证据。公式检查继续优先报告原有专用错误。OPS 现核对中国 supervisor 实际 Exec 命令和活动 API 指针，并把中国/海外备份与工作路径固定到各自独立挂载；恢复校验记录路径，但不因备份挂载不可用而阻挡服务回滚。
- 当前最终修复验证：English 测试模块 17 passed；共享中文数量解析相关测试 29 passed；OPS 离线故障注入 selfcheck 9 项 PASS。Ruff、五个 Python 文件逐文件 Black、`py_compile`、`git diff --check` 通过。测试 PostgreSQL 是隔离实例；provider 调用、生产数据库和远程主机访问均为 0。此前 218 passed / 1 skipped 的组合运行是这些最终修复之前的字节，主控需对当前源码运行最终组合测试与 CI。累计第 3 轮已结束；本修复是按本地审查限额记录的已测试未审查修复，不声明独立 reviewer PASS、不安排第 4 轮；主控继续最终 CI、OPS 审核和发布流程。

## 2026-11-01 Primer lexical “下一步” validation repair

- The actual CAS AI Primer attempt failed after its two permitted calls; the failed draft and receipts remain unchanged. Offline reproduction isolated the unsupported `1` to the fixed phrase `下一步`, which had been read as the explicit count `一` + `步`. The cited E16/E17 material contains no corresponding quantity. `一组工具` and `不一致的输入` are not parsed as counts and were left unchanged.
- The Chinese quantity scan now blanks only `下一步` in its private scan text via the existing position-preserving substitution helper. Stored/display text, occurrences elsewhere, explicit `一步`/`只有一步`, `下两步`, and `第一步`/`第1步` remain unchanged and strictly validated. No prompt, budget, provider, receipt, or article state changed.
- The 229-test Chinese/English/async suite passed 228 passed / 1 skipped on identical product source before final formatting and test-function placement cleanup. After that cleanup, the saved Primer regression, existing SOM range test, and English saved-Primer regression passed (3 passed). A full rerun on the final test bytes stalled at 46% for over two minutes without test errors; it was stopped and preserved, not counted as a pass. Final Ruff, isort, per-file Black, `py_compile`, and `git diff --check` passed. Logs are in `reports/interpretation-number-repair-20261101/english/primer-next-step-focused-tests.log` and `primer-next-step-focused-final.log`.
- This is a tested final fix under the exhausted local-review limit, not an independent reviewer PASS. The exhausted Primer attempt remains failed and immutable; the root owner will commit, run current-HEAD CI, and use a separately verified untouched candidate for any later generation.

## 2026-11-01 Source Portals catalog expansion

- On `feat/source-portal-coverage` from `main` a3c7d39, added 15 official directory cards, bringing the reviewed catalog to 25. Distinct topics at one institution remain separate cards; alternate routes for the same directory share one card. The 32-site daily plan is unchanged. Six monitored items remain without directory cards: IABA/EAA monitor-only, Istituto hold, one focused SOA article, and AMA/ACA Colombia without a verified extractable materials directory.
- Read-only page probes showed 5 of the 15 new URLs currently form complete captures under the existing semantic parser; incomplete pages do not create change prose. The catalog update alone does not prove all 25 cards have recent updates. Existing daily runtime, Hub schema, targets, budgets, classification, and schedules were not edited.
- Focused `test_source_portals.py` passed 21/21 against a disposable PostgreSQL database, then that database was removed. Ruff, Black, and `git diff --check` passed. Deployment and switching the frozen local automation require a separate release decision after PR checks.

### Issue #450 locale-scoped interpretation sync — 2026-11-02

- Target ACKs are now keyed by target, interpretation ID, and locale. Source identity is recorded separately from the full draft SHA audit. When English becomes ready after both Chinese ACKs, candidate scanning preserves those ACKs and exposes English as pending. English-only target writes require the same source identity and stored Chinese digest, update only `{english_translation}`, and verify the persisted row and locale digests before ACK; conflicting ready English is rejected. No schema change was made.
- Focused writer/runtime regressions passed 15/15, including EN-only late recovery, per-target retry, readback, identity/Chinese-digest/English-conflict rejection, and no-ready-English behavior. Black, Ruff, and `git diff --check` passed. No production generation, target write, or shared-config change was performed. Work remains uncommitted on `codex/issue-450-local-interpretation`; controller owns broader regression validation and independent review.
- Fresh-review repairs: Codex process communication is now bounded by the remaining prompt deadline; timeout cancels communication, terminates/reaps the process tree, and surfaces `TimeoutError`. An acknowledged locale projection drift now returns conflict without replacing the stored ACK. Fake-process timeout and zh/en digest-drift regressions pass; production generation and target writes remain unrun.
- Post-merge budget/accounting review: queued generation attempts now resume in the same attempt, while interrupted attempts still start a new attempt. Metered receipts use non-null `provider_calls` as the authoritative strict count; Codex receipts use `outer_attempts` when `provider_calls` is null. Three isolated helper/state/budget tests passed. The reported PG-backed selectors could not run here because `POSTGRES_TEST_URL` is unset; rerun them with the controller's isolated PG16 endpoint.
- Final review repairs: the target ACK writer now preserves an acknowledged locale receipt for repeated matching `unknown` or `acknowledged` writes, and rejects projection drift without changing the receipt. Local prompt generation now uses the earlier of the absolute stream deadline and prompt timeout, with `asyncio.wait_for` cancellation and existing generator cleanup. Focused ACK/deadline stream tests passed 11/11; production generation and target writes were not run.

- Final related PostgreSQL integration run after both review fixes and the fast-forward to `dcad36c` (#451): **462 passed, 1 skipped** across article interpretation, English translation, local collection runtime/target worker, PostgreSQL connection, and Content Hub test modules. The disposable PostgreSQL 16.15 container had no host bind mount; its default anonymous data volume was removed with the container after tests. The port was bound only to `127.0.0.1`; test URLs were process-scoped. No production/Hub database or data was used.
- Final static checks passed: Black (11 Python files), Ruff, AST parse (11 files), and `git diff --check`. Branch is current with `origin/main`; implementation remains uncommitted.
- One local TypeSafe review assessment used a minimized anonymous packet. Requested `jev-latest` resolved to `jev-1.14.0`; both candidate findings were preliminarily classified valid/in-scope. Policy confidence was 0.43 for each, evidence probabilities were 0.84 and 0.72, and review-summary coverage was 0.40. Treat as weak supplemental evidence, not a code-review pass. The report is outside this repository at the task visualization path; no review state file was edited.
### Issue #450 final review and local runtime preflight — 2026-11-02

- Fresh independent review 2 returned CHANGES_REQUESTED with two reproducible, in-scope findings: the target ACK writer can replace an already acknowledged projection when a later valid ACK carries changed content under the same source identity; and article generation can receive a fresh full timeout even when the enclosing stream has less time remaining. Reviewer confirmed both with offline repros; 49 selected offline tests and `git diff --check` passed. No code changes were made after this review.
- The development shell has Codex CLI 0.154.0 and `codex login status` reports a local ChatGPT login. The tracked `config/sites.yaml` is only the development template and has no article interpretation route. In this shell, `CONFIG_PATH`, `DATABASE_URL`, and local API token/URL are unset, and `127.0.0.1:5000` is not listening. No live generation, local application DB, SSH, or target writes were attempted.
- The two completed CHANGES_REQUESTED rounds meet the project policy's TypeSafe adjudication gate. The latest user clarification permits unrestricted local calls; it does not authorize sending review material to the external TypeSafe service. Await explicit authorization for a minimal anonymized assessment before any further code decision or repair.
- The review-cycle state path remains unknown and the earlier round was not reserved through `review_cycle.py`; do not fabricate or hand-edit state. Await the assigned absolute state-file path before reconciling supported workflow records.

### Issue #450 review registration and TypeSafe adjudication — 2026-11-02

- Correction to the prior local preflight note: the shared same-project runtime config exists at `C:/Project/AI_actuarial_inforsearch/reports/local-automation-state/config.local.json` and is authorized for this task. This workflow uses the local generator plus the existing SSH stream/native DB worker; a local API listener or local `DATABASE_URL` is not required. The `article_interpretation` backend/model/reasoning fields are an authorized follow-up Ops setting, not a user-supplied configuration blocker. The earlier environment probe did not represent the production route.
- The user authorized the minimum TypeSafe egress scope at 2026-11-02T16:01:06Z: anonymous acceptance criteria, synthetic expected/actual repros, and generic finding summaries only. No source, real article, repository/Issue/file identifier, connection data, or credential was sent. Each completed review received a separate assessment; both returned preliminary `valid`/`in_scope` dispositions for its findings. Coverage probabilities were low (0.07 and 0.13), so these are supplemental evidence only.
- Second-failed-cycle TypeSafe Judge result (Jev 1.14.0, 2026-11-02T16:10:17Z): `repair_both_same_worker`, confidence 0.99. The outbound packet used only a generic evidence key. The raw result and local-only mapping to the pending workflow key are preserved in the task evidence directory; raw result SHA-256 is in `controller-review-audit.json`.
- Historical review registration is now reconciled through supported `review_cycle.py` commands in actual order. The first review (`/root/issue_450_review`) and second review (`/root/issue_450_final_review`) both returned `CHANGES_REQUESTED`; each has its own saved report. Their original native completion timestamps are unavailable per both reviewers and are recorded as null, not estimated. The original state was at review_count=0 because neither review was reserved before completion; no reservation time was backfilled. The authoritative state now correctly records review_count=2 and failed_review_cycles=2. The deviation and late registration timestamps are documented in the local audit.
- The same persistent worker has been tasked to fix the two findings from review 2. No production generation, SSH target write, route-config edit, commit, PR, or merge has occurred in this follow-up stage.

### Issue #450 pre-acceptance live check — 2026-11-02

- The authorized local runtime route is configured as `codex-cli / gpt-6-luna / high`. Read-only preflight passed: Hub status/schema, both target profiles and capacity, local state/data locations, and the 32-site contract. The saved-draft scan found no pending ready interpretation; sync-only returned `no_candidates`.
- The real local generation command reached the China one-shot worker but returned `stream_route_invalid` before any model prompt. `generation_calls=0` and `outer_attempts=0`; English settings and generated drafts were not reached. No target write, article generation, or budget change occurred.
- Both target containers lack `CodexArticleRuntime`; their installed `article_interpretations.py`, `article_interpretation_english.py`, and `storage.py` bytes differ from the reviewed worktree. The one-shot path currently streams the target worker only, so the installed service modules must match the reviewed code before live acceptance.
- No schedule was changed. The prior China 10:00 Asia/Shanghai generation schedule remains as observed; there is no overseas generation schedule or local 08:00 schedule. The completed 2026-11-02 round remains immutable, and its exhausted content versions will not be retried or reset.
- At Draft PR publication, the implementation matched fresh review 3. GitHub Actions CI run `41484600195` then failed the required `dead-code-symbols` job on three newly added unused declarations; this is a check failure, not a review cycle. The same worker removed the uncalled module-hash helper/constants and unused `_SyncCursor` fixture (37 lines total, no behavior change). The controller independently confirmed the diff, ran the two affected CLI tests (2 passed), and reran `npm run dead-code:symbols` (PASS, zero baseline findings); worker-reported Ruff, Black and `git diff --check` also passed. The repair is awaiting commit, a fresh local review and current-HEAD CI.
- Read-only inspection confirms both API containers still run source SHA `eee4531286bd2e87180daf67dd73e9c787d400ec` under release `source-portals-20261102-eee4531286bd`; each has a different image digest. They lack `CodexArticleRuntime` and their installed service modules differ from the Issue branch. No deployment, local generation, target write or schedule change has occurred since the earlier failed handshake. The completed `2026-11-02` round and exhausted identities remain unchanged.
- The single Copilot request was actually accepted at `2026-11-02T16:47:37Z` and work began at `16:48:07Z`. The supported state transition would not record it while the PR is Draft; this deviation and the guard rejection are recorded through `review_cycle.py record-decision`. No second request or quota probe was made.
- Next: commit and push the CI repair, run fresh review 4 and current-HEAD CI, then finish the controlled live acceptance only with the exact reviewed code and a fresh eligible version. Do not mark acceptance complete or change schedules before exact two-target readback passes.

### Issue #450 receiver release artifact review — 2026-11-02 15:52 ET

- At product source HEAD `337df9c46727e4166d57f27ba7e4e55ebde86d52`, all six GitHub jobs passed. Read-only baseline confirms both live API images lack `ai_actuarial/codex_environment.py`, which the candidate receiver path imports. This is a real runtime gate failure, separate from CI; no model request or source retry is needed to establish it.
- A local one-site-at-a-time code-only receiver overlay is prepared under `reports/local-interpretation-migration-20261102/issue450-native-release/`. The manifest pins the four full files, exact target baselines, component-only labels, unchanged EEE site identity, schema 6, and zero migrations. `deployable=false` remains set.
- Independent controller review found and the same worker fixed: prepared containers no longer receive canonical `ai-api`/`api` network aliases; cutover blocks if the original container configuration drifts after prepare; the runbook refreshes a read-only receipt before verify to satisfy the five-minute receipt gate under the seven-minute rollback watchdog.
- Validator, adapter self-check, AST parse, Ruff, and CLI `--help` all pass. Self-check reports no production change. No Docker, SSH, API, database, model, or schedule operation was run for this artifact. Both schedules remain unchanged; no acceptance, deployment, or migration is claimed.
- SHA-256 binding for the local artifact: `issue450_native_release.py` `2cdf10cc57789f028d791f554975f2a19a2d0c699964077035ce52f56a744cb3`; `receiver-overlay-manifest.json` `5afec5f2d5de28f0e980e8ab741bc3069d71e49d344701dbc46dc8d4832248a8`; `validate_receiver_overlay.py` `935bfd17de3279e7bd712a029ae8df5f4c17d19961d17112fd51954b30f25ad0`; `README.md` `7ceac1deae4e025cd91cce47ad4072d067b371302401a9fa84fc841f7ffc1075`; `next-readonly-snapshot.md` `f0277ca2f385c5ed2854610827d70df50a336a1f78ec662b82838924b2e09a82`. The manifest pins the overlay and schema-reference file hashes.
- Next: bind this exact artifact in the PR branch, run a fresh independent Sol/high ops review, and proceed only after its result and the existing live-operation gates. Keep the existing China automation active until the user's acceptance conditions pass.

### Issue #450 receiver release artifact review 7 fixes — 2026-11-02 16:22 ET

- The same Issue worker fixed four AC-5/AC-7 release-artifact findings: pointer writes now use unique same-directory temporary files and clean them after failure; rollback recognizes a candidate left under the pending name; the watchdog budget is 25 minutes; readiness requires all 30 catalog URLs to be non-empty and distinct. A retry after rollback uses a new private state directory.
- The code-only receiver overlay remains pinned to source component SHA 337 and site SHA EEE. deployable=false, migrations_to_apply=[], database schema 6, and the existing schedules remain unchanged.
- Final artifact SHA-256: adapter issue450_native_release.py 3e278d57fea21746f443e1135d409f84bdfbe7eb927ee6810a83d6e0b679754e; manifest receiver-overlay-manifest.json 2ba56c0cb9aad3791e0a5770fb47eb938aa304ea8a8bff1a7d490edfe0750a42; validator validate_receiver_overlay.py 935bfd17de3279e7bd712a029ae8df5f4c17d19961d17112fd51954b30f25ad0; README 2f245d9d3fa7edca0ecf3558074b842ee7fae08d7922908f3bce3bf509c60703; next read-only snapshot a95ad83cb17d9c37d88b67e17621299863bc1469e6f8ffd915e43f5e9c56588c.
- Worker evidence: issue450-ops-fix7-worker.md, SHA-256 462fde0877524e0b019f824bb9bedc08fb225c4627de090c37bb864b51497f2a.
- Independent local checks passed: receiver validator; adapter self-check (production_changed=false, 4 modules, 0 migrations, watchdog 1500 seconds); Python AST; Ruff; both CLI --help commands. Worker also passed JSON and whitespace checks. No Docker, SSH, API, database, model, or schedule operation was run for this package.
- PR #452 remains Draft. The GitHub run on the prior status head was still in progress; a current-head CI result is required after this status update. Review 8 and live two-target acceptance are pending. No generation, target write, deployment, merge, or schedule change is claimed.

### Issue #450 receiver and local-client identity repair — 2026-11-02

- The release verifier now binds all four receiver files to fixed Git blob identities and raw-byte hashes. The workstation gate now checks both actual local execution files against their fixed Git blob identities, normalized LF content, and separate Windows raw SHA-256 before invoking local preflight. The standalone package validator checks the client reference metadata; the workstation gate checks the actual local files.
- Red/green evidence: the unmodified package passes; scratch copies with a receiver file or local client file changed and only manifest size/raw SHA refreshed are accepted when the new content check is removed and rejected by the fixed code. Prior four rollback/readiness cases also have isolated red/green results. No red test modified the frozen package.
- Review 8 TypeSafe Judge (Jev 1.14.0) selected repair. Only anonymized criteria and synthetic reproduction summaries were sent. Worker reports: issue450-ops-review8-fix-worker.md (SHA-256 99b91f09a4d4e184e1ebb709b60d4ee8206c3d2a6550f3c63a85cf01c627f6ee) and issue450-ops-review8-local-client-worker.md (SHA-256 d41a6af9cf95fac0ae4d80f14cfc5d0d7943f8b6c44c89ed8556c26cc43d0684). Review-7 red/green report SHA-256 77c6a15fc8b125eb4763839adaac768df45c778a8988fa09a0e19f34e19e9d12.
- Final local artifact SHA-256: adapter issue450_native_release.py f4dcc6496798697a9f05fae44ff62ac34da5c75f38dfc4c7092abd30f5550b79; validator validate_receiver_overlay.py 12a79bec95b4924c40a19d0d189b073e7b5fbc315d4c2ab8d324f9f857c138f8; manifest receiver-overlay-manifest.json 2ba56c0cb9aad3791e0a5770fb47eb938aa304ea8a8bff1a7d490edfe0750a42; README a58de61bcb2ea1f386063b39d763a8c9d277326262efae5e4826594039fb9c8c.
- Independent checks passed: validator; adapter self-check (production_changed=false, 4 receiver modules, 0 migrations, watchdog 1500 seconds, receiver/client tamper checks); AST; Ruff; JSON; whitespace; CLI help. Candidate Git blob IDs for both local source files match the pinned candidate tree.
- PR #452 remains Draft. The prior status-head CI run was still in progress; current-head CI and fresh review 9 are required after this update. No workstation preflight, deployment, target write, generation, database/API readback, schedule change, or merge has occurred.

### Issue #450 receiver rollback failure reporting — 2026-11-02

- The round-9 AC-7 fix now reports immediate rollback accurately. A successful restore remains a nonzero cutover failure but states that the original receiver is healthy and the watchdog stop was confirmed. If rollback or watchdog cleanup fails, the message reports the observed timer as active, inactive, or unknown, without claiming a successful stop.
- Red/green evidence: the unchanged fixed package passes the offline self-check; the scratch copy with the previous unconditional watchdog error fails the same rollback assertion. The self-check exercises the helper used by cutover's exception path.
- Worker report: `issue450-ops-review9-fix-worker.md`, SHA-256 `BFBEF4F1EC115F77A92BA4E2ECB495F71ED1CDE06388D7D1E3CC8CB1EDC69700`.
- Independent checks passed: receiver overlay validator; adapter self-check (4 receiver modules, zero migrations, `production_changed=false`); AST parse; Ruff; manifest JSON; CLI help. Final package hashes: adapter `603AD98C5A2E2B5F2A6A1E2190812FC0CC5D8395ECEF93F2D72F2A81B133666D`, validator `12A79BEC95B4924C40A19D0D189B073E7B5FBC315D4C2AB8D324F9F857C138F8`, manifest `2BA56C0CB9AAD3791E0A5770FB47EB938AA304EA8A8BFF1A7D490EDFE0750A42`, README `63047CD1C75332303F6B6AF3EC45D39696F863286FC6A1AEEF95B74FA1D14D3C`, read-only snapshot `A95AD83CB17D9C37D88B67E17621299863BC1469E6F8FFD915E43F5E9C56588C`.
- No workstation preflight, Docker, SSH, API, database, model, generation, target write, deployment, or schedule operation was run. The China schedule remains active. PR #452 remains Draft; fresh review 10 and current-HEAD CI are still required.

### Issue #450 review-10 release-state repair — 2026-11-02

- The review-10 AC-7 defect was confirmed: after candidate acceptance, a manual rollback could restore the old receiver while leaving the candidate marked accepted. The same worker updated the receiver adapter and README only. Successful rollback now moves its timestamp/readback to `superseded_acceptance` and sets `accepted=false`, but only after old-receiver health, module hash, and supervisor checks. A failed restoration keeps the original acceptance fields. `verify` refuses a completed rollback before preflight; cutover refuses accepted, started, or rolled-back states. If timer shutdown fails after rollback, the next watchdog invocation retries timer stop without stopping or renaming containers again.
- State matrix and regressions cover prepare initialization; cutover re-entry; successful verify; accepted-to-manual-rollback; verify after rollback; restoration readback failure; watchdog on accepted state; and timer-stop retry after completed rollback.
- Red/green: the new check fails on the frozen pre-edit package because `accepted` remains true (exit 1) and passes on the fixed package (exit 0). Worker report `issue450-ops-review10-fix-worker.md`, SHA-256 `0F601F6038862C93797F872E1897BAAC5EF21E9810B48DF4E24F540CAD805234`.
- User authorized two TypeSafe calls on this new finding using only generic acceptance, synthetic trigger, and expected/actual summaries. Review assessment marked the finding preliminary valid; Jev Judge selected repair (confidence 0.91; repair probability 0.94). The raw anonymized Judge result and local-only evidence-key binding are preserved outside the checkout.
- Manager independently reran the red/green check, receiver validator, adapter self-check (4 modules, zero migrations, `production_changed=false`), AST, Ruff, manifest JSON, CLI help, and whitespace scan; all passed.
- Final local artifact SHA-256: adapter `9CC717F6A22BACDF9F9CA961DB49A06249A1F9AC22182A249B7B3067D9B0279C`; README `AEDBD6ED4E3C0B643A508AB5990692B39AFB85EA4F018526B3E0C5C773710851`; validator `12A79BEC95B4924C40A19D0D189B073E7B5FBC315D4C2AB8D324F9F857C138F8`; manifest `2BA56C0CB9AAD3791E0A5770FB47EB938AA304EA8A8BFF1A7D490EDFE0750A42`; read-only snapshot `A95AD83CB17D9C37D88B67E17621299863BC1469E6F8FFD915E43F5E9C56588C`.
- No Docker, SSH, API, database, model, generation, target write, deployment, or schedule operation was run. PR #452 remains Draft. This fix needs a fresh full-scope review 11 and current-HEAD CI before advancing.

### Issue #450 watchdog rollback retry — 2026-11-02

- Review-11 fix is limited to the ignored 13-file local receiver package: `issue450_native_release.py` and `README.md`. Rollback intent is persisted before service/container changes; a watchdog retries only when recovery is pending, while accepted state without pending recovery stays a no-op. Successful restoration persists completion before clearing pending; an interrupted cleanup only clears the marker and stops the timer.
- Combined state regression covers acceptance, timer-stop failure, failed first restoration, persisted watchdog retry, late accepted no-op, and completed-pending cleanup. Frozen package is red; fixed package is green. Worker report: `issue450-ops-review11-fix-worker.md`, SHA-256 `5A0E026310342AA6CB3DF9E0E7F888EDC4B1A2E27F80A6AF1E1D1F333E7CFFC3`.
- Independent validator, native-release self-check, and Ruff passed. Adapter SHA-256 `24DA8844B33EDC97554CF9C7EF4AB29BCE104409B54E72364FBD1F2E95CE967E`; README SHA-256 `E59FCEFFEAADFF58DAC66CA759ED531DB9D2DE6A2BAF17FB0FAC055AD9979A87`. No production, database/API, model, target, deployment, or schedule operation was run.
- PR #452 remains Draft. This status-only commit advances the PR HEAD for review-cycle tracking; current-HEAD CI and a fresh full-scope review are required. Real generation, two-target readback/idempotency, plan changes, and merge remain pending.

### Issue #450 Ops review 12 repair — 2026-11-02

- Fresh full-scope review 12 found four reproducible AC-5/AC-7 issues: normal inactive service status aborted rollback; verify and watchdog could persist conflicting stale snapshots; interruption after candidate creation left an unrecoverable fixed-name resource; and verify accepted a pre-ready workstation receipt. The anonymized TypeSafe assessment marked all four preliminary in-scope; the separate Judge chose repair-all (0.81 probability, 0.75 confidence). Review summary coverage was low (0.06), so the concrete reproductions and controller code-path confirmation remain the evidence basis.
- The same implementation worker updated only the ignored local receiver adapter and README. Rollback now accepts only the native inactive/failed status results; state-mutating phases use a cross-process lock and reload after locking; preparation persists a resumable stage before candidate creation and validates any existing candidate; verify requires receipt start time at or after candidate-ready time.
- Red/green: all four checks failed against the exact frozen R12 package and passed against the fixed package. Package remains 13/13 files; only adapter and README differ. Worker report `issue450-ops-review12-fix-worker.md`, SHA-256 `A93CE013B8F64666F028020653DAC16DC6D43DD0E77F9A0BCD2476A77FD964D4`.
- Independent validator, full self-check, Ruff, and recursive 13-file count passed. Linux `fcntl` cross-process self-check passed in cached Python 3.11 slim with no network, read-only package mount, read-only root filesystem, and temporary-only writable storage. Adapter SHA-256 `83AE8091746A53C36718159D8B3BE9FDA60A6F72B109A8C85423901C6CDF01EF`; README SHA-256 `6B0216CC53F460B1B17EC838A3132CA3747CEDDB8335FA1FD297D705C3C23F16`; manifest unchanged at `2BA56C0CB9AAD3791E0A5770FB47EB938AA304EA8A8BFF1A7D490EDFE0750A42`.
- No deployment, target service, API, database, generation, or schedule action was run. PR #452 remains Draft. The status-only push advances the branch for fresh review 13 and current-HEAD CI; real generation, two-target readback/idempotency, plan changes, and merge remain pending.

### Issue #450 Ops review-13 repair — 2026-11-02

- Fresh review 13 found four AC-5/AC-7 issues in the local receiver release package. The same worker changed only the adapter and README: interrupted verification now keeps rollback recovery pending; verification enforces the stored 25-minute watchdog deadline; prepare retries complete only missing network attachments after identity checks; and rollback stops the persisted watchdog unit.
- The exact frozen 13-file R13 baseline is preserved outside the checkout. All four regressions use the public CLI dispatcher and temporary on-disk state: frozen package 4/4 red, fixed package 4/4 green. The package remains 13 files and only adapter/README differ.
- Windows manager checks passed: package validator, complete self-check, Ruff, CLI help and negative argument check, AST/manifest parse, final newline/whitespace checks, hashes, and recursive file count. Cached Linux Python 3.11 self-check also passed with pull disabled, network disabled, read-only package mount, and temporary-only writable storage; the adapter hash was unchanged before/after.
- Local release package SHA-256: adapter `827B993478D58F2D3E83D428A7C1DAF75A4FA2DF5361B015F382E3D20B88EDBC`; README `9157DAE017DC00F739B2D31908B2A55BE5091B902576D744610A2EE5DF0A6E33`; manifest unchanged `2BA56C0CB9AAD3791E0A5770FB47EB938AA304EA8A8BFF1A7D490EDFE0750A42`. Worker report SHA-256 `5C679B53C7162C1F17D25F2EB25F00B0BB37D4C9315CB9E96CF0F566BB062729`.
- No online service, container, timer, API, database, generation, deployment, or schedule operation occurred. PR #452 remains Draft. This status-only commit advances the PR HEAD for fresh full-scope review 14 and current-HEAD CI; real local generation, two-target native readback/idempotency, schedule changes, and merge remain separate gates.

### Issue #450 Ops review-14 accepted-verify idempotency — 2026-11-02

- Fresh full-scope review 14 found that repeating verify after acceptance and watchdog expiry could restore the prior receiver and reverse the accepted marker. The reviewer and manager independently reproduced it through the public CLI with persistent synthetic state, fresh receipt parsing, and mocked service/container operations; it maps to C5 idempotent reruns and C7 safe rollback.
- The anonymized TypeSafe assessment marked the finding preliminary valid (criterion mapping 0.96; reproduction evidence 0.86). The separate Judge selected accept_repair (probability 0.82; confidence 0.73). User authorization covers R14 and final review 15 with the same anonymized scope, up to four calls total; two R14 calls have been used. Raw responses and the local-only lifecycle binding remain outside the checkout.
- The same worker changed only the local receiver adapter. Completed accepted state now returns already_accepted/idempotent before pending-verification deadlines; rollback_pending and rollback_completed checks remain first. The retry does not save state or repeat readbacks/container operations, and preserves the original acceptance timestamp/readback.
- Red/green regression uses the public CLI and persisted temporary state: the frozen package fails the second verify with watchdog_deadline_exceeded; the fixed package returns already_accepted/idempotent=true after the 25-minute deadline, with acceptance bytes and container state unchanged. accepted plus rollback_pending still returns rollback_recovery_pending.
- Independent checks passed: overlay validator, complete self-check (production_changed=false; four modules; zero migrations), Ruff, CLI help, expected missing-argument exit 2, and recursive 13-file snapshot comparison (only adapter changed). Worker report SHA-256 A5A672626E06AE30992162365B4AC03EACB0FA1132180A4AB24AA1377228B431. Adapter SHA-256 563EF00A25F8A13076A001A30E5D6C9A95D95E9FF2F9013E10CB44EBDCC6AEE7; README and manifest hashes are unchanged from review 13.
- No target, production, deployment, database, generation, or schedule operation occurred. PR #452 remains Draft. Final fresh review 15, current-HEAD CI, live target migration/readback, schedule changes, merge, and cleanup remain pending.


### Issue #450 final tested recovery correction — 2026-11-02 20:10 ET

- Final local review 15 returned CHANGES_REQUESTED; cumulative completed reviews 15 and failed cycles 12. The final scoped TypeSafe assessment and Judge accepted only recovery scheduling after an uncertain timer stop; the reporting-only candidate was excluded. The Judge selected repair_recovery_only with confidence 0.98. The four specifically authorized anonymous calls are complete.
- The same persistent implementation worker corrected pending rollback after timer stop already took effect but its client timed out or was interrupted. When the old timer is confirmed inactive, recovery uses a new unique timer identity, persists it, and confirms the new timer active. Existing acceptance and rollback guards remain.
- Frozen-source red and fixed-source green use the public CLI with persistent synthetic state and the timer-stop side effect already applied. Validator, complete self-check, Ruff, help/negative CLI, AST/JSON, whitespace and 13-file comparison passed. Only the local receiver adapter changed.
- Exact local artifact SHA-256: adapter 8aac6a902e9b156b8ba252acce886eb697ae464f3a33123bdeeea7a01a03dae9; README 9157dae017dc00f739b2d31908b2a55be5091b902576d744610a2ee5df0a6e33; manifest 2ba56c0cb9aad3791e0a5770fb47eb938aa304ea8a8bff1a7d490edfe0750a42.
- Independent Linux full self-check passed on the exact adapter with before/after hashes unchanged, cached Python 3.11, no network, read-only source and temporary-only writable storage. Both targets also passed an isolated native systemd smoke: stop an owned test timer, start a uniquely named recovery timer, run /usr/bin/true successfully, and clean all test units. Existing services, containers, databases and production schedules were untouched by those smoke tests.
- Per the user's quick-mode local-review-limit exception, this is the final tested correction without another Sol review. It is not recorded as reviewer PASS; no review 16 or additional TypeSafe call is permitted under this completed budget.
- Product receiver source remains 337df9c46727e4166d57f27ba7e4e55ebde86d52 for four modules; full site identity remains EEE and no database migration is requested. This status commit binds the final artifact for current-HEAD CI. Live receiver cutover, real local Chinese/English generation, two-target readback/idempotency, old-plan disable/local08 enable, merge and cleanup remain required.

## 2026-11-05 Issue #460 local implementation

- Worker branch `codex/issue-460-feedback-widget`, based on `4e8a06972403515502e8e7e5396b91fb235ecd29`. Added a lazy-loaded feedback-only widget and bilingual form, mounted in Layout; no AI UI or generation path.
- Final local acceptance: feedback component tests 8/8, typecheck/build/diff whitespace checks pass. Browser: 32 route × viewport × locale × theme cases, 0 axe violations; desktop Ask Agent card remains uncovered and mobile main scrolls while drawer is open. All panel targets are at least 44px.
- Real isolated PostgreSQL 16.15/loopback API/browser acceptance: seven receipt/text readbacks match one row each; retry after a committed response drop returns same receipt; 500/429 fault-injected retries, double-click one POST, feedback-disabled and capabilities-failure states request no feedback module; generation count 0. Evidence and screenshots under `reports/issue-459-464-20261105/issue-460/`; sanitized ignored receipt in `reports/issue-460/acceptance.json`.
- Initial automated run passed but a manager visual check found the panel covered the homepage Ask Agent card. It is retained as initial visual FAIL; final corrected matrix and screenshots PASS under the evidence `browser/final/` directory. Initial evidence is preserved under `browser/initial/`.
- No commit, push, PR, deployment, or production change by the worker. Independent review and manager SHA binding remain pending.
- Isolated validation resources were shut down after readback: disposable container `codex-issue460-pg16` removed; loopback ports 8000, 5173, and 56618 verified free. See the shutdown receipt in the retained evidence directory.

### Issue #460 review-fix R1/R2 — 2026-11-05

- Addressed accepted review items R1/R2 on the same Issue branch. The SupportWidget's fixed transparent wrapper now lets pointer events pass through except on the panel and entry; on `/chat` below 1280px the panel is raised 64px. Other routes retain the existing panel position. Final browser smoke at 390x844 and 1024x844 confirms the input hit target is Chat's `textarea[data-testid=input-chat-message]`, the send hit target belongs to `button-send-message`, and clicking it submits one mocked Chat request at each width. No provider request occurred. The first panel-only adjustment still intercepted the input; failed and corrected evidence is retained under `browser/review-fix/`.
- Feedback submissions now retain the complete first payload (including locale) and `client_request_id` while the outcome is uncertain. A language change therefore retries the same canonical request and can recover the original receipt; editing content/type or changing route clears that retry snapshot and creates a new id.
- Review-fix checks: focused Vitest 9/9, typecheck, production build, browser smoke at both widths, and `git diff --check` passed. Full 32-combination matrix and real API/PostgreSQL closure were not rerun for these targeted changes; prior evidence remains preserved. Exact logs/results are listed in `reports/issue-460/acceptance-review-fix.json` and the worker report addendum.
- Worker-owned Vite server was stopped and port 5173 had no listener. Changes remain local and uncommitted; no commit, push, PR, or production operation was performed.

### Issue #460 R1 Chat control-row follow-up — 2026-11-05

- Manager visual review found that the Chat textarea and send were reachable, but Expert mode, the RAG selector row, and Knowledge Bases were obscured at 390px and 1024px. Corrected by moving only the `/chat` panel farther upward (128px bottom margin at widths up to 1279px); the entry trigger remains in place and other routes retain their layout.
- The expanded browser smoke trial-clicked and hit-tested the composer, send, Expert selector, both RAG choices, and Knowledge Bases selector. All six were visible and actual `elementFromPoint` targets mapped to Chat at both viewport sizes. Actual Chat send remained functional; mocked requests per viewport 1, provider calls 0.
- New evidence: `browser/review-fix-chat-controls/`. Focused Vitest 9/9, typecheck, build, diff-check, and browser smoke passed; the full matrix and real API/PostgreSQL closure were not repeated. The acceptance receipt and worker report were updated with exact paths/results.

### Issue #460 R1 Chat expanded-menu follow-up — 2026-11-05

- The review-2/Judge finding traced to Chat's composer/footer `backdrop-blur` stacking context: increasing only the popup child z-index did not move it above the SupportWidget stacking layer. Set the Chat footer context to z-60; feedback panel and Chat state remain independent.
- Browser smoke now actually expands and selects a Chat mode, both RAG choices, and a synthetic available KB with feedback open at 390px and 1024px. Mode/KB menu options pass `elementFromPoint` and trial-click checks, and their selected state is verified. Feedback text remains unchanged, feedback stays open, Chat send remains reachable, and provider count is 0 (all `/api` is mocked).
- Final smoke, focused tests 9/9, typecheck, build, and diff-check pass. Failed/intermediate attempts are retained in `browser/review-fix-chat-menus/`; final screenshots, JSON and logs are also there. Full 32-case/API-PG checks were not rerun.

### Issue #460 R1 final conditional layer and validation — 2026-11-05

- The Chat footer stacking layer now rises to z-60 only while the support widget is open. Layout provides `group/support-widget` plus `data-feedback-open`; Chat uses Tailwind's matching group-data selector. This preserves the default Chat stacking order while allowing the menus above the feedback panel.
- Conditional final version passed the menu smoke at both viewport sizes. All mode/RAG/KB choices were selected; feedback text and open panel were preserved, Chat send worked, and provider count stayed at 0. Final screenshots were reviewed and are saved in `browser/review-fix-chat-menus/`; pre-conditional screenshots and all failed/intermediate logs remain alongside them.
- Final validations on the exact final code: focused Vitest 9/9, typecheck, build, diff-check, and browser menu smoke all PASS, exit 0. The JSON receipt now points to the final logs/results. Full 32-case matrix and real API/PostgreSQL were not rerun.

### Popup z-index baseline restored — 2026-11-05

- The two Chat dropdown popup classes are restored to their original `z-50`; the composer/footer stacking context alone conditionally becomes z-60 while feedback is open. This keeps the menu fix local to the open-widget state.
- Repeated final menu smoke at 390px/1024px passed after this correction, including actual mode/RAG/KB selection, hit tests, trial clicks, feedback text/panel preservation, and mocked Chat send. Provider calls 0. `npm run build` and `git diff --check` also passed, exit 0. Final evidence and refreshed receipt are in `browser/review-fix-chat-menus/` and `reports/issue-460/acceptance-review-fix.json`.
- Vitest was not rerun for the popup z-index-only adjustment; the preceding 9/9 run remains valid. Full matrix/API-PG were not rerun.

### Issue #460 round-3 overlay audit — 2026-11-05 (in progress)

- Added bounded overlay order for the Chat drawer and Layout mobile navigation while preserving the feedback widget/form and draft. Drawer/navigation actual click cases pass at 390x844; Chat mode/RAG/KB actual selection smoke passes at 390x844 and 1024x844.
- Database and FileDetail dialog hit checks were extended to both 390px and 1024px, including header close, confirm trial only, and actual cancel. At 390px all tested actions hit the dialog. At 1024px header close and cancel work, but confirm center is intercepted by feedback form on both routes; no confirm action was submitted. This is a reproducible in-scope AC1 issue awaiting a narrow host-layer solution from the read-only Architect.
- Current smoke evidence: `browser/overlay-review-3/issue460-overlay-round3-control-audit.json` and `.log`; pre-Architect tests: focused Vitest 9/9, typecheck, build, and diff-check all pass, logs in `browser/overlay-review-3/checks/`. The browser smoke exits 1 to report the confirmed 1024px collision. Full 32-case/API-PG closure was not rerun.

### Issue #460 round-3 overlay audit — final — 2026-11-05

- Read-only caller review confirmed `ConfirmDeleteModal` is used by Database, FileDetail, and Knowledge with no lower route stacking context. At 1024px, its `lg:z-50` tied the later SupportWidget z-50, causing the measured confirm hit collision. Removed only that responsive override; the dialog remains z-60 at all widths.
- Final target smoke passed at 390x844 and 1024x844. Chat mode/RAG/KB selection and send passed; feedback text/panel remained intact. At 390px, Chat drawer interactions, drawer-first backdrop interception, and Layout sidebar navigation to `/knowledge` passed with the feedback draft preserved. Database/FileDetail at both widths: header close, confirm trial-only hit, and actual cancel click all hit the dialog. Confirm was never submitted; feedback drafts survived cancel.
- Pre-fix 1024px confirm hit failures remain in `browser/overlay-review-3/`; final JSON/log and screenshots are in `browser/review-fix-chat-menus-final-z60/`. Focused Vitest 9/9, typecheck, build, diff-check and targeted browser smoke all PASS. Full 32-case matrix and real API/PostgreSQL were not rerun. All API calls were mocked, provider calls 0.
- Vite stopped; port 5173 has no listener. Worktree remains uncommitted. Receipt and worker report include exact checks and evidence paths.
- Repeated final smoke after adding a wait for the dialog opacity animation before screenshots; all browser actions still pass. Final modal screenshot is stable and shows the dialog above the widget; transition captures are retained with `-pre-animation-wait` suffixes. Final `git diff --check` also passes.

### Issue #460 FileDetail-owned dialog overlay follow-up — final — 2026-11-05

- The expanded browser smoke reproduced the Catalog cancel control being intercepted by the feedback textarea at 390px. The pre-fix failure is preserved in `browser/review-fix-owned-modals/`.
- Raised only FileDetail's own Catalog/Chunk `Modal` overlay from z-50 to z-[60] and added stable IDs for the modal surface/cancel controls. At both widths, Catalog and Chunk submit controls now pass trial-click/element hit checks (no submit action is performed), cancel controls hit the correct modal and actual cancel clicks close it; feedback remains open and retains its synthetic sentinel.
- Final complete overlay/control audit passed: Chat menu selections at 390/1024, drawer-after-feedback controls/conversation, drawer-first support-trigger interception, Layout nav to `/knowledge`, Database/FileDetail ConfirmDelete header/confirm-trial/cancel at 390/1024, and FileDetail Catalog/Chunk submit-trial/cancel at 390/1024. API routes are synthetic mocks; provider calls 0.
- Focused Vitest 9/9, typecheck, build, diff-check, and full targeted overlay browser smoke PASS. Final evidence: `browser/review-fix-owned-modals-final/`; no full 32-case matrix or real PG/API closure rerun. Vite stopped; port 5173 has no listener. Work remains local/uncommitted.

### Issue #460 final local review and overlay verification — 2026-11-05

- Final implementation keeps feedback and future assistant modules separate. The support entry is gated by #459 capabilities and loads the feedback form on open. Current overlay ordering keeps Chat menus above feedback, Chat and site drawers above overlapping content, and Database/FileDetail modal controls clickable while preserving typed feedback.
- The final targeted browser audit passed at 390x844 and 1024x844: Chat mode/RAG/KB selection and send; Chat drawer in both open orders; mobile site navigation; Database/FileDetail delete dialogs; FileDetail Catalog and Chunk dialogs. Destructive or submit controls were trial-clicked only; cancel actions were clicked. Feedback text remained intact and model/provider calls were zero.
- Focused Vitest passed 9/9; typecheck, build, and diff check passed. Build retains the existing Vite large-chunk advisory. Fresh independent local review passed; TypeSafe review assessment recorded no candidate findings.
- The earlier 32/32 browser matrix and seven-row isolated API/PostgreSQL closure remain in the acceptance receipt and evidence bundle; they were not rerun after overlay-only changes. No production service, live data, or provider was used. No dependency or lockfile changed.
- Local acceptance and review are complete. The implementation SHA, current-HEAD GitHub checks, PR, and publication remain pending.

### Issue #460 committed local review state — 2026-11-05

- Implementation commit: `0f381302e7114711e840a829c321f37dd860f589`. The ignored canonical receipt `reports/issue-460/acceptance.json` is now bound to this SHA; the receipt will be force-added in a separate evidence commit. Local review is PASS; push, current-HEAD GitHub checks, and Draft PR are pending.

### Issue #460 Draft PR publication — 2026-11-05

- Pushed `codex/issue-460-feedback-widget` and opened Draft PR [#466](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/466), which includes `Closes #460`. Implementation SHA remains `0f381302e7114711e840a829c321f37dd860f589`; canonical receipt is committed and SHA-bound.
- Copilot auto mode made one initial request attempt. GitHub did not add a reviewer (`reviewRequests=[]`; review list empty), so Copilot is recorded unavailable for this Issue and will not be retried.
- At the initial PR snapshot, `dead-code-files` passed and `dead-code-symbols` was running on head `8419542c3e6bc4d4a281eabecf2923b7ccb4f129`. The PR remains Draft while final current-HEAD checks complete. No production change.

### Issue #460 remote review lifecycle and C5 overlay fixes — 2026-11-05

- Applied the accepted R1/R2 lifecycle fixes and the C5 bounded overlay plan in `codex/issue-460-feedback-widget`; no dependencies changed. A local error boundary contains a rejected feedback chunk with retry; first-open feedback stays mounted but hidden on close; Escape is scoped to the open widget; stale route responses cannot update the new route; Chat footer/panel layering at small viewports leaves Chat controls and feedback submit reachable.
- C5 final 390x500 keyboard-available-height simulation passed: panel y=19.25..251.25 (top at least 16px and bottom within 500px), feedback form scrollTop 0→159, 44px submit upper/lower inner points both hit `feedback-submit`, and actual submit returned a receipt visible inside the scrollable form. Chat mode upper/lower edge hits resolved to `button-mode-selector`; real mode/RAG/KB/input/send actions passed at 390x844 and 1024x844.
- Final new-head matrix passed 32/32 route × viewport × locale × theme combinations (Home, Database, File Detail, Chat; 1280x900/390x844; en/zh; light/dark), axe 0, six fault scenarios, seven real API receipt entries, PostgreSQL16 readback 7/7 rows, provider/generation calls 0. Results are under external evidence `reports/issue-459-464-20261105/issue-460/browser/remote-fix-final-matrix-20261105/`; earlier 32-case results remain historical and were not overwritten.
- Final overlay smoke passed: Chat mode/RAG/KB selections, input/send, drawer, site sidebar navigation, Database/File Detail delete dialogs, File Detail Catalog/Chunk dialogs, feedback draft preservation, and 390x500 edge checks. Final JSON/log and ready/success screenshots are under `reports/issue-459-464-20261105/issue-460/remote-fix-lifecycle-final/`.
- Real browser→FastAPI→isolated PostgreSQL16.15 close/reopen replay passed on final source: first request committed with HTTP201 then its browser response was aborted; closing/reopening retained draft and request ID; retry sent identical payload/ID and received the original receipt; PostgreSQL contained exactly one matching row; generation calls 0. Separate evidence is under `remote-fix-lifecycle-final-v2/`.
- Final checks: `npx vitest run --config vitest.config.ts client/src/features/feedback` (13/13), `npm run typecheck`, `npm run build` (exit 0 with the existing large-chunk advisory), and `git diff --check` all passed. Logs are under `remote-fix-lifecycle-final-v2/`.
- Preserved C5 intermediate failures: the original bottom-inner point hit `rag-mode-option-agentic`; +8px spacing moved interception to the Chat footer background; pointer transparency alone made the hit test pass but the screenshot still showed visual overlap. Architect review and bounded Judge selected transparent footer surface plus a reduced small-viewport height cap; after a 2px border-box correction the final panel top is 19.25px and visual/control assertions pass. Prior failures remain in `remote-fix-lifecycle-final/`.
- Full-matrix attempt 1 failed because the isolated API had already been stopped (capabilities HTTP500); attempt 2 exposed the old harness expectation that Escape unmounts the form. Both logs are retained. The harness now asserts hidden-but-mounted and the restarted final run passed.
- This round changed only seven scoped source/test files: `SupportWidget.tsx`, `FeedbackForm.tsx`, `FeedbackForm.test.tsx`, `use-i18n.ts`, `Chat.tsx`, `Issue460ChatReachability.browser-smoke.mjs`, and `Issue460Feedback.browser-smoke.mjs`. No raw screenshots/logs were added to git; acceptance evidence is sanitized.
- Dedicated FastAPI PID 51508 and container `issue460-final-matrix-pg16-20261105` were stopped/removed. Ports 8000 and 55458 are free; manager-owned Vite PID 40104 on 5173 remains running and was not stopped. Unrelated PostgreSQL containers were not touched.
- Worktree is on `codex/issue-460-feedback-widget`, currently uncommitted. `reports/issue-460/acceptance.json` has been updated with `implementation_sha: null` pending the first authorized implementation commit; the planned follow-up binds the resulting implementation SHA. No commit or push has been made yet.

### Issue #460 remote-fix implementation commit — 2026-11-05

- Implementation/status commit: `f2e74df`. The sanitized canonical acceptance receipt now binds this implementation SHA and will be committed as a separate evidence commit; both commits will be pushed together once. No status-only push is planned.
## CIA news discovery and exact HTML capture — 2026-11-06

- Worktree branch `fix/cia-news-discovery` adds the public WordPress `news` REST feed to `cia-ica` only. Saved frontier repair preserves the processed prefix and cursor; each later normal run schedules one bounded page-1 feed refresh at the cursor even while later feed pages or story pages remain queued. Page 2+ pagination remains URL-deduplicated. `cia-research-publications` keeps its publication-only feed. Existing host/member exclusions, 30-request cap and collect-first categorization remain intact.
- Exact CIA `/news/` URLs now use the existing HTML article path, store extracted full article text, prefer the decoded H1 for title, skip outbound link traversal and deduplicate by existing URL/SHA. Other exact URLs retain the prior document download path and filename title.
- Focused source tests passed 10 cases, including REST post enqueue, monitor separation, old-frontier/prefix preservation, recurring refresh under a one-request cap, exact HTML replay, exact PDF replay and CLI help/JSON plan behavior. The final complete runtime suite passed all 119 tests (3 warnings) against isolated task-owned PostgreSQL 16 on loopback55473 and the existing test-only `disk_usage` seam; production capacity gates were unchanged. Evidence: `reports/cia-news-addition-20261106/product-runtime-tests-final.json` and `.log` in the controller workspace. `black --check` and `git diff --check` passed. An earlier uncontrolled run had 114 passed / 5 failed due to a stale encoded-title expectation, unset PostgreSQL test URL, and test-host capacity gating; the title assertion was corrected and the controller-only environment seam resolved the remaining environmental failures. Real live checks and deployment remain controller-owned.
- Changed scope: `ai_actuarial/local_collection_runtime.py`, `tests/test_local_collection_runtime.py`, and local flow references. No config, schema, dependency, live target, scheduler, or sibling repository changed. No commit/push/PR by this worker.
- Source portal fixture follow-up: `tests/test_source_portal_daily.py` now models the new CIA news REST request as an empty JSON response; the file-only bounded-run fixture allows that request plus one PDF while remaining partial. Twenty-five non-DB source-portal/capture fixture cases passed with the existing test-only capacity seam. Connected PostgreSQL regressions remain controller-run because this worker shell has no `POSTGRES_TEST_URL`.
- R1 F1 repair: periodic polling now skips only a page-1 news request already pending, not the paginated page-2 backlog. Page-2 pagination identity remains URL-based across polls to prevent duplicate archive pages. Removed the redundant `/news/` landing-page repair entry; the news REST feed is sufficient and avoids consuming a request on a generic navigation page. Added a regression with two old story pages, a generated page-2 item and a one-request run; it verifies a fresh page-1 poll runs, the old processed prefix/cursor persist, page 2 stays unique and old stories remain pending. The shared source-portal fixture returns empty JSON for news REST. File-only partial attempt uses two requests (one feed + one PDF); portal-dedup fixture carries an already-observed feed row to isolate its publication provenance assertion. Controller runner passed all 263 tests across runtime, target-worker and source-portal modules (3 warnings, 13.85s) using isolated PG16 and the existing test-only capacity seam. Black and diff checks pass. No live write/deployment or commit/push.
- R2 F1 repair: a CIA page-1 feed item now sorts before pending CIA stories and archive pages, including a failed page-1 item being retried. Source-portal root priority remains `-2`; only the latest CIA page 1 receives `-3` ahead of it. All other site behavior is unchanged. The regression retains 35 old stories, a page-2 item and the page-1 retry after its first failure; under the unchanged 30-request cap the retry is first, 29 stories process, 6 stay pending, the processed prefix and retry attempt/error record remain, page 2 stays unique, and no additional page-1 poll is inserted. Focused pair passed. Final connected PG16 run: 264 passed, 3 warnings in 15.23s; Black, Ruff and diff checks passed. Current hashes are in `reports/cia-news-discovery-20261106/local-validation.md`. Review 3 is pending. No live write/deployment, commit or push.

\r\n

## 2026-11-06 本机精算解读手动 URL 入口

- 在独立分支 `codex/interpretation-enable-20261106` 为 `article-interpretations` 增加互斥的 `--file-url`，沿本机 stream 传到既有 `ArticleInterpretationService.run(file_url=...)`；保留未传字段时的日轮请求形状，并沿用现有英文翻译与来源/正文校验路径。
- 聚焦相关测试 47 项通过；CLI `--help`、`--json`、Ruff、Black 和 `git diff --check` 通过。验证仅使用模拟生成器，没有真实模型调用、目标写入/同步或 automation 变更。等待独立审核；未提交或推送。

## 2026-11-06 本机精算解读手动同步范围修复

- 手动 URL 流程仅在本轮完成且唯一 ready slot 存在时，把该 interpretation ID 传到 native 精确候选读取；失败/无 ready 时不启动同步。精确读取绕过全局扫描锁和游标读写，原身份校验、ACK 与 writer 保持。
- 一次性导出校验拒绝人工编辑/接受标记，且只接受 validator 正文加服务精确构造的出处尾注。聚焦测试 49 项通过；Ruff、Black、CLI help、导出断言自检和差异检查通过。未运行本机模型、目标写入或 automation，未提交/推送，等待独立复审。


## 2026-11-06 本机解读定向入口代码验收

- 最终file-url回执保留cumulative_outer_attempts，并只以本次实际Chinese prompt数记outer_attempts；本次0不自动sync，原生累计预算/完成receipt不写回、不重置。51项聚焦测试通过（一次faiss DLL初始化瞬时失败后单次重跑通过），Ruff/Black/help/json/diff通过；fresh Sol/high R4 PASS，真实审查4完成/3 CHANGES，裁定及历史报告保存在独立报告目录。
- 一次真实本机IAA新原文Chinese1、English2 outer尝试，中英文native Ready；保留unlabelled_inference/unsupported_number两项nonfatal内容提示，不宣称推断/数字依据完全核实。原生两端各locale只投影一次并各ACK，中国verified、海外zh inserted/en updated。代码末次计数修正不改变已实跑的generator、validator、原文或writer正向路径，没有为它重复生成或重放同步。
- 本机稿和真实生成/同步回执在`reports/local-interpretation-enable-20261106/runs/2026-11-06-real-iaa/`与相邻candidate-run。实际DB/API一次读回仍以其单独readback.json为准；当前代码提交不把尚未完成的排程启用或CI写成成功。任务只做本轮生成/同步，交付后用户编辑不监控、不追同步。


## 2026-11-06 PR471 精确ID缺失回执修复

- 初始手动Copilot请求被API422拒绝；仓库自动review真实在b845 HEAD完成，15分钟反馈快照确认1条scope内问题：精确ID缺失/非Ready不能空集误报全部ACK。已由同一Luna/high worker修复，targeted查status并分别记录not_found/not_ready issue；Ready且已确认ACK及global空扫描语义保持。
- 56项聚焦测试、Ruff/Black/diff通过，fresh Sol/high定点复核PASS；期间既有faiss DLL初始化瞬时失败保留，完整重跑通过。TypeSafe按新证据真实jev1.14选择最小修复；不重请Copilot或开新反馈窗口。
- 修复仅影响未命中/非Ready负路径；本轮真实稿已交付的gen、writer正向路径与既有ACK/DB/API回读证据保持，不再生成、重放同步或读取用户后续稿件编辑。原定10点计划仍待当前HEAD代码检查后正式启用。

## 2026-11-07 Issue #475 — accepted review repairs

- Branch `codex/issue-475-assistant-runtime` now mounts the public Assistant Feature through an admin-only `/api/assistant/runtime/query` path. The normal `/api/assistant/query` and explicit legacy modes remain unchanged. Settings enable/disable updates install or remove the Feature while feedback stays independent.
- The test skill now has `SKILL.md` and `skill.json` loaded by Registry; the runtime loop has no skill-specific code. Finished answers have a distinct `answer` intent and truthful evidence IDs; the UI accepts them without showing a clarification prompt or inventing links.
- Manager validation passed all 134 related backend tests with the isolated PostgreSQL service, all 25 assistant client tests, typecheck, build, Black, Ruff, and diff check. The build retains the existing Vite large-chunk advisory.
- Manager made one bounded structured-output request per current Chat binding using read-only configuration and no quota/database/config writes. Both providers returned parseable JSON, but neither selected the expected fixture tool for the simplified natural-language probe. This prompt did not mirror the Feature Runtime's exact JSON envelope, and the containers run revision `bec94c5`; it is not evidence that the new loop fails, and it does not qualify live tool selection. No retry was made under the one-call-per-site bound.
- Source remains uncommitted for manager review. External repair evidence: `reports/issue-473-480-20261107/issue-475/worker-repair-report.md`.
- Follow-up schema correction: legacy `QueryResponse` again permits only its five original intents; `FeatureResponse` alone permits `answer`. The regression checks the legacy OpenAPI response reference and both model schemas. Focused Python 90 passed (1 PostgreSQL case deselected); Black/Ruff passed. Evidence: `reports/issue-473-480-20261107/issue-475/worker-schema-fix.md`.
- Manager's current-head test logs and sanitized provider results are in `reports/issue-473-480-20261107/issue-475/worker-logs/` and `manager-live-provider-qualification.json`. Source remains uncommitted pending current-head independent review and provider-probe assessment.
- Current provider-adapter repair: only the confirmed top-level `type: json_object` label is removed at the Feature's Chat adapter; all other extra keys remain subject to the core's exact action check. Sanitized regressions passed 47 focused backend tests, Black and Ruff. No live provider was called in this repair. Evidence: `reports/issue-473-480-20261107/issue-475/worker-runtime-adapter-repair.md`.
- Current runtime-prompt repair: the instruction now spells out the exact call/finish/clarify JSON object shapes and requires `action` in every one. An evidence-backed finish without `action` remains invalid; canonical finish succeeds. Focused 49 tests, Black and Ruff passed. No parser relaxation or provider call. Evidence: `reports/issue-473-480-20261107/issue-475/worker-runtime-prompt-repair.md`.


## 2026-11-07 Issue #475 — final local provider qualification and review reset

- The persistent worker repaired the Feature-only Chat adapter to strip only the confirmed top-level `type: json_object` label and updated the runtime prompt to require the exact `action` field for call, finish, and clarify shapes. Core parsing remains strict; a finish object without `action` remains invalid.
- Current local source passed the exact bounded runtime flow against each existing Chat binding: DeepSeek Flash and OpenAI `gpt-6-luna` each made 3 model calls, selected `test_lookup.search` then `test_lookup.detail`, returned evidence `test_lookup:sample`, and finished with an answer matching the observed fixture detail. Final diagnostics and all pre-repair failures are preserved in `reports/issue-473-480-20261107/issue-475/manager-live-runtime-qualification-final.json`.
- Backend suite: 140 passed, 3 existing SWIG deprecation warnings. Assistant client: 25 passed. Typecheck, build, Black, Ruff, and `git diff --check` passed. The build has the existing Vite large-chunk advisory.
- Live qualification ran the current local Runtime/Feature adapter with the servers’ existing read-only Chat configurations; both containers remain at revision `bec94c5d523296dcd1f1d7d42eb770b1b940437b`. It did not exercise the new HTTP route, Host authorization/scope, or quota path; those are covered by backend tests. No deployment, production data/config write, or quota write occurred.
- The reserved R3 reviewer inspected the earlier source snapshot, paused, then became stale after further source changes. Its attempt was officially aborted through `review_cycle.py`; it produced no report and consumed no round. State remains 2 completed reviews / 2 failed cycles. A fresh R3 reviewer is pending final snapshot binding; the inspected reviewer will not be reused.
- Source remains uncommitted on `codex/issue-475-assistant-runtime`; no unrelated changes were noticed. GitHub CI is pending Draft PR publication.
## 2026-11-07 Issue #476 — worker implementation checkpoint

- Branch `codex/issue-476-skill-artifacts`, baseline `fd2f4e5d203e923c42e2c65a557f799d59d9d3e3`. PostgreSQL migration 0008 adds immutable skill releases and revisioned slots. The Assistant Feature resolves a per-run published snapshot from the durable artifact store; import validates registered code, content hashes and UAT provenance before publication. Recovery includes `agent_artifacts` and verifies restored release bytes.
- Isolated PostgreSQL 16 container `issue476-pg16-20261107`: 61 focused tests passed; Black, isort, Ruff and diff check passed. An isolated full backup/verify/restore smoke passed with container-native PostgreSQL clients and read the same published release afterward. The six existing recovery tests requiring local Windows `pg_dump`/`pg_restore` could not pass on this host because those binaries are absent; their first-run failures and the successful container-native smoke are recorded externally in `reports/issue-473-480-20261107/issue-476/worker-logs/`.
- No model/provider, production database, Chat/credential binding or deployment was exercised. Source is uncommitted for manager review. Full evidence: `reports/issue-473-480-20261107/issue-476/worker-report.md`.

## 2026-11-07 Issue #476 — accepted review repairs

- Same worker addressed reviewer F1–F3: UAT receipt must match skill/version, every artifact digest, code SHA, data/KB and model and cannot carry rejected or unknown fields; activation and runtime resolve validate every declared artifact; full backup and verification cross-check PG artifact references against saved bytes. An isolated v7→v8 upgrade retained representative Chat, RAG and feedback rows, and a legacy backup manifest without an artifact index verified.
- Before the repairs, the new F1/F2/F3 negative suites failed 8/2/2 cases respectively. After repair, 75 related tests passed; Black, isort, Ruff and diff checks passed. Container-native full backup→verify→restore of a two-artifact release passed and read both artifacts after restore. The six existing Windows-native recovery tests remain blocked by missing local PostgreSQL client binaries. Evidence: `reports/issue-473-480-20261107/issue-476/worker-fix-report.md`. Source remains uncommitted for fresh review; no production or real-model run.

## 2026-11-07 Issue #476 — inline-only recovery correction

- A published release containing only inline text now permits full backup when `DATA_DIR/agent_artifacts` does not exist; the already-validated external artifact index continues to reject missing or corrupt file-backed content. The new regression failed before the correction and passed after it. The container-native recovery smoke restored both a two-file release and an inline-only release, then read their published content from PostgreSQL.
- Current focused suite: 76 passed; Black, isort, Ruff and diff checks passed. The six existing Windows-native recovery tests remain blocked by absent local PostgreSQL client binaries; no model, production or deployment run occurred. Source remains uncommitted. Evidence: `reports/issue-473-480-20261107/issue-476/worker-r2-fix-report.md`.

## 2026-11-07 Issue #476 — draft lifecycle correction

- `ArtifactStore.import_source(..., draft=True, uat=None)` now stores a non-activatable draft with fixed code/data/model provenance. `validate_draft` locks that row, rechecks the immutable package digest, registered skill and all artifact bytes, then applies the same strict UAT contract before moving it to validated. Existing direct validated import remains supported; activation still requires validated/published. A failed UAT or corrupt artifact leaves the row draft.
- New red-before/green-after draft regression and 77 related tests passed. Black, isort, Ruff and diff checks passed. Container-native external and inline full recovery smokes both passed; six Windows-native recovery tests remain blocked by missing local client binaries. No real model, production or deployment run. Source remains uncommitted; evidence: `reports/issue-473-480-20261107/issue-476/worker-r3-fix-report.md`.

## 2026-11-07 Issue #476 — registered tool contract correction

- `ArtifactStore` now receives the code package's registered Tool objects and requires every declared `tool_id`/executor/arguments model triple to match before source import, draft promotion, activation or active resolution. Three wrong-contract tests failed before and passed after the change. Existing direct and draft valid paths remain accepted.
- Related suite: 80 passed. Black, isort, Ruff and diff checks passed after a format-only correction. Container-native external and inline full recovery smokes passed. Windows-native recovery tests remain blocked by missing local PostgreSQL 16 clients; no real model, production or deployment run. Source remains uncommitted; evidence: `reports/issue-473-480-20261107/issue-476/worker-r4-fix-report.md`.

## 2026-11-07 Issue #476 — empty PostgreSQL release set correction

- PostgreSQL AssistantFeature now uses one `resolve_active()` result unconditionally, including an empty Registry and empty pinned release ID map. A new isolated PostgreSQL regression confirmed the former no-slot path invoked the bundled executor; after correction it cannot invoke that tool. Non-PostgreSQL legacy and published snapshot paths remain covered.
- Focused suite: 81 passed. Black, isort, Ruff and diff checks passed. Windows-native recovery tests remain blocked by missing local PostgreSQL 16 clients; no real model, production or deployment run. Source remains uncommitted; evidence: `reports/issue-473-480-20261107/issue-476/worker-r5-fix-report.md`.

## 2026-11-07 Issue #476 — tool scopes and repeat activation

- ArtifactStore now rejects a candidate tool whose required scopes omit any scope required by its code-registered Tool. Repeating activation of the current release retains the previous release while still incrementing the CAS revision, so A→B→B can roll back to A. Both focused regressions failed before and passed after the fix.
- Related suite: 83 passed; Black, isort, Ruff and diff checks passed. Windows-native recovery tests remain blocked by missing local PostgreSQL 16 clients; no real model, production or deployment run. Source remains uncommitted; evidence: `reports/issue-473-480-20261107/issue-476/worker-r6-fix-report.md`.

## 2026-11-07 Issue #476 — R7 review and current-source recovery validation

- Fresh independent Sol/high R7 review passed all six product files against AC1–AC10; TypeSafe review-summary coverage was 0.93 with no findings. Formal state: 7 reviews completed, 6 requiring changes; R5's separate blocked Judge record remains preserved.
- On the final source at HEAD `fd2f4e5d203e923c42e2c65a557f799d59d9d3e3` and frozen product patch SHA256 `551fdd0bd2733697938be3fba6b035f8a0e9c7f2b8152338390860cc3d592519`, a current-code container-native full backup→verify→restore→readback smoke passed for both file-backed and inline-only releases. Restored release metadata and artifact contents were readable. Source file digests and raw outputs are in `reports/issue-473-480-20261107/issue-476/manager-r7-recovery-smoke-final.json` and `worker-logs/manager-r7-recovery-smoke-final.txt`; the exact task-owned PG16 container is stopped.
- Two earlier smoke attempts did not reach product assertions: one used a Python interpreter without `psycopg2`, and one omitted `PYTHONPATH`; both raw execution reports are retained. The six Windows-native recovery tests still cannot run because local PostgreSQL 16 `pg_dump`/`pg_restore` binaries are absent. No real-model or production run occurred. Product source is committed locally as `39349d6`; push and Draft PR creation remain pending.
## 2026-11-07 Issue #476 — PR #483 official remote-feedback assessment

- The one official Copilot snapshot on PR #483 HEAD `bd20e57315d78ae061e4856712a076dc4ba23e49` yielded two reproducible AC findings: a full 40-character Git SHA-1 code identity was rejected, and concurrent different-skill activation could commit a duplicate tool ID set. Both failed focused isolated-PG tests before repair and passed afterward. Code SHA validation now accepts full Git SHA-1/SHA-256 IDs while artifact hashes remain SHA-256; activation takes a feature/site transaction advisory lock before its existing CAS and set validation.
- Three comments were rejected against current supported workflows: mutable validated payload requires direct SQL outside ArtifactStore; database-only backups intentionally omit files and restore-smoke reports that insufficiency; Assistant Host has only the default site binding (feedback site key is separate). The current focused suite passed 85 tests; Black, isort, Ruff and diff checks passed. External evidence: `reports/issue-473-480-20261107/issue-476/worker-remote-feedback-assessment.md`. No commit, push, PR change, production write, or real-model run occurred in this worker pass.
- The concurrent activation regression now uses an event at the second thread's advisory-lock statement while the first transaction is paused before commit, replacing its timing sleep. With this deterministic overlap, both focused remote-fix tests and the 85-test related suite passed; style and diff checks passed. Test-quality supplement: `reports/issue-473-480-20261107/issue-476/worker-remote-feedback-test-supplement.md`.

## 2026-11-07 Issue #476 — 远端反馈经理裁定与 R8 待审

- 官方一次性 Copilot 快照已完成；经理复核并运行 TypeSafe 远端评估后，AC7 代码 SHA 与 AC4 并发激活两项确认并已修，其他三项因分别要求越过应用写入边界、把 database-only 当完整恢复、或引入当前 Host 不支持的多站绑定而不采纳。TypeSafe摘要与逐项证据：`reports/issue-473-480-20261107/issue-476/manager-remote-assessment-pr483.md`、`typesafe-review-remote-pr483.json`。
- 当前六文件产品补丁冻结 SHA256 `8e3eca16ee34a9c8f8dfbd65b7ba36c027f8acf4652512971e9f861e2f4058db`，用于新的独立本地复审。worker在当前代码树上完成确定性并发红绿与85项相关测试；Black、isort、Ruff、差异检查通过。R7 最新容器恢复证据 `manager-r7-recovery-smoke-final.json` 已通过 file-backed 与 inline-only 两条恢复读回；本轮不改恢复路径，无需重复该 smoke。
- PR 当前仍是旧HEAD `bd20e57315d78ae061e4856712a076dc4ba23e49`，先前5项CI成功、quality-gate仍运行；本次修改尚未提交/推送，新HEAD全部必需CI和R8独立审查待完成。Windows原生恢复客户端、真实模型和生产观察未执行。

## 2026-11-07 Issue #476 — R8 PASS 与 quality-gate 修复

- Fresh R8 独立审查核对冻结的六文件产品补丁（SHA256 `8e3eca16ee34a9c8f8dfbd65b7ba36c027f8acf4652512971e9f861e2f4058db`），按 AC1–AC10 未发现可复现范围内问题；实际审查与探测 turn 均为 gpt-6-sol/high。TypeSafe Jev-latest 无发现，摘要覆盖率 0.83。正式状态为 8 轮完成、6 轮需修改；路由证据、审查报告与 TypeSafe 结果在 Issue 报告目录。
- PR #483 旧 HEAD `bd20e57315d78ae061e4856712a076dc4ba23e49` 的质量检查仅因测试静态迁移清单未含 `0008_agent_skill_releases.sql` 失败。原错误只在测试夹具；同一 worker 增加这一项后，目标测试 1 passed、`tests/test_sqlite_schema_runner.py` 52 passed，Black/isort/Ruff/diff 检查通过。该改动只修正预期清单，没有产品语义变化。证据：`worker-check-repair-report.md` 与 `worker-logs/ci-schema-*.txt`。
- 远端反馈接受的两项产品修正仍在当前隔离工作树中；待分开记录 CI 夹具修复和远端反馈修正后提交推送。最终 PR HEAD 必须通过全部必需检查；不重请 Copilot，不刷新一次性远端反馈快照。Windows 原生恢复测试仍受缺少 PostgreSQL 16 `pg_dump`/`pg_restore` 限制；R7 容器恢复 smoke 早于 R8 产品补丁，不代表当前精确代码重跑。未运行真实模型、生产或部署。

## 2026-11-07 Issue #477 — manager preimplementation assessment

- Active repository/worktree: `AI_actuarial_inforsearch`, branch `codex/issue-477-document-research`, baseline `df2fea2acdd9a61c7ccc58ef2f0b590bc5f08851`. Sibling repositories remain out of scope. Product source has not been edited.
- Source-backed tier: **complex**. The scope crosses KB catalog, Ready publication, Standard RAG, live membership/deletion, skill manifests/executors, and current source/date contracts. Validation will cover the exact SOA target, bilingual location, excerpts/citations, fallback gates, date semantics, follow-up re-evidence, and per-tool scope changes.
- AC7 is unresolved at the boundary: the current Feature endpoint is one-turn and has no conversation ID/context store. A read-only Architect is assessing the smallest compatible context contract; TypeSafe adjudication is required before fixing the implementation worker route.

- AC7 decision: use caller-carried `selected_target` with `kb_id` and `file_id`; each turn revalidates all current access/membership and retrieves fresh excerpts. TypeSafe selected this option (probability 0.71, confidence 0.56, low confidence retained); the manager chose it as the smallest contract within the explicit scope, which does not require server-side continuity or a broader conversation rewrite.

## 2026-11-07 Issue #477 — manager pre-review evidence

- Current worktree remains `codex/issue-477-document-research`; the 12 product/test paths are frozen at source snapshot `6d25c8b88fc2cb4a646658dca0088cd2a2c71fe25476e79e73e48a3d70955e25`. The live SOA probe’s source digest was reconciled to raw file bytes and matches the isolated activation smoke. A narrow regression excludes a real Ready `Acknowledgements` child beneath `Key Findings`.
- Post-fix focused PostgreSQL suite: 130 passed, 4 existing warnings. Black, isort, Ruff, and `git diff --check` passed. Isolated PostgreSQL Skill import/activation and current Host smoke passed; real `search_sections` ran over isolated Ready fixture artifacts, with a deterministic model and no production data.
- Live read-only Host probe against the two existing Chat bindings: China PASS for one SOA query, three model calls, two tools, Ready Key Findings, exact quote verified against the live excerpt, Chinese summary/source link; overseas located and read the same Ready section but final model call returned provider unavailable, so FAIL. Both production `published_time` values are NULL; their `first_seen` values are kept separate. No production database/config/artifact/quota/session/index write occurred. The official route’s live artifact is PARTIAL, not a two-site acceptance PASS.
- Public web Chat remains signed out; deployed production code is an earlier revision. Production artifact activation, HTTP `config.write` route, Standard fallback, dynamic revocation, and production deployment have not been exercised. Fresh independent local review is pending; no commit or PR has been created.

## 2026-11-07 Issue #477 — overseas provider diagnosis correction

- The initial overseas run’s `PROVIDER_UNAVAILABLE` status was traced to the probe’s 700-token override: the third call consumed exactly 700 completion tokens and stopped with `finish_reason=length`; no HTTP status or upstream API error code/type was observed. This is not evidence of a provider outage.
- One bounded retry used the existing configured 1000-token limit without changing the 30-second, four-model-call, or six-tool-call Host budgets. Live find and Ready read succeeded, but the final model output was rejected by the Host as `NO_EVIDENCE` after 814 completion tokens. Raw output was discarded, so the specific invalid evidence ID/shape versus quote mismatch is unknown. No further retry was run; overseas remains FAIL. China’s separate live PASS remains valid. Evidence: `reports/issue-473-480-20261107/issue-477/manager-live-soa-probe-overseas-700-token-diagnostic.json` and `manager-live-soa-probe-overseas-diagnostic.json`.


## 2026-11-07 Issue #477 — R1 fixes recorded, R2 review pending

- The existing Issue worker completed the review-requested fixes; the manager recorded them with the quick-mode lifecycle. Current product/test snapshot is frozen for R2: 12 paths, patch SHA-256 `1a22331332dc36005930fac5f11a843ae9f667c3fd08c8cda91a48cafb53d804`; external manifest: `reports/issue-473-480-20261107/issue-477/r2/source-manifest.json`.
- Focused isolated PostgreSQL regression: 139 passed, 4 warnings. Final targeted Black/isort/Ruff/diff check passed on the four latest-edited files; an earlier style run covered ten files before those edits. Raw logs are retained outside the checkout. No redundant full-suite rerun was made.
- The prior two-site live observation used source snapshot `6d25c8b88fc2cb4a646658dca0088cd2a2c71fe25476e79e73e48a3d70955e25`, before the current fixes. China completed one read-only query; overseas returned `NO_EVIDENCE` after locating and reading the target. The original model payload was not retained. Overall live evidence remains partial and does not validate the current source or establish a provider defect. No production write, configuration change, retry, or deployment occurred.
- A unique R2 dispatch request is frozen at `reports/issue-473-480-20261107/issue-477/r2/review-dispatch-request.json`; awaiting root-controller fresh Sol/high reviewer receipt. No commit, push, or PR yet.


## 2026-11-07 Issue #477 — R2 adjudicated, same worker fixing

- Fresh independent R2 review of the frozen 12-file patch completed with three reproducible AC3/AC7 findings. Native reviewer route and all 21 tool calls were independently audited; no prior review/Judge/worker conclusion or `.hermes` contents were read. Full report and audit remain in the external Issue evidence directory.
- The manager independently reproduced all three findings. The required TypeSafe assessment marked each preliminary valid/in-scope; the actual Jev Judge selected `accept_all_three` (0.67 probability, 0.59 confidence). The existing Issue worker is continuing the fixes; no new worker or reviewer was created for implementation.
- Product source is unchanged since the R2 snapshot. The existing current-source focused result remains 139 passed, 4 warnings; it is not post-R2-fix validation. The old live observation still predates current code and remains partial. No new provider call, production write, or deployment occurred.
- The manager will re-run focused regressions and final formatting/lint checks on the resulting current source, record the fix, then request the next fresh independent local review as required by quick mode.


## 2026-11-07 Issue #477 — R2 accepted fixes, R3 review pending

- The existing Issue worker completed all three accepted R2 fixes for AC3 grounding/citation completeness and AC7 explicit target correction. Official lifecycle recorded the same-worker repair; state is `awaiting_review`, with two completed review rounds and two failed cycles.
- Current 12-file product/test snapshot is frozen against HEAD `df2fea2acdd9a61c7ccc58ef2f0b590bc5f08851`; normalized patch SHA-256 `ffeec36e624058e30845c300fec2c83ed1d1fff8ad5e9dd28cc3460863e6f84f`. Complete file/base manifest and neutral review package are under `reports/issue-473-480-20261107/issue-477/r3/`.
- Final isolated PostgreSQL regression: 143 passed, 4 warnings. Black 26.3.1, isort 8.0.1, Ruff 0.15.12, and 12-path temporary-index diff check passed. No new provider call, production write, deployment, commit, push, or PR occurred.
- Historical live observation predates this source snapshot, is partial, and retained no raw model payload; it is not current-source UAT. `graphify-out/` remains pre-existing/untracked and outside the review. A fresh independent R3 Sol/high review is pending controller dispatch.


## 2026-11-07 Issue #477 — R3 local review active

- Fresh reviewer thread `01a1b80e-fbca-7ec0-87cc-7cbf922350f5` was registered as Sol/high in the official lifecycle; review round 3 is active against the frozen 12-file patch SHA-256 `ffeec36e624058e30845c300fec2c83ed1d1fff8ad5e9dd28cc3460863e6f84f`.
- Reviewer received the controller-neutral AC1–AC8 brief, current source manifest/full patch/current source, and only the permitted three raw evidence files. It was instructed not to read `.hermes`, prior review/Judge/worker/Architect/Copilot/remote conclusions, dispatch/fix-validation metadata, or sibling repositories.
- No source edits, broad test rerun, provider call, production write, deployment, commit, push, or PR occurred during dispatch.


## 2026-11-07 Issue #477 — R3 AC6 finding adjudicated, same worker fixing

- R3 fresh Sol/high review found one realistic AC6 error-path defect: after a unique document catalog hit, a body-read tool exception returned an empty answer and discarded the known source URL. The manager reproduced the exact current `run()` result (`TOOL_UNAVAILABLE`, empty answer; find succeeds/read errors).
- TypeSafe review preliminarily classified the finding valid/in-scope. The required fresh Jev Judge chose `accept_ac6_finding` (0.91 probability, 0.86 confidence); lifecycle disposition is accepted. Evidence is external under `reports/issue-473-480-20261107/issue-477/r3/`.
- The existing Issue worker is repairing this one AC6 path. A fresh local review will follow because the fix changes user-visible error handling. No additional review/Judge outcome, worker, provider retry, production write, commit, push, or PR has been made since R3.


## 2026-11-07 Issue #477 — R3 fix recorded, R4 review pending

- The same Issue worker repaired the AC6 body-read failure path in `loop.py` and added focused regressions. On a matching unique current-turn catalog result, the response now retains the report title and actual source link with an explicit unavailable status; ambiguous and mismatched targets retain the prior error behavior.
- Final isolated PostgreSQL suite: 147 passed, 4 warnings. Black 26.3.1, isort 8.0.1, Ruff 0.15.12, and 12-path temporary-index diff check passed. A current-source stub smoke also returned the located title, source URL, and unavailable status within the same 2 model/2 tool attempts.
- Official lifecycle recorded this material same-worker fix; state is `awaiting_review`, with three completed local review rounds / three changes outcomes. R4 current patch SHA-256: `3e8934ab19061db47e2e276a1a1ce0c047c7227d56f605cbbfc3f120f550eb0c`; the complete neutral brief and source manifest are under `reports/issue-473-480-20261107/issue-477/r4/`.
- No current live-provider/production validation, deployment, commit, push, or PR occurred. The historical live record remains pre-current-source and partial. `.hermes/project-status.md` remains manager-owned; `graphify-out/` remains excluded.


## 2026-11-07 Issue #477 — R4 local review active

- Fresh independent reviewer thread `01a1b823-48d8-7670-8232-b7d2d8b94fb7` is registered as gpt-6-sol/high in the official lifecycle; round 4 reviews the frozen 12-file patch SHA-256 `3e8934ab19061db47e2e276a1a1ce0c047c7227d56f605cbbfc3f120f550eb0c`.
- The reviewer received the controller-neutral current-source brief, manifest/full patch/current files and only the three permitted raw validation records. It must mark each AC1–AC8 inspected or not assessed. Startup exclusions include `.hermes`, prior conclusions, controller metadata and sibling repositories.
- Current-source focused validation is 147 passed with four warnings; pinned style and diff checks passed. No provider/production operation or remote GitHub action was performed.


## 2026-11-07 Issue #477 — R4 findings adjudicated, same worker fixing

- Fresh R4 Sol/high review documented coverage for AC1–AC8 and found two reproducible items: AC6 loses the matched report/link on body-read failure when unrelated catalog candidates were also returned; AC7 ranks rejected SOA reports ahead of the requested ASHK target for the Chinese correction `不是SOA，是ASHK问卷`.
- The manager independently reproduced both on current source. TypeSafe assessed both preliminary valid/in-scope; the required fresh Jev Judge selected `accept_both` (0.60 probability, 0.50 confidence). Official lifecycle records the two accept dispositions and the resolved adjudication.
- The same Issue worker is repairing these two bounded paths and their regressions; a fresh R5 review will follow because behavior and target ranking change. No reviewer PASS, source validation, live-provider call, production write, deployment, commit, push, or PR has occurred since R4.


## 2026-11-07 Issue #477 — R4 fixes recorded, R5 review pending

- The same worker fixed both AC6 and AC7 paths in `loop.py`, `document_research.py`, and focused tests. A body-read failure now uses the unique observed catalog row matching the exact failed target even when unrelated candidates were returned; Chinese `不是…是…` / `不是…而是…` correction phrasing ranks only the corrected target terms.
- Final isolated PostgreSQL suite: 148 passed, 4 warnings. Black 26.3.1, isort 8.0.1, Ruff 0.15.12 and 12-path temporary-index diff check passed. Current-source deterministic smoke verifies the Chinese ASHK correction ranks first and the two-candidate body-read failure returns the matched Survey title/link with an honest unavailable status.
- Official lifecycle recorded the material same-worker fix; state is `awaiting_review`, with four completed local review rounds / four changes outcomes. R5 current patch SHA-256: `e6e12067a988dfd4c0aa0323bef441f6f9ce747e3e79b8ba221f8efb6ba3db83`; full neutral package is under `reports/issue-473-480-20261107/issue-477/r5/`.
- No live-provider/production validation, deployment, commit, push or PR occurred. `.hermes/project-status.md` remains manager-owned and `graphify-out/` remains excluded.


## 2026-11-07 Issue #477 — R5 local review active

- Fresh independent reviewer thread `01a1b833-a312-7892-9085-69a98ef6eb4b` is officially registered as gpt-6-sol/high; round 5 reviews the exact 12-file patch SHA-256 `e6e12067a988dfd4c0aa0323bef441f6f9ce747e3e79b8ba221f8efb6ba3db83`.
- The reviewer received the controller-neutral brief, source manifest/full patch/current source and the three permitted raw evidence files. It must mark AC1–AC8 individually inspected or not assessed. The startup boundary excludes `.hermes`, prior conclusions, controller metadata, and sibling repositories.
- Current-source focused validation is 148 passed with four warnings; pinned style/diff checks passed. No provider/production operation or remote GitHub action occurred during dispatch.





## 2026-11-07 Issue #477 — R9 修复已记录，R10 审查待 controller 派发

- R9 同一 worker 完成 AC5/AC8 修复；经理追加核对发现 Ready 发布后文件标题变化会误报正文不可用，按 AC5 交回同一 worker修正为按已发布章节的目标 URL 判定。最终完整隔离 PostgreSQL 相关测试 249 passed/4 warnings，标题回归 5 passed；Black、isort、Ruff 与 13 路径临时索引 diff check 均通过。原始日志与 SHA 核验见 `reports/issue-473-480-20261107/issue-477/r9/`。
- 官方 lifecycle 已 `record-fix`：stage=awaiting_review，review_count=9/15，failed_review_cycles=9，R9 fixes 影响用户可见状态/来源输出，必须独立复审。交接与经理核验记录为 `r9/worker-r9-fix.md`、`r9/worker-r9-ready-target-followup.md`、`r9/manager-r9-final-fix-verification.json`。
- 本地完整 R10 当前源包待冻结并提交 controller；fresh Sol/high 独立审查须通过 controller 唯一派发及资格回执。没有 reviewer PASS；未提交、推送、创建 PR、部署或写生产数据。`graphify-out/` 保持排除。
## 2026-11-07 Issue #477 — R10 当前源包已交 controller

- R10 neutral packet 已冻结于 `reports/issue-473-480-20261107/issue-477/r10/`，request id `64411f99-8e9d-4613-9175-73f32a0b8e36`；完整 13 路径 patch SHA-256 `71bd4eacaf7a10fe8ecf012200645c5da07ec15d34957f050748861915beecc3`，manifest SHA-256 `9e25142dd649d4cd2cf15a3e6e6bf0bb3361a051eb1bee2770cfea334e044f40`。逐文件 SHA 全匹配，临时索引 patch 重建和diff检查通过，真实 Git index 未变。
- 官方 lifecycle 当前 `awaiting_review`、9/15，R9 material fixes 已记录。已向 controller 发唯一 reviewer request；等待 fresh gpt-6-sol/high reviewer 及匹配的最终独立性凭据，当前不开始或消费 R10。无 reviewer PASS；无 commit、push、PR、部署或生产写入。
## 2026-11-08 Issue #477 — R10 PASS and current-source UAT complete

- Official R10 lifecycle is `local_review_complete`: fresh gpt-6-sol/high review PASS for the exact 13-path patch `71bd4eacaf7a10fe8ecf012200645c5da07ec15d34957f050748861915beecc3`; review_count=10/15, failed_review_cycles=9, no pending fix. TypeSafe Review returned no findings. Authorization-continuity correction and the separate UAT Judge disposition are append-recorded; historical counts and R10 PASS are unchanged.
- Current source Artifact/FeatureHost smoke PASS using an isolated PostgreSQL schema and temp Ready fixtures. `document_research` and `test_lookup` were imported and activated; the Host used real `search_sections`, made two tool calls, and returned the target Survey, exact quote, Chinese answer and soft-stale status. Model was a deterministic stub; production data was not used. Evidence: `reports/issue-473-480-20261107/issue-477/manager-artifact-activation-current-source-stub-aligned.txt`; combined source fingerprint `363e13b129ccdcb41536d19fffecf3d3f1880b027f08753151b838e4eb675348`.
- One bounded, read-only current-source provider qualification ran on each server’s own existing Chat binding. China/DeepSeek passed with a verified target Key Findings quote and Chinese answer (4 model calls, 2 tool calls). Overseas/OpenAI had the same target membership and usable Ready data; after two successful tools, model call 3 exhausted its configured 1000 completion tokens on reasoning and returned `PROVIDER_UNAVAILABLE` (27.95s); recorded as FAIL, not PASS. TypeSafe Judge preferred retaining this as an existing binding limit (0.57 probability, confidence 0.35); manager accepted no code/config change because current evidence does not show that a shorter output contract would avoid provider reasoning truncation. No server binding or production setting was changed. Full report: `reports/issue-473-480-20261107/issue-477/manager-live-soa-current-source-r10-20261108T025133Z.json`.
- All 13 current product/test hashes still match the R10 manifest; current base commit remains `df2fea2acdd9a61c7ccc58ef2f0b590bc5f08851`. No product code changed after review. Next: scoped commit, authorized Draft PR, current-HEAD required CI/remote feedback, then merge/closure/cleanup only through existing gates. No production deployment or data/config/session/quota/index writes.

## 2026-11-08 Issue #477 — Draft PR published

- Scoped product and status changes are committed as `f584ccb5af077e00bc0ebda5fcc7d13301a2278f`; draft PR #484 targets `main` and closes #477. The pre-existing `graphify-out/` directory was excluded from staging.
- Copilot review was requested once at initial PR publication. GitHub returned insufficient remaining quota; Copilot is disabled for the rest of this Issue per the queue policy. No retry was made.
- Initial current-HEAD CI run `42440969115` was in progress at the first status snapshot; combined commit status had not yet reported checks. The R10 independent local PASS covers the exact 13 product/test files; no product source changed after that review. Overseas live-provider generation remains the documented 1000-reasoning-token limitation; no production writes or deployment occurred.
- Next: wait for current-HEAD CI and the single remote-feedback window, resolve only confirmed AC-scoped feedback, then complete merge/closure/cleanup gates.
## 2026-11-08 Issue #478 — R1 F1–F4 repair ready for fresh review

- The same worker corrected all four accepted review findings: source-filtered recent files, Host-grounded resource answers for cited evidence, the exact weekly-updates guide query, and a clickable Weekly link when model prose only names `/weekly`.
- Seven new regression cases failed before the fix and passed after it. The final task-isolated PostgreSQL focused suite passed 355/355 with four existing warnings; Black, isort, Ruff and `git diff --check` passed on the current source.
- Current HEAD remains `977083471cb2ba7c37195bceba16133d06f361ad`; the 35-file source snapshot SHA-256 is `62633a54da3e8a7ccc54296e95a674987a0f8dc5691e88bc42a48cf341e449d7`. No commit, push, PR, deployment or production write by this worker. Evidence and the fixed-source package are in `reports/issue-473-480-20261107/issue-478/`. Fresh independent review is next.

## 2026-11-08 Issue #478 — R3 findings accepted; same-worker repair active

- R3 used a fresh native reviewer thread `01a1bb05-b7eb-75e3-a9f8-ee6c993096cb`, verified gpt-6-sol/high; the controller audited the final route, all actual tool inputs, source hashes and report provenance. Current report SHA-256: `02d39402ddd04e89bc33ef67bf708ce8800711f89ecc29c8d0f2b78817504e5c`. The one-shot reviewer was archived after consumption.
- Current-source manager reproductions confirmed: (1) a false account/delete claim is returned with the current feature-guide citation, (2) a `chat.query`-only identity receives a clickable `/weekly` action despite the route requiring `files.read`, and (3) a 13-source result says total 13 but emits 12 with no truncation notice or complete-source action. Evidence: `reports/issue-473-480-20261107/issue-478/r3/current-review-attempt-1/controller-r3-reproduction.json`.
- TypeSafe local review Jev 1.14 classified all three as preliminary `valid/in_scope` (F1 mapping 0.92/reproduction 0.87; F2 0.93/0.87; F3 0.64/0.85). The separate actual Judge selected `accept_all` (probability 0.57, confidence 0.43) using only the current R3 evidence. The manager independently verified source behavior and accepted all three under AC2/AC3/AC6. Formal lifecycle: review_count=3/15, failed_review_cycles=3, R3 TypeSafe/Judge recorded, stage=`fixing`, no pending adjudication.
- The same selected gpt-6-sol/high worker `01a1ba98-6fac-7673-b9b0-a4ddbd546946` is assigned to fix all three findings. It must ground all guide completion paths, match weekly actions to current permission, reuse source `truncated/action` metadata, inspect same-shaped call sites, and add one isolated AC5 backend test chaining Host draft → simulated edit/explicit confirm → API/PostgreSQL receipt → CLI pull/dedup → reviewed. The confirmation UI and ordinary browser workflows remain #479.
- Current pre-fix source fingerprint is `c571938a6319c5bc931ca24660856b37dff2cc08fbdbd5de09343b420678b00f` at base HEAD `977083471cb2ba7c37195bceba16133d06f361ad`. No current-source live-provider, ordinary UI/browser, real-site production, full-repository suite, commit, push, PR, deployment or production write was performed.

## 2026-11-08 Issue #478 — R3 fixes recorded, R4 review pending controller dispatch

- The same gpt-6-sol/high worker completed accepted R3 fixes for AC2/AC3/AC6 and added the isolated AC5 backend contract test. Guide answers now use exact current section content, weekly actions recheck current identity/scopes before exposing `/weekly`, and truncated source results report shown/total with the full Source Portals action. The AC5 test exercises Host draft → simulated user edit/explicit confirmation → existing feedback API/PostgreSQL receipt → local CLI pull/dedup → reviewed status.
- Official lifecycle recorded the material same-worker repair: `stage=awaiting_review`, `review_count=3/15`, `failed_review_cycles=3`. Current source manifest fingerprint is `0fae32fdf31816196ca0c12351328ba58bfc14cbeca41d646ad28d7778d985bb`; exact changed product/test paths and per-file hashes are in `reports/issue-473-480-20261107/issue-478/r3/fix-f1-f3/source-manifest.json`.
- Pre-fix regressions showed six expected failures; post-fix regressions passed 7/7. Focused isolated PostgreSQL suite passed 368 tests with four warnings; the AC5 integration case passed 1 test with three warnings. Black, isort, Ruff and `git diff --check` passed on current source. Raw logs and hashes, plus independent source/ZIP manifest verification, are retained in `reports/issue-473-480-20261107/issue-478/r3/fix-f1-f3/`.
- No fresh R4 reviewer has been dispatched yet; the current-source neutral packet and route/provenance must be frozen by the root controller before dispatch. No live-provider, ordinary UI/browser, production, full-repository suite, commit, push, PR, deployment, or production write was performed.

## 2026-11-08 Issue #478 — R4 packet frozen; controller route receipt pending

- Fresh R4 review packet is frozen at `reports/issue-473-480-20261107/issue-478/r4/current-review-attempt-1/`. It contains the complete current #478 body, the neutral #479 handoff boundary, current 35-file source manifest/ZIP/patch, and bounded current validation evidence. Source fingerprint `0fae32fdf31816196ca0c12351328ba58bfc14cbeca41d646ad28d7778d985bb`; patch SHA-256 `5a2389bcfdccde703b023691c4b1a8b137726400fbf5749e3f6bee9ab143e265`.
- Unique fresh-review request `f90414ea-d2d3-4a02-ba84-dec80e3d00a4` is in `review-dispatch-request-current.json`. The three Markdown files were mechanically decoded and verified as UTF-8. A fresh reviewer has not been created/started by this manager; wait for controller's exact route and first-input audit receipt, then run official `start-review` and send only the neutral brief.
- Lifecycle remains `awaiting_review`, review_count=3/15, failed_review_cycles=3. No product/test source changed, no tests rerun, and no commit, push, PR, live-provider call, ordinary UI/browser test, production write or deployment occurred during packet preparation.

## 2026-11-08 Issue #478 — R4 local review started; first-input audit pending

- Official lifecycle now records local review round 4 as active for fresh reviewer `01a1bb33-5b17-77e3-9494-7f15ea169b8f`, gpt-6-sol/high. The controller's route probe verified the required model/effort, zero probe tool calls, and idle readiness; the formal task was sent only after that probe.
- The reviewer was instructed to make the brief its first repository tool call and write only `reviewer-round-4.md`. The controller is auditing the actual first input and full source/route provenance now. Until that receipt passes, no review outcome is consumed and no fix is dispatched.
- Candidate remains the same frozen 35-file uncommitted snapshot. No product/test edits, new tests, provider calls, browser/UI checks, production reads/writes, commit, push or PR occurred during review dispatch.

- 主控已完成 R4 reviewer 首批实际工具输入审计：探测阶段 0 次工具调用；实质任务首个工具只读了中立 brief，之后才读 AGENTS、当前 worktree 状态和许可的当前源包材料；实际上下文为 gpt-6-sol/high。首输入凭据保存在 `reports/issue-473-480-20261107/issue-478/r4/current-review-attempt-1/controller-initial-tool-inputs.json`。此为初始审计，不代表最终独立性/报告哈希核验或 PASS；唯一审查者继续审查中。

- R4 独立审查者已完成只读报告，初步结论为 `CHANGES_REQUIRED`，提到一项周报导航结果偏差。主控尚需完成最终来源/工具输入/源码包/报告哈希审计；在此之前不消费报告、不登记 finding、不启动 TypeSafe，也不派同一 worker 修复。

## 2026-11-08 Issue #478 — R4 AC2 finding adjudicated; same worker fixing

- Manager independently reproduced the R4 weekly-query ranking failure in the current Host: `怎么查看周报` returns `features-dashboard` first; a deterministic finish citing only that evidence returns no `/weekly` action despite `chat.query` and `files.read`. This is directly within AC2's Host/backend help-and-action contract; ordinary browser transport remains #479.
- TypeSafe Review 1.14 returned preliminary `valid/in_scope` for F1 (criterion mapping 0.94, reproduction evidence 0.87). The required new TypeSafe Judge for failed cycle 4 chose `accept_ac2_finding` (probability 0.90, confidence 0.85). Both reports and packets are under `reports/issue-473-480-20261107/issue-478/r4/`.
- Official lifecycle is `fixing`, review_count=4/15 and failed_review_cycles=4; R4 report is consumed and the one-shot reviewer was archived. The original implementation worker is fixing only the AC2 guide/Host path and a focused regression; another fresh review will follow because behavior changes.
- R4 also identified distinct validation gaps: no actual local CLI command, live-provider/current-site data run, all-four-switches run, ordinary browser flow or full-repository suite. These remain explicitly unclaimed and are tracked separately from the code finding.

## 2026-11-08 Issue #478 — R5 AC2 fix recorded; live qualification before fresh review

- The same worker changed shared help ranking so exact section-title overlap breaks body-score ties, and added Chinese weekly-query help/Host regressions for authorized and denied users. Ordinary feature-overview ordering remains covered. Only three product/test paths differ from the previous 35-file source snapshot.
- Official material fix validation is recorded (`stage=awaiting_review`, review_count=4/15, failed_review_cycles=4). Current 35-file source fingerprint is `77e753b7d01f1c4c80c22334da3070dee9467fd8186b7071edbe5d06a2c5fdd2`; patch SHA-256 `dcd4875587a736b869bbf449607107d46a54b45df31fb0ddfac71d7d0b29b465`. Manager independently verified the manifest/ZIP/patch and reran the affected isolated PostgreSQL suite: 182 passed, 4 warnings; Black/isort/Ruff and diff check passed.
- No R5 reviewer has been dispatched yet. Before freezing the fresh neutral review packet, the manager will run the AC-required actual local feedback CLI chain, four-switch combination checks, and bounded read-only current-source/current-site model qualification on each server's existing Chat binding. Browser/UI remains #479; no production write/deployment is planned.


## 2026-11-08 Issue #478 — R5 R11 现场验收；AC4 文档引用失败复现

- 当前候选源仍为冻结的 35 文件 R5 指纹 `77e753b7d01f1c4c80c22334da3070dee9467fd8186b7071edbe5d06a2c5fdd2`，现场验证期间未修改产品源码。两站零模型调用预检均通过：当前 `ai-api` 容器、公开 Ready SOA 文档、只读数据库快照及站点 `assistant_agent` 预算均符合预期（3000 初始 token、4000 恢复 token、3 次重试策略、每问 6 次模型请求、180 秒总预算、单请求 60 秒）。
- 正确 R11 raw-SDK 验证记录：`reports/issue-473-480-20261107/issue-478/r5/pre-review-validation/current-live-qualification-r11-20261108T140550Z.json`（SHA-256 `C70A4C57A9D0BE02867F1BC4FDCF1663BE32CA944A22021D9A609BAACD5D33E8`）。中国站 6/6 路径通过、14 次请求（本次上限 18；此前 harness 中断可能已发出最多 6 次）；海外站 5/6 路径通过、13 次请求（上限 24）。原始 SDK create hook、Agent 计数与站点事件对账一致；SDK 重试为 0；每次请求不超过 60 秒；只读快照、容器和源指纹在运行前后未变化。
- 海外站 `document_research` 查找 SOA Member AI Survey 和读取当前 Ready `Key Findings` 均成功，但最终动作以章节 `section_id` 作为 `evidence_id`，Host 要求的是独立生成的工具证据 ID，故两次模型执行均以 `NO_EVIDENCE` 安全拒绝；最终引文也未通过当前摘要的逐字校验。模型均为当前 `gpt-6-luna`，请求使用 3000 `max_completion_tokens`、`finish_reason=stop`，不是 token 截断或超时。
- 同一文档路径的有界复测报告：`reports/issue-473-480-20261107/issue-478/r5/pre-review-validation/current-live-document-research-r11-retry-20261108T141153Z.json`（SHA-256 `83E3E5860F7E3D5B06167D0259470302D0571705A20350B4D42A7A9A3287E9BA`，3 次请求）。两次模型动作中错误证据 ID 指纹均为 `5fc082d1a701`，恰为已返回 `section_id` 的 SHA-256 前缀；两次引用 hash 相同且不是当前 excerpt 的精确子串。此为 AC4“读报告→原文”路径的可复现失败，主控已收到证据并应交给同一持久 worker 修复及添加回归验证；R5 reviewer 尚未派发。
- 另有一次 R11 runner 本地 `query_records` 未初始化，导致首条中国站路径结果未保存。该次只读预检已通过，provider 精确调用数不可恢复、上界 6；记录在 `current-live-qualification-r11.json`（`PRECHECK_PASS_RUN_INCOMPLETE`）。后续中国站上限降至 18 以保证该 R11 批次累计不超过 24。没有生产写入、反馈提交、部署、提交或 PR。
## 2026-11-08 Issue #478 — post-live document quote repair ready for review

- Same worker traced two read-only live `NO_EVIDENCE` answers to an explicit Chinese quote request bypassing the guarded current Ready excerpt path, plus a prompt that confused content-bound evidence IDs with section locators. The Host correctly rejected the nonexact quote and wrong ID.
- Two new regressions failed before the product edit and passed afterward. Final isolated PostgreSQL affected suite: 208 passed, 4 existing warnings; Black, isort, Ruff, and whitespace checks passed. Only the agent loop and document research tests differ from the prior R5 source snapshot.
- Exact 35-file source package and validation logs: `reports/issue-473-480-20261107/issue-478/r5/post-live-document-quote-fix/`; fingerprint `fd8da0f97b915c977a7e99e07c0b22ed6ac47a0de1e27e6b20e14514e7dd7454`. HEAD remains `977083471cb2ba7c37195bceba16133d06f361ad`; no live retry, commit, push, PR, or production operation. Fresh independent review is next.


## 2026-11-08 Issue #478 — post-fix R11 document flow passes both sites

- On source fingerprint `fd8da0f97b915c977a7e99e07c0b22ed6ac47a0de1e27e6b20e14514e7dd7454`, the manager ran one bounded R11 `document_research` check per site: overseas 4 provider calls, China 4, 8 total within the controller-selected 12-call cap. Both passed with exact quote validation; `find_documents` and `read_document_sections` succeeded on the current Ready SOA source. Current source/containers, read-only database snapshots, Host/runtime counters and provider event reconciliation passed; no production writes, feedback submission, quota/session/artifact writes or deployment occurred.
- Reports and hashes: overseas report `current-live-document-research-r11-post-fix-20261108T143003Z.json` SHA-256 `4536cf41ffba27446ec1a6b9998087b4739748c58d27d8a231f93e4ae2eda9cd`; China report `current-live-document-research-r11-post-fix-china-20261108T143304Z.json` SHA-256 `43ffacc56e298101241e8925bf756b2c1e55a9bc044b52833c2687afcaa86efc`. Call journals are stored beside them. These checks cover only `document_research` on the fixed source; the earlier 6-path R11 results remain tied to source fingerprint `77e753…` and are not presented as a full rerun of all six paths.
- The 35-file patch/package and focused validation remain frozen and verified: patch SHA-256 `7fe8b670a3684030a4358f3eb7796621738c803d33049023f4053b921f8f0116`; focused PostgreSQL suite 208 passed, 4 existing warnings; two new regressions failed before and passed after. Current source is ready for a fresh independent R5 review. No commit, push, PR or production action occurred.

## 2026-11-08 Issue #478 — R5 packet ready; verified reviewer route needed

- The neutral current-source R5 packet is frozen at `reports/issue-473-480-20261107/issue-478/r5/current-review-attempt-1/`; it contains the complete product patch, the 35-file source package, Issue/AGENTS materials, worker/test evidence and both current-source site reports. It excludes prior reviewer and Judge reports.
- The configured independent reviewer must be gpt-6-sol/high. The Issue runtime audit records that `collaboration.spawn_agent` did not honor requested model/effort overrides; a route-only probe returned both values unverified and read no repository material. No review was started or counted; lifecycle remains `awaiting_review`, `review_count=4/15`, `active_review=false`.
- The Codex app route can set and verify the required model but creates a separate visible task. Waiting for the user to explicitly authorize that task before dispatch. Evidence: `reports/issue-473-480-20261107/issue-478/r5/controller-r5-reviewer-route-readiness.json`.

## 2026-11-08 Issue #478 — R5 dispatch packet finalized

- Updated the packet’s `issue.json` from the current GitHub fetch (`updated_at=2026-11-08T11:46:37Z`; full 1,868-character body includes the authorization update, phased #478/#479 boundary and AC1–AC6). The packet now contains only the neutral brief, AGENTS, current Issue, complete patch/source package, 208-pass focused log, neutral current-candidate validation summary, and the two current-source site reports/journals.
- The review brief sets the first-input rule and blocks `.hermes`, `graphify-out`, earlier review/fix/worker/manager history, Judge/dispatch artifacts and broad reports browsing. It allows only the enumerated current packet plus source files listed in the current manifest.
- A unique dispatch request and manifest hash are now ready for the main controller. This preparation did not start or count a review; lifecycle remains `awaiting_review`, count 4/15. No source, test, or live-provider changes were made during packet correction.

## 2026-11-08 Issue #478 — R5 packet handed off for controller dispatch

- The request is `reports/issue-473-480-20261107/issue-478/r5/review-dispatch-request-r5.json`, request ID `ab193fe4-6c94-474e-aed2-b1073e44bc62`. Packet is `reports/issue-473-480-20261107/issue-478/r5/current-review-attempt-1/`; its 12-file manifest SHA-256 is `f61698ffa021c131e2fd934ca0bff6ef891c0668ec762486fd0685151e97734f`. All listed file hashes and the current GitHub Issue snapshot were verified.
- Per the latest steering, dispatch belongs to the main controller. This packet-preparation step did not start/count a review or create a reviewer. Lifecycle remains `awaiting_review`, review_count `4/15`, active review false.

- Correction to the earlier route note: latest steering assigns dispatch to the main controller; the packet request is ready at `reports/issue-473-480-20261107/issue-478/r5/review-dispatch-request-r5.json`. No reviewer has been dispatched and the local review count remains 4/15.

## 2026-11-08 Issue #478 — reviewer route correction

- The prior note requesting a new user authorization is superseded: the user already authorized the quick Issue workflow and fresh reviewer delegation. Do not ask again.
- `/root/r5_reviewer_route_probe` was a completed route-only probe, not a reviewer. Model/reasoning stayed unverified; it read no repository files, made no substantive tool calls, and produced no review report. Its result is preserved but not consumed.
- Main controller alone creates the native fresh gpt-6-sol/high reviewer. This manager will reserve the official review only after receiving the exact reviewer UUID and initial-input receipt. No review has started; count remains 4/15.

## 2026-11-08 Issue #478 — R5 review officially started

- After the main controller supplied the exact native reviewer UUID and initial route receipt, official `start-review` reserved R5 for `01a1bbae-3380-7a33-9ec2-dcec3442dee3` on `local`, gpt-6-sol/high. Initial probe was 0 tool calls. State is `local_review`, active round 5; completed `review_count` remains 4/15 until a qualified report is consumed.
- The read-only assignment was sent to that exact thread. Its first substantive tool call is required to read only the absolute `review-brief.md`; it must inspect the full 128,521-byte patch in segments and write only `reviewer-round-5.md`. Main controller has been asked to audit the actual first tool input. The initial dispatch receipt remains `qualified_independent_review=false`, `final_independence_audit_pending=true` until the final actual-input/source/route/report SHA audit completes.
- Same persistent implementation worker remains selected. No product source changed; no provider/service/production operation, test run, commit, push, PR, or merge occurred during dispatch.

## 2026-11-08 Issue #478 — R5 first-input gate passed; final audit pending

- Main controller’s `r5/controller-initial-tool-inputs.json` confirms both actual turns used gpt-6-sol/high. The first substantive tool call read only the absolute `review-brief.md`; subsequent calls read packet AGENTS/worktree status, only the current whitelist, and verified the complete patch byte/line/hash and HEAD. It found no access to `.hermes`, graphify, prior history or dispatch history.
- This passes only the first-input gate. The reviewer is still inspecting the candidate; final current-source/route/report SHA qualification remains pending. Do not consume a reviewer report or finish the round until that full receipt arrives.

## 2026-11-08 Issue #478 — R5 report returned; final qualification pending

- The sole R5 reviewer has completed and reported its result. Report path: `reports/issue-473-480-20261107/issue-478/r5/current-review-attempt-1/reviewer-round-5.md`; reviewer-reported SHA-256 `7a56088193b145ac6469df33f3fef76677fa44fb229391330e5cc88f746b0bdb`.
- Main controller has been asked to verify all actual inputs, current source, route and report hash and send the final qualification receipt. The report body/finding has not been consumed; no review was finished and no fix was dispatched. Official R5 remains active, completed count 4/15.

## 2026-11-08 Issue #478 — R5 AC2 finding accepted; same worker fixing

- R5 report passed the main controller’s final route/source/input/report-hash audit and was formally consumed. Outcome `changes`; review_count=5/15, failed_review_cycles=5, `needs_fix=true`.
- Manager independently replayed exact English and Chinese weekly questions through the current Host. Both retained the `weekly-reports` citation and clickable action while omitting the file-reading instruction present in the current guides and Issue AC2 usage requirement.
- TypeSafe Review Jev 1.14 classified F1 valid/in_scope (criterion mapping 0.96, reproduction evidence 0.88). Because this is the fifth failed review cycle, TypeSafe Judge Jev 1.14 selected `accept_ac2_finding` (confidence 0.92); lifecycle recorded the adjudication as resolved. Both result packets are under `reports/issue-473-480-20261107/issue-478/r5/`.
- The one-shot R5 reviewer is archived. The confirmed AC2 Host answer omission is going to the same persistent senior worker for a minimal English/Chinese Host regression and repair. AC5 observations remain coverage notes, not a second finding; manager will verify the existing isolated feedback-chain evidence and any needed final-candidate rerun separately. No code edit or production action occurred during adjudication.
## 2026-11-08 Issue #478 — R5 AC2 file-reading fix ready for controller check

- Same persistent worker fixed the sole accepted R5 AC2 finding: the Host's English and Chinese weekly-guide answer now tells users with access to open a listed file for its details, source link, and available preview or Markdown. No #479 UI flow or AC5 coverage note was changed.
- The exact English and Chinese questions across four snapshot states failed 8/8 before the Host edit and passed 8/8 afterward. Final isolated PostgreSQL affected suite: 186 passed, 4 existing warnings; Black, isort, Ruff, and whitespace checks passed.
- Report and verified 35-file source package: `reports/issue-473-480-20261107/issue-478/r5/fix-ac2-file-reading/`; fingerprint `c88b79438a6d8b9c06e7a2a95907b7ff9194340283fc1298e9df01b3f565e257`. Only `ai_actuarial/features/assistant/feature.py` and `tests/test_assistant_agent_runtime.py` differ from the prior source manifest. HEAD remains `977083471cb2ba7c37195bceba16133d06f361ad`; no provider/production operation, commit, push, PR, or lifecycle change. Controller check and fresh R6 review are next.

## 2026-11-08 Issue #478 — AC2 weekly reading step validated; R6 packet ready

- The same senior worker added the missing conditional listed-file reading step to the English and Chinese Host weekly guide answer and extended the existing weekly state test across both languages and all four snapshot states. Only `ai_actuarial/features/assistant/feature.py` and `tests/test_assistant_agent_runtime.py` differ from the preceding 35-file current-source snapshot.
- The eight regressions failed before the answer change for the expected missing instruction and passed after. The manager independently reran the eight cases and the related isolated-PostgreSQL suite (186 passed, 4 existing warnings); Black, isort, Ruff, whitespace checks and all four assistant/feedback switch combinations passed on the frozen current candidate. The source archive/manifest hashes and reverse-applicable full patch were independently verified.
- Current source fingerprint: `c88b79438a6d8b9c06e7a2a95907b7ff9194340283fc1298e9df01b3f565e257`; full patch SHA-256 `fe4805c0d0cab3913d227a7c09d5a4f99e7f9c69737db06995172351075d92c9`. Manager validation: `reports/issue-473-480-20261107/issue-478/r6/manager-fix-validation.json`.
- AC5 actual subprocess feedback CLI evidence and current-candidate feature-switch results are preserved in the neutral packet. China and overseas `document_research` live checks each passed with four calls on fingerprint `fd8da0f97b915c977a7e99e07c0b22ed6ac47a0de1e27e6b20e14514e7dd7454`; this is not represented as a full live rerun on the exact current fingerprint. No new live model call or production operation was made for the localized Host text change.
- Official lifecycle recorded the material same-worker fix and is `awaiting_review`, completed review count `5/15`, no fix pending. R6 packet is `reports/issue-473-480-20261107/issue-478/r6/current-review-attempt-1/`, packet manifest SHA-256 `05ef005a3cbf9352ba73d8396d0e30c627aa8809a6b160750dc5647bab67c410`, request ID `ee3f94dc-5998-462c-8850-6cafa22f91cb`. It contains 20 hashed evidence files, the current Issue snapshot and complete patch/archive, while excluding `.hermes`, prior reviewer/Judge reports and prior history.
- Next: main controller creates one fresh read-only gpt-6-sol/high reviewer, audits its first actual tool input and final source/report route, then formally consumes the qualified R6 result. No commit, push, PR, or merge has occurred.

## 2026-11-08 Issue #478 — R6 independent review started

- The main controller created fresh read-only reviewer `01a1bbd0-e1e8-72d2-90b4-c486f70141ad` on `local` with gpt-6-sol/high. The initial route probe made no repository tool calls. Official lifecycle reserved R6; `review_count` remains 5/15 until a qualified report is consumed.
- The first substantive repository tool call read only the absolute `review-brief.md`. The next calls read only the packet AGENTS, current Issue snapshot, current candidate summary, packet manifest, source manifest, and complete patch. The reviewer is reading the frozen archive/patch and has been instructed to write only `reviewer-round-6.md`; final source/route/report qualification remains pending.
- Packet request `ee3f94dc-5998-462c-8850-6cafa22f91cb`, manifest SHA-256 `05ef005a3cbf9352ba73d8396d0e30c627aa8809a6b160750dc5647bab67c410`; source fingerprint `c88b79438a6d8b9c06e7a2a95907b7ff9194340283fc1298e9df01b3f565e257`. No product source changed while dispatching.

## 2026-11-08 Issue #478 — R6 AC2/AC4 finding confirmed; same worker fixing

- The qualified R6 gpt-6-sol/high reviewer found that a same-turn `usage_navigation.guide` + `resources_updates.weekly` answer replaces the weekly guide instructions with the data summary. The manager independently replayed the exact English and Chinese paths on source `c88b79438a6d8b9c06e7a2a95907b7ff9194340283fc1298e9df01b3f565e257`: both retained the current-period summary and clickable `/weekly` action but lost older-period selection and listed-file reading instructions. Reproduction: `r6/manager-r6-finding-reproduction.json`; qualified review SHA-256 `8555b62c88282a7d32e73ce39c7a15e0db43ab24c8af727fbcca253b9316c726`.
- TypeSafe Review Jev 1.14 assessed F1 valid/in_scope (criterion mapping 0.95, reproduction 0.87, in-scope probability 0.84). Required Judge adjudication for the repeated failed cycle selected `accept_ac2_ac4_finding` (probability 0.97, confidence 0.96). Inputs/results are in `r6/typesafe-review-r6-*` and `r6/typesafe-judge-r6-*`; official state is `fixing`, review_count 6/15, failed cycles 6, no adjudication pending.
- The same persistent worker is fixing only the AC2/AC4 Host path and a bilingual paired-tool regression for published/no-snapshot cases. Weekly-only answer behavior, current access checks, and the `/weekly` link gate must remain intact. R6 reviewer is completed and archived. No live call, commit, push, PR, merge, or production operation occurred.
## 2026-11-08 Issue #478 — R6 AC2/AC4 combined weekly fix ready for controller check

- The same persistent worker repaired the accepted R6 finding in the Host's guide + weekly-data answer. The combined answer now retains View all, historical selection and listed-file reading steps alongside the Host-verified published/no-snapshot/no-new state. Guide-only and resource-only behavior and the existing access gate remain intact.
- Six English/Chinese combined-path regressions failed before the product edit and passed afterward. The related isolated PostgreSQL suite passed 192 tests with 4 existing warnings; Black, isort, Ruff and whitespace checks passed. Six exact local Host answers were captured without a Provider call.
- Report and verified 35-file source package: `reports/issue-473-480-20261107/issue-478/r6/fix-ac2-combined-weekly/`; fingerprint `cca2e56eb6663cb25a52413ae453ef449b6fa7115102d1ade0645111ccb3dd69`, full patch SHA-256 `3cb0c4b2f6ea636df4d3355a23c5db72d4cd928e4a3e8275fa4dd09753b7030a`. Only Host feature and Host test differ from the prior snapshot. HEAD is still `977083471cb2ba7c37195bceba16133d06f361ad`; no production/live Provider operation, lifecycle change, commit, push or PR. Controller check and R7 neutral packet preparation are next.

## 2026-11-08 Issue #478 — material fix recorded; R7 request prepared

- The official `record-fix` entry uses the same `gpt-6-sol` / `senior_worker` / high worker. It records a material behavior change and moves the Issue to `awaiting_review`; the review count remains 6/15, failed cycles remain 6, and no adjudication is pending.
- The manager independently reran the six bilingual weekly-guide/data cases (6 passed) and Black, isort, Ruff, and `git diff --check`. The R7 request includes the complete current GitHub body, frozen 35-file source, full candidate patch, current green logs and historical validation by its original source fingerprint.
- R7 request `issue-478-r7-20261108-cca2e56e` is at `reports/issue-473-480-20261107/issue-478/r7/review-request.json`; packet manifest SHA-256 `f1115e1dccf0bd523833f06f7dbdff8c3d5c4d766cead290cecfa12ae6b67e20`. The review packet contains no `.hermes`, prior reviewer report, Judge result, or manager fix report. The program controller must verify and dispatch the fresh reviewer.
- Current-source evidence is fixture Host tests plus the isolated PostgreSQL suite; no current-source Provider, production, or browser run was made. Earlier dual-site Provider results use `fd8da0f...`; earlier R11 partial results and actual feedback CLI use `77e753b...`; neither is represented as validation of current source `cca2e56e...`. No commit, push, PR, merge, or production operation occurred.

## 2026-11-08 Issue #478 — R7 independent review underway

- Official `start-review` is recorded for review round 7, reviewer `01a1bbfa-3184-7d22-a8c5-769dfa4d0a4d` (`gpt-6-sol`, reviewer, high). The controller's initial route receipt is qualified for this request; it has not yet completed the final actual-input/source/report audit.
- One substantive read-only task was sent, with the first-tool requirement limited to the absolute R7 `review-brief.md`. No reviewer conclusion has been consumed and no TypeSafe review has been run for R7.
- Candidate source and packet remain unchanged. Wait for the exact report and controller final audit before consuming the review or taking the next workflow step. Review count remains 6/15 until formal completion; #479 remains unstarted.


## 2026-11-08 Issue #478 — R7 passed; current-source acceptance coverage reviewed

- Official lifecycle is `local_review_complete`: 7 completed local reviews and 6 failed review cycles. **Only R7 passed**; R1–R6 findings and failures remain unchanged. The qualified fresh Sol/high reviewer is archived. TypeSafe Jev 1.14 returned no findings and Noul coverage 0.51; keep that value as uncertain support, not an acceptance PASS or a fixed block threshold. No repeat Judge was needed.
- Frozen candidate remains source fingerprint `cca2e56eb6663cb25a52413ae453ef449b6fa7115102d1ade0645111ccb3dd69`, all 35 file hashes unchanged. R7 report SHA-256 is `efb0350a4814132c83081302a1e59202f6e4dd5c571abdd8fa22208fbfc62757`.
- Independent AC1–AC6 coverage check found no additional acceptance-mapped source issue. AC1 discovery uses the generic manifest `catalog_discovery` result contract; the independent registry and third-name catalog tests cover loop-free extension, body read and follow-up. The earlier architecture note about finder-name allowlists does not apply to this candidate. AC2/AC6 are covered by current help/Host/access/failure tests, six bilingual R6 regressions, four switch combinations, and current source focused tests.
- AC3 actual-site resource paths were exercised on source `77e753b7d01f1c4c80c22334da3070dee9467fd8186b7071edbe5d06a2c5fdd2`; those results remain historical. Resource skill manifests/executors are unchanged in the current candidate; current Host grounding, date distinctions and empty states have current-source tests. No exact-`cca2` live-provider result is claimed.
- AC4's repeated overseas quote failure on `77e` preceded the targeted loop/prompt repair. The `fd8da0f97b915c977a7e99e07c0b22ed6ac47a0de1e27e6b20e14514e7dd7454` post-repair validation passed exact quote checks with four read-only model requests on each site. From `fd8` through `cca2`, `loop.py`, the document-research executor and focused document tests are unchanged; current-source tests cover the two-turn discovery/read/follow-up link and the bilingual guide+weekly follow-up path. These live outcomes are not relabeled as exact-`cca2` runs. Ordinary Chat/browser continuation remains #479.
- AC5 has a current-source Host draft → simulated edit/confirm → PostgreSQL receipt → local pull/dedupe → reviewed contract test, plus a separate actual CLI subprocess run against loopback FastAPI and isolated PostgreSQL. Current-source focused suites passed 167 tests with 3 warnings; the CLI check, four switch combinations, six weekly regressions, related 192-test PostgreSQL suite, and static checks passed. Detailed evidence and source-boundary decision: `reports/issue-473-480-20261107/issue-478/r7/current-source-ac-coverage.json` and `r7/post-review-verification/`.
- No current-source real Provider call, ordinary browser test, production write or deployment was performed. The unchanged affected-path evidence plus current-source regressions is sufficient for this Host/backend boundary; proceed with the authorized commit, Draft PR and normal CI/feedback/merge gates.

## 2026-11-08 Issue #478 — PR #485 ready; initial remote feedback assessed

- Commit `ac692ff7bdbebb8bb8123958693122741aed3421` was published in ready PR [#485](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/485), whose body contains `Closes #478`. No product source changed after the R7 review.
- The one remote-feedback snapshot, `r7/initial-remote-feedback-pr-485.json`, contains only Copilot's notice that review was unavailable due to quota; it is a service-status notice rather than an AC1–AC6 code finding. The same implementation worker's disposition is in `r7/remote-feedback-worker-assessment-pr485.md`; TypeSafe Jev 1.14 assessed summary coverage at 0.87 in `r7/remote-typesafe-result.json`. The snapshot had no Issue comments or review threads. Copilot was not retried and the feedback window was not reopened.
- CI run `42502343477` was running on `ac692ff` when this status was recorded: dead-code files/symbols, Python, frontend, and Office jobs had passed; unified quality-gate remained in progress. Merge remains gated on passing current-HEAD checks and a fresh zero-thread query.
- The initial snapshot is the only remote-feedback fetch for this PR. No current-source real Provider call, ordinary browser test, production write, or deployment is claimed; ordinary Chat/browser continuation remains #479.
## 2026-11-09 Issue #479 — R7 CI and one-shot UAT local recovery pending review

- On `codex/issue-479-assistant-ui` at starting HEAD `0fc00de`, the worker reproduced the three required dead-code symbol findings, kept `Query` internal, and added exact FastAPI/Pydantic whitelist references. The symbol gate now passes with zero findings; the versioned route and validator are exercised by the Assistant runtime tests.
- The saved China Q4 overview selected feedback, features and Weekly help but returned only Weekly. A red bilingual regression reproduced the loss; the Host now combines selected non-Weekly help with Weekly guide/current data while retaining the access and link gate. Six final overview variants pass.
- An independent offline Weekly browser fixture reproduced the early-empty timing race and passed the response-based wait plus genuine-empty control. The original one-shot UAT artifacts and driver remain unchanged. Q2/Q3 fallback quotes and citations are verified against saved current excerpts, but raw draft/verifier output is absent; no root cause or real-model PASS is claimed.
- Related non-PostgreSQL tests: 219 passed, 2 existing PostgreSQL variants excluded because `POSTGRES_TEST_URL` is unset. Typecheck, build, Black, isort, Ruff, diff check, symbol gate, and offline browser stub passed. Source changes are uncommitted. Details: `reports/issue-473-480-20261107/issue-479/r7-ci-uat-recovery/worker-report.md`.
## 2026-11-09 Issue #479 — current body publication-date follow-up validated locally

- The saved China Q2/Q3 citations have null `source_date`; Q3 requested an explicit unknown. The Host now states the publication date or “not recorded” in the answer, using only the final selected body evidence ID's current `SourceCitation.source_date`. Eight bilingual/date/fallback cases failed before the change and pass after; a second-read case prevents old evidence dates from leaking, and the revocation control confirms no date/citation after `SCOPE_REVOKED`.
- The offline driver copy ran a synthetic Chinese Q2 through the actual guarded loop with three fixed model callbacks. Draft fields, verifier raw/parsed/valid result and synthetic request IDs are preserved under `final-current-uat/offline-recovery/`; physical provider/site/API calls were zero. This accepted control does not explain the original real-model `SUMMARY_UNVERIFIED` results.
- Final non-PostgreSQL related suite: 228 passed, 2 existing PostgreSQL variants excluded for missing `POSTGRES_TEST_URL`. Symbol gate, typecheck, build, Black, isort, Ruff, diff check and offline Weekly race control passed. All work remains uncommitted; details: `reports/issue-473-480-20261107/issue-479/r7-ci-uat-recovery/publication-date-followup.md`.

## 2026-11-09 Issue #479 — current-body publication-date follow-up dispatched

- The saved current-body evidence shows a null publication date in both matching catalog rows and the returned citation, with no explicit unknown notice. This is independently supported by the existing SourceCitation/body rendering path; the Q2/Q3 SUMMARY_UNVERIFIED cause remains unknown.
- The same worker received a scoped follow-up for a minimal date fix and tests, plus synthetic offline Q2 verifier evidence. Delivery succeeded; the immediate readback showed the worker turn active but no acknowledgement yet. No waiting was done.
- The previous CI symbol, Q4 overview and offline Weekly race work remains uncommitted in the issue worktree. The manager did not run tests, modify source/tests, call live providers/sites, or change the original UAT artifacts. See reports/issue-473-480-20261107/issue-479/manager-0fc00de-body-date-followup-handoff.json.

## 2026-11-09 Issue #479 — R8 manager local verification complete; check repair pending

- Independent unfiltered five-file PostgreSQL suite passed: 256 passed, 0 failed, 0 deselected, 4 warnings. Owned temporary container `d01275a067f714130b8eba5e0b9a2acb75952dc1b84da2db27b08ca4a411940f` used official state manager_id, loopback 55483 and tmpfs only; it was stopped/auto-removed and the port is free.
- `npm run dead-code:check`, `npm run typecheck`, `npm run build` and the two requested Vitest files passed (52 tests). Black/isort and Ruff on feature/tests passed. The symbol whitelist has the same 53 E402 Ruff baseline findings as original HEAD; Ruff with only E402 ignored passes. `git diff --check` passed.
- Offline Weekly race reproduced RED/GREEN/GREEN; synthetic Q2 accepted control passed with 3 fixed callbacks and 0 physical provider requests. The original real Q2/Q3 verifier cause remains unknown; no live UAT was run.
- All five approved paths are the only worktree changes; no untracked files. Next step is one scoped commit, verify Draft PR #486 still points at 0fc00de before a normal push, then record check repair and freeze the neutral R8 package. Current-head remote CI is to be recorded as observed without waiting.

## 2026-11-11 server deployment follow-up

- The user authorized direct production deployment and requested one durable backup on local D:. The single package is `D:\AI_actuarial_inforsearch-backups\issue480-prod-20261110`; its payload manifest and archive checks passed. Database dumps are transaction-consistent; the China file archive was captured while the app was live and is not an atomic file snapshot. No full restore drill was run.
- Removed only AI InfoSearch backup directories from both servers and disabled the overseas AI backup timers. China Marathon backups and unrelated project backups remain. A failed overseas deploy attempt left no server snapshot files; the temporary directory was removed.
- China root scripts `/home/ubuntu/deploy-marathon-calendar.sh` and `/home/ubuntu/deploy-incidence-tables.sh` passed syntax checks and read-only preflight. Marathon check resolved GitHub `main` to `d2fc1e26807e8ff57d922427b4a57bfa2581bad0`; Rate Atlas is on release `2568fff86138e20fbb93dc5f4e67c7d40dab09ed`.
- Overseas `/root/deploy-ai-actuarial-inforsearch.sh` now accepts check options in either order and refuses deployment when live containers are not owned by the expected Compose project. Its `--check codex/issue-480-assistant-uat` exits 3 on that runtime-owner gate. A previous deploy invocation failed at recovery snapshot setup due a missing Python YAML dependency before build or service replacement. The API stayed healthy; home and API health returned HTTP 200 afterward.
- No AI InfoSearch production deployment or provider-backed UAT completed. China still has four runtime overlays based on older code that conflict with the candidate. Overseas uses manually managed containers; the repository Compose deploy path cannot take over safely. Climate Monitor remains behind documented cutover and scheduler gates. Meeting has no identified GitHub repository.
- Created deployment Skills under `C:\Users\ferry\.codex\skills` for AI InfoSearch, Marathon Calendar and Climate Monitor; updated the existing Rate Atlas Skill. All four passed `quick_validate.py`.
- This follow-up changed no product source files. Issue #480 live UAT remains incomplete and must not be recorded as passed or ready to merge.

## 2026-11-11 #480 database and deployment alignment

- `POSTGRES_TEST_URL` is only for PostgreSQL integration tests: helpers create isolated `test_*` schemas and drop them at test teardown. Both production APIs use `DATABASE_URL` to their respective server PostgreSQL instances (`aiinforsearch-postgres16` / `ai_actuarial`); the two instances are separate.
- The local workstation check found no PostgreSQL process or listener on ports 5432 or 55432, and no database dump in this repository. The local database endpoint/snapshot is therefore not available to link. Production rollout retains each site's existing database connection rather than redirecting to an unverified source.
- Both production hosts now have the same root deployment script (SHA-256 `9daf485ba122ebfe42f7689906bdcb2347d993237bb8435f8d198546b7fb5ec3`). The candidate Compose override binds API and frontend only to loopback, attaches API to the existing PostgreSQL network, and keeps Caddy independently managed.

## 2026-11-11 #480 review follow-up on cc0d239

- Fresh independent review found four issues. TypeSafe Jev 1.14.0 selected `accept_narrow_repair` for the upgrade bootstrap, shared Caddy network, dated catalog fallback, and organization coverage, with confidence from 0.94 to 0.98. The decision SHA-256 is `8f42fe253484f3f39cffc92fb21dcfaaf5519ed806da1deded897bacf1958a3c` in `reports/issue-473-480-20261107/issue-480/typesafe-review-cc0d-followups-20261111/decision.json`.
- Five regressions failed on the reviewed candidate and passed after repair. The runbook prepares the PostgreSQL bridge before invoking the old updater, and the production override keeps the existing app bridge settings. Recent and catalog fallback queries use the same rolling UTC first-seen rules. The seven-day organization list uses a grouped query across the matching rows and keeps three file cards.
- The local `npm run dead-code:symbols` command reproduced the CI failure on the Pydantic `window_days` field. The single documented whitelist reference cleared it. Both symbol checks passed with zero baseline findings.
- All 315 focused tests passed with isolated PostgreSQL 16. Local Compose 5.5.1 recreated API and frontend while preserving the shared network and the running Caddy container. Test containers, networks, volumes, and the loopback database port were cleaned up. Provider-backed UAT and production rollout remain pending.

## 2026-11-11 #480 review follow-up on 980d9e1

- TypeSafe Jev 1.14.0 selected `accept_narrow_repair` with confidence 1.00 for canonical source scope, collection versus publication timing, and explicit development Compose selection. The decision SHA-256 is `a2008d741bb1784e13e5d8ad9e6fd6b7c65609e23605aef2f6885063df80c2a1` in `reports/issue-473-480-20261107/issue-480/typesafe-review-980d9e-followups-20261111/decision.json`.
- Seven regressions reproduced on the reviewed candidate. Both Assistant collection routes enforce a named canonical source even if it has no files and the model omits it. Explicit first-collection intent gates the rolling first-seen window. Development management commands use the base Compose file and production examples select both files.
- All 392 focused tests passed with isolated PostgreSQL 16. Development and production Compose config checks, file and symbol gates, formatting, lint, and diff checks passed. The PostgreSQL container and port were cleaned up and Compose validation created no daemon resources. The evidence ledger is `reports/issue-473-480-20261107/issue-480/review-980d9e-worker-20261111/evidence-ledger.jsonl`, SHA-256 `7e78261be9ee242f9e63aa307aeab325ba27e6a4bd6516054325fa509aa9c744`.

## 2026-11-11 #480 review follow-up on 960ce50

- TypeSafe Jev 1.14.0 selected `accept_narrow_repair` for the explicit rolling-week phrase and the source-only catalog fallback, with confidence 1.00 and 0.97 respectively. The decision SHA-256 is `ab3a49b3c116cf6da1c93becfeea039bb79d47b03edcbd6b442c188114d32310` in `reports/issue-473-480-20261107/issue-480/typesafe-review-960ce-followups-20261111/decision.json`.
- Both findings reproduced against the reviewed candidate. The collection wording `近一周` now uses the UTC seven-day first-seen window. A dated catalog call whose text matches only the named canonical organization uses recent collection instead. Publication controls remain free of first-seen bounds and genuine topics retain catalog matching.
- All 395 focused tests passed with isolated PostgreSQL 16. Development and production Compose validation, file and symbol gates, Black, isort, Ruff, and diff checks passed. The temporary database container and port were cleaned up. The evidence ledger is `reports/issue-473-480-20261107/issue-480/review-960ce-worker-20261111/evidence-ledger.jsonl`, SHA-256 `046d317b2d24313596fcd16f5572611dd5ce3879da73f75d5d461e59ee594a1a`.
