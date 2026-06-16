# FastAPI 文件读取接口第二批实施计划

## 一、现状分析

- 当前分支：`feature/fastapi-native-file-read-phase2`
- 当前基线：`main` 已合入第一批原生 FastAPI 读接口
- 已原生迁移的接口：
  - `GET /api/health`
  - `GET /api/migration/status`
  - `GET /api/stats`
  - `GET /api/categories`
  - `GET /api/files`
- 仍由 legacy Flask 提供、且 React 直接依赖的结构化文件读接口：
  - `GET /api/sources`
  - `GET /api/files/detail?url=...`
  - `GET /api/files/{file_url}/markdown`

### 页面依赖面

- `Database` 仍依赖：
  - `GET /api/sources`
  - `GET /api/files`
  - `GET /api/categories`
- `FileDetail` 仍依赖：
  - `GET /api/files/detail?url=...`
  - `GET /api/files/{file_url}/markdown`
- 仍保留在后续批次、不纳入本轮的接口：
  - `GET /api/download`
  - `GET /api/rag/files/preview`
  - `GET /api/files/{file_url}/chunk-sets`

### 技术判断

- `/api/sources` 很小，底层直接复用 `Storage.get_unique_sources()` 即可。
- `/api/files/detail` 本质是单文件详情读取，底层直接复用 `Storage.get_file_with_catalog(url)`。
- `/api/files/{file_url}/markdown` 是轻量读接口，底层直接复用 `Storage.get_file_markdown(url)`。
- `/api/download` 和 preview 属于文件响应/流式预览，不应和本轮 JSON 读接口迁移绑在一起。

## 二、需求说明

本轮目标是在不修改 React 调用地址和返回结构的前提下，将以下 Flask 读接口迁为 FastAPI 原生：

- `GET /api/sources`
- `GET /api/files/detail`
- `GET /api/files/{file_url}/markdown`

明确不在本轮范围内的内容：

- 不迁移下载流接口
- 不迁移文件预览接口
- 不迁移 markdown 写接口 `POST /api/files/{file_url}/markdown`
- 不调整前端页面调用方式

约束条件：

- 保持既有 JSON 契约兼容
- 保持 `REQUIRE_AUTH=true/false` 下的权限语义兼容
- 保持 legacy Flask fallback，不影响未迁移接口

## 三、技术方案

### 路由层

在现有 `ai_actuarial/api/routers/read.py` 中继续补充原生读路由：

- `GET /api/sources`
- `GET /api/files/detail`
- `GET /api/files/{file_url}/markdown`

权限映射保持与 Flask 一致：

- `/api/sources` 使用 `files.read`
- `/api/files/detail` 使用 `files.read`
- `/api/files/{file_url}/markdown` 使用 `markdown.read`

### 服务层

在 `ai_actuarial/api/services/read.py` 中继续补充更小的读服务函数：

- `list_sources(...)`
- `get_file_detail(...)`
- `get_file_markdown(...)`

设计要求：

- 服务层只负责数据读取和响应载荷拼装
- 路由层只负责参数解析、权限校验、HTTP 错误语义
- 尽量直接复用 `Storage` 现有能力，不在本轮新建额外数据库抽象

### 返回契约

保持与现有 Flask 完全兼容：

- `/api/sources` 返回：
  - `{"sources": [...]}`
- `/api/files/detail` 返回：
  - `{"file": {...}}`
  - 缺失 `url` 参数时返回 `400`
  - 文件不存在时返回 `404`
- `/api/files/{file_url}/markdown` 返回：
  - `{"success": true, "markdown": {...}}`
  - 无 markdown 或文件不存在时仍返回 `200`，且 `markdown` 为 `null`

### 测试策略

在现有 FastAPI 集成测试基础上扩充：

- 原生路由优先级是否生效
- `/api/sources` 正常返回 source 列表
- `/api/files/detail` 的成功、缺参、404 场景
- `/api/files/{file_url}/markdown` 的空值、有值、认证场景
- `REQUIRE_AUTH=true` 时 bearer token 与 Flask session cookie 行为
- `/api/migration/status` 中 `native_paths` 是否包含新增接口

## 四、实施步骤

### Phase 1: 扩展读服务层

预计耗时：0.5-1 小时

- [ ] 新增 sources/detail/markdown 读服务函数
- [ ] 复用现有 `Storage` 能力，避免复制 Flask 路由逻辑
- [ ] 保持返回结构与 Flask 对齐

### Phase 2: 扩展 FastAPI 原生读路由

预计耗时：0.5-1 小时

- [ ] 增加三个原生 GET 路由
- [ ] 对齐权限与状态码语义
- [ ] 确认 native route 会优先于 legacy Flask mount

### Phase 3: 自动化测试

预计耗时：0.5-1 小时

- [ ] 扩充 FastAPI 定向测试
- [ ] 跑相关旧测试，重点验证 markdown 行为兼容
- [ ] 跑全量 `pytest`

### Phase 4: 文档与记录

预计耗时：0.5 小时

- [ ] 记录实现范围、测试结果、兼容性说明
- [ ] 补开发日志
- [ ] 输出用户测试建议

## 五、关键决策

### 决策 1：是否把 `download` 一并迁走

- 选项 A：本轮把 `download` 也纳入
- 选项 B：本轮只做结构化 JSON 读接口

选择：B

原因：

- `download` 是文件响应，不属于这轮最稳定的 JSON 读接口迁移范围
- 一起做会把权限、路径解析、磁盘文件存在性和浏览器行为耦合进来
- 先把 React 最直接依赖的结构化读取接口迁完，能更快得到稳定可测的结果

### 决策 2：是否连 `POST /api/files/{file_url}/markdown` 一起迁移

- 选项 A：读写一起迁
- 选项 B：本轮先迁 GET，写接口留到下一批

选择：B

原因：

- 这轮主题是文件读取接口第二批，不把写路径混进来
- markdown 写入涉及权限、参数校验和更新后回读，风险高于只读接口
- 先把 `FileDetail` 的读链路完全原生化，下一批再迁写接口更清晰

## 六、风险与回退

- 风险 1：`file_url` 路径参数的解码行为与 Flask 存在细微差异
  - 应对：用现有 markdown URL 编码测试覆盖空格和百分号场景
- 风险 2：`/api/files/detail` 的 400/404 语义不一致
  - 应对：明确补 FastAPI 测试覆盖
- 风险 3：权限依赖和 legacy 行为不完全一致
  - 应对：保留 `REQUIRE_AUTH=true/false` 双模式测试

回退方案：

- 任何未迁移接口仍由 legacy Flask fallback 提供
- 若本轮新增原生端点出现问题，可在单个提交级别回退，不影响已完成的第一批读接口
