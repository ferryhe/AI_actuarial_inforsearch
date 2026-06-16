# File Title Editing, AI-Suggested Titles, Catalog Language Selection, and Configurable AI Prompts — 2026-03-08

## Overview

This document records the design decisions and implementation details for the
feature additions and bug fixes merged in the PR "Add file title editing,
AI-suggested title, catalog language selection, and fully configurable AI
prompts".

Four separate deficiencies were addressed:

1. **File titles were not editable** — FileDetail had no title field; scraped
   files were permanently stuck with whatever title the crawler inferred.
2. **AI catalog never suggested a title** — `catalog_llm.py` did not produce a
   `suggested_title`; even if it had, no code path applied it.
3. **Catalog and chatbot prompts were hardcoded** — Operators could not tune
   AI behaviour without editing source code.
4. **No catalog output language control** — Keywords, summaries, and suggested
   titles always followed the LLM's default language choice.

---

## Problem 1 — File titles not editable in FileDetail

### Root cause

`FileDetail.tsx` rendered `file.title` as plain text in the Catalog Information
section but provided no input field for it in edit mode. The `/api/files/update`
endpoint already accepted `category`, `summary`, and `keywords` but ignored a
`title` key.

### Fix — Backend (`ai_actuarial/web/app.py`)

The `/api/files/update` handler now reads an optional `title` parameter from
the JSON body and writes it directly to the `files` table (separate from the
`catalog_items` table which stores AI-generated metadata).

```python
title = data.get("title")
if title is not None:
    title = str(title).strip() or None   # empty string → NULL (clears the title)
```

An empty string is normalised to `None`, effectively clearing a previously set
title.

### Fix — Frontend (`client/src/pages/FileDetail.tsx`)

- `editTitle` state is initialised from `file.title` when edit mode opens.
- A text input is rendered inside the Catalog Information section, alongside
  the existing category / summary / keywords fields.
- The title is only sent to the backend when it has actually changed
  (`titleChanged` guard), keeping the payload minimal.

```tsx
const titleChanged = editTitle.trim() !== (file.title || "").trim();
// ...
title: titleChanged ? editTitle.trim() : undefined,
```

**Bug fix (Copilot review):** The original implementation used
`editTitle.trim() || undefined`, which coerced an empty string to `undefined`,
silently skipping the update and making it impossible to clear a title once set.
The fix sends `editTitle.trim()` directly — an empty string is forwarded to the
backend which normalises it to `None`.

---

## Problem 2 — AI catalog never produced or applied a suggested title

### Root cause

`LlmCatalogResult` had no `suggested_title` field; the OpenAI prompt did not
ask for one; and `catalog_incremental.py` had no logic to write a title back
to the database even if one were returned.

### Fix — `ai_actuarial/catalog_llm.py`

`LlmCatalogResult` gains a `suggested_title: str | None` field.

The default OpenAI system prompt was also substantially improved:

| Aspect | Before | After |
|--------|--------|-------|
| Language | Fixed English output | Matches source document language automatically |
| Title rules | Not specified | Must reflect actual content; must not contain site name, series name, or section heading |
| Keywords | Accepted generic terms | Excludes "report", "document", "analysis", etc.; focuses on domain-specific terms |
| Output format | JSON not enforced | Requires pure JSON with no code-block wrapper |
| Categories | May be translated | Must be returned as exact English identifiers (no translation) |

### Fix — `catalog_incremental.py`

`_process_single_row` returns a 4-tuple `(row_data, item, status, suggested_title)`.

Both public entry-points gain new parameters:

```python
def run_catalog_for_urls(
    urls: list[str],
    *,
    update_title: bool = False,
    catalog_system_prompt: str | None = None,
    output_language: str = "auto",
) -> None: ...

def run_incremental_catalog(
    *,
    update_title: bool = False,
    catalog_system_prompt: str | None = None,
    output_language: str = "auto",
) -> None: ...
```

When `update_title=True` and the LLM returns a non-empty `suggested_title`, it
is written to `files.title` under the `_db_lock` for thread safety.

### Fix — `app.py` catalog task handler

The task request body is inspected for `update_title`, `output_language`, and
`catalog_system_prompt`. `output_language` is validated to `{auto, en, zh}`.
All three are threaded through to the catalog functions.

### Frontend — opt-in checkboxes and dropdown

Both `Tasks.tsx` (`CatalogForm`) and `FileDetail.tsx` (catalog modal) received:

