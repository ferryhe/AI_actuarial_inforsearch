# FastAPI 全量迁移计划

> 目标：把 React 产品面向用户的所有能力都切到原生 FastAPI；Flask 只保留临时兼容层与遗留 HTML，直到产品级 `/api/*` 全部清空为止。

## 一、当前已经删掉/隐藏的旧功能（基于当前分支改动）

说明：这里的“删掉”是指**已经从 React 的 FastAPI-native shell 中移除入口、替换为不可用页、或降级为只读**；并不等于 Flask 后端代码已经完全删除。

### 1. 已从路由主入口移除，统一改为 `FeatureUnavailable`
来源：`client/src/App.tsx`

- 登录页 `/login`
- 注册页 `/register`
- 文件预览 `/file-preview`
- Chat `/chat`
- Tasks `/tasks`
- Logs `/logs`
- Knowledge 列表 `/knowledge`
- Knowledge 详情 `/knowledge/:kbId`
- Settings `/settings`
- Users `/users`
- Profile `/profile`

这些页面原先直接挂真实页面组件，现在已统一改成 `FeatureUnavailable`，文案明确写的是“仍依赖 legacy APIs，因此在 FastAPI-native mode 下隐藏”。

### 2. 文件详情页已删除旧实现，替换为 FastAPI 原生只读版本
来源：`client/src/App.tsx`、`client/src/pages/NativeFileDetail.tsx`

- 原 `FileDetail` 已不再作为主路由组件使用
- `/file-detail` 现在改为 `NativeFileDetail`
- 新页面只保留：
  - 文件基础信息读取
  - markdown 读取
- 已移除旧页中的能力：
  - 元数据编辑
  - markdown 编辑
  - 重新 catalog
  - chunk set 管理/生成
  - 删除文件
  - 下载/预览联动按钮
  - 依赖任务轮询的操作按钮

### 3. 侧边栏导航已删除的旧入口
来源：`client/src/components/Layout.tsx`

已从导航菜单移除：
- Chat
- Tasks
- Logs
- Knowledge
- Users
- Profile
- Settings

侧边栏目前只保留：
- Dashboard
- Database

### 4. Dashboard 快捷操作已删除的旧入口
来源：`client/src/pages/Dashboard.tsx`

已移除快捷入口：
- Task Center
- Knowledge Bases
- Chat

Dashboard 现在只保留数据库浏览作为主要入口之一。

### 5. 顶栏已删除的旧认证相关入口
来源：`client/src/components/Layout.tsx`、`client/src/context/AuthContext.tsx`

已删除/停用：
- 顶栏用户信息展示
- `/profile` 入口按钮
- logout 按钮
- `/login` 按钮
- 依赖 legacy 登录流的重定向逻辑
- 调 `/api/auth/me` + `/api/user/me` 的旧认证探测逻辑
- 调 `/logout` 的前端登出流程

现在的认证判断被简化为：
- 用 `/api/stats` 能否成功来探测 FastAPI 可用性
- 若返回 401，只判断“当前环境要求认证”，但不再暴露 legacy 登录 UI

### 6. Database 页面已删除/降级的旧功能
来源：`client/src/pages/Database.tsx`

已删除或降级：
- 导出 CSV 按钮
- 基于角色的导出能力判断
- 表格多选 checkbox
- 批量删除悬浮条
- bulk delete 错误提示条
- `ConfirmDeleteModal` 批量删除流程
- 行内 preview 按钮
- 行内 download 按钮
- 选择态高亮与批量操作状态

Database 目前被明确标记为：`FastAPI-native read-only view`。

---

## 二、这些已删旧功能背后仍依赖的 Flask/Legacy API 面

来源：`docs/API_MIGRATION_STATUS.md`、各旧页面源码。

### 1. Auth / User
主要还依赖：
- `/api/auth/me`
- `/api/auth/tokens`
- `/api/user/me`
- `/api/user/profile`
- `/api/admin/users`

对应旧页面：
- `Login.tsx`
- `Register.tsx`
- `Profile.tsx`
- `Users.tsx`
- `Settings.tsx` 的 token 管理区

