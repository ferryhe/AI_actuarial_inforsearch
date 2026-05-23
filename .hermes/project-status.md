# Project Status

- Date: 2026-05-23
- Branch: codex/fix-knowledge-deepseek-database-explain
- Scope: Knowledge KB creation embedding UI removal, DeepSeek official model endpoint defaults, and Database-to-Chat AI document explanation restoration.
- Latest baseline: origin/main at d05198e729456c7830830e7dc0babdf834ba0a0e after PR #113 merge and successful Gitee sync follow-up.
- Knowledge page: The create-KB panel no longer renders an embedding selector or read-only embedding field; embedding remains backend-defined and surfaced only through existing KB metadata/status.
- DeepSeek config: Verified official DeepSeek docs list OpenAI-compatible `base_url` as `https://api.deepseek.com` and current model IDs as `deepseek-v4-flash` and `deepseek-v4-pro`; updated runtime/discovery defaults from `/v1` to the official root endpoint while keeping legacy aliases.
- Chat document explanation: Chat already posts `document_content`, `document_filename`, and `document_file_url` when given a document; Database now restores an AI explain action for markdown-backed files and routes the selected file to Chat, where Chat fetches markdown and submits the document context directly.
- Verification: `python -m pytest tests/test_knowledge_react_source.py tests/test_database_react_source.py tests/test_chat_react_source.py tests/test_llm_models.py tests/test_ai_runtime.py tests/test_chatbot_core.py tests/test_catalog_runtime.py -q` passed; `python -m pytest tests/test_chat_react_source.py tests/test_database_react_source.py tests/test_knowledge_react_source.py tests/test_llm_models.py tests/test_ai_runtime.py -q` passed; `npm.cmd run build` passed with the existing large-chunk warning; local Vite HTTP smoke returned 200 for `/database` and `/knowledge`; `git diff --check` passed.
- Verification notes: Initial `npm run build` was blocked by local PowerShell script execution policy for `npm.ps1`; reran successfully with `npm.cmd run build`. Playwright/browser automation was unavailable because `playwright` is not installed in local `node_modules`, so the UI smoke used Vite HTTP route checks.
- Pre-PR review gate: Blocked; `codex --help` failed normally and with escalated sandbox permissions with `Program 'codex.exe' failed to run: Access is denied`.
- Notes: No sibling repositories were read or modified.
