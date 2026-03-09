# FastAPI 原生读接口实施计划

## 一、现状分析

- 当前分支：`feature/fastapi-native-read-endpoints`
- 基线分支：`feature/react-fastapi-migration`
- 当前 FastAPI 仅原生提供：
  - `/api/health`
  - `/api/migration/status`
- 目标接口目前仍由 legacy Flask 提供：
  - `GET /api/stats`
  - `GET /api/files`
  - `GET /api/categories`
- React 端实际依赖如下：
  - Dashboard：
    - `GET /api/stats`
    - `GET /api/files?limit=8&order_by=last_seen&order_dir=desc`
  - Database：
    - `GET /api/files`
    - `GET /api/sources`
    - `GET /api/categories`
  - task options：
    - `GET /api/categories?mode=used`

### 代码现状判断

- `/api/stats` 本身已经很小，只是组合了几个独立方法：
  - `Storage.get_file_count()`
  - `Storage.get_cataloged_count()`
  - `Storage.get_sources_count()`
  - 运行中任务数
- `/api/categories` 也比较清晰：
  - 默认模式优先读 `categories.yaml`
  - `mode=used` 回退数据库唯一分类
- `/api/files` 表面是一个大接口，但底层核心查询已经收敛到单一函数：
  - `Storage.query_files_with_catalog()`
- 这个查询函数当前返回字段很多，明显超过某些页面的最小需要。

### 页面实际字段依赖

- Dashboard 对 `/api/files` 只需要：
  - `url`
  - `title`
  - `original_filename`
  - `source_site`
  - `content_type`
  - `last_seen`
- Database 对 `/api/files` 需要：
  - `url`
  - `title`
  - `original_filename`
  - `source_site`
  - `content_type`
  - `last_seen`
  - `category`
  - `summary`
  - `markdown_content`
  - `markdown_source`
  - `bytes`
  - `deleted_at`
- 当前 `Storage.query_files_with_catalog()` 实际会返回更多字段：
  - `sha256`
  - `source_page_url`
  - `local_path`
  - `last_modified`
  - `etag`
  - `published_time`
  - `first_seen`
  - `crawl_time`
  - `keywords`
  - `markdown_updated_at`
  - `rag_chunk_count`
  - `rag_indexed_at`

结论：

- 你说得对，`/api/files` 里面的内容不该简单当成一个“页面大接口”照搬。
- 但短期内不建议直接修改前端公共 API 地址，因为那会扩大迁移面。
- 更稳的做法是：
  - 对外继续兼容 `GET /api/files`
  - 在 FastAPI 内部先拆成更小的服务函数和响应投影
  - 如果后面确认收益明显，再新增更细的专用小接口

## 二、需求说明

目标是在不破坏现有 React 调用的前提下，把以下接口迁为 FastAPI 原生：

- `GET /api/stats`
- `GET /api/categories`
- `GET /api/files`

同时引入更小的内部能力拆分：

- stats 聚合函数
- category 读取函数
- file list 查询与字段投影函数

可选的后续优化目标：

- 为 Dashboard 单独提供更轻量的 recent-files 接口
- 为 Database 单独提供 filters/options 接口
- 将 `/api/files` 从“全字段大列表”收缩成更明确的 view model

约束条件：

- 当前 React 页面不改 URL，不改现有调用参数
- 当前 JSON 契约先保持兼容
- `REQUIRE_AUTH=true/false` 两种模式都要维持现有行为
- legacy Flask fallback 保留，未迁移接口不受影响

## 三、技术方案

### 方案概述

在 `ai_actuarial/api/routers/` 下新增读接口模块，在 `ai_actuarial/api/` 下新增共享依赖/服务层，将现有 Flask 读逻辑拆成更小的 Python 函数，然后由 FastAPI 路由组合返回兼容 JSON。

### 分层方案

1. 路由层

- 负责解析 query 参数
- 调用权限依赖
- 组装 HTTP 响应

2. 服务层

- `get_dashboard_stats(...)`
- `list_categories(...)`
- `list_used_categories(...)`
- `list_files(...)`
- `project_recent_files(...)`
- `project_database_files(...)`

3. 数据层

- 优先复用现有 `Storage` 抽象
- 配置仍复用 `_get_categories_config_path()` 与 YAML 读取逻辑

### `/api/files` 的建议拆法

#### 对外第一阶段

仍保留：

- `GET /api/files`

但在 FastAPI 内部拆成：

- 参数解析函数
- 文件查询函数
- Dashboard/Database 共用字段投影函数

#### 对外第二阶段可选

如果后续想进一步瘦身，可新增：