### 2. Config / Schedule / Task orchestration
主要还依赖：
- `/api/config/sites`
- `/api/config/sites/add`
- `/api/config/sites/update`
- `/api/config/sites/delete`
- `/api/config/sites/import`
- `/api/config/backups`
- `/api/config/backups/restore`
- `/api/config/backups/delete`
- `/api/config/backend-settings`
- `/api/config/llm-providers`
- `/api/config/ai-models`
- `/api/config/search-engines`
- `/api/config/categories`
- `/api/schedule/status`
- `/api/scheduled-tasks`
- `/api/scheduled-tasks/add`
- `/api/scheduled-tasks/update`
- `/api/scheduled-tasks/delete`
- `/api/schedule/reinit`
- `/api/tasks/active`
- `/api/tasks/history`
- `/api/tasks/log/<task_id>`
- `/api/tasks/stop/<task_id>`
- `/api/collections/run`
- `/api/utils/browse-folder`
- `/api/catalog/stats`
- `/api/markdown_conversion/stats`
- `/api/chunk_generation/stats`

对应旧页面：
- `Tasks.tsx`
- `Logs.tsx`
- `FileDetail.tsx`
- `Settings.tsx`

### 3. Knowledge / RAG / Chat
主要还依赖：
- `/api/chat/conversations`
- `/api/chat/conversations/{id}`
- `/api/chat/query`
- `/api/chat/knowledge-bases`
- `/api/chat/available-documents`
- `/api/chunk/profiles`
- `/api/chunk/profiles/{profile_id}`
- `/api/chunk-sets/cleanup`
- `/api/files/<file_url>/chunk-sets`
- `/api/files/<file_url>/chunk-sets/generate`
- `/api/rag/files/preview`
- `/api/rag/knowledge-bases`
- `/api/rag/knowledge-bases/{kb_id}`
- `/api/rag/knowledge-bases/{kb_id}/stats`
- `/api/rag/knowledge-bases/{kb_id}/files`
- `/api/rag/knowledge-bases/{kb_id}/files/pending`
- `/api/rag/knowledge-bases/{kb_id}/categories`
- `/api/rag/knowledge-bases/{kb_id}/bindings`
- `/api/rag/knowledge-bases/{kb_id}/index`
- `/api/rag/categories/unmapped`
- `/api/rag/files/selectable`

对应旧页面：
- `Chat.tsx`
- `Knowledge.tsx`
- `KBDetail.tsx`
- `FileDetail.tsx`
- `FilePreview.tsx`

### 4. File mutation / export / download
主要还依赖：
- `/api/files/update`
- `/api/files/delete`
- `/api/download`
- `/api/export`

对应旧页面：
- `Database.tsx`
- `FileDetail.tsx`
- `FilePreview.tsx`

---

## 三、当前 FastAPI 已原生承接的范围

来源：`docs/API_MIGRATION_STATUS.md`、`ai_actuarial/api/routers/read.py`

已在 FastAPI 的原生 `/api/*` 下提供：
- `/api/health`
- `/api/migration/status`
- `/api/migration/inventory`
- `/api/stats`
- `/api/sources`
- `/api/categories`
- `/api/files`
- `/api/files/detail`
- `/api/files/{file_url:path}/markdown`

当前结论：**只覆盖了 Dashboard / Database / NativeFileDetail 这一小段只读主路径。**

---

## 四、把“全部改成 FastAPI”的执行计划

原则：
- 一个 PR 只做一个明确范围
- 先补 FastAPI API，再恢复对应前端页面
- 每个阶段都必须减少 Flask `/api/*` 依赖面，而不是做新的兼容债务
- 每个 PR 都要更新 `docs/API_MIGRATION_STATUS.md`
- 每个 PR 都要补测试，确保新增能力不再走 Flask fallback

## PR 1：把 Config / Task 的只读面迁到 FastAPI

### 目标
恢复最小可用的任务总览与配置读取，但只做读，不做写。

### 后端范围
新增或迁移到 `ai_actuarial/api/routers/ops_read.py`：
- `GET /api/config/sites`
- `GET /api/schedule/status`
- `GET /api/scheduled-tasks`
- `GET /api/tasks/active`
- `GET /api/tasks/history`
- `GET /api/tasks/log/{task_id}`
- `GET /api/config/backend-settings`
- `GET /api/config/llm-providers`
- `GET /api/config/ai-models`
- `GET /api/config/search-engines`
- `GET /api/config/categories`

### 前端范围
- 恢复 `/tasks` 为只读版任务中心
- 恢复 `/logs` 为只读版日志页
- 恢复 `/settings` 为只读配置查看页
- 仍然不开放任何写操作按钮

