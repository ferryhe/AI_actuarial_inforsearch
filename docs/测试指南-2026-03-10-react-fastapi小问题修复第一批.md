# React/FastAPI 小问题修复第一批测试指南

## 启动方式

### 1. 启动后端

```bash
.\.venv\Scripts\python.exe -m ai_actuarial api --host 127.0.0.1 --port 8000
```

### 2. 启动前端

```bash
npm run dev
```

## 手工回归清单

### 1. Database -> FileDetail -> 返回

- [ ] 打开 `http://localhost:5173/database`
- [ ] 切到第 2 页或之后的页面
- [ ] 带上任意 source/category/query 筛选
- [ ] 点击某个文件进入 FileDetail
- [ ] 点击返回按钮

预期：

- 回到原来的 Database 分页和筛选状态
- 不跳首页

### 2. FileDetail -> Preview -> 返回 -> 再返回

- [ ] 从 Database 进入某个 FileDetail
- [ ] 点击 `Preview`
- [ ] 在 Preview 页面点击返回
- [ ] 回到 FileDetail 后再次点击返回

预期：

- 第一次返回回到刚才的 FileDetail
- 第二次返回回到原来的 Database 页面
- 不会在 FileDetail 和 Preview 之间循环

### 3. Catalog task / FileDetail catalog 显示

- [ ] 打开 `Tasks`
- [ ] 展开 `Catalog` 表单
- [ ] 检查 provider 信息提示
- [ ] 再打开任意 FileDetail 的 `Catalog` modal

预期：

- 显示当前实际生效的 catalog provider/model
- 不再显示所有候选 provider 的列表
- 文案类似 `DeepSeek - deepseek-chat`

### 4. Task History log 默认位置

- [ ] 打开 `Tasks`
- [ ] 在 `Task History` 里点开一个有较多日志的任务
- [ ] 观察 Application Log 区域初始位置

预期：

- 默认视角落在日志末尾
- 能直接看到最近的错误、统计和最终结果

### 5. Database category filter

- [ ] 打开 `Database`
- [ ] 展开 filters
- [ ] 查看 category 下拉框

预期：

- 下拉框能显示数据库当前实际使用过的 category
- 选择后列表筛选正常生效

## 已完成自动化验证

```bash
npm run build
.\.venv\Scripts\python.exe -m pytest -q -o addopts=
```

结果：

- `npm run build` 通过
- `405 passed, 39 warnings, 4 subtests passed`
