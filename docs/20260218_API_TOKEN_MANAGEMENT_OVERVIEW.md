# API Token管理功能 - 项目概述 / API Token Management - Project Overview

**创建日期 / Created**: 2026-02-18  
**状态 / Status**: 研究和规划完成 / Research & Planning Complete

---

## 快速导航 / Quick Navigation

📚 **主要文档 / Main Documents:**
1. [RAGFlow API Token管理研究报告](./20260218_RAGFLOW_API_TOKEN_MANAGEMENT_RESEARCH.md) - 详细的技术分析和方案设计
2. [API Token管理实现计划](./20260218_API_TOKEN_MANAGEMENT_IMPLEMENTATION_PLAN.md) - 6阶段实施计划和代码示例

---

## 项目背景 / Project Background

### 当前问题 / Current Issues

当前项目使用`.env`文件管理API密钥，存在以下问题：

1. ❌ **安全性低** - API密钥明文存储在文件中
2. ❌ **管理困难** - 需要手动编辑文件，容易出错
3. ❌ **缺少验证** - 无法验证API密钥是否有效
4. ❌ **不支持多用户** - 所有用户共享同一套配置
5. ❌ **难以扩展** - 添加新API提供商需要修改代码

### 解决方案 / Solution

基于RAGFlow的最佳实践，设计一套现代化的API token管理系统：

✅ **数据库加密存储** - 使用Fernet对称加密  
✅ **Web UI管理** - 友好的图形界面  
✅ **实时验证** - 添加API密钥时立即验证  
✅ **多提供商支持** - 统一管理LLM、搜索引擎等多种API  
✅ **向后兼容** - 保留`.env`作为fallback机制  

---

## 核心特性 / Core Features

### 1. 安全存储 / Secure Storage

```
API密钥 → Fernet加密 → 数据库存储
解密密钥 → TOKEN_ENCRYPTION_KEY (环境变量)
```

- **加密算法**: Fernet (对称加密，AES-128)
- **密钥管理**: 环境变量，不提交到代码库
- **数据库**: SQLite (默认) / PostgreSQL (可选)

### 2. 多层fallback / Multi-layer Fallback

```
优先级顺序:
1. 数据库 (最高优先级)
   ↓
2. sites.yaml配置文件
   ↓
3. .env环境变量 (向后兼容)
```

这种设计确保平滑迁移，不会破坏现有功能。

### 3. 支持的API提供商 / Supported Providers

#### LLM提供商 (已规划)
- ✅ OpenAI (GPT-4, GPT-3.5, embeddings)
- ✅ Anthropic (Claude)
- ✅ Mistral AI (OCR, chat)
- ✅ Google Gemini
- ✅ Cohere (chat, embedding, rerank)
- ✅ SiliconFlow (国内访问快)
- ✅ 智谱AI, 百度千帆, 阿里通义

#### 搜索API (已规划)
- ✅ Brave Search
- ✅ SerpAPI
- ✅ Serper
- ✅ Bing Search API
- ✅ Google Custom Search

#### 其他API (未来)
- 📄 文档处理 (LlamaParse, Unstructured.io)
- 🌐 翻译服务 (DeepL, Google Translate)
- 📊 数据服务 (Wolfram Alpha, AlphaVantage)

### 4. Web UI功能 / Web UI Features

Settings页面新增"API Tokens"标签：

```
┌─────────────────────────────────────────┐
│  Settings → API Tokens                   │
├─────────────────────────────────────────┤
│  [LLM提供商] [搜索引擎] [文档处理] [其他]  │
├─────────────────────────────────────────┤
│  Provider  │ API Key  │ Status │ Actions │
│  OpenAI    │ sk-...xyz│   ✓   │ [验证][删除]│
│  Brave     │ BSA...123│   ✓   │ [验证][删除]│
│  + 添加新Token                            │
└─────────────────────────────────────────┘
```

**操作功能:**
- 📝 添加/编辑API token
- 🔍 实时验证有效性
- 👁️ 脱敏显示(只显示前后4位)
- 🗑️ 删除token
- 📊 查看使用统计

---

## 技术架构 / Technical Architecture

### 系统架构图 / System Architecture

```
┌──────────────────────────────────────────────┐
│          Frontend (Settings UI)               │
│  - Token列表展示                               │
│  - 添加/编辑表单                               │
│  - 验证状态显示                                │
└─────────────────┬────────────────────────────┘
                  │ REST API (JSON)
┌─────────────────▼────────────────────────────┐
│         Backend API Endpoints                 │
│  GET    /api/tokens      - 列表              │
│  POST   /api/tokens      - 添加/更新         │
│  DELETE /api/tokens/:id  - 删除              │
│  POST   /api/tokens/:id/verify - 验证        │
└─────────────────┬────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────┐
│           Service Layer                       │
│  TokenService      - CRUD操作                │
│  TokenEncryption   - 加密/解密               │
│  ApiKeyProvider    - 统一获取接口            │
│  TokenVerification - API验证                 │
└─────────────────┬────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────┐
│          Database (api_tokens表)              │
│  - 加密存储                                   │
│  - 使用统计                                   │
│  - 验证状态                                   │
└───────────────────────────────────────────────┘
```

### 数据库设计 / Database Schema

