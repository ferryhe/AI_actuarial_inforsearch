# 代码审查任务计划

## 项目信息
- **项目**: AI_actuarial_inforsearch
- **分支**: code-review
- **目标**: 熟悉代码、识别改进点

## 审查范围

### 1. 核心模块
- [ ] `catalog.py` / `catalog_incremental.py` - 目录管理
- [ ] `crawler.py` - 爬虫模块
- [ ] `storage.py` / `storage_v2.py` - 存储层

### 2. AI 模块
- [ ] `chatbot/` - 聊天机器人
- [ ] `rag/` - RAG 检索增强
- [ ] `llm_models.py` - LLM 模型集成

### 3. Web 模块
- [ ] `web/app.py` - Flask 应用
- [ ] `web/chat_routes.py` - 聊天路由

### 4. 数据库
- [ ] `db_models.py` - 数据模型
- [ ] `db_backend.py` - 数据库后端

## 审查标准
1. 代码质量 (可读性、复杂度)
2. 性能考虑
3. 安全风险
4. 依赖管理
5. 文档完整性

## 输出
- findings.md - 发现的问题
- progress.md - 审查进度
