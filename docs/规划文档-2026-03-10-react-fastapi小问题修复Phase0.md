# React/FastAPI 小问题修复实施计划

## 一、现状分析

- 当前分支：`feature/react-fastapi-ui-bugfixes-round1`
- 基线分支：`feature/fastapi-native-file-read-phase2`
- 本轮问题集中在 React 页面交互和任务配置展示，不涉及新的后端架构迁移

### 问题清单

1. `Database -> FileDetail -> 返回` 无法稳定回到原分页/筛选位置，部分场景会回首页
2. `Catalog task` / `FileDetail Catalog modal` 当前只配置了一个 catalog 模型时，界面仍显示所有可用 provider，且不显示具体模型
3. `Task History -> Log` 默认只看到启动部分，用户不容易看到运行结果和最后总结
4. `Database` category filter 不能正确显示当前已有 category
5. `FileDetail -> FilePreview -> 返回 -> 再返回` 出现循环返回

### 代码路径判断

- 导航问题主要在：
  - `client/src/pages/Database.tsx`
  - `client/src/pages/FileDetail.tsx`
  - `client/src/pages/FilePreview.tsx`
- Catalog task / category / task log 问题主要在：
  - `client/src/hooks/use-task-options.ts`
  - `client/src/pages/Tasks.tsx`
  - `client/src/pages/FileDetail.tsx`
  - `ai_actuarial/web/app.py`

## 二、需求说明

本轮目标是修复现有 React 主流程中的小问题，不改变核心 API 结构：

- 保持 Database、FileDetail、FilePreview 的 URL 路径不变
- 保持 Catalog task 和 FileDetail catalog 提交流程不变
- 保持 Task History 后端日志接口不变
- 尽量用最小改动修复用户可见问题

不在本轮范围内：

- 不新增新的 FastAPI 原生业务接口
- 不重构整个任务中心
- 不调整 Settings 页面 AI model 配置流程

## 三、技术方案

### 1. 导航链路修复

目标：

- `Database -> FileDetail` 时保留当前分页、搜索、筛选状态
- `FileDetail -> FilePreview -> 返回` 时回到原始 FileDetail
- 从该 FileDetail 再返回时，继续回到原始 Database 页面，而不是 Preview 或首页

方案：

- 统一显式传递 `from` 参数，不依赖浏览器 history 作为主路径
- `FileDetail` 打开 `FilePreview` 时，传入完整 detail URL 作为 preview 返回目标
- `FilePreview` 优先按显式 `from` 返回
- `FileDetail` 返回优先按显式 `from` 返回，只有缺失时才退回 history

### 2. Catalog provider/model 展示修复

目标：

- 当后台 AI Config 已选定 catalog provider + model 时，任务页和文件详情页只展示当前生效的那一个配置
- 展示格式至少包含 provider 和 model

方案：

- `useTaskOptions()` 不再返回“所有可用于 catalog 的 provider 列表”作为主展示
- 改为优先读取 `/api/config/ai-models` 的 `current.catalog`
- 结合 `available` 与已配置 provider 集合，只暴露当前实际可用的 catalog 目标

### 3. Task History 日志视角修复

目标：

- 打开日志时默认看到最新结果，而不是最顶部启动日志

方案：

- 保持 `/api/tasks/log/<task_id>` 不变
- 前端日志 modal 在日志加载后自动滚动到最底部
- 保留手动刷新按钮

### 4. Database category filter 修复

目标：

- category filter 显示当前数据库实际使用到的 category

方案：

- `Database` 改用 `/api/categories?mode=used`
- 前端兼容 `string[]` 返回结构，不再假设 `{name, count}` 形状

## 四、实施步骤

### Phase 1: 导航与返回链路

预计耗时：0.5-1 小时

- [ ] 修复 `Database -> FileDetail` 返回目标
- [ ] 修复 `FileDetail -> FilePreview` 的回跳链路
- [ ] 消除 Preview/Detail 返回循环

### Phase 2: 任务配置与筛选展示

预计耗时：0.5-1 小时

- [ ] 调整 `useTaskOptions()` 的 catalog 展示逻辑
- [ ] 更新 Tasks / FileDetail catalog UI 文案
- [ ] 修复 Database category filter 数据源

### Phase 3: 日志体验与验证

预计耗时：0.5 小时

- [ ] 调整 Task History log modal 默认滚动位置
- [ ] 跑前端构建
- [ ] 跑相关后端测试与全量 pytest

### Phase 4: 文档

预计耗时：0.5 小时

- [ ] 补开发日志
- [ ] 补测试指南

## 五、关键决策

### 决策 1：是否改浏览器 history 逻辑为主

- 选项 A：继续依赖 `history.back()`
- 选项 B：用显式 `from` 作为主返回路径，history 只兜底

选择：B

原因：

- 多跳转链路里，history 很容易把 Preview 当成上一个页面，导致循环
- 显式返回目标更稳定，也更容易测试

### 决策 2：Catalog 区域是否显示所有候选 provider

- 选项 A：显示所有“可能可用”的 provider
- 选项 B：显示当前 AI Config 实际选中的 catalog provider/model

选择：B

原因：

- 用户真正关心的是“当前会用哪个模型”
- 当前 UI 把“候选 provider”误当成“当前配置”，会误导操作

### 决策 3：Task log 是否改为倒序

- 选项 A：后端返回倒序
- 选项 B：保持日志原始顺序，前端默认滚动到底部

选择：B

原因：

- 保持日志文件和页面内容顺序一致
- 改动更小，不影响现有 API
