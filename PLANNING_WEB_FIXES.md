# Web Interface Fix & Feature Implementation Plan

本计划详细列出了修复和完善 AI Actuarial InfoSearch Web 界面的步骤。

## 📅 Phase 1: 修复导航与链接 (Navigation Fixes)
目标：确保 Web 界面上的所有按钮都能跳转到正确的页面。

- [x] **1.1 修正 `index.html`**
    - **文件**: `ai_actuarial/web/templates/index.html`
    - **操作**: 将 "Run Scheduled Collection" 卡片的跳转链接从 `/collection/scheduled` 修改为 `/scheduled_tasks`。
    - **注意事项**: 链接已修正。
- [x] **1.2 修正 `tasks.html`**
    - **文件**: `ai_actuarial/web/templates/tasks.html`
    - **操作**: 将 "Scheduled Collection" 卡片的跳转链接从 `/collection/scheduled` 修改为 `/scheduled_tasks`。
    - **注意事项**: 链接已修正。

## 📂 Phase 2: 实现文件导入功能 (File Import Feature)
目标：实现缺失的本地文件夹导入功能。

- [x] **2.1 创建前端模板**
    - **文件**: `ai_actuarial/web/templates/collection_file.html` (新建)
    - **内容**: 表单包含路径输入(`directory_path`)、递归开关(`recursive`)、扩展名(`extensions`)。
    - **注意事项**: 模板已创建。
- [x] **2.2 添加后端路由**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 添加 `@app.route("/collection/file")` 渲染模板。
    - **注意事项**: 路由已添加。
- [x] **2.3 实现后端逻辑**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 在 `run_collection` 接口中添加 `if collection_type == "file":` 分支，调用 `FileCollector`。
    - **注意事项**: 逻辑已实现。

## 🤖 Phase 3: 实现定期任务逻辑 (Scheduled Tasks Logic)
目标：让界面上的 "Run" 按钮真正触发后台爬虫。

- [x] **3.1 引入依赖**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 导入 `ScheduledCollector` 类。
    - **注意事项**: 已导入。
- [x] **3.2 连接后端逻辑**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 在 `run_collection` 接口的 `scheduled` 分支中，实例化 `ScheduledCollector` 并根据参数执行收集。
    - **注意事项**: 逻辑已实现。

## 👁️ Phase 4: 实现文件详情/预览 (File View)
目标：修复数据库列表中点击 "View" 报 404 的问题。

- [x] **4.1 创建详情页模板**
    - **文件**: `ai_actuarial/web/templates/file_view.html` (新建)
    - **内容**: 展示文件元数据（标题、摘要、关键词等）及下载/预览操作。
    - **注意事项**: 模板已创建。
- [x] **4.2 添加预览路由**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 添加 `@app.route("/file/<path:file_url>")`，实现根据 URL 查找并在前端展示文件信息。
    - **注意事项**: 路由已添加。

## ⚡ Phase 5: 任务异步化 (Asynchronous Execution)
目标：防止收集任务阻塞 Web 服务器，并提供实时进度反馈。

- [x] **5.1 封装后台执行器**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 创建 `execute_collection_task` 函数，使用 `threading.Thread` 运行收集任务。
    - **注意事项**: 已封装。
- [x] **5.2 更新任务状态管理**
    - **文件**: `ai_actuarial/web/app.py`
    - **操作**: 确保任务开始、进行中、结束时更新 `_active_tasks` 全局字典，以便前端轮询获取进度。
    - **注意事项**: 状态管理已集成到后台任务中。

## ✅ Project Completed
所有计划任务已完成。Web 界面现在具备完整的功能导航、文件导入、定期任务执行（异步）以及文件详情预览功能。

### ⚠️ 注意事项
1. **任务持久化**: 当前任务状态存储在内存中 (`_active_tasks`)，重启服务器会丢失任务历史。生产环境建议使用 Redis/Celery。
2. **文件路径安全**: 文件预览和下载虽然有基础的路径检查，但仍需确保 `download_dir` 配置正确且不仅限于 `/`。
3. **数据库并发**: 异步任务为每个线程创建了新的 SQLite 连接，这是正确的做法。但高并发写入可能会遇到锁竞争。

