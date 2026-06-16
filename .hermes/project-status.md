# Project Status

- Date: 2026-06-16
- Branch: `codex/p0-1-markdown-conversion-config`
- Baseline: `origin/main` at `32ebedd`.
- Scope: P0-1 Markdown conversion config split and admin/UI/runtime integration.
- PR: [#147](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/147) — open; CI passed; Copilot comments addressed.
- Previous PRs: [#146](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/146) — merged; [#145](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/145) — merged.

## Current State

- This branch adds `config/markdown_conversion.yaml` as the markdown conversion runtime source of truth for default tool, enabled tools, format-specific candidate chains, paid/API auto toggles, tuning knobs, and scan limits.
- Backend read/write endpoints now expose `/api/config/markdown-conversion` with existing `config.read` / `config.write` authorization and optional `CONFIG_WRITE_AUTH_TOKEN` guard.
- Markdown conversion runtime now defaults to configured `auto`, keeps `auto` from resolving to `docling`, runs configured candidate chains, skips unconfigured paid/API tools in auto mode, rejects disabled explicit tools, and clamps scan counts to configured limits with a hard safety cap.
- Frontend Markdown task surfaces and FileDetail conversion controls now load tool order/defaults/limits from the markdown conversion config API instead of hardcoding the OpenDataLoader-first order.
- Local `docker-compose.override.yml` still has an unrelated production override diff and must remain uncommitted for this PR.

## Verification

- `python3 -m pytest tests/test_markdown_conversion_config.py tests/test_doc_to_md_engine_defaults.py tests/test_fastapi_ops_write_endpoints.py::test_markdown_conversion_config_read_write_endpoint_roundtrip -q` passed: 13 tests after Copilot fixes.
- `npm test` passed and ran the Vite production build after Copilot fixes; Vite still emits the existing large chunk warning.
- `git diff --check` passed.
- GitHub CI `python-smoke` passed on PR #147.
- Independent spec review pass 2: PASS.
- Independent code-quality/security review pass 2: PASS for markdown conversion scope after excluding `docker-compose.override.yml`; noted the unrelated override as not-to-commit.
- Copilot review comments addressed: stable POST tool ordering, markdown tuning config cache, UI scan count lower bound, markdown config payload guard, and removal of an unused task runtime parameter.

## Notes

- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, active Docker volumes, logs, or local production overrides into this PR.
