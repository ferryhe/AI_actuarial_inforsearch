# Project Status

- Date: 2026-05-23
- Branch: codex/fix-knowledge-backend-embedding-config
- Scope: Knowledge page embedding configuration controls.
- Latest baseline: Merged origin/main after PR #107 landed.
- Changes: Removed Knowledge page embedding model selection and stopped posting embedding_model when creating a KB. The create form now displays the backend-configured embedding provider/model from /api/rag/knowledge-bases current_embeddings as read-only context.
- PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/110
- Verification: python -m pytest tests/test_knowledge_react_source.py -q; python -m pytest tests/test_fastapi_rag_admin_endpoints.py -q; npm.cmd run build.
- Pre-PR review gate: Blocked because `codex --help` fails with `Program 'codex.exe' failed to run: Access is denied`.
- Merge readiness: Resolved post-PR-107 `.hermes/project-status.md` add/add conflict by preserving this PR's current status on top of origin/main.
- Browser smoke: http://127.0.0.1:5173/knowledge loaded with no framework overlay or console errors. Create KB panel showed the backend embedding read-only block and no embedding selector.
- Notes: No sibling repositories were read or modified.
