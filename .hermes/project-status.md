# Project Status — Issues #315 and #310 release batch

- Updated: 2026-08-31 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch`
- Branch: `codex/issues-315-310-config-release`
- Baseline: `origin/main@ce8d762`
- Task: implement #315, then #310, and validate them as one release batch

## Scope and boundaries

- #315 makes Chat the sole provider/model/credential route for both Chat and
  Weekly Explanation while retaining Weekly-specific prompt and generation
  policy.
- #310 makes `CONFIG_PATH` the authoritative mutable `sites.yaml`, moves
  production ownership outside Git, adds create-once bootstrap and atomic
  writes, and aligns Compose, backup, deployment, and release tooling.
- Production migration, deployment, restart, and model/provider changes remain
  outside scope and belong to #313.
- Sibling repositories remain off-limits.

## Implementation state

- #315 implementation is committed as `404c831`.
- #310 implementation is committed as `8cdcd0d`.
- Independent review fixes for both Issues are committed as `2e76aea` and
  pushed to the release branch.
- The two Issues are being published together in one PR/release batch, with
  separate commits for review clarity.
- PR #316 is open: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/316`.
- An independent subagent review found six acceptance-relevant gaps across two
  passes. All six are fixed with regression coverage. The final independent
  rereview found no remaining blocker and concluded the batch is releasable.

## Acceptance results

- Combined backend acceptance after review fixes: 143 tests passed and one
  Windows-only skip across AI runtime, Weekly
  Explanation generation/scheduling, Settings read/write, FastAPI startup,
  YAML configuration, recovery tooling, diagnostics, external config, and
  scheduled collection.
- #310 focused matrix: 18 passed and one POSIX metadata test skipped on Windows,
  including explicit-path authority,
  missing/invalid/unreadable/unwritable fail-closed behavior, atomic failure
  recovery, no-overwrite bootstrap, external Settings writes, restart reload,
  Git reset/checkout/clean isolation, and #315 inheritance through an external
  config.
- The skipped POSIX permission/ownership preservation test passed separately in
  a Python 3.11 Linux container.
- Review regressions now cover credential-only Weekly replay invalidation,
  production CLI template rejection, deployment path-consistency enforcement,
  legacy migration refusal for external state, atomic mode/owner retention, and
  config-independent schema diagnostics.
- Ruff: passed for all touched Python implementation and test files.
- CLI: root `--help` and `config-bootstrap --help` passed; the test suite also
  exercised JSON success and no-overwrite error output.
- Frontend: `npm run typecheck` and `npm run build` passed. Vite emitted only
  the existing large-chunk advisory.
- Compose: production render passed with dummy required environment values;
  Docker emitted only the existing obsolete `version` advisory.
- Shell wrappers: Git Bash syntax checks passed. `shellcheck` is not installed.
- `git diff --check`: passed; only Windows line-ending notices were emitted.
- PR #316 `python-smoke` passed on review-fix head `2e76aea`; merge state is
  clean, with no remote comments or review threads requiring action.

## Files changed

- Runtime and API: `ai_actuarial/ai_runtime.py`, `ai_actuarial/shared_runtime.py`,
  `ai_actuarial/api/app.py`, and relevant read/write/import/Weekly services.
- CLI/config: `ai_actuarial/cli.py`, `config/yaml_config.py`,
  `config/sites.yaml`, and `scripts/migrate_env_to_yaml.py`.
- Operations: Compose files, production backup/full-backup/deploy wrappers, and
  `.env.example`.
- UI/docs: Settings routing help, translations, README, deployment/service/
  credential guides, and `docs/runtime-config.md`.
- Tests: AI runtime, Weekly Explanation, Settings/API, YAML loader, and the new
  #310 runtime-config matrix.

## Working tree notes

- Existing untracked `diagrams/` and `graphify-out/` remain untouched and will
  not be committed.
- No other unrelated tracked changes are present.

## Blockers or decisions needed

- No code or test blocker.
- #313 still requires separate production-write authorization, an owner, and a
  maintenance window. This batch does not perform that migration.

## Recommended next action

- Merge PR #316 when merge authorization is given, then handle the production
  rollout separately under #313.
