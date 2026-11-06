# Website assistant knowledge scope

The assistant uses the existing Chat identity, provider configuration and daily quota. It does not create Chat conversations or messages. Feedback remains a separate module and is written only after the user confirms the ordinary form.

The server configuration starts with no KB access:

```yaml
features:
  assistant_enabled: false
  feedback_enabled: false
  assistant_public_kb_ids: []
  assistant_staff_kb_ids: []
```

Public KB IDs are available to callers with `chat.query`. Staff KB IDs additionally require an authenticated identity with `assistant.internal`, assigned to operator/admin through the existing role permissions. Listing a KB grants no assistant access. Request bodies accept only `message`, `mode` and `locale`; caller-supplied KB IDs are rejected. Empty KB scope is rejected before quota, retrieval or model initialization.

Modes are `auto`, `usage`, `catalog` and `knowledge`. Directory queries require the existing `files.read` and `catalog.read` permissions. They search and send only title, summary, organization/source, date, category and source identity/link/version. Markdown never participates in directory matching. Body questions search the current usable Ready Data publication, including its existing soft-stale service version. If unavailable or hard stale, the same allowed KB can use Standard RAG. Current file membership filters retained index entries. Planner summaries are never body evidence.

Answers select exact excerpts from the evidence supplied to the model. Citations identify `help`, `catalog` or `kb`, the actual section/file, an internal source link and any available version/date. Earlier serving evidence is labeled. No evidence produces a fixed unavailable/no-result response without knowledge-answer generation.

Responses expose total `generation_attempts`, separate `routing_generation_attempts` / `answer_generation_attempts`, and actual `embedding_attempts`. Auto uses at most two generation attempts; each explicit mode uses at most one. Assistant embeddings retain the configured retry count capped at three per provider batch, disable hidden SDK retries and use the remaining request deadline. Dimension probes and retries are counted at the provider call; cached embeddings make no provider attempt. Existing Chat retry behavior is unchanged.

Focused validation:

```text
python -m pytest tests/test_assistant_knowledge.py tests/test_assistant_feature_matrix.py tests/test_fastapi_assistant_endpoints.py tests/test_fastapi_chat_endpoints.py tests/test_fastapi_agentic_rag_endpoints.py tests/test_rag_runtime.py
npx vitest run --config vitest.config.ts client/src/features/assistant client/src/features/feedback client/src/components/support-widget
npm run typecheck
npm run build
npm run test:a11y
```

PostgreSQL tests require `POSTGRES_TEST_URL` pointing to an isolated PostgreSQL 16 database. Unit/mock checks do not establish real-provider acceptance; the Issue acceptance receipt separately records the real provider, authorized KB identity matrix, browser links and feedback-to-inbox readback. Production flags and schedules remain separate deployment decisions.
