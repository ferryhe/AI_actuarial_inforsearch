# Task/Settings Parameter Alignment — 2026-03-08

## Overview

This document records the design decisions and implementation details for the
task-settings parameter alignment work merged in PR #51.

---

## Problem

Four distinct issues were identified:

1. **OCR tool list silently lost local engines when AI was configured.**  
   `extractOcrTools()` filtered tools solely by presence in the AI-models
   availability response. Because the backend always returns `DEFAULT_MODELS`
   (fallback lists) for every known provider regardless of whether an API key
   is set, once any provider appeared in the response the local tools (docling,
   marker) were dropped.

2. **Catalog task had no feedback about missing AI provider.**  
   The `CatalogForm` in Tasks.tsx showed a static hint text. Users could start
   catalog tasks that would immediately fail because no AI provider was
   configured. The `FileDetail.tsx` catalog modal had a similar gap.

3. **`file_deletion_enabled` was environment-variable-only.**  
   There was no way to toggle file deletion from the web UI without restarting
   the server. Admins had to SSH in and change the `ENABLE_FILE_DELETION` env
   var.

4. **System runtime flags were not visible in the UI.**  
   Flags like `require_auth`, `enable_global_logs_api`, rate limiting and
   CSRF were invisible to administrators without direct server access.

---

## Changes

### `client/src/hooks/use-task-options.ts`

`extractOcrTools()` and `extractCatalogProviders()` now accept a
`configuredProviders: Set<string>` parameter (built from the already-fetched
`/api/config/llm-providers` response). Only providers with actual API keys
are considered when deciding which API-backed tools/providers to expose.
Local tools are always included.

```ts
// Before — unreliable: shows API tools even when key is missing
function extractOcrTools(available): ConversionTool[]

// After — reliable: requires provider to be in the configured set
function extractOcrTools(available, configuredProviders: Set<string>): ConversionTool[]
```

This was a critical correctness fix: the backend's `get_available_models()`
returns `DEFAULT_MODELS` as a fallback for every known provider regardless of
API key presence. Relying solely on model availability produced false positives.

### `client/src/pages/Tasks.tsx` — CatalogForm

Replaced the static provider hint with a live status badge:
- **Green badge** — lists configured catalog-capable providers.
- **Amber warning** with link to Settings — shown when `catalogProviders` is
  empty after the provider-gating fix.
- Run button is disabled when no provider is configured.

### `client/src/pages/FileDetail.tsx`

- Catalog modal shows the same amber warning when no AI provider is configured.
- Submit button is disabled when `taskOptions.catalogProviders.length === 0`.
- Removed the now-redundant `/api/config/ai-models` fetch (data is already
  provided by the shared `useTaskOptions()` hook).

### `client/src/pages/Settings.tsx`

New **System** tab (`Shield` icon) added as a fifth settings tab:
- **File Deletion** — toggle switch that persists `system.file_deletion_enabled`
  to `sites.yaml`. Takes effect immediately without a server restart.
- **Other flags** (`require_auth`, `enable_global_logs_api`, rate limiting,
  CSRF, security headers) — read-only status badges reflecting env var state.

### `ai_actuarial/web/app.py`

#### `_is_file_deletion_enabled()` (new helper)
Reads `system.file_deletion_enabled` from `sites.yaml` first; falls back to
the `ENABLE_FILE_DELETION` env var. Handles YAML type variations correctly:
- `bool` values used directly
- Strings normalized: `"true"/"yes"/"1"/"on"` → `True`; `"false"/"no"/"0"/"off"` → `False`
- Unexpected types → `False` (conservative)

This replaces the fragile `os.getenv("ENABLE_FILE_DELETION") == "true"` check
in the file deletion route.

#### `_serialize_backend_settings()`
Reads `system.file_deletion_enabled` from the YAML `system` section (with
env var fallback) and exposes it in the `runtime` response block. UI reads
this to initialize the toggle state.

#### Backend-settings POST handler
New `system` input section: accepts `file_deletion_enabled` with strict type
coercion. Rejects non-boolean/non-string values with HTTP 400. Persists to the
`system` section in `sites.yaml`.

### `client/src/hooks/use-i18n.ts`

Added 24 new translation strings (EN + ZH) covering:
- Catalog provider status messages
- System settings tab labels
- Feature flag display labels and hints

**Bug fix**: The ZH translation for `settings.system_runtime_desc` contained
unescaped ASCII double quotes (`"YAML"`) inside a double-quoted TS string,
causing a `SyntaxError [ERR_INVALID_TYPESCRIPT_SYNTAX]` at parse time.
Fixed by escaping: `\"YAML\"`.

---

## Reviewer Feedback Addressed

| Comment | Assessment | Action |
|---------|------------|--------|
| `use-task-options.ts`: `available` is unreliable for key presence | Valid — backend returns DEFAULT_MODELS even without keys | Fixed: intersect with `/api/config/llm-providers` configured set |
| `FileDetail.tsx`/`Tasks.tsx`: same root cause | Valid — cascading fix after hook fix | Fixed: `catalogProviders` now reflects actual key presence |
| `use-i18n.ts:1200` unescaped `"YAML"` syntax error | Valid — confirmed by Node.js parse error | Fixed: `\"YAML\"` |
| `_is_file_deletion_enabled()` `bool("false")` = `True` | Valid — security risk | Fixed: proper string normalization |
| System POST handler same bool() issue | Valid — API robustness | Fixed: strict type coercion with HTTP 400 on bad input |

---

## Testing

- Python unit tests: `pytest tests/test_yaml_config.py tests/test_web_settings.py` — 13 passed
- Python syntax: `py_compile` on `app.py` — OK
- TypeScript syntax: Node.js parse check on `use-i18n.ts` — no syntax error after fix
- CodeQL security scan: 0 alerts (python + javascript)
