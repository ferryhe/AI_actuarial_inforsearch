# FastAPI 原生读接口实施计划

## 一、现状分析

- 当前分支：`feature/fastapi-native-read-endpoints`
- 基线分支：`feature/react-fastapi-migration`
- 当前 FastAPI 仅原生提供：
  - `/api/health`
  - `/api/migration/status`
- 其余 API 仍由 FastAPI 网关挂载 legacy Flask 回退。
- 本次目标的 3 个接口目前都在 Flask 中实现：
  - `/api/stats`
  - `/api/files`
  - `/api/categories`
- React 端直接依赖这些接口：
  - Dashboard：`/api/stats`、`/api/files`
  - Database：`/api/files`、`/api/categories`
  - task options：`/api/categories?mode=used`

## 二、需求说明

目标是在不改变前端调用方式的前提下，把以下接口改为 FastAPI 原生实现：

- `GET /api/stats`
- `GET /api/files`
- `GET /api/categories`

约束条件：

- 返回 JSON 结构必须与当前 Flask 接口保持兼容。
- 保留现有鉴权语义：
  - `REQUIRE_AUTH=true` 时必须走 token/session 权限校验。
  - `REQUIRE_AUTH=false` 时保留公共只读访问行为。
- legacy Flask fallback 继续保留，未迁移接口不受影响。
- 完成后必须通过自动化测试，并补文档记录。

## 三、技术方案

### 方案概述

在 `ai_actuarial/api/routers/` 下新增读接口路由模块，FastAPI 直接调用现有 `Storage` 抽象和配置读取逻辑，避免通过 HTTP 再转发到 Flask。

### 关键设计

1. 鉴权与权限

- 为 FastAPI 增加与 Flask 行为一致的轻量权限依赖。
- 优先复用现有 Flask 中成熟的 token/session 规则，而不是重新定义一套新的权限模型。
- 本批只覆盖 `stats.read` / `files.read` 这类读权限。

2. 数据来源

- `/api/stats`：直接调用 `Storage.get_file_count()`、`get_cataloged_count()`、`get_sources_count()`，并补上运行中任务数。
- `/api/files`：直接调用 `Storage.query_files_with_catalog()`，保留现有 query 参数和分页格式。
- `/api/categories`：
  - `mode=used` 时走数据库唯一分类。
  - 默认模式优先读取 `categories.yaml`，缺失时回退数据库。

3. 兼容策略

- 响应字段名、默认值、查询参数名称保持不变。
- React 端不改调用地址，不改请求参数。
- 通过新增 FastAPI 测试确认原生路由优先于 Flask fallback 生效。

4. 测试策略

- 新增 FastAPI 集成测试，覆盖：
  - 基本成功响应
  - `REQUIRE_AUTH=true` 时的鉴权
  - `REQUIRE_AUTH=false` 时的公共访问
  - `/api/files` 的分页/筛选
  - `/api/categories?mode=used`
  - `/api/migration/status` 中 native path 列表更新
- 回归全量 pytest。

## 四、实施步骤

### Phase 1: 搭建共享依赖与测试骨架

**时间估算**: 1-1.5 小时

**步骤**:

- [ ] 设计 FastAPI 读接口模块结构与响应模型
- [ ] 建立 FastAPI 侧读权限依赖
- [ ] 新增原生读接口测试文件骨架

### Phase 2: 迁移 `/api/stats`

**时间估算**: 0.5-1 小时

**步骤**:

- [ ] 实现 `GET /api/stats`
- [ ] 补 Dashboard 依赖字段测试
- [ ] 确认 native route 出现在 migration status 中

### Phase 3: 迁移 `/api/categories`

**时间估算**: 0.5-1 小时

**步骤**:

- [ ] 实现 `GET /api/categories`
- [ ] 覆盖默认模式与 `mode=used`
- [ ] 校验 Database / task options 依赖字段

### Phase 4: 迁移 `/api/files`

**时间估算**: 1-2 小时

**步骤**:

- [ ] 实现 `GET /api/files`
- [ ] 保持分页、排序、筛选参数兼容
- [ ] 校验 Dashboard / Database 使用场景

### Phase 5: 自动化验证与文档

**时间估算**: 0.5-1 小时

**步骤**:

- [ ] 跑新增 FastAPI 测试
- [ ] 跑全量 pytest
- [ ] 记录开发日志与测试结果

## 五、关键决策点

### 决策 1: 直接复用 Storage，还是调用 legacy Flask 逻辑

**选项**: A. 通过 HTTP/WSGI 间接调用 Flask；B. 直接调用 Storage 和配置逻辑

**选择**: B

**理由**: 这批接口本身就是读接口，底层逻辑简单稳定，直接调用抽象层更清晰，也更符合“原生 FastAPI”目标。

### 决策 2: 先迁移哪个接口

**选项**: A. 先做 `/api/files`；B. 先做 `/api/stats` 和 `/api/categories`

**选择**: B

**理由**: `/api/stats` 和 `/api/categories` 读路径更短、依赖更少，适合作为 FastAPI 鉴权和返回契约的第一批验证。

### 决策 3: 是否顺带重构 Flask 权限逻辑

**选项**: A. 先抽出完整共享 auth 模块；B. 先做最小兼容适配

**选择**: B

**理由**: 当前目标是接口迁移，不是权限系统重构。先保证兼容和测试通过，再考虑后续抽象。

## 六、风险与注意事项

- FastAPI 原生路由和 Flask mount 的优先级必须验证，避免看起来迁了但实际仍走 Flask。
- `/api/files` 返回结构较大，字段兼容性是本批最大回归点。
- 认证场景要覆盖 `REQUIRE_AUTH=true` 和 `false` 两种模式。
- `categories.yaml` 与数据库 fallback 的行为必须与 Flask 保持一致。

## 七、成功标准

- [ ] `/api/stats`、`/api/files`、`/api/categories` 由 FastAPI 原生提供
- [ ] React 端 Dashboard / Database / task options 无需改动即可正常调用
- [ ] `/api/migration/status` 能反映新增 native paths
- [ ] 新增测试通过
- [ ] 全量 pytest 通过
- [ ] 开发日志完成

## 八、时间估算

**总计**: 3.5-6.5 小时
