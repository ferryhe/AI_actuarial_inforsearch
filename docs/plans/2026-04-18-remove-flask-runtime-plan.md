# Remove Flask Runtime Implementation Plan

> 目标：把 `ai_actuarial.web` 从 FastAPI 产品运行时中彻底移除，让 React + FastAPI 成为唯一正式产品面；Flask/WSGI/legacy HTML 不再参与 API 启动、会话处理或边界测试。

**当前时间：** 2026-04-18 08:22:13 EDT

**当前判断：**
- `tests/test_fastapi_no_flask_runtime.py` 已证明：删除 `ai_actuarial/web` 后，FastAPI 的 auth/chat/config/schedule/collection 核心能力仍能工作。
- 现在真正阻止“彻底删掉 Flask”的，不是主功能缺失，而是：
  1. `ai_actuarial/api/app.py` 仍尝试 import/mount legacy Flask app
  2. `api/deps.py`、`api/services/auth.py`、`api/services/chat.py` 仍保留 Flask session serializer 兼容分支
  3. `tests/test_flask_api_boundary.py` 仍把 legacy Flask app 存在当成基线假设
  4. migration / inventory 文案仍围绕“FastAPI + Flask 并存兼容层”组织

**总原则：**
- 一个 PR 只做“删除 Flask runtime 依赖”这个明确范围。
- 先改测试与运行时边界，再删代码；不要先物理删除模块再补锅。
- 每一步都必须保证：`tests/test_fastapi_no_flask_runtime.py` 持续通过。

---

## 一、目标状态

完成后应满足：

1. `ai_actuarial/api/app.py` 不再 import `ai_actuarial.web.app`
2. FastAPI 不再使用 `WSGIMiddleware` 挂载 legacy Flask app
3. `request.app.state` 中不再依赖 `legacy_flask_app` / `legacy_mount_enabled` / `legacy_flask_only_signatures`
4. auth/chat/session 全部使用 FastAPI-native cookie/session 逻辑
5. migration / boundary 测试不再要求 legacy Flask 存在
6. `tests/test_fastapi_no_flask_runtime.py` 应转化为默认常规能力保障，而不是“特例模式”
7. 最终可以删除 `ai_actuarial/web/`，且核心产品测试仍通过

---

## 二、分阶段执行清单

### 阶段 1：重写运行时边界测试，让 CI 不再要求 Flask 存在

**目标：** 先把“Flask 必须存在”的测试约束拆掉，改成“FastAPI standalone 是正常状态”。

**文件：**
- 修改：`tests/test_flask_api_boundary.py`
- 可能新增：`tests/test_fastapi_runtime_boundary.py`
- 参考：`tests/test_fastapi_no_flask_runtime.py`
- 参考：`ai_actuarial/api/route_inventory.py`
- 参考：`ai_actuarial/api/routers/migration.py`

**要做的事：**
1. 取消 `legacy_flask_app is not None` 这种硬要求
2. 把当前 boundary test 改成检查：
   - FastAPI native route inventory 是稳定的
   - 不允许重新引入新的 Flask runtime import/mount
3. 保留必要的 route inventory 保护，但从“冻结 Flask-only surface”改成“冻结 standalone FastAPI authority 行为”
4. 明确 `tests/test_fastapi_no_flask_runtime.py` 成为主验证链，而不是旁路验证

**验证：**
```bash
python -m pytest tests/test_flask_api_boundary.py tests/test_fastapi_no_flask_runtime.py -q
```

**完成标志：**
- CI 不再把 Flask app 存在当作先决条件
- boundary 测试表达的是真正的目标架构，而不是历史过渡态

---

### 阶段 2：从 `api/app.py` 中移除 Flask import/mount

**目标：** 让 `create_app()` 成为纯 FastAPI 工厂，不再尝试挂 WSGI legacy app。

**文件：**
- 修改：`ai_actuarial/api/app.py`
- 可能修改：`ai_actuarial/api/routers/migration.py`
- 可能修改：`ai_actuarial/api/route_inventory.py`

**要做的事：**
1. 删除：
   - `from a2wsgi import WSGIMiddleware`
   - `import ai_actuarial.web.app as legacy_web_app`
   - `app.mount("/", WSGIMiddleware(...))`
