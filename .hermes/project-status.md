# Project Status — Issue #285 Implementation

- Updated: 2026-08-31 10:39 EDT
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch`
- Branch: `codex/issue-285-markdown-content`
- Baseline: `origin/main@3a0bce6a195b3e947da97c2a0e9cd4c62b2d9ae7`
- Issue: [#285](https://github.com/ferryhe/AI_actuarial_inforsearch/issues/285)
- State: implementation, independent review fixes, verification, commit, push, and PR complete; PR remains open and unmerged

## Scope and boundaries

- Added a shared safe `MarkdownContent` frontend component.
- Integrated it only into Assistant message bodies in `Chat.tsx` and Markdown view mode in `FileDetail.tsx`.
- Kept User messages as plain text and left citations, retrieved blocks, and tool trace outside the Markdown pipeline.
- Did not modify `NativeFileDetail.tsx`, `FilePreview.tsx`, sibling repositories, or unrelated product areas.

## Implementation

- Added `react-markdown@10.1.0`, `remark-gfm@4.0.1`, and `remark-breaks@4.0.0`.
- Added stable plugin/component mappings and memoized `MarkdownContent` plus `MessageBubble`.
- Enabled GFM tables, task lists, strikethrough, autolinks, fenced/inline code, and natural line breaks.
- Enabled `skipHtml`; Markdown images are disallowed; no `rehype-raw`, `highlight.js`, or uncontrolled prop spreading was added.
- Links allow validated internal `/path` routes and absolute `http`/`https` URLs only. Invalid, dangerous, scheme-relative, malformed, credential-bearing, and non-link URLs render as text.
- External links use `target="_blank"` and `rel="noopener noreferrer"`; internal links stay in the current tab.
- Added bounded width, long-token wrapping, and local horizontal scrolling for tables and code blocks.
- Removed the 109-line local `MarkdownRenderer` from `FileDetail.tsx`.

## Verification

- TDD red phase: 4 expected failures before the component and wiring existed.
- Focused/source/component suite: `38 passed` with 3 existing SWIG deprecation warnings.
- Production build: passed; Vite transformed 2,403 modules.
- Baseline bundle: CSS 67.56 kB / 11.35 kB gzip; JS 966.14 kB / 253.48 kB gzip.
- Final bundle after review fixes: CSS 68.20 kB / 11.46 kB gzip; JS 1,125.94 kB / 302.18 kB gzip.
- Browser smoke at 320/768/1024/1440 px: no page or bubble horizontal overflow; wide tables and long code scroll locally; long URLs/tokens wrap; User Markdown remains literal in the real Chat page.
- `npm exec -- tsc --noEmit` is still blocked by pre-existing errors in `category-labels.ts`, `Categories.tsx`, `Dashboard.tsx`, `Database.tsx`, `Settings.tsx`, and scheduled-task components. No error referenced an Issue #285 file.

## Review and PR state

- PR: [#305](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/305)
- Initial commit: `37acf87d64ded6e47651222bf5aa7528da217c85`
- GitHub CI `python-smoke`: passed in 1m25s.
- Fifteen-minute delayed review check: 0 Issue comments, 0 inline comments, 0 failed/pending checks.
- Copilot could not review because its quota was exhausted; it provided no code finding.
- User-requested independent subagent review found two valid P2 issues: dropped GFM table alignment and dropped ordered/task-list semantics.
- Both findings were fixed by a strict alignment whitelist, preserving `<ol start>`, and removing bullets only for parser-generated GFM task lists.
- Regression fixtures now assert right-aligned GFM columns, non-1 ordered-list starts, and task lists without duplicate bullets.
- Focused tests and production build passed again after both fixes.

## Working tree notes

- Product changes are limited to the shared component/tests, Chat/FileDetail wiring, package manifests, and the focused source-test update.
- Pre-existing untracked `diagrams/` and `graphify-out/` remain outside the product change and must not be staged.
- `graphify-out/` also contains local graph-query memory generated during implementation.

## Blockers or decisions needed

- No Issue #285 blocker remains.
- The existing Vite large-chunk advisory remains non-blocking. No syntax-highlighting dependency was added.
- The repository dependency audit reports 10 items; broad dependency remediation is outside this Issue.

## Recommended next action

- Commit and push the two confirmed review fixes plus this status update, confirm the rerun CI state, then leave PR #305 open for user merge direction.
