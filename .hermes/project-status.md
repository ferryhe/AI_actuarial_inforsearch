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
- Classified the current baseline: 9 TypeScript files, 5 Python modules, 28
  TypeScript symbols, and 93 Python symbols.
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

## Acceptance results

- Unified quality gate: passed. Pytest reported 1,880 passed and 10 skipped;
  Black, isort, and Pylint exactly matched their reviewed baselines.
- Dead-code gate: passed with 9/5 file findings and 28/93 symbol findings,
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

- Commit and push the path-specific `middleware/` cleanup, verify PR #318, then
  continue with `ai_actuarial/models/` as the next small independent directory.
  Merge only after explicit authorization.