2. 删除/重构 `app.state` 中仅用于 legacy Flask 的字段：
   - `legacy_backend`
   - `legacy_mount_enabled`
   - `legacy_mount_error`
   - `legacy_flask_app`
   - `legacy_route_inventory`
   - `legacy_api_paths`
   - `legacy_flask_only_signatures`
   - 相关 sample/count 字段
3. 保留必要的 native task runtime refs，不动业务 runtime 本体
4. 更新 migration/status 输出，改成反映“FastAPI standalone”现实

**验证：**
```bash
python -m pytest tests/test_fastapi_no_flask_runtime.py tests/test_fastapi_chat_endpoints.py tests/test_fastapi_auth_endpoints.py tests/test_fastapi_rag_admin_endpoints.py -q
```

**完成标志：**
- `api/app.py` 中不再出现 `ai_actuarial.web.app` / `WSGIMiddleware`
- FastAPI 应用启动路径完全不依赖 Flask

---

### 阶段 3：移除 auth session 的 Flask 兼容分支

**目标：** 让 auth 完全依赖 FastAPI-native session secret / cookie serializer。

**文件：**
- 修改：`ai_actuarial/api/deps.py`
- 修改：`ai_actuarial/api/services/auth.py`
- 测试：`tests/test_fastapi_auth_endpoints.py`
- 测试：`tests/test_fastapi_no_flask_runtime.py`

**要做的事：**
1. 精简 `_decode_flask_session()`，改成纯 FastAPI session decode
2. 删除 `legacy_flask_app` 分支下的 cookie name / serializer 逻辑
3. 统一 `fastapi_session_secret` / cookie config 为唯一 session 来源
4. 确保 register/login/logout/profile/admin/token 管理不退化

**验证：**
```bash
python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_fastapi_no_flask_runtime.py -q
```

**完成标志：**
- `api/deps.py` / `api/services/auth.py` 不再引用 `legacy_flask_app`
- auth 全链路在 standalone FastAPI 下稳定通过

---

### 阶段 4：移除 chat session 的 Flask 兼容分支

**目标：** 让 guest chat / conversation session 只走 FastAPI-native cookie/session。

**文件：**
- 修改：`ai_actuarial/api/services/chat.py`
- 测试：`tests/test_fastapi_chat_endpoints.py`
- 测试：`tests/test_fastapi_no_flask_runtime.py`

**要做的事：**
1. 删除 `_legacy_app()` 和 `legacy_flask_app` 相关 session serializer 分支
2. `apply_session_update()` 只保留 FastAPI cookie 设置逻辑
3. 保证 guest 会话、conversation CRUD、chat query 仍工作

**验证：**
```bash
python -m pytest tests/test_fastapi_chat_endpoints.py tests/test_fastapi_no_flask_runtime.py -q
```

**完成标志：**
- `api/services/chat.py` 不再引用 `legacy_flask_app`
- chat/conversation 在无 Flask 模块下仍完全可用

---

### 阶段 5：清理 migration / inventory / 文档口径

**目标：** 把迁移状态页和说明文档从“并存兼容期”改成“FastAPI-only”。

**文件：**
- 修改：`ai_actuarial/api/routers/migration.py`
- 可能修改：`ai_actuarial/api/route_inventory.py`
- 修改：`README.md`
- 修改：`docs/ARCHITECTURE.md`（若有相关旧口径）
- 修改：`docs/API_MIGRATION_STATUS.md`（若有相关旧口径）

**要做的事：**
1. 删除对 legacy mount 状态的核心依赖展示
2. 保留有用的 native route inventory / authority 信息
3. README 里明确：
   - FastAPI 是唯一产品 API
   - legacy Flask HTML/runtime 已删除或不再参与运行
4. 清掉“Flask 兼容挂载仍是正常产品形态”的旧说法

**验证：**
- 读 migration/status 输出是否符合新架构
- 文档与当前实现一致

---

### 阶段 6：物理删除 `ai_actuarial/web/` 并做最终回归

**目标：** 真正把 Flask legacy 模块从仓库和运行时中删除。

