# Project Status — Issue #317 dead-code and unified quality gates

- Updated: 2026-08-31 EDT
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

## Files changed

- Gate implementation/config: `scripts/dead_code_gate.py`,
  `scripts/quality_gate.py`, `knip.json`, `eslint.config.mjs`, `pyproject.toml`,
  `package.json`, lockfile, development requirements, and both baselines.
- Framework review: `config/dead_code_whitelist.py`.
- Automation: `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.
- Documentation: `docs/dead-code.md`, docs index, and both root READMEs.
- Focused cleanup/tests: affected React files, small Python unused-argument
  cleanups, gate tests, and narrow full-suite contract corrections.

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

- Evaluate required checks and remote review/Copilot feedback on PR #318's
  final head. Merge only after explicit authorization.
