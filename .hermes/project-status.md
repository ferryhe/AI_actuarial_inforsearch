# Project Status — Issue #249 Admin Settings Authentication

- Updated: 2026-08-28
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-249-admin-settings-auth`
- Baseline: `cfa06f3a99b21574f103d9671d91e337aea1db80`
- Issue: `#249 fix: diagnose and prevent admin settings saves returning Forbidden`

## Reproduction and delivery

- Baseline local browser reproduction used a seeded `JG Local` admin fixture with no production credentials.
- Visible UI showed Settings and Users, but Markdown Save returned sanitized `403 Forbidden` from `POST /api/config/markdown-conversion`.
- The failing node resolved the request as unauthenticated/reader without `config.write`, while the valid signed JG email session resolved `/api/auth/me` as admin with `config.write`.
- Post-fix browser smoke showed Markdown Save success, sanitized POST `200`, GET `200`, and refresh/readback preserved `MarkItDown`.
- No cookie, token, local-storage, session-storage, password, or secret values were inspected or logged.

## Acceptance delivery

1. Captured the exact sanitized failure contract (`403 Forbidden`) and compared `/api/auth/me` with the Settings POST identity resolution.
2. A valid admin email session saves Markdown Conversion settings and reads back the same value with stable user, role, and permissions.
3. Duplicate signed cookies are resolved deterministically: valid admin email sessions are not downgraded by stale token sessions; conflicting active identities fail closed; invalid or inactive siblings do not mask a unique active identity; explicit headers cannot bypass conflicts.
4. Email login clears stale stored token material. Guest-token CSRF behavior remains compatible, and invalid auth material fails closed.
5. Settings now distinguishes session, permission, CSRF, validation, config-write, and operation-specific failures while preserving safe backend detail.
6. All 14 admin-visible Settings mutation paths use the shared error formatter. Non-admin write denial and existing permission/CSRF checks remain unchanged.
7. Markdown filesystem/YAML write failures return safe JSON `500` detail without internal paths.

## TDD and verification

- Initial #249 RED: `6 failed, 2 passed`; initial GREEN and subsequent review fixes expanded the suite.
- Managed review round 1 accepted five in-scope findings; each received targeted RED/GREEN proof.
- Managed review round 2 passed with no findings. Authoritative managed `review_count=2` and local review is closed.
- Repository Codex CLI pre-PR gate found two additional AC-3 duplicate-session cases. Their RED/GREEN evidence was `6 failed, 21 passed` to `27 passed`, then `4 failed, 27 passed` to `31 passed`.
- Final independent Codex CLI gate: no actionable defects.
- Final focused auth/settings/authority selection: `59 passed`.
- Chat endpoints: `30 passed`; ops read/write endpoints: `36 passed`.
- Required `python-smoke`: `13 passed`.
- Frontend production build: passed (`2136` modules transformed).
- Ruff on new/scoped code, compileall, and `git diff --check`: passed. The pre-existing unused `time` import in `chat.py` remains outside #249 scope.
- In-app Browser post-fix smoke: Settings save success, POST `200`, GET/readback `200`.

## Scope and current state

- Backend changes are limited to FastAPI session resolution, guest-chat session decoding, and safe Markdown write errors.
- Frontend changes are limited to stored login token cleanup and Settings mutation error presentation.
- Regression coverage is in `tests/test_issue_249_admin_settings_auth.py` and `tests/test_settings_react_source.py`.
- No authorization grants, permission/CSRF removal, legacy-token exposure, production operation, secret access, or sibling-repository changes were made.
- Implementation, browser smoke, managed review, and the separate pre-PR Codex gate are complete. PR publication and remote lifecycle are next.