- **"Let AI suggest and update file title"** checkbox — only visible when an
  AI catalog provider is configured; defaults to unchecked (opt-in).
- **"AI Output Language"** dropdown — `Auto-detect / English / 中文`; only
  visible when an AI catalog provider is configured.

---

## Problem 3 — Catalog and chatbot prompts hardcoded

### Root cause

`catalog_with_openai()` used a single hardcoded system prompt.  
`chatbot/prompts.py` had no override mechanism.  
`chat_routes.py` had no way to load custom prompts at runtime.

### Fix — `catalog_llm.py`

`catalog_with_openai()` now accepts `custom_system_prompt: str | None`.  When
provided and non-empty it replaces the built-in default entirely.  An
`output_language` parameter appends a language-forcing instruction when set to
`"en"` or `"zh"`.

### Fix — `chatbot/prompts.py`

`get_system_prompt()` and `build_full_prompt()` accept a `prompts_override: dict`
parameter.  Each key corresponds to a named prompt (`base`, `expert`, `summary`,
`tutorial`, `comparison`).  An empty string for any key falls back to the
built-in default, so partial overrides work correctly.

### Fix — `chatbot/llm.py`

`generate_response()` accepts and passes `prompts_override` through to
`build_full_prompt()`.

### Fix — `chat_routes.py`

At each chat request, `ai_config.chatbot.prompts` is loaded from `sites.yaml`
and passed to `generate_response()`.

`_build_summarization_system_prompt()` similarly accepts a `custom_prompt`
override loaded from `ai_config.chatbot.summarization_prompt`.  The default
summarization prompt was also improved: language-aware output, clearer citation
rules, and better per-mode descriptions.

### Fix — `/api/config/ai-models` GET/POST

The endpoint now exposes all configurable prompts:

```
GET  /api/config/ai-models
→ {
    "catalog": { "system_prompt": "..." },
    "chatbot": {
      "prompts": { "base": "...", "expert": "...", "summary": "...",
                   "tutorial": "...", "comparison": "..." },
      "summarization_prompt": "..."
    }
  }

POST /api/config/ai-models
body: { "catalog": { "system_prompt": "..." } }
→ Saves to sites.yaml; returns updated config
```

An empty string for any prompt key clears the override and restores the
built-in default at runtime.

### Storage in `sites.yaml`

```yaml
ai_config:
  catalog:
    system_prompt: ""          # empty = use built-in default
  chatbot:
    prompts:
      base: ""
      expert: ""
      summary: ""
      tutorial: ""
      comparison: ""
    summarization_prompt: ""
```

---

## Problem 4 — No catalog output language control

### Root cause

The catalog pipeline had no mechanism to force the LLM to produce output in a
specific language for keywords, summaries, and suggested titles.  The LLM
defaulted to the document's own language, which is often desirable, but
operators needed the ability to enforce a specific language for consistency.

### Fix

`catalog_with_openai()` appends one of the following instructions to the system
prompt when `output_language` is not `"auto"`:

| Value | Instruction appended |
|-------|----------------------|
| `"en"` | `"Respond in English for all text fields (summary, keywords, suggested_title)."` |
| `"zh"` | `"Respond in Chinese (Simplified) for all text fields (summary, keywords, suggested_title)."` |
| `"auto"` | *(nothing appended; LLM matches the document language)* |

Category names are **not** affected by this setting — the prompt explicitly
requires the LLM to return category identifiers as exact English labels
regardless of output language, avoiding keyword-matching breakage.

---

## Problem 5 — No dedicated UI for AI prompt configuration

### Fix — Settings → Prompts tab (`client/src/pages/Settings.tsx`)

A new **Prompts** tab was added to the Settings page, using a reusable
`PromptEditorCard` component.

| Card | Stores to | Description |
|------|-----------|-------------|
| Catalog AI System Prompt | `ai_config.catalog.system_prompt` | Full system prompt for AI cataloging |
| Chatbot Base Instructions | `ai_config.chatbot.prompts.base` | Rules applied to all chat modes |
| Chatbot – Expert Mode | `ai_config.chatbot.prompts.expert` | Appended for Expert mode |
| Chatbot – Summary Mode | `ai_config.chatbot.prompts.summary` | Appended for Summary mode |
| Chatbot – Tutorial Mode | `ai_config.chatbot.prompts.tutorial` | Appended for Tutorial mode |
| Chatbot – Comparison Mode | `ai_config.chatbot.prompts.comparison` | Appended for Comparison mode |
| Document Summarization Prompt | `ai_config.chatbot.summarization_prompt` | Used when Ask AI summarises a document |

