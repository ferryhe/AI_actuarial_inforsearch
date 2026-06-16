# 用户管理系统工程报告
# User Management System Engineering Report

**版本**: 1.0  
**日期**: 2026-03-06  
**项目**: AI Actuarial Info Search  

---

## 目录 / Table of Contents

1. [需求分析](#1-需求分析)
2. [用户分层设计](#2-用户分层设计)
3. [技术架构](#3-技术架构)
4. [数据库设计](#4-数据库设计)
5. [权限系统设计](#5-权限系统设计)
6. [AI使用配额设计](#6-ai使用配额设计)
7. [API端点设计](#7-api端点设计)
8. [页面与模板](#8-页面与模板)
9. [安全考量](#9-安全考量)
10. [数据库增强建议](#10-数据库增强建议)
11. [实现摘要](#11-实现摘要)
12. [后续建议](#12-后续建议)

---

## 1. 需求分析

### 原始需求

项目需要设计一套完整的用户管理体系，支持：

| # | 需求 | 状态 |
|---|------|------|
| 1 | 未注册用户有限访问权限 | ✅ 已实现 |
| 2 | 邮箱注册功能 | ✅ 已实现 |
| 3 | 高级会员（Premium）AI配额扩展 | ✅ 已实现 |
| 4 | 会员制度完整设计 | ✅ 已实现 |
| 5 | 用户配额查看与升级页面 | ✅ 已实现 |
| 6 | 管理员用户管理功能 | ✅ 已实现 |
| 7 | 双级别Operator | ✅ 已实现 |
| 8 | 数据库增强分析 | ✅ 本报告涵盖 |
| 9 | 工程报告 | ✅ 本文件 |

---

## 2. 用户分层设计

### 2.1 完整用户角色体系

```
匿名用户 (Anonymous)
  └─ 最低权限，IP限流
     
注册用户 (Registered)  
  └─ 邮箱注册，基础AI配额
  
高级会员 (Premium)
  └─ 更高AI配额，完整KB访问
  
运营者-无AI (Operator)
  └─ 任务管理，无AI对话
  
运营者-有AI (Operator AI)
  └─ 任务管理 + AI对话
  
管理员 (Admin)
  └─ 完全权限
```

### 2.2 各角色功能对比

| 功能 | 匿名 | 注册 | 高级 | Operator | Operator AI | Admin |
|------|------|------|------|----------|-------------|-------|
| 首页/数据库浏览 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 文件详情查看 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 知识库(KB)查看 | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| AI对话 | ✅(1次/天) | ✅(5次/天) | ✅(100次/天) | ❌ | ✅(100次/天) | ✅(无限) |
| 任务管理 | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| 文件上传/编辑 | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| 系统设置 | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| 用户管理 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| 任务历史(前N条) | 2条 | 全部 | 全部 | 全部 | 全部 | 全部 |

### 2.3 会员制度商业设计

参照主流AI会员制产品（OpenAI ChatGPT、Perplexity AI等）的设计逻辑：

**免费层（Free）**
- 目标：吸引用户注册，体验产品
- AI Chat：5次/天
- 限制：只读，无文件操作

**高级会员（Premium）**  
- 建议定价：¥29/月 或 ¥299/年
- AI Chat：100次/天
- 包含：完整KB访问、文件下载
- 转化率目标：5-10%的注册用户

**企业/Operator**
- 定价：按需定制
- 包含：系统操作权限
- 适合：内部团队、合作机构

**配额重置策略**
- 每日UTC 00:00自动重置（基于`quota_date` ISO日期）
- 管理员可手动重置任意用户配额
- 建议实现：周期付费续费后自动升级（当前为管理员手动操作）

---

## 3. 技术架构

### 3.1 认证机制（双轨制）

本系统采用**双轨认证**模式，向后兼容：

```
┌─────────────────────────────────────────────────────┐
│                  请求进入 (Request)                   │
└──────────────────────────┬──────────────────────────┘
                           │
         ┌─────────────────┴─────────────────┐
         │                                   │
    ┌────▼─────┐                      ┌──────▼──────┐
    │ 邮箱用户  │                      │ Token用户   │
    │ (新系统) │                      │ (现有系统)  │
    └────┬─────┘                      └──────┬──────┘
         │  session["email_user_id"]         │  session["auth_token_id"]
         │                                   │  或 Bearer token
         └─────────────────┬─────────────────┘
                           │
                 ┌─────────▼─────────┐
                 │  _load_auth_from  │
                 │  _request()       │
                 │  → 合成统一token  │
                 └─────────┬─────────┘
                           │
                 ┌─────────▼─────────┐
                 │  权限检查          │
                 │  require_permissions│
                 └───────────────────┘
```

### 3.2 配额检查流程

```
AI Chat请求 → 检查角色
     │
     ├─ 匿名用户 → 查IP配额 → 超1次? → 返回429 (提示注册)
     │
     ├─ 注册用户 → 查user_id配额 → 超5次? → 返回429 (提示升级)
     │
     ├─ 高级用户 → 查user_id配额 → 超100次? → 返回429
     │
     └─ 其他角色 → 正常处理
                      │
                      └─ 增加配额计数 → 执行查询
```

---

## 4. 数据库设计

### 4.1 新增表结构

#### `users` 表 - 邮箱注册用户

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,           -- 唯一邮箱
    password_hash TEXT NOT NULL,          -- PBKDF2-SHA256 哈希
    role TEXT NOT NULL DEFAULT 'registered', -- 角色
    is_active INTEGER NOT NULL DEFAULT 1, -- 账号状态
    email_verified INTEGER NOT NULL DEFAULT 0, -- 邮箱验证状态
    display_name TEXT,                    -- 显示名称
    notes TEXT,                           -- 管理员备注
    created_at TEXT,                      -- 创建时间 ISO8601
    last_login_at TEXT,                   -- 最后登录时间
    email_verified_at TEXT                -- 邮箱验证时间
);
```

**索引**: `idx_users_email(email)`, `idx_users_role(role)`

#### `user_quotas` 表 - 每日配额跟踪

```sql
CREATE TABLE user_quotas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                -- 注册用户ID（可空）
    ip_address TEXT,                -- 匿名用户IP
    quota_date TEXT NOT NULL,       -- 日期 YYYY-MM-DD
    ai_chat_count INTEGER DEFAULT 0, -- 当日AI查询次数
    created_at TEXT,
    updated_at TEXT
);
```

**索引**: `(user_id, quota_date)`, `(ip_address, quota_date)`

#### `user_activity_logs` 表 - 操作审计日志

```sql
CREATE TABLE user_activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                -- 关联用户ID
    ip_address TEXT,                -- 客户端IP
    action TEXT NOT NULL,           -- 操作类型
    resource TEXT,                  -- 操作资源
    detail TEXT,                    -- 详情JSON或文本
    created_at TEXT                 -- 操作时间
);
```

**索引**: `idx_user_activity_user(user_id)`, `idx_user_activity_created(created_at)`

### 4.2 现有表保留

| 表名 | 说明 | 变更 |
|------|------|------|
| `auth_tokens` | 现有token认证 | 无变更（向后兼容）|
| `audit_events` | 系统审计事件 | 无变更 |
| `files` | 文件元数据 | 无变更 |
| `catalog_items` | 文件处理状态 | 无变更 |

---

## 5. 权限系统设计

### 5.1 权限矩阵

```python
_GROUP_PERMISSIONS = {
    "registered": {
        "stats.read", "files.read", "catalog.read",
        "markdown.read", "chat.view", "chat.query", "chat.conversations"
    },
    "premium": {
        # 同 registered + 同样的权限集合（配额由配额层控制）
    },
    "reader": {
        # 原有token-reader: 同registered + files.download
    },
    "operator": {
        # 任务管理全权限，无AI
        "files.*", "catalog.*", "markdown.*", "config.*",
        "schedule.write", "tasks.*", "logs.task.read"
        # 注意: 无 chat.* 权限
    },
    "operator_ai": {
        # operator 全权限 + AI对话
    },
    "admin": {
        # 全部权限 + users.manage
    }
}
```

### 5.2 新增权限

| 权限 | 说明 |
|------|------|
| `users.manage` | 管理员用户管理（仅admin）|

---

## 6. AI使用配额设计

### 6.1 配额限制表

| 角色 | 每日AI Chat次数 | 说明 |
|------|----------------|------|
| anonymous | 1次/IP/天 | 最低，鼓励注册 |
| registered | 5次/用户/天 | 注册福利 |
| premium | 100次/用户/天 | 付费会员 |
| reader (token) | 50次/用户/天 | 原有token用户 |
| operator | 0次 | 无AI权限 |
| operator_ai | 100次/用户/天 | 运营AI用户 |
| admin | 10000次/用户/天 | 实际无限 |

### 6.2 超额提示策略

```
匿名用户超额 → "已达到每日AI对话限制（1次/天）。请注册获取更多额度。"
注册用户超额 → "已达到每日AI对话限制（5次/天）。请升级高级会员获得100次/天。"
高级用户超额 → "已达到每日AI对话限制（100次/天）。"
```

HTTP 状态码: `429 Too Many Requests`

### 6.3 配额重置机制

- **自动重置**: 基于`quota_date`（UTC日期），新的一天自动产生新记录
- **手动重置**: 管理员通过 `POST /api/admin/users/{id}/reset-quota` 重置
- **精确计数**: 在配额验证通过后、AI查询执行前增加计数（防止API超时导致计数丢失）

---

## 7. API端点设计

### 7.1 用户认证端点

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| GET/POST | `/register` | 邮箱注册 | 无需 |
| GET/POST | `/email-login` | 邮箱登录 | 无需 |
| POST | `/logout` | 退出登录 | 已登录 |
| GET | `/profile` | 用户个人页面 | 已登录 |
| GET | `/upgrade` | 会员升级页面 | 无需 |

### 7.2 配额端点

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| GET | `/api/user/quota` | 查询当前配额 | 无需 |

**响应示例**:
```json
{
  "success": true,
  "role": "registered",
  "used": 3,
  "limit": 5,
  "remaining": 2,
  "date": "2026-03-06"
}
```

### 7.3 管理员端点

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/admin/users` | 用户管理页面 | users.manage |
| GET | `/api/admin/users` | 用户列表API | users.manage |
| POST | `/api/admin/users/{id}/role` | 修改用户角色 | users.manage |
| POST | `/api/admin/users/{id}/active` | 启用/禁用用户 | users.manage |
| POST | `/api/admin/users/{id}/reset-quota` | 重置配额 | users.manage |
| GET | `/api/admin/users/{id}/activity` | 查看操作记录 | users.manage |

---

## 8. 页面与模板

### 8.1 新增页面

| 页面 | 路径 | 描述 |
|------|------|------|
| `register.html` | `/register` | 注册页面：邮箱、密码、显示名称 |
| `email_login.html` | `/email-login` | 邮箱登录页面 |
| `profile.html` | `/profile` | 个人资料：账号信息、配额进度条、操作记录 |
| `upgrade.html` | `/upgrade` | 会员套餐对比与升级说明 |
| `admin_users.html` | `/admin/users` | 用户管理：列表、筛选、角色修改、配额重置 |

### 8.2 导航栏更新

- 未登录: 显示「注册」和「登录」按钮
- 已登录: 显示用户邮箱链接（点击进入个人页面）和「退出」按钮
- Admin: 导航栏增加「Users」链接
- 根据角色控制导航项可见性（Chat、Tasks、Knowledge Bases等）

---

## 9. 安全考量

### 9.1 密码安全

- **算法**: PBKDF2-SHA256，迭代260,000次（符合OWASP建议2023+）
- **盐值**: 每个用户独立随机16字节盐值
- **比较**: `secrets.compare_digest()` 防止时序攻击
- **存储**: 仅存储哈希，永不记录明文密码

### 9.2 配额安全

- IP配额依赖`request.remote_addr`，在有反向代理时需配置`TRUST_PROXY=true`
- 配额检查失败时采用**非阻断**策略（`try/except`），避免因DB故障阻断正常业务
- 建议生产环境中将配额存储迁移到Redis以提高性能

### 9.3 权限控制

- 所有用户管理API通过`require_permissions("users.manage")`装饰器保护
- 密码哈希值从API响应中剥离
- 用户活动日志记录管理员操作（`admin_set_role`, `admin_reset_quota`等）

### 9.4 输入验证

- 邮箱格式验证（包含`@`）
- 密码最短8字符
- 角色枚举验证（防止注入无效角色）
- SQL注入防护（使用参数化查询）

### 9.5 待改进点

- [ ] 邮箱验证流程（发送验证邮件）
- [ ] 密码重置流程（忘记密码）
- [ ] 登录失败次数限制（暴力破解防护）
- [ ] JWT令牌替代session（多实例部署支持）
- [ ] 支付集成（自动升级Premium）

---

## 10. 数据库增强建议

### 10.1 当前数据库状态评估

**优点**:
- 使用SQLite + WAL模式，适合中小规模部署
- 已有良好的表索引设计
- 支持参数化查询，无SQL注入风险

**局限性**:
- SQLite不支持真正的并发写入
- 无内置连接池
- 配额数据如频繁更新会产生写锁竞争

### 10.2 近期建议（当前规模适用）

1. **增加`deleted_at`软删除字段到`users`表**（已有在`files`表的先例）
2. **配额索引优化**: 已通过`(user_id, quota_date)`和`(ip_address, quota_date)`复合索引覆盖
3. **定期清理旧配额记录**: 建议保留90天，超过自动删除

### 10.3 中期建议（增长后适用）

| 问题 | 建议方案 |
|------|----------|
| 并发写配额 | 引入Redis存储每日配额（原子INCR操作） |
| 用户增长 | 迁移到PostgreSQL（更好的并发和全文搜索） |
| 会话管理 | 引入Redis存储session（支持多实例部署） |
| 搜索性能 | 考虑PostgreSQL的`pg_trgm`扩展优化邮箱搜索 |

### 10.4 长期建议（规模化后适用）

- 引入**读写分离**（PostgreSQL主从复制）
- 考虑**分区表**（按月分区`user_activity_logs`）
- 引入**数据仓库**（用户行为分析、配额统计报表）

### 10.5 推荐的SQLite优化（立即可用）

```python
# 在Storage.__init__中建议添加：
self._conn.execute("PRAGMA journal_mode=WAL;")      # 已有
self._conn.execute("PRAGMA synchronous=NORMAL;")   # 建议添加
self._conn.execute("PRAGMA cache_size=-64000;")    # 64MB缓存
self._conn.execute("PRAGMA temp_store=memory;")    # 临时表放内存
self._conn.execute("PRAGMA mmap_size=268435456;")  # 256MB内存映射
```

---

## 11. 实现摘要

### 11.1 本次实现的文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `ai_actuarial/db_models.py` | 新增 | User, UserQuota, UserActivityLog SQLAlchemy模型 |
| `ai_actuarial/storage.py` | 扩展 | 新增用户管理存储方法，新增3张表的schema初始化 |
| `ai_actuarial/web/app.py` | 扩展 | 新增角色、配额常量、密码工具函数、注册/登录/管理员路由 |
| `ai_actuarial/web/chat_routes.py` | 修改 | 注入AI Chat配额检查逻辑 |
| `ai_actuarial/web/templates/base.html` | 修改 | 更新导航栏，支持注册/登录入口和角色敏感导航 |
| `ai_actuarial/web/templates/register.html` | 新增 | 用户注册页面 |
| `ai_actuarial/web/templates/email_login.html` | 新增 | 邮箱登录页面 |
| `ai_actuarial/web/templates/profile.html` | 新增 | 用户个人资料与配额仪表板 |
| `ai_actuarial/web/templates/upgrade.html` | 新增 | 会员升级对比页面 |
| `ai_actuarial/web/templates/admin_users.html` | 新增 | 管理员用户管理页面 |

### 11.2 向后兼容性

- ✅ 原有token认证（admin/operator/reader token）**完全保留**
- ✅ 原有API端点无任何变更
- ✅ 现有`operator`角色默认无AI访问（需显式升级为`operator_ai`）
- ✅ 所有现有测试通过（17/17）

---

## 12. 后续建议

### 12.1 优先级高（建议立即实现）

1. **邮箱验证**: 注册后发送验证链接，提高账号安全性
2. **密码重置**: 忘记密码流程（通过邮件发送重置链接）
3. **登录失败限制**: 5次失败后锁定账号或要求验证码

### 12.2 优先级中（1-3个月内）

1. **支付集成**: 支持支付宝/微信支付自动升级Premium
2. **配额预警**: 当用户剩余配额不足20%时，在UI显示提醒
3. **批量用户管理**: 管理员可批量导入/导出用户数据（CSV）
4. **用户统计仪表板**: 管理员查看注册趋势、活跃用户数、配额使用率等

### 12.3 优先级低（长期规划）

1. **OAuth2集成**: 支持微信/Google/GitHub第三方登录
2. **API配额**: 为付费用户提供API访问权限和配额
3. **团队账号**: 企业级多用户团队管理
4. **审计报告**: 用户行为分析和安全审计PDF报告生成

---

*本报告由AI Copilot生成，对应PR: copilot/design-user-management-system*
