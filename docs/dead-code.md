# Dead-code and quality gates

The repository uses layered, non-mutating checks. File reachability runs before symbol
analysis so an orphaned module cannot hide unused symbols. Existing findings are recorded
in reviewed, exact baselines; the baselines may shrink but may never grow automatically.

## Commands

Install the pinned scanners first:

```bash
npm ci
python -m pip install -r requirements-dev.txt
```

Run the fast file layer, the symbol layer, or both:

```bash
npm run dead-code:files
npm run dead-code:symbols
npm run dead-code:check
```

The unified Python quality gate runs the requested checks without modifying the checkout:

```bash
python scripts/quality_gate.py
# equivalent tool sequence:
python -m pytest -q
python -m black --check ai_actuarial scripts tests config
python -m isort --check-only ai_actuarial scripts tests config
python -m pylint --errors-only --disable=import-error ai_actuarial scripts tests config
```

Reports are written below `reports/` as readable text and JSON. CI uploads the same files as
artifacts. The pre-commit hook runs file reachability; pre-push runs symbol analysis and the
unified quality gate.

## Entry points and dynamic imports

`knip.json` defines the production React entry (`client/src/main.tsx`) separately from test
entries. The Python graph is configured in `[tool.dead_code]` in `pyproject.toml`:

- `production_entries` are importable application/CLI roots.
- `script_entry_globs` are standalone production scripts.
- `test_entry_globs` are added only in development mode; tests cannot keep production code
  alive in the default production scan.
- `dynamic_imports` lists repository modules imported through runtime strings. Every entry
  needs a reason, and a stale entry fails the scan.

Use `python scripts/dead_code_gate.py files --mode development` only when investigating test
reachability. CI and the standard npm commands use production mode.

## Findings, baselines, and allowlists

`dead-code-baseline.json` stores normalized identities as `path + kind + symbol`, without line
numbers. Every existing item has a reviewed `classification` (`remove` or `whitelist`) and a
reason. A new item fails; a missing baseline item also fails so cleanup must update the
baseline. Vulture findings at 100% confidence always fail and cannot be baselined.

Framework-discovered Python hooks live in `config/dead_code_whitelist.py`. It contains explicit
references for FastAPI routes, Pydantic validators, middleware hooks, and pytest fixtures.
Each reference requires an inline reason, and the gate verifies that imports, symbols, and
class members still exist. SQLAlchemy/Pydantic inference findings that cannot be expressed as
runtime references remain reviewed in the baseline instead of being hidden by broad excludes.

Knip excludes only the vendored PDF.js subtree. Do not add a directory-wide ignore for normal
application code. ESLint errors are direct failures; existing React hook dependency warnings
remain visible without being treated as dead-code findings.

## Safe cleanup and baseline updates

1. Confirm the reported file or symbol is not an entry, framework hook, public contract, or
   approved dynamic import.
2. Delete it in a focused change and run the relevant tests.
3. Run the gate. It should fail only with a `stale baseline` entry.
4. Remove resolved baseline entries with:

   ```bash
   python scripts/dead_code_gate.py all --update-baseline
   ```

The update refuses any new finding or 100%-confidence Vulture result and preserves the review
metadata for retained entries. Never copy current scanner output wholesale into the baseline.

`quality-gate-baseline.json` applies the same exact, shrink-only migration to historical Black,
Isort, and Pylint violations. New files are expected to pass immediately. After formatting or
fixing a legacy file, run:

```bash
python scripts/quality_gate.py --update-baseline
```

Pytest failures are never baselined. Both baseline update commands are intentional maintenance
operations; CI only runs check mode and never deletes or rewrites source files.

## CI order

The `dead-code-files` job is the first gate. `dead-code-symbols` depends on it. The unified
quality job, frontend lint/type-check/build, and the existing Python smoke checks depend on the
symbol job. A file-level failure therefore stops deeper checks while preserving the report
artifact needed to review it.
