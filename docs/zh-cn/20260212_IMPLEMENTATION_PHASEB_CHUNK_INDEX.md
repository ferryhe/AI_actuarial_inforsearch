# 实现报告 - 2026-02-12 - Phase B 任务页 Chunk/Index 任务落地

## 1. 本次范围

按 `docs/20260212_GLOBAL_CHUNK_KB_COMPOSITION_PLAN.md` 的 Phase B 执行：

- 任务系统新增两类任务：
  - `chunk_generation`
  - `kb_index_build`
- Tasks 页面新增两类任务入口与弹窗。
- 后端新增 chunk 候选统计接口。
- KB 任务查询兼容 `kb_index_build` 历史展示。

## 2. 后端改动

### 2.1 `ai_actuarial/web/app.py`

- `execute_collection_task(...)` 新增 `chunk_generation` 分支：
  - 支持 `file_urls` 或 `scan_start_index + scan_count` 两种范围。
  - 支持 `profile_id` 复用已有 profile，或按临时参数自动 upsert profile。
  - 支持 `overwrite_same_profile`（覆盖同配置 chunk）与默认复用策略。
  - 任务日志输出 created/overwritten/reused/no_markdown/errors 统计。
- `execute_collection_task(...)` 将 `kb_index_build` 作为 `rag_indexing` 同路径执行（兼容旧索引流程）。
- `_get_rag_kb_tasks(...)` 过滤条件扩展为同时包含：
  - `rag_indexing`
  - `kb_index_build`
- `/api/collections/run`：
  - `valid_types` 增加 `chunk_generation`、`kb_index_build`
  - 参数校验增加：
    - `chunk_generation` 必须有 `file_urls` 或 `scan_count`
    - `kb_index_build` 必须有 `kb_id`
- 新增 `GET /api/chunk_generation/stats`：
  - 返回 markdown 文件总数、已有 chunk 的文件数、首个缺 chunk 的索引位置。

### 2.2 `ai_actuarial/web/rag_routes.py`

- KB 任务历史 fallback 读取兼容 `kb_index_build` 类型。

## 3. 前端改动

### 3.1 `ai_actuarial/web/templates/tasks.html`

任务卡新增：

- `Generate Chunks`
- `Build KB Index`

新增弹窗：

- `chunk-generation-modal`
  - Chunk Profile（选择已有 or 自定义）
  - Chunk 参数（size/overlap/splitter/tokenizer/version）
  - 扫描范围（start/scan count）
  - 覆盖策略（overwrite_same_profile）
- `kb-index-build-modal`
  - KB 选择
  - 可选 file_urls（逐行）
  - incremental / force_reindex

新增前端逻辑：

- `openChunkGenerationModal` / `startChunkGeneration`
- `openKbIndexBuildModal` / `startKbIndexBuild`
- `loadChunkGenerationStats`
- `loadChunkProfiles`
- `loadKbOptionsForIndexBuild`

## 4. 验证结果

执行：

- `python -m pytest -q`

结果：

- `71 passed`
- 无新增失败。

## 5. 备注

- 当前 `kb_index_build` 为任务层新类型，执行逻辑与现有 `rag_indexing` 兼容共用（符合 Phase B “双写/兼容”目标）。
- 下一阶段（Phase C）可进一步将 KB 索引完全切换到“基于 `kb_chunk_bindings` 的新模型”执行链路。
