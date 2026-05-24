# Project Status

- Date: 2026-05-24
- Branch: `fix/rbac-chat-i18n`
- Latest baseline: latest `origin/main` when the branch was created.
- Scope: Tighten RBAC for anonymous/registered/operator/admin users and fix chat/login/register i18n gaps. Sibling repositories were not read or modified.
- Backend RBAC: Guest/anonymous permissions are limited to public database/file/markdown reads plus chat view/query; anonymous stats, tasks, and conversation listing were removed. Registered users keep read-only access; operators can run/stop/schedule tasks but do not get `config.write`, token management, or user management; admins retain full configuration/user/token access.
- Backend compatibility: legacy auth group names are normalized (`anonymous`→`guest`, `reader`→`registered`, `operator_ai`→`operator`) before deriving permissions.
- Frontend RBAC: route guards and task UI now use explicit permission checks. Guest users do not see task controls; signed-in readers get read-only task/history access; operators get run/stop/schedule actions; settings/users remain admin-only.
- Chat i18n: retrieved citation actions now use `chat.file_detail` and `chat.preview` instead of hardcoded Chinese labels.
- Auth i18n: `/login` and `/register` now use i18n keys for headings, labels, buttons, errors, token controls, and helper text; both pages include a language toggle and a `Back to home`/`返回主页` link.
- Review decision: local Codex review flagged operator loss of `config.write` on KB mutation endpoints. This was not applied because the current user requirement says only admins can change settings and operators should execute tasks/task settings, not important configuration.
- Verification passed: `python -m pytest tests/test_auth_react_source.py tests/test_chat_react_source.py tests/unit/test_permissions.py -q` (28 passed, 3 warnings).
- Verification passed: `python -m pytest tests/unit/test_permissions.py tests/test_auth_react_source.py tests/test_chat_react_source.py tests/test_fastapi_auth_endpoints.py tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_rag_admin_endpoints.py tests/test_fastapi_file_preview.py tests/test_fastapi_chat_endpoints.py tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_read_endpoints.py -q` (100 passed, 3 warnings).
- Verification passed: `npm run build` (passed with the existing Vite large-chunk warning).
- Verification passed: `git diff --check` (passed).
- Browser smoke passed on local Vite/FastAPI: `/login` Chinese view shows `返回主页`, `登录`, `邮箱`, `密码`, `注册`; token tab shows Chinese token labels and controls; `/register` Chinese view shows `返回主页`, `创建账号`, `显示名称`, `邮箱`, `密码`, `确认密码`, `创建账号`; English register view still renders correctly.
- Known out-of-scope full-suite failures from earlier investigation: `test_fastapi_entrypoint.py` CSRF secret setup, `test_code_review_fixes.py`/`test_fastapi_react_cleanup.py` path assumptions, and `test_safe_pickle.py` pickle safety assertions.
