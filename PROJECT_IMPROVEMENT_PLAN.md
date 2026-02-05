# 项目改进计划：功能增强与体验优化 (Phase 2)

本计划旨在解决反馈中的具体问题，并全面提升系统的文件管理能力和交互体验。

## 🛡️ 1. 核心逻辑增强：排除与筛选机制 (Exclusion & Filtering)

**目标**：确保“已删除/排除”的文件不再被下载或导入，并在所有采集入口统一筛选逻辑。

> **问题诊断**：此前 `Crawler` 中虽有 `_is_excluded` 检查，但可能：
> 1. 仅在下载后检查 URL，未在下载前检查文件名。
> 2. `ScheduledCollector` 和 `FileCollector` 可能未严格复用相同的筛选配置。
> 3. 已知文件去重依赖于 `storage.file_exists(link)`，但如果文件被手动删除（状态变更），需确保逻辑能处理这种情况。

**实施步骤**：

- [x] **1.1 全局排除逻辑统一**
    - **位置**: `ai_actuarial/crawler.py` (以及 `utils.py` 如果适用)
    - **逻辑**: 确保在发送网络请求**之前**，就根据 `config/sites.yaml` 中的 `exclude_keywords` (如 `exam`) 和 `exclude_prefixes` 对 URL 进行预检查。
    - **强化**: 在文件下载完成后，再次根据最终文件名（`original_filename`）进行二次排除检查。
- [x] **1.2 数据库对比增强**
    - **位置**: `ai_actuarial/collectors/file.py`, `ai_actuarial/crawler.py`
    - **逻辑**: 不仅检查 `file_exists` (URL是否存在)，还要比较数据库中文件大小，如果出现相同的文件大小的文件，再计算待导入文件的 SHA256，对比数据库中 `sha256` 字段，防止文件名不同但内容相同的文件重复入库。
- [x] **1.3 本地文件对比**
    - **位置**: `ai_actuarial/collectors/file.py`, `ai_actuarial/crawler.py`
    - **逻辑**: 如果下载时提示已经有该文档，就放弃下载，这说明已经有这个文档了
- [x] **1.4 导入(Import)与URL入口的筛选**
    - **位置**: `FileCollector` 和 `URLCollector`
    - **逻辑**: 在执行收集前，强制加载全局的 Exclusion 配置，主动过滤掉包含 `exam` 等关键词的文件路径或 URL，数据库对比增强，和 本地文件对比

## 📂 2. 文件导入功能升级 (File Import UI)

**目标**：提供更友好的文件夹选择方式，并确保本地导入也遵循严格的筛选规则。

- [x] **2.1 增加文件夹选择按钮**
    - **位置**: `collection_file.html`
    - **修改**: 添加 `<input type="file" id="directory-input" webkitdirectory directory multiple />`，允许用户通过浏览器原生对话框选择目录。
    - **脚本**: 编写 JS 逻辑，读取选定文件夹下的所有文件路径，填充到之前的文本框中（或直接传递给后端）。
- [x] **2.2 后端逻辑对接**
    - **位置**: `app.py` -> `FileCollector`
    - **修改**: 确保后端接收到的文件列表在处理前进行步骤 1.1，1.2，1.3 中提到的排除关键词过滤和数据库查重。

## 🧪 3. Url Collection 测试

**目标**：验证 URL 单点采集功能的稳定性。

- [x] **3.1 功能验证**
    - **测试**: 手动输入包含和不包含排除词的 URL，验证系统是否正确接纳或拒绝。
    - **测试**: 输入已存在数据库中的 URL，验证是否正确跳过。

## 📅 4. 定期任务界面重构 (Scheduled Tasks UI)

**目标**：将简单的列表页升级为功能齐全的任务控制台。

### 4.1 布局重构 (Tab Layout)
- [x] **实现 Tabs 切换组件**
    - **位置**: `scheduled_tasks.html`
    - **内容**: 将界面划分为三个标签页：
        1.  **Configured Sites & Management** (配置与管理)
        2.  **Manual Trigger** (手动触发)
        3.  **Collection History** (采集历史)

### 4.2 站点管理增强 (Site Management)
- [x] **新增 "Add Site" 按钮**
    - **功能**: 弹出模态框 (Modal)，允许用户输入 Site Name, URL, Max Pages, Keywords 等信息。
    - **后端**: 实现写入 `config/sites.yaml` 的接口。
- [x] **新增 "Edit" 按钮 (每行)**
    - **功能**: 点击列表中的 Edit，弹出模态框加载该站点当前的 YAML 配置（或表单数据）。
    - **后端**: 实现更新 `config/sites.yaml` 中特定条目的接口。
- [x] **模糊搜索/筛选**
    - **功能**: 在列表顶部增加搜索框，实时过滤显示的站点列表（基于 Site Name 或 URL）。

### 4.3 历史记录增强 (History & Logs)
- [x] **"View Log" 按钮**
    - **功能**: 在 History 列表中每一行增加按钮。
    - **逻辑**: 点击后弹窗显示该次任务的详细执行日志。
    - **后端**: 需确保每次任务执行的 Log 被持久化存储（如保存为 `.log` 文件或存入独立数据库表），并通过 API `GET /api/logs/<task_id>` 提供。

## 📝 5. 全局日志系统 (Global Logs)

**目标**：提升系统透明度，方便排错。

- [x] **Tasks 界面日志面板**
    - **位置**: `tasks.html` (或新增 `logs.html`)
    - **功能**: 展示系统级别的运行日志（不仅是单次采集任务，还包括应用启动、错误等）。
    - **实现**: 读取 Python `logging` 输出的文件（需配置 FileHandler）。

---

## ⚠️ 开发注意事项 (Notes for Developer)

1.  **YAML 处理**: Python 的 YAML 库在读写时可能会丢失原始文件中的注释。如果用户在意配置文件中的手动注释，需谨慎处理写入逻辑（或仅追加）。
2.  **安全性**: `FileCollector` 结合 Web 端的目录选择仅能传递文件名列表（浏览器安全限制不能传递完整绝对路径给后端，除非是在本地运行且手动填入路径）。**修正方案**：由于这是一个本地运行的工具，我们保留手动输入框（支持复制粘贴绝对路径），同时提供 `webkitdirectory` 辅助获取相对路径结构，或者明确告知用户这是本地工具，服务端可以直接访问本地路径。
3.  **性能**: 引入 SHA256 查重会增加 I/O 开销，对于大文件需优化（如先比大小，再比哈希）。