### 测试
新增：
- `tests/test_fastapi_ops_read_endpoints.py`
- 为 React 侧补最小路由/渲染测试

### 完成标志
- Tasks/Logs/Settings 能在 FastAPI-native mode 下只读打开
- 以上页面不再触发 Flask 专属读接口

---

## PR 2：把 Config / Schedule / Task 写操作迁到 FastAPI

### 目标
让任务中心恢复完整运维能力。

### 后端范围
新增或迁移到 `ai_actuarial/api/routers/ops_write.py`：
- `POST /api/config/sites/add`
- `POST /api/config/sites/update`
- `POST /api/config/sites/delete`
- `POST /api/config/sites/import`
- `GET /api/config/sites/export`
- `GET /api/config/sites/sample`
- `GET /api/config/backups`
- `POST /api/config/backups/restore`
- `POST /api/config/backups/delete`
- `POST /api/scheduled-tasks/add`
- `POST /api/scheduled-tasks/update`
- `POST /api/scheduled-tasks/delete`
- `POST /api/schedule/reinit`
- `POST /api/tasks/stop/{task_id}`
- `POST /api/collections/run`
- `GET /api/utils/browse-folder`
- `GET /api/catalog/stats`
- `GET /api/markdown_conversion/stats`
- `GET /api/chunk_generation/stats`

### 前端范围
- 恢复 `Tasks.tsx` 完整功能
- 从 `FeatureUnavailable` 改回真实 `/tasks`
- Dashboard 恢复 Task Center 快捷入口
- 侧边栏恢复 Tasks 导航

### 测试
新增：
- `tests/test_fastapi_ops_write_endpoints.py`
- 任务启动/停止/调度回归测试

### 完成标志
- `Tasks.tsx` 不再依赖 Flask `/api/*`
- 任务中心可以在 FastAPI-native mode 下完整工作

---

## PR 3：把文件写操作与预览能力迁到 FastAPI

### 目标
把文件相关功能从只读补齐到可编辑、可下载、可预览。

### 后端范围
新增或迁移到 `ai_actuarial/api/routers/files_write.py`：
- `POST /api/files/update`
- `POST /api/files/delete`
- `POST /api/files/{file_url:path}/markdown`
- `GET /api/download`
- `GET /api/export`
- `GET /api/rag/files/preview`
- `GET /api/files/{file_url:path}/chunk-sets`
- `POST /api/files/{file_url:path}/chunk-sets/generate`

### 前端范围
- 恢复 Database 的：
  - preview
  - download
  - export
  - 多选/批量删除
- 恢复 FileDetail 的：
  - metadata 编辑
  - markdown 编辑
  - delete
  - chunk set 操作
- 恢复 FilePreview 页面

### 测试
新增：
- `tests/test_fastapi_file_mutations.py`
- `tests/test_fastapi_file_preview.py`

### 完成标志
- Database 不再是 read-only view
- FileDetail / FilePreview 完整走 FastAPI

---

## PR 4：把 Knowledge / RAG 管理能力迁到 FastAPI

### 目标
恢复知识库与 chunk profile 的全部管理能力。

### 后端范围
新增或迁移到 `ai_actuarial/api/routers/rag_admin.py`：
- `GET/POST/PUT/DELETE /api/rag/knowledge-bases...`
- `GET/POST/DELETE /api/chunk/profiles...`
- `POST /api/chunk-sets/cleanup`
- `GET /api/rag/categories/unmapped`
- `GET /api/rag/files/selectable`
- `POST /api/rag/knowledge-bases/{kb_id}/bindings`
- `POST /api/rag/knowledge-bases/{kb_id}/categories`
- `POST /api/rag/knowledge-bases/{kb_id}/index`
- `GET /api/rag/knowledge-bases/{kb_id}/stats`
- `GET /api/rag/knowledge-bases/{kb_id}/files/pending`

### 前端范围
- 恢复 `/knowledge`
- 恢复 `/knowledge/:kbId`
- 恢复侧边栏 Knowledge
- 恢复 Dashboard 的 Knowledge 快捷入口

### 测试
新增：
- `tests/test_fastapi_rag_admin_endpoints.py`
- 绑定、索引、分类、文件选择回归测试

### 完成标志
- Knowledge / KBDetail 不再依赖 Flask `/api/*`

---

