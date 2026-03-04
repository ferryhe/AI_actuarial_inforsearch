# 代码审查任务计划

## 项目信息
- **项目**: AI_actuarial_inforsearch
- **分支**: code-review
- **目标**: 熟悉代码、识别改进点

## 审查范围

### 1. 核心模块
- [ ] `ai_actuarial/catalog.py` - 目录管理 (~985行)
- [ ] `ai_actuarial/catalog_incremental.py` - 增量目录 (~975行)
- [ ] `ai_actuarial/crawler.py` - 爬虫模块 (~751行)
- [ ] `ai_actuarial/storage.py` - 存储层 (~2,553行)

### 2. AI 模块
- [ ] `ai_actuarial/chatbot/` - 聊天机器人 (~2,000行)
- [ ] `ai_actuarial/rag/` - RAG 检索增强 (~2,300行)
- [ ] `ai_actuarial/llm_models.py` - LLM 模型集成 (~386行)

### 3. Web 模块
- [ ] `ai_actuarial/web/app.py` - Flask 应用 (~4,296行)
- [ ] `ai_actuarial/web/chat_routes.py` - 聊天路由 (~924行)
- [ ] `ai_actuarial/web/rag_routes.py` - RAG 路由 (~1,375行)

### 4. 数据库
- [ ] `ai_actuarial/db_models.py` - 数据模型 (~81行)
- [ ] `ai_actuarial/db_backend.py` - 数据库后端 (~396行)

## 审查标准
1. 代码质量 (可读性、复杂度)
2. 性能考虑
3. 安全风险
4. 依赖管理
5. 文档完整性

## 输出
- findings.md - 发现的问题
- progress.md - 审查进度