```sql
CREATE TABLE api_tokens (
    id INTEGER PRIMARY KEY,
    provider VARCHAR(50),        -- openai, brave, etc.
    category VARCHAR(20),        -- llm, search, etc.
    api_key_encrypted TEXT,      -- 加密的密钥
    api_base_url VARCHAR(255),   -- 可选base URL
    status VARCHAR(10),          -- active/disabled
    verification_status VARCHAR(20),
    last_verified_at TIMESTAMP,
    usage_count INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(provider, category)
);
```

---

## 实施计划 / Implementation Plan

### 6个阶段 / 6 Phases

| 阶段 | 时间 | 主要任务 | 交付物 |
|------|------|----------|--------|
| **Phase 1: 基础设施** | Week 1 | 数据库模型、加密服务 | 可运行的迁移脚本 |
| **Phase 2: Backend** | Week 2 | REST API端点、验证逻辑 | 完整的Backend API |
| **Phase 3: 集成** | Week 3 | 与现有系统集成 | 统一的API key获取接口 |
| **Phase 4: Frontend** | Week 4 | UI界面开发 | 可用的管理界面 |
| **Phase 5: 安全** | Week 5 | 安全审查、测试 | 安全评估报告 |
| **Phase 6: 发布** | Week 6 | 文档、部署 | v1.0正式发布 |

### 当前进度 / Current Progress

✅ **已完成:**
- [x] RAGFlow源码分析
- [x] 技术方案设计
- [x] 详细实施计划
- [x] 数据库设计
- [x] 代码示例准备

🔄 **下一步:**
- [ ] Team review和反馈收集
- [ ] Phase 1实施准备
- [ ] 环境配置(生成TOKEN_ENCRYPTION_KEY)

---

## 安全考虑 / Security Considerations

### 加密方案 / Encryption

- **算法**: Fernet (symmetric encryption)
- **密钥存储**: 环境变量`TOKEN_ENCRYPTION_KEY`
- **密钥轮换**: 支持密钥更新和重新加密

### 访问控制 / Access Control

```python
# 权限级别
PERMISSIONS = {
    "admin": ["read", "write", "delete", "verify"],
    "user": ["read"],
    "service": ["read", "verify"]
}
```

### 日志安全 / Logging Security

- ✅ API密钥不出现在日志中
- ✅ 敏感字段自动脱敏
- ✅ 审计日志记录关键操作

### 传输安全 / Transport Security

- ✅ HTTPS强制
- ✅ CSRF保护
- ✅ Content Security Policy

---

## 迁移指南 / Migration Guide

### 从.env迁移 / Migrating from .env

**步骤1: 生成加密密钥**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

将结果添加到`.env`:
```bash
TOKEN_ENCRYPTION_KEY=your-generated-key-here
```

**步骤2: 创建数据库表**
```bash
python scripts/create_api_tokens_table.py
```

**步骤3: 迁移现有密钥**
```bash
python scripts/migrate_env_to_database.py
```

**步骤4: 验证**
```bash
# 访问Web UI
http://localhost:5000/settings
# 点击"API Tokens"标签
# 检查所有token是否正确迁移
```

### 向后兼容性 / Backward Compatibility

即使迁移后，系统仍会尝试从以下位置读取：
1. 数据库 (优先)
2. sites.yaml
3. .env (fallback)

这确保逐步迁移，不会中断现有服务。

---

## 性能考虑 / Performance Considerations

### 缓存策略 / Caching

```python
# API密钥会被缓存，避免频繁解密
@lru_cache(maxsize=100)
def get_api_key(provider, category):
    # 从数据库读取并解密
    ...
```

### 数据库优化 / Database Optimization

- ✅ 索引: `(provider, category)`, `(provider, status)`
- ✅ 连接池: 复用数据库连接
- ✅ 批量操作: 减少数据库往返

---

## 常见问题 / FAQ

**Q: 如果忘记TOKEN_ENCRYPTION_KEY怎么办？**
A: 需要重新生成密钥并重新设置所有API token。这是设计上的安全考虑。

**Q: 是否支持团队协作？**
A: 当前版本为单用户设计。多用户支持需要添加用户权限系统，已在future roadmap中。

**Q: 如何备份API tokens？**
A: 备份数据库文件和TOKEN_ENCRYPTION_KEY即可。注意安全存储备份文件。

**Q: 可以使用外部密钥管理服务吗？**
A: 可以。可以扩展`TokenEncryption`类对接AWS KMS、Azure Key Vault等服务。

**Q: 性能影响如何？**
A: 加密/解密开销很小(<1ms)，通过缓存进一步降低。API调用本身的网络延迟远大于加解密时间。

---

## 参考资料 / References

### 项目文档
- [RAGFlow研究报告](./20260218_RAGFLOW_API_TOKEN_MANAGEMENT_RESEARCH.md)
- [实现计划](./20260218_API_TOKEN_MANAGEMENT_IMPLEMENTATION_PLAN.md)
- [配置迁移计划](./20260215_CONFIG_MIGRATION_PLAN.md)
- [动态模型获取](./implementation/20260217_DYNAMIC_MODEL_FETCHING.md)

### 外部资源
- [RAGFlow GitHub](https://github.com/infiniflow/ragflow)
- [Cryptography Library](https://cryptography.io/)
- [OWASP API Security](https://owasp.org/www-project-api-security/)

---

## 联系方式 / Contact

如有问题或建议，请：
- 📧 创建GitHub Issue
- 💬 在PR中评论
- 📝 更新本文档

---

**文档维护者 / Document Maintainer**: AI Actuarial Research Team  
**最后更新 / Last Updated**: 2026-02-18  
**版本 / Version**: 1.0
