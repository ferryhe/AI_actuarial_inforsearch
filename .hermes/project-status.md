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
- The two Issues are being published together in one PR/release batch, with
  separate commits for review clarity.
- PR #316 is open: `https://github.com/ferryhe/AI_actuarial_inforsearch/pull/316`.

## Acceptance results

- Combined backend acceptance: 139 tests passed across AI runtime, Weekly
  Explanation generation/scheduling, Settings read/write, FastAPI startup,
  YAML configuration, recovery tooling, diagnostics, external config, and
  scheduled collection.
- #310 focused matrix: 30 tests passed, including explicit-path authority,
  missing/invalid/unreadable/unwritable fail-closed behavior, atomic failure
  recovery, no-overwrite bootstrap, external Settings writes, restart reload,
  Git reset/checkout/clean isolation, and #315 inheritance through an external
  config.
- Ruff: passed for all touched Python implementation and test files.
- CLI: root `--help` and `config-bootstrap --help` passed; the test suite also
  exercised JSON success and no-overwrite error output.
- Frontend: `npm run typecheck` and `npm run build` passed. Vite emitted only
  the existing large-chunk advisory.
- Compose: production render passed with dummy required environment values;
  Docker emitted only the existing obsolete `version` advisory.
- Shell wrappers: Git Bash syntax checks passed. `shellcheck` is not installed.
- `git diff --check`: passed; only Windows line-ending notices were emitted.

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

- Wait about 15 minutes and evaluate PR #316 CI and remote review/Copilot
  feedback before handing off #313.