## PR 5：把 Chat / 会话能力迁到 FastAPI

### 目标
恢复聊天与 RAG 问答主路径。

### 后端范围
新增或迁移到 `ai_actuarial/api/routers/chat.py`：
- `GET/POST/DELETE /api/chat/conversations`
- `GET /api/chat/conversations/{id}`
- `POST /api/chat/query`
- `GET /api/chat/knowledge-bases`
- `GET /api/chat/available-documents`

### 前端范围
- 恢复 `/chat`
- 恢复侧边栏 Chat
- 恢复 Dashboard 的 Chat 快捷入口

### 测试
新增：
- `tests/test_fastapi_chat_endpoints.py`
- 对话 CRUD + query 流程测试

### 完成标志
- Chat 页不再依赖 Flask `/api/*`

---

## PR 6：把 Auth / User / Admin 迁到 FastAPI

### 目标
恢复真正可用的 FastAPI-native 身份与权限体系。

### 后端范围
新增或迁移到 `ai_actuarial/api/routers/auth.py`：
- `GET /api/auth/me`
- `GET/POST /api/auth/tokens`
- `POST /api/auth/tokens/{token_id}/revoke`
- `GET /api/user/me`
- `PATCH /api/user/profile`
- `GET /api/admin/users`
- `POST /api/admin/users/{id}/role`
- `POST /api/admin/users/{id}/enable`
- `POST /api/admin/users/{id}/disable`
- `POST /api/admin/users/{id}/reset-quota`
- `GET /api/admin/users/{id}/activity`

同时明确：
- 登录、注册、登出到底继续沿用 session cookie，还是统一成 token/session API
- React 端只允许走 FastAPI 暴露的 auth contract

### 前端范围
- 恢复 `/login`
- 恢复 `/register`
- 恢复 `/profile`
- 恢复 `/users`
- 顶栏恢复用户态显示与 logout
- `RequireAuth` 改回原生 FastAPI auth guard

### 测试
新增：
- `tests/test_fastapi_auth_endpoints.py`
- `tests/test_fastapi_admin_user_endpoints.py`

### 完成标志
- 所有认证和用户管理流量都走 FastAPI
- 不再需要依赖 legacy sign-in flows

---

## PR 7：收口兼容层，冻结并压缩 Flask `/api/*`

### 目标
把 Flask API 从“还在兜底的产品后端”降为“几乎空壳的兼容层”。

### 后端范围
- 更新 `tests/fixtures/flask_api_route_signatures.json`
- 将已迁走的 Flask `/api/*` 路由从 baseline 中移除
- 新增“迁移完成阈值”校验：
  - 若 React 仍引用 Flask-only endpoint，则 CI fail
- 逐步禁止 FastAPI-native shell 命中 fallback

### 文档范围
更新：
- `docs/API_MIGRATION_STATUS.md`
- `docs/ARCHITECTURE.md`
- `replit.md`
- 任何仍写着 “Flask API” 为主入口的开发文档

### 完成标志
- React 产品路径 100% 由 FastAPI 提供
- Flask `/api/*` 只剩极少量未迁历史接口，且不再被 React 使用

---

## 五、执行顺序建议

按用户偏好的“小 PR、可验收”方式，建议严格按下面顺序推进：

1. PR 1：Config/Task 只读
2. PR 2：Config/Task 写操作
3. PR 3：文件写操作 + 预览
4. PR 4：Knowledge/RAG
5. PR 5：Chat
6. PR 6：Auth/User/Admin
7. PR 7：兼容层收口与文档清理

这样做的好处：
- 先恢复运维面，再恢复内容面，再恢复 AI 交互面，最后恢复认证面
- 每个 PR 都能单独验收
- 每个 PR 都能明确减少一批 Flask endpoint 依赖

---

## 六、每个 PR 的统一验收清单

每个 PR 合并前都必须完成：

- 后端：新增 FastAPI router 与测试
- 前端：对应页面从 `FeatureUnavailable` 恢复或增强
- 文档：更新 `docs/API_MIGRATION_STATUS.md`
- 验证：启动 FastAPI 后，手动访问对应页面并确认 network 只命中 FastAPI-native endpoint
- 边界：`tests/test_flask_api_boundary.py` 与新增 endpoint 测试一起通过

推荐额外加一条前端验收规则：
- 若页面仍会打到 legacy-only API，就不允许把入口重新放回导航