**文件：**
- 删除：`ai_actuarial/web/` 整个目录（若阶段 2~4 已无引用）
- 删除/更新：残余相关测试与文档

**要做的事：**
1. 搜索全仓库 `ai_actuarial.web` / `legacy_flask_app`
2. 清掉最后的 import / dead code
3. 删除 `ai_actuarial/web/`
4. 全量跑 FastAPI 产品面关键测试

**验证建议：**
```bash
python -m pytest \
  tests/test_fastapi_no_flask_runtime.py \
  tests/test_fastapi_chat_endpoints.py \
  tests/test_fastapi_auth_endpoints.py \
  tests/test_fastapi_rag_admin_endpoints.py \
  tests/test_fastapi_ops_read_endpoints.py \
  tests/test_fastapi_ops_write_endpoints.py \
  tests/test_react_fastapi_authority.py \
  -q

npm run build
```

**完成标志：**
- 仓库内无 `ai_actuarial.web.app` 运行时引用
- `ai_actuarial/web/` 可删除
- React + FastAPI 主产品能力仍全部通过

---

## 三、本 PR 建议范围（第一刀）

为了继续保持“小 PR、单范围”，这一个新分支建议先只做：

### PR A：Remove Flask runtime assumption from tests and app factory

**范围只包含：**
- 阶段 1
- 阶段 2
- 必要的最小文档更新

**不在这个 PR 里做：**
- auth 兼容 session 全量收口
- chat 兼容 session 全量收口
- 物理删除 `ai_actuarial/web/`

这样可以先把最核心的 runtime 方向定住：
> FastAPI app factory 本身不再 mount/import Flask

后面的 auth/chat session 清理再拆后续 PR，更稳。

---

## 四、我现在就开始做的第一步

我将从 **阶段 1** 开始：
1. 先改 boundary 测试，让它不再把 Flask 存在当成基线
2. 同时检查 `api/app.py` 里删掉 legacy mount 后最小需要补哪些测试/状态字段
3. 跑 focused pytest 验证这一刀的真实影响

---

## 五、关键验证命令清单

```bash
# 先看当前 no-Flask 主链是否稳定
python -m pytest \
  tests/test_fastapi_no_flask_runtime.py \
  tests/test_fastapi_chat_endpoints.py \
  tests/test_fastapi_auth_endpoints.py \
  tests/test_fastapi_rag_admin_endpoints.py \
  -q

# 做第一刀时的 focused 回归
python -m pytest tests/test_flask_api_boundary.py tests/test_fastapi_no_flask_runtime.py -q

# app factory / runtime 进一步收口后
python -m pytest \
  tests/test_fastapi_no_flask_runtime.py \
  tests/test_fastapi_chat_endpoints.py \
  tests/test_fastapi_auth_endpoints.py \
  tests/test_fastapi_rag_admin_endpoints.py \
  tests/test_fastapi_ops_read_endpoints.py \
  tests/test_fastapi_ops_write_endpoints.py \
  -q

# 前端 authority 不应回退到 Flask-only endpoint
python -m pytest tests/test_react_fastapi_authority.py -q

# React build
npm run build
```

---

## 六、风险点

1. **session 行为变更风险**
- auth/chat 当前虽然能 no-Flask 跑，但仍有兼容分支
- 删 runtime mount 后，若 session secret/cookie 配置遗漏，容易出现登录态/guest 会话细节回归

2. **boundary test 心智迁移风险**
- 现有 `test_flask_api_boundary.py` 代表的是旧治理方式
- 改这类测试时，必须确保新的约束更强而不是更弱

3. **文档过时风险**
- 计划文档、README、迁移状态页里有不少“FastAPI+Flask 并存”表述
- 代码先删干净后，文档如果不改，会误导后续开发

---

## 七、预期产出

这条 remove-flask 主线最终完成后，仓库状态应该变成：

- React 产品面 → 只依赖 FastAPI
- FastAPI app factory → 纯原生，不再 mount Flask
- auth/chat session → 纯 FastAPI-native
- `ai_actuarial/web/` → 可删除
- 测试体系 → 不再把 legacy Flask 当作基线假设

---

**接下来执行：先做阶段 1。**
