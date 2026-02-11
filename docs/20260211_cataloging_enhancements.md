# 2026-02-11 Cataloging Enhancements (Markdown + OpenAI + Recompute)

This document describes cataloging improvements added after the token-auth/permissions rollout.

## What Changed

- Cataloging can now run from:
  - `source` (extract text from the local file), or
  - `markdown` (use markdown stored in `catalog_items.markdown_content`, typically produced via Markdown Conversion in File Details).
- Cataloging now supports:
  - `skip_existing` (default): only process new/changed files (or version changes)
  - `overwrite_existing`: recatalog even if the file was already cataloged with the same pipeline version
- Cataloging providers:
  - `local` (KeyBERT + rule-based categorization): default
  - `openai` (ChatGPT): enabled when `OPENAI_API_KEY` is configured
- File Details now includes a **Catalog (AI)** action that submits a single-file catalog task (same options as batch).

## UI Entry Points

- Batch: `Tasks` -> `Cataloging` -> "Run Incremental Cataloging"
  - Select `Catalog From`: `Source file` or `Markdown`
  - Choose `Skip already cataloged` or `Overwrite existing content (recompute)`
  - Choose provider: `Local` or `OpenAI (ChatGPT)` (if configured)
- Single file: open a file in `Database` -> `File Details`
  - Click `Catalog (AI)` and submit a 1-file catalog task

## OpenAI Configuration (.env)

Add these in `.env` (see `.env.example`):

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (optional, for OpenAI-compatible gateways)
- `OPENAI_DEFAULT_MODEL` (default: `gpt-4o-mini`)
- `OPENAI_TIMEOUT_SECONDS`

If `OPENAI_API_KEY` is not set, the UI keeps the OpenAI provider option disabled.

## Prompt Location

The default OpenAI prompt and JSON parsing are implemented in `ai_actuarial/catalog_llm.py`.

## Notes On Recompute Behavior

- Candidate selection is based on:
  - missing catalog record, OR
  - file SHA changed, OR
  - pipeline version changed, OR
  - (optional) previous status was `error` and `retry_errors=true`
- The pipeline version used by cataloging includes provider and input source, so switching providers (or source vs markdown) naturally triggers re-cataloging without needing `overwrite_existing`.
