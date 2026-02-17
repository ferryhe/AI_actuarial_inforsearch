# Convert to Markdown: doc_to_md Integration (2026-02-10)

## Goal

Implement the previously-placeholder "Convert to Markdown" task by integrating a real conversion layer with multiple engines, and wire it into:

- Task Center: batch conversion
- Database -> File Detail -> Markdown Content: per-file conversion submit while editing

## What Was Implemented

### 1. `doc_to_md` Package (Local)

Added a local `doc_to_md` Python package (copied/adapted from `ferryhe/doc_to_md`) with these engines:

- `docling`
- `marker`
- `mistral` (API)
- `deepseekocr` (SiliconFlow OpenAI-compatible API)

Also included a lightweight fallback engine:

- `local` (plain text extraction -> Markdown wrapper)

Entry point used by the web app:

- `doc_to_md/registry.py`: `convert_path(path, engine=...)`

### 2. Settings From `.env`

Added `config/settings.py` so engines read configuration directly from the repository `.env` (via `pydantic-settings`), including:

- `MISTRAL_API_KEY`, `MISTRAL_DEFAULT_MODEL`, timeouts/retries
- `SILICONFLOW_API_KEY`, `SILICONFLOW_BASE_URL`, model, timeouts/retries
- `DOCLING_MAX_PAGES`, `DOCLING_RAISE_ON_ERROR`
- `MARKER_*` options

### 3. Backend Wiring: Markdown Conversion Task

Updated the existing markdown conversion task in:

- `ai_actuarial/web/app.py`

Changes:

- Replace placeholder conversion with `doc_to_md.registry.convert_path(...)`.
- Store `markdown_source` as `converted_{engine_used}` (important for `auto`, which selects a concrete engine).
- Errors now include the engine name and exception message.

### 4. UI Wiring

Task Center batch conversion (`/tasks`):

- `ai_actuarial/web/templates/tasks.html` now exposes engine choices:
  - `auto`, `marker`, `docling`, `mistral`, `deepseekocr`
- File filtering includes `image/*` types for OCR-driven engines.

File detail page conversion submit:

- `ai_actuarial/web/templates/file_view.html`
- In Markdown "Edit" mode, added:
  - Engine selector
  - Overwrite checkbox
  - "Convert From File" button that submits a background conversion task and exits edit mode immediately.

## How To Use

### Batch Conversion

1. Open `/tasks`
2. Click "Convert to Markdown"
3. Select files, choose engine, submit
4. Monitor progress in Active Tasks / History

### Per-File Conversion

1. Open Database -> file detail
2. Markdown Content -> Edit
3. Select engine, click "Convert From File"
4. The editor exits to view mode immediately; check Task Center for progress

## Dependencies / Installation Notes

Engines have optional heavy dependencies:

- `marker`: install `marker-pdf`
- `docling`: install `docling`
- `mistral`: install `mistralai`
- `deepseekocr`: install `openai` and (for PDF rendering) `pypdfium2`

If an engine dependency is missing, conversion fails with a clear error message in task history.

## Known Gaps / Things To Consider Next

- Asset handling: some engines can output images (assets). Currently, the web UI stores Markdown but does not persist/serve extracted images.
- Engine availability UX: the UI always shows all engines; it does not detect missing deps or missing API keys before submission.
- Auto engine policy: current `auto` selection is conservative and extension-based; you may want a smarter policy per MIME type and per installed deps.
- Task persistence: tasks are in-memory with history persisted; if the server restarts mid-conversion, active tasks are lost.

