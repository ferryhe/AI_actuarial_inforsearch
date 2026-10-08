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
  performed. #313 remains open and #364/PR #403 remains blocked behind its full
  acceptance. The #313-to-#364 heartbeat remains active.

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
