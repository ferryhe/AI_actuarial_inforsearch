# 用户管理模块完善日志 — 2026-03-08

## 概述

本次开发完善了用户管理模块，补全了 Profile API、自助设置、管理员开关接口，并修复了 React 前端与后端之间的集成断点。

---

## 已完成功能

### 1. 用户注册（/register）
- 已实现邮箱 + 密码注册，密码 PBKDF2-SHA256（260,000 次迭代）哈希存储
- 防重复邮箱检查；支持可选 Display Name
- 新注册用户默认角色为 `registered`，每日 AI 对话配额 5 次
- 注册成功后自动登录并写入 activity log

### 2. 用户个人信息与设置（/api/user/me, /api/user/profile）

#### GET /api/user/me
返回当前登录用户的：
- 账户信息（id, email, display_name, role, is_active, created_at, last_login_at）
- 今日 AI 对话配额（used / limit / remaining / date）
- 最近 20 条 activity 记录

支持邮箱用户（session email_user_id）和 Token 用户（auth_token）双重认证。

#### PATCH /api/user/profile
- 更新 `display_name`（最长 100 字符）
- 修改密码：需提供 `current_password`（防止越权），新密码最少 8、最多 1024 字符
- 参数校验：JSON body 必须是 object（非 list），字段必须是 string 类型
- 操作成功后写入 activity log

### 3. 用户订阅管理与剩余配额

各角色每日 AI 对话配额：

| 角色         | 每日配额 |
|-------------|---------|
| anonymous   | 1       |
| registered  | 5       |
| premium     | 100     |
| operator    | 0       |
| operator_ai | 100     |
| admin       | 10,000  |

配额在 `user_quotas` 表中按日期原子性检查与递增（`check_and_increment_ai_chat_quota()`）。

### 4. 管理员用户管理

#### 角色管理
- `POST /api/admin/users/<id>/role` — 修改用户角色（admin 权限）
- 有效角色：`registered`, `premium`, `operator`, `operator_ai`, `admin`

#### 账户开关
- `POST /api/admin/users/<id>/enable` — 启用账户（新增，修复 React 前端调用空接口的问题）
- `POST /api/admin/users/<id>/disable` — 停用账户（新增）
- `POST /api/admin/users/<id>/active` — 原始通用接口（仍可用）

#### 配额重置
- `POST /api/admin/users/<id>/reset-quota` — 重置今日配额

#### 用户行为日志
- `GET /api/admin/users/<id>/activity` — 查看用户操作日志
  - 返回 `logs` 和 `activity` 两个字段（向后兼容）
  - 每条记录包含 `timestamp`（由 `created_at` 派生），解决 React UI 显示 "Invalid Date" 的问题

---

## 前端页面（React SPA）

### Profile 页面（/profile）
- 账户信息卡：邮箱、角色徽章、注册时间、最后登录
- 配额进度条：≥80% 时变为琥珀/红色警示
- 最近活动列表：操作名称、时间、IP
- 设置表单：修改 Display Name、修改密码（带当前密码验证）

### 导航
- Layout.tsx 侧边栏新增 "My Profile / 我的账户" 入口（UserCircle 图标）

---

## 代码质量改进（基于 Code Review 反馈）

| 问题 | 修复 |
|------|------|
| `Profile.tsx` 使用 `React.FormEvent` 但未导入 React 命名空间 | 改为 `import { type FormEvent }` 并使用 `FormEvent` |
| `fetchProfile()` 吞掉所有错误，导致非认证错误（500/网络故障）也显示"未登录"提示 | 新增独立 `fetchError` 状态；401/403 → 登录提示；其他错误 → 错误信息 + 重试按钮 |
| 活动日志条目缺少 `timestamp` 字段，React UI 显示 Invalid Date | 在 `/api/admin/users/<id>/activity` 响应中对每条记录添加 `timestamp` 别名（来源 `created_at`） |
| `api_user_update_profile` 未校验 JSON body 类型，非 dict 输入会触发 500 | 添加 `isinstance(data, dict)` 检查，字段类型校验，返回 400 |

---

## 测试覆盖

运行测试：`python3 -m pytest tests/test_user_management.py -v`

**总计 55 个测试，全部通过。**

新增/覆盖的测试类：

| 测试类 | 覆盖场景 |
|--------|---------|
| `TestUserStorageMethods` | create_user, get_user_by_email/id, update_user_role/active/profile |
| `TestUserQuotaMethods` | check_and_increment_ai_chat_quota, get_ai_chat_quota_used |
| `TestUserActivityLog` | log_user_activity, list_user_activity |
| `TestRegistrationEndpoint` | 成功注册、重复邮箱、无效邮箱、短密码 |
| `TestEmailLoginEndpoint` | 正确密码登录、错误密码、未知邮箱、停用账户 |
| `TestAdminUserEndpoints` | 修改角色、enable/disable、重置配额、查看活动日志 |
| `TestUserMeEndpoint` | 邮箱用户、Token 用户、未认证 |
| `TestUserProfileUpdateEndpoint` | 更新 display_name、修改密码、错误当前密码、非 dict body、字段类型校验 |

---

## 文件变更列表

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `ai_actuarial/web/app.py` | 修改 | 新增 /api/user/me, /api/user/profile, /api/admin/users/<id>/enable/disable；修复 activity timestamp；加强 profile 更新参数校验 |
| `ai_actuarial/storage.py` | 修改 | 新增 `update_user_profile()`，`get_ai_chat_quota_used()` |
| `client/src/pages/Profile.tsx` | 新增 | 用户个人信息与设置页面 |
| `client/src/components/Layout.tsx` | 修改 | 侧边栏新增 Profile 入口 |
| `client/src/lib/api.ts` | 修改 | 新增 `apiPatch<T>()` 帮助函数 |
| `client/src/hooks/use-i18n.ts` | 修改 | 新增 profile 相关中英文翻译键 |
| `client/src/App.tsx` | 修改 | 添加 `/profile` 路由 |
| `tests/test_user_management.py` | 修改 | 新增 14 个集成/单元测试 |

---

## 参考：主流 AI 服务商用户管理对比

| 功能 | OpenAI | Anthropic | 本系统 |
|------|--------|-----------|-------|
| 邮箱注册 | ✅ | ✅ | ✅ |
| SSO/OAuth | ✅ | ✅ | 待规划 |
| 角色/权限体系 | API Key 级 | Organization | 角色表（5 种） |
| 用量配额 | 按费用 | 按费用 | 按角色/天 |
| 配额用量查看 | ✅ | ✅ | ✅ |
| 管理员后台 | Dashboard | Console | React 管理页 |
| 用户操作日志 | ✅ | ✅ | ✅ |
| 自助密码修改 | ✅ | ✅ | ✅ |
| 邮件验证 | ✅ | ✅ | 待规划 |
| 双因素认证 | ✅ | ✅ | 待规划 |

### 后续可规划功能

1. **邮箱验证**：注册后发送确认邮件，verified 状态才允许使用全功能
2. **OAuth 集成**：Google / GitHub 第三方登录
3. **双因素认证（2FA）**：TOTP（如 Google Authenticator）
4. **API Key 管理**：用户可生成个人 API Key，用于程序化调用
5. **订阅 / Billing**：premium 套餐购买流程与自动配额升级
6. **用户自助注销**：GDPR 合规数据删除