- `GET /api/dashboard/recent-files`
- `GET /api/database/files`
- `GET /api/database/filter-options`

然后再逐步让 React 页面切过去。

这样做的好处：

- 先把“Flask -> FastAPI 原生”这个目标完成
- 不把“接口瘦身”和“框架迁移”耦合到同一个 PR
- 未来如果要继续拆 API，有现成的服务层可以复用

### 鉴权设计

- 为 FastAPI 增加轻量权限依赖
- 行为对齐现有 Flask：
  - `stats.read`
  - `files.read`
- `REQUIRE_AUTH=false` 时保留公共只读访问
- `REQUIRE_AUTH=true` 时沿用 token/session 语义

### 测试策略

新增 FastAPI 集成测试，覆盖：

- `/api/stats`
- `/api/categories`
- `/api/files`
- `REQUIRE_AUTH=true`
- `REQUIRE_AUTH=false`
- `/api/files` 的分页、排序、筛选
- `mode=used`
- `/api/migration/status` 中 native path 列表更新

## 四、实施步骤

### Phase 1: 建立共享服务层与测试骨架

**时间估算**: 1-1.5 小时

**步骤**:

- [ ] 抽出 FastAPI 读接口共享依赖
- [ ] 抽出 stats/categories/files 服务函数
- [ ] 新增 FastAPI 读接口测试骨架

### Phase 2: 迁移 `/api/stats`

**时间估算**: 0.5-1 小时

**步骤**:

- [ ] 实现 `GET /api/stats`
- [ ] 保持 Dashboard 字段兼容
- [ ] 验证 native route 生效

### Phase 3: 迁移 `/api/categories`

**时间估算**: 0.5-1 小时

**步骤**:

- [ ] 实现 `GET /api/categories`
- [ ] 覆盖默认模式与 `mode=used`
- [ ] 验证 Database 和 task options 契约

### Phase 4: 迁移 `/api/files`

**时间估算**: 1.5-2.5 小时

**步骤**:

- [ ] 实现 `GET /api/files`
- [ ] 内部拆分参数解析、查询、字段投影
- [ ] 对齐 Dashboard 与 Database 的共同字段
- [ ] 验证分页、排序、筛选语义

### Phase 5: 评估下一步接口瘦身

**时间估算**: 0.5 小时

**步骤**:

- [ ] 判断是否值得新增 `recent-files` / `database/files` / `filter-options`
- [ ] 如果不在本轮实施，记录为后续子 PR 范围

### Phase 6: 自动化验证与文档

**时间估算**: 0.5-1 小时

**步骤**:

- [ ] 跑新增 FastAPI 测试
- [ ] 跑全量 pytest
- [ ] 补开发日志与测试结果

## 五、关键决策点

### 决策 1: 是先改外部接口，还是先拆内部服务层

**选项**: A. 直接新增很多细接口并同步改 React；B. 先保持旧 URL，不改 React，内部先拆小

**选择**: B

**理由**: 这次主任务是迁移到 FastAPI 原生，不是同时做前端 API 全面重构。先内部拆小、外部兼容，风险最低。

### 决策 2: `/api/files` 是否保留

**选项**: A. 立即废弃 `/api/files`；B. 本轮保留 `/api/files`，后续再演进

**选择**: B

**理由**: Dashboard 和 Database 都依赖它，立即拆掉会扩大改动范围。当前更适合先把逻辑拆干净，再看是否值得把 URL 层也切开。

### 决策 3: 优先迁移顺序

**选项**: A. 先做 `/api/files`；B. 先做 `/api/stats` 和 `/api/categories`

**选择**: B

**理由**: 这两个接口更简单，适合先验证 FastAPI 权限、配置访问和原生路由优先级。

## 六、风险与注意事项

- `/api/files` 的字段兼容性是这一批最大的回归点。
- FastAPI 原生路由必须验证优先级，避免表面迁移但实际仍走 Flask。
- `categories.yaml` 与数据库 fallback 行为必须与 Flask 一致。
- 内部服务层拆分不能顺带改变排序、筛选、默认值语义。

## 七、成功标准

- [ ] `GET /api/stats` 由 FastAPI 原生提供
- [ ] `GET /api/categories` 由 FastAPI 原生提供
- [ ] `GET /api/files` 由 FastAPI 原生提供
- [ ] React 端 Dashboard / Database / task options 无需改动即可继续工作
- [ ] FastAPI 内部已形成更小的服务函数边界
- [ ] 新增测试通过
- [ ] 全量 pytest 通过
- [ ] 开发日志完成

## 八、时间估算

**总计**: 4.5-7.5 小时