Each card shows the currently stored value or "(Using built-in default prompt)"
when blank.  Clicking **Edit** opens an inline textarea; **Save** POSTs to
`/api/config/ai-models`; **Cancel** discards changes.

**Bug fix (Copilot review):** The original `savePrompt()` had no error handling.
A network or server error would propagate silently — the user would see nothing.
The fix wraps the `apiPost` call in `try/catch`, shows an error toast on failure
(reusing the existing `settings.models_save_error` translation key), and keeps
the editor open so the user can retry. `handleSave` now only closes the editor
on success.

---

## i18n additions

All new UI strings were added in both English (`en`) and Chinese (`zh`) in
`client/src/hooks/use-i18n.ts`:

| Key | EN | ZH |
|-----|----|----|
| `catalog.update_title` | Let AI suggest and update file title | 让 AI 建议并更新文件标题 |
| `catalog.output_language` | AI Output Language | AI 输出语言 |
| `catalog.lang_auto` | Auto-detect | 自动检测 |
| `catalog.lang_en` | English | English |
| `catalog.lang_zh` | 中文 | 中文 |
| `settings.tab_prompts` | Prompts | 提示词 |
| `settings.prompt_catalog_title` | Catalog AI System Prompt | 编目 AI 系统提示词 |
| `settings.prompt_chatbot_base_title` | Chatbot Base Instructions | 聊天基础指令 |
| `settings.prompt_chatbot_expert_title` | Chatbot – Expert Mode | 聊天 – 专家模式 |
| `settings.prompt_chatbot_summary_title` | Chatbot – Summary Mode | 聊天 – 摘要模式 |
| `settings.prompt_chatbot_tutorial_title` | Chatbot – Tutorial Mode | 聊天 – 教学模式 |
| `settings.prompt_chatbot_comparison_title` | Chatbot – Comparison Mode | 聊天 – 对比模式 |
| `settings.prompt_summarization_title` | Document Summarization Prompt | 文档摘要提示词 |

---

## Test results

Targeted test run (`-k "catalog or prompt or title or ai_model"`):

```
27 passed, 370 deselected
```

All tests covering `TestPrompts` (`test_get_system_prompt_*`,
`test_build_full_prompt`), catalog-related API endpoints, and title/headline
attribute checks pass.  The full suite has 41 failures attributable to
pre-existing infrastructure constraints in the sandbox (blocked external network
for `tiktoken` model downloads, uninitialised database, and CSRF/auth
configuration not matching the test harness) — none are caused by this PR.

Frontend build: `✓ built in ~4s` with no TypeScript errors.

---

## Files changed

| File | Type | Summary |
|------|------|---------|
| `ai_actuarial/web/app.py` | Backend | `/api/files/update` title field; catalog task reads `update_title`, `output_language`, `catalog_system_prompt`; `/api/config/ai-models` extended |
| `ai_actuarial/catalog_llm.py` | Backend | `suggested_title` in result; improved default prompt; `custom_system_prompt` + `output_language` params |
| `ai_actuarial/catalog_incremental.py` | Backend | 4-tuple return from `_process_single_row`; `update_title`, `catalog_system_prompt`, `output_language` params propagated |
| `ai_actuarial/web/chat_routes.py` | Backend | Loads chatbot/summarization prompt overrides from `sites.yaml` at runtime |
| `ai_actuarial/chatbot/prompts.py` | Backend | `prompts_override` parameter on `get_system_prompt()` and `build_full_prompt()` |
| `ai_actuarial/chatbot/llm.py` | Backend | `prompts_override` passed to `build_full_prompt()` |
| `client/src/pages/FileDetail.tsx` | Frontend | Title input in edit mode; `update_title` + `output_language` in catalog modal; title-clear bug fix |
| `client/src/pages/Tasks.tsx` | Frontend | `update_title` checkbox + `output_language` dropdown in `CatalogForm` |
| `client/src/pages/Settings.tsx` | Frontend | New Prompts tab with `PromptEditorCard`; `savePrompt` error handling fix |
| `client/src/hooks/use-i18n.ts` | Frontend | EN + ZH translations for all new keys |
