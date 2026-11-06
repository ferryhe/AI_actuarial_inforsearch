# Assistant help maintenance

## Source files and references

The read-only help endpoints load only `docs/help/user-guide.en.md` and `docs/help/user-guide.zh.md`. Update `HELP_FILES` in `ai_actuarial/assistant/help.py` only when an approved user guide is added or removed. Do not place secrets, logs, deployment configuration, internal runbooks, or archived material in the help directory. Search reloads the allowlisted Markdown files for each request, so edits and removals take effect without restarting the API.

Each guide's front matter needs a unique `doc_id`, `language` (`en` or `zh`), `title`, and `source_version`. Keep `doc_id` stable for that language and update `source_version` for a published content change. Every `##` heading needs a stable `{#section-id}` and nonempty content. IDs must match `[a-z0-9][a-z0-9-]{0,63}` and section IDs must not repeat within a document. Search includes the section heading in matching and results include the exact section's `content_hash`; clients must pass all six reference fields to `/api/assistant/help/section`. A changed version, title, language, or hash returns `HELP_REFERENCE_EXPIRED` and no current section text. A removed document or section returns `HELP_NOT_FOUND`.

The search is lexical and deterministic. Keep user wording and key terms in each section. English uses word tokens; Chinese uses character bigrams and trigrams. It does not crawl websites, read other repository files, use embeddings, or call a model. Keep the fixed 18-query acceptance fixture aligned with each guide edit.

## V1 publication checklist

- Confirm that both approved guide files describe only behavior present in the UI and API. Recheck permission-gated controls in `client/src/components/Layout.tsx`, `client/src/pages/Database.tsx`, `client/src/pages/Categories.tsx`, `client/src/pages/FileDetail.tsx`, `client/src/pages/Knowledge.tsx`, and `client/src/pages/Chat.tsx`, plus role permissions in `ai_actuarial/shared_auth.py`.
- Record the tested source commit SHA and file hashes for both Markdown guides and `ai_actuarial/assistant/help.py`.
- Record UI version evidence: root `package.json` version and the frontend build's source SHA. Record API version evidence from `GET /api/health` (`build_info.release_manifest_id` and `git_sha`). If the build reports `unknown`, record that exact value rather than inferring a release. Bind the implementation SHA after commit.
- Run `python -m pytest tests/test_assistant_help.py tests/test_fastapi_assistant_help_endpoints.py` and the manager's isolated real-HTTP lifecycle checks for edit/reload, removal, stale references, and disabled endpoints. TestClient alone is not the real-HTTP acceptance.
- Confirm `assistant_enabled` is explicitly enabled only in the intended deployment. It defaults off. `feedback_enabled` remains independent and defaults off.

## Current implementation evidence

This guide set was prepared against source baseline `6b183ffb73a579230a45fba838cf037571105276` on `codex/issue-462-help-docs`. The current feedback widget checks `feedback_enabled`; the help question panel and knowledge-base question panel are not shipped. Bind the implementation SHA in the V1 acceptance record after the implementation commit and capture the deployment's actual version values during release acceptance.
