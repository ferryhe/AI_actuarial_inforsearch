# FastAPI 无 Flask 收口计划（PR8.1-PR8.4）

> 只保留可执行下一步。

## PR8.1：接管 task / scheduler runtime owner

### 目标
- 去掉 FastAPI 对 `legacy_start_background_task` 的运行时依赖
- 去掉 FastAPI 对 `legacy_init_scheduler` 的运行时依赖
- 删除 Flask 后，`/api/schedule/reinit` 与 `/api/collections/run` 仍可工作

### 完成标志
- 无 Flask 环境下 `POST /api/schedule/reinit` 返回 200
- 无 Flask 环境下 `POST /api/collections/run` 返回 200
- 针对 no-Flask runtime 增加回归测试

---

## PR8.2：补 `/api/config/backend-settings` native 写接口

### 目标
- 为 FastAPI 增加 `POST /api/config/backend-settings`
- 与现有 `GET /api/config/backend-settings` 保持一致的配置来源与返回语义
- 删除 Flask 后，Settings 页面不再命中 410

### 完成标志
- 无 Flask 环境下 `POST /api/config/backend-settings` 返回 200
- 针对后端配置写入增加端到端测试

---

## PR8.3：补 no-Flask chat session fallback

### 目标
- 无 Flask 时也能持久化 guest chat session
- 创建 conversation 后，list/detail/delete 仍能识别同一 guest 身份

### 完成标志
- 无 Flask 环境下创建 conversation 后可 list/detail/delete
- 增加 guest chat session fallback 回归测试

---

## PR8.4：补 auth fallback 启动约束与验证

### 目标
- 明确 no-Flask auth cookie fallback 的 secret 来源
- 避免 register/login 成功但 session 无法持久化的假阳性
- 为 no-Flask auth 增加启动与行为验证

### 完成标志
- 无 Flask 环境下 register/login 后 `GET /api/auth/me` 显示已登录
- logout 后会话正确清空
- 增加 no-Flask auth 回归测试

---

## 最终交付物
- 无 Flask 临时副本可启动
- 主页面可打开
- Task / Scheduler 写操作可成功
- Settings 写操作可成功
- Chat guest session 可持久化
- Auth session 可持久化
- 关键路径测试通过
- 提交最终 PR
