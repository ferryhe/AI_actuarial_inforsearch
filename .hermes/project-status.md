# Project Status — Issue #317 dead-code and unified quality gates

- Updated: 2026-09-01 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch`
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
  reduced the Python side to 1 module and 72 symbols.
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

- Commit and push the path-specific `ai_actuarial/api/services/` cleanup to PR
  #318, verify its CI and review feedback, then continue with
  `client/src/components/`. Keep the final root-level orphan
  `ai_actuarial/pipeline_config.py` for a separately verified cleanup. Merge
  only after explicit authorization.
