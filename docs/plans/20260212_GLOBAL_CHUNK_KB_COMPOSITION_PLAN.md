# 20260212 Global Chunk + KB Composition Plan

## 1. 目标与原则

本方案将 RAG 能力拆成两层：

- 全局层：先生成并管理 `chunk`（不绑定 KB）
- KB 层：只负责组合 chunk 并构建/管理 index

核心目标：

- 同一文件允许存在多个 chunk（不同配置）
- KB 新增文件时，若配置匹配则复用 chunk；不匹配则自动生成新 chunk
- Database 页面可查看和管理“无 chunk / 多 chunk / 多 index”场景
- KB 页面聚焦“组合”能力
- Tasks 页面新增 chunk/index 任务，支持同配置覆盖策略

## 2. 关键业务规则

### 2.1 文件与 Chunk 关系

- 一个文件可有多个 `chunk_set`
- `chunk_set` 由以下维度唯一确定：
  - `file_url`
  - `markdown_hash`
  - `chunk_profile_id`

说明：

- 同文件、同 markdown、同配置 => 可直接复用同一 chunk_set
- markdown 更新或配置变化 => 生成新的 chunk_set

### 2.2 KB 与 Chunk 关系

- KB 只组合 chunk，不拥有 chunk 原始数据
- KB 内文件在“组合阶段”按 KB 的 `chunk_profile` 检查匹配：
  - 匹配：直接引用已有 chunk_set
  - 不匹配：创建 chunk 任务生成后再引用

### 2.3 Index 规则

- index 始终属于 KB（不做全局 index）
- KB index 由以下因素决定：
  - KB 文件选择结果（引用的 chunk_set）
  - embedding model
  - index type / params

建议约束：

- 一个 KB 仅允许一个 active embedding model
- 一个 KB 仅允许一个 active chunk_profile（避免混乱检索语义）

## 3. 数据模型（新增）

### 3.1 配置与全局 Chunk

- `chunk_profiles`
  - `profile_id`, `name`, `chunk_size`, `chunk_overlap`, `splitter`, `tokenizer`, `version`, `created_at`

- `file_chunk_sets`
  - `chunk_set_id`, `file_url`, `markdown_hash`, `profile_id`, `status`, `chunk_count`, `created_at`, `updated_at`
  - 唯一键：`(file_url, markdown_hash, profile_id)`

- `global_chunks`
  - `chunk_id`, `chunk_set_id`, `chunk_index`, `content`, `token_count`, `section_hierarchy`, `content_hash`, `created_at`

- `chunk_embeddings`（可选，建议做）
  - `chunk_id`, `embedding_model`, `vector_ref`, `dim`, `created_at`
  - 用于缓存，避免重复 embedding 计算

### 3.2 KB 组合与索引

- `kb_chunk_bindings`
  - `kb_id`, `file_url`, `chunk_set_id`, `bound_at`, `bound_by`

- `kb_index_versions`
  - `index_version_id`, `kb_id`, `embedding_model`, `index_type`, `status`, `artifact_path`, `chunk_count`, `built_at`

- `kb_index_items`（可选）
  - `index_version_id`, `chunk_id`
  - 用于追踪某个 index 实际包含哪些 chunk

## 4. 页面方案

## 4.1 Database 页面（总览 + 入口）

目标：解决“没有 chunk 如何看、多个 chunk 如何看、多个 index 如何看”

列表列建议：

- `#` 序号
- 标题 / 来源 / 分类
- Markdown（有/无）
- Chunk（无 / 1 / N）
- Index（无 / 1 / N，表示此文件被多少 KB 索引）
- 操作（View）

点击行进入 File Details（核心管理页）。

### 4.2 File Details 页面（细节管理页）

在 Markdown 区域上方新增两个区块：

- Chunk Status
  - 无 chunk：显示 Empty 状态 + `Create Chunk Task`
  - 单 chunk：显示 profile、更新时间、chunk 数、来源 markdown_hash
  - 多 chunk：显示 chunk_set 列表（profile、时间、chunk 数、被哪些 KB 引用）+ 可预览

- Index Status
  - 无 index：显示 Empty 状态
  - 单/多 index：按 KB 展示 `KB | embedding model | updated | chunk_count`

操作建议：

- `Create Chunk Task`（可带 profile 预设）
- `Rebuild Chunk (same profile)`
- `Bind to KB`（快速加入某 KB 组合）
- `Submit Index Task`（按 KB）

## 4.3 KB 页面（主功能：组合）

KB 页面只做组合与编排，不做底层 chunk 编辑。

主要视图：

- KB 配置区
  - `chunk_profile`
  - `embedding_model`
  - `index_type`

- 文件组合区（每个文件展示匹配状态）
  - `Matched`：可直接纳入
  - `Need Chunk`：缺同配置 chunk，可一键批量生成
  - `Ready to Index`：可直接提交 index

主要动作：

- `Generate Missing Chunks`
- `Bind Matched Chunks`
- `Build/Update Index`

## 5. Tasks 页面方案（新增两个任务类型）

## 5.1 Chunk Generation Task（类似 doc_to_md）

字段：

- Scope：单文件 / 多文件 / 筛选结果
- Chunk Profile：选择已有 profile 或临时参数
- Overwrite Policy：
  - `skip_same_profile`（默认）
  - `overwrite_same_profile`（覆盖同配置）
- Name：任务名

执行结果：

- created / reused / overwritten / failed 数量

## 5.2 Index Task

字段：

- KB
- file scope（全部绑定文件 / 指定文件）
- incremental / force rebuild
- embedding model（默认 KB 配置）

执行结果：

- indexed files / total chunks / failed files

## 6. API 设计（建议）

- `POST /api/chunk/profiles`
- `GET /api/chunk/profiles`
- `POST /api/files/{file_url}/chunk-sets/generate`
- `GET /api/files/{file_url}/chunk-sets`
- `GET /api/files/{file_url}/indexes`
- `POST /api/rag/knowledge-bases/{kb_id}/bindings`
- `POST /api/rag/knowledge-bases/{kb_id}/index/build`
- `GET /api/rag/knowledge-bases/{kb_id}/composition/status`

任务接口扩展：

- `type = chunk_generation`
- `type = kb_index_build`

## 7. 覆盖与版本策略

- 默认：不覆盖同配置 chunk（复用）
- 显式勾选后：覆盖同配置 chunk
- 覆盖动作建议保留历史版本（软删除/历史表），便于回滚与审计

## 8. 迁移实施阶段

### Phase A（Schema + 兼容）

- 加新表，不移除旧表
- 旧流程可继续跑

### Phase B（双写）

- 生成 chunk 时写入新模型
- KB 索引仍可兼容旧逻辑

### Phase C（切换）

- KB 组合与索引全面改走新模型
- UI 切换到新状态展示

### Phase D（清理）

- 清理旧字段/旧任务路径（可延后）

## 9. 验收标准

- 同一文件可生成并保留多个 chunk_set
- KB 新增文件时，匹配配置可复用，不匹配会触发生成
- Database 可清楚区分：无 chunk / 多 chunk / 多 index
- File Details 可查看并管理 chunk_set 与 index 记录
- Tasks 可提交 chunk/index 任务，支持同配置覆盖策略
- 全量测试通过

## 10. 需要你最终确认的开关

- 是否强制 KB 单一 `chunk_profile`（建议：是）
- 是否强制 KB 单一 `embedding_model`（建议：是）
- 覆盖同配置 chunk 时，是否保留历史版本（建议：是）
- Database 列表是否直接显示 `Chunk=N` / `Index=N` 计数（建议：是）
