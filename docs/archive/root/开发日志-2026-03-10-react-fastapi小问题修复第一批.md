# 2026-03-10 React/FastAPI 小问题修复第一批开发日志

## 本轮目标

修复 React 主界面中的 4 个用户可见问题：

1. `Database -> FileDetail -> 返回` 无法稳定回到原分页/筛选位置
2. Catalog task / FileDetail catalog modal 显示所有候选 provider，而不是当前实际生效的 catalog provider/model
3. Task History 打开 log 时默认只看到顶部启动日志，不容易看到最新结果
4. Database category filter 不能正确显示当前已有 category
5. `FileDetail -> FilePreview -> 返回 -> 再返回` 可能陷入循环

## 已完成修复

### 1. 页面返回链路修复

新增了 [`navigation.ts`](/c:/Projects/AI_actuarial_inforsearch/client/src/lib/navigation.ts)，统一处理：

- 当前页面相对路径提取
- `from` 参数清洗
- FileDetail / FilePreview 路径拼装

对应改动：

- [`Database.tsx`](/c:/Projects/AI_actuarial_inforsearch/client/src/pages/Database.tsx)
- [`FileDetail.tsx`](/c:/Projects/AI_actuarial_inforsearch/client/src/pages/FileDetail.tsx)
- [`FilePreview.tsx`](/c:/Projects/AI_actuarial_inforsearch/client/src/pages/FilePreview.tsx)

结果：

- Database 打开 FileDetail 时会带上当前分页、筛选、搜索状态
- FileDetail 返回时优先回到显式 `from`
- FileDetail 打开 Preview 时，会把完整 detail 路径作为 preview 的返回目标
- Preview 返回后，再从 FileDetail 返回，不会再回 Preview 形成循环

### 2. Catalog task 当前模型展示修复

调整了 [`use-task-options.ts`](/c:/Projects/AI_actuarial_inforsearch/client/src/hooks/use-task-options.ts)：

- 不再把“所有可用于 catalog 的 provider”直接展示给任务页
- 改为优先读取 `/api/config/ai-models` 的 `current.catalog`
- 最终展示当前实际生效的 `provider + model`

结果：

- 当后台只配置了一个 catalog 模型时，任务页和文件详情页会显示类似 `DeepSeek - deepseek-chat`
- 不再误把候选 provider 列表当成当前配置

### 3. Task History log 默认视角修复

调整了 [`Tasks.tsx`](/c:/Projects/AI_actuarial_inforsearch/client/src/pages/Tasks.tsx)：

- 日志 modal 加入 `ref`
- 日志加载完成后自动滚动到底部

结果：

- 打开 log 时优先看到最近的运行结果和最终总结
- 手动刷新后也会保持滚动到最新日志

### 4. Database category filter 修复

调整了 [`Database.tsx`](/c:/Projects/AI_actuarial_inforsearch/client/src/pages/Database.tsx)：

- category filter 改为读取 `/api/categories?mode=used`
- 前端兼容 `string[]` 返回，而不是错误假设成 `{name, count}` 结构

结果：

- 当前数据库里实际使用过的 category 可以正常显示在筛选框里

## 自动化验证

### 前端构建

执行命令：

```bash
npm run build
```

结果：

- 构建通过

### 后端全量测试

执行命令：

```bash
.\.venv\Scripts\python.exe -m pytest -q -o addopts=
```

结果：

- `405 passed`
- `39 warnings`
- `4 subtests passed`

## 提交记录

- `e85672b` `docs: add phase 0 plan for react fastapi bugfix round 1`
- `c282a92` `fix: resolve react navigation and task option regressions`

## 当前状态

这轮问题修复已经完成，且没有改动后端 API 契约。当前更适合继续处理的下一批小问题，会是：

1. 如果需要，把旧 Flask `settings.html` 里的 task history log 也补成默认滚动到底部
2. 继续核查 Preview 从 Database 直接进入时的按钮文案是否要改成更通用的“返回”
