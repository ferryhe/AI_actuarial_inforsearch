# Embedding 配置收敛单 PR 开发计划

日期：2026-05-01  
来源：`Embedding 配置收敛开发计划.docx`  
执行方式：单 PR，主题为 `Embedding credential binding contract + RAG diagnostics`

## Summary

本 PR 将原计划中的 credential id contract、RAG 诊断增强、运维脚本和文档合并交付。边界保持收敛：不新增数据库表、不迁移 function binding 到 DB、不重写 Settings 页面。

## Key Changes

- `ai_runtime` 正式支持 credential id contract：
  - `provider:category:db:<row_id>`
  - `provider:category:instance:<instance_id>`
  - `provider:category:env`
  - legacy `provider:category:<instance_id>` 仅兼容读取。
- `/api/config/provider-credentials` 同时回显 `credential_id` 和 `stable_credential_id`。
- `/api/config/ai-routing` 写入前严格校验 credential id，错误绑定返回 400，不再静默 fallback。
- RAG embedding 初始化失败时返回非敏感上下文：provider、model、credential source/id/label/error、base URL 是否存在。
- RAG admin/chat knowledge-bases 的 `current_embeddings` 回显 credential configured/error 状态。
- Settings 只做最小兼容：优先提交 stable credential id，并显示 credential error。
- 新增诊断脚本与指南：
  - `scripts/diagnose_embedding_runtime.py`
  - `docs/guides/AI_PROVIDER_CREDENTIALS.md`
  - `docs/guides/RAG_EMBEDDINGS_RUNTIME.md`

## Public Interfaces

- `GET /api/config/provider-credentials` 新增 `stable_credential_id`。
- `GET /api/config/ai-routing` 新增或补齐 `stable_credential_id`、`configured`、`credential_error`。
- `POST /api/config/ai-routing` 接受 stable credential id，非法或不可用 credential id 返回 400。
- `GET /api/rag/knowledge-bases` 与 `GET /api/chat/knowledge-bases` 的 `current_embeddings` 增加非敏感 credential 诊断字段。

## Test Plan

```bash
python -m pytest tests/test_ai_runtime.py -q
python -m pytest tests/test_rag_runtime.py tests/test_fastapi_rag_admin_endpoints.py tests/test_fastapi_chat_endpoints.py -q
python -m pytest tests/test_fastapi_ops_read_endpoints.py tests/test_fastapi_ops_write_endpoints.py -q
npm run build
python -m pytest tests/test_react_fastapi_authority.py -q
python scripts/diagnose_embedding_runtime.py --config config/sites.yaml --json
```

## Assumptions

- `api_tokens` 继续作为 credential instance 存储。
- `sites.yaml` 只保存 provider/model/credential binding 和非密参数。
- 推荐新写法为 `openai:llm:instance:default`；历史 row id `openai:llm:db:<id>` 保持兼容。
- `.env` 仍可作为 bootstrap/import fallback，但不是长期运行时主源。
