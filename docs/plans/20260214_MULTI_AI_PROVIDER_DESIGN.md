# 多AI Provider配置设计方案

## 目标
支持多个AI Provider，用户可在Settings页面选择不同场景使用的模型。

## Provider分类

### 1. **Embedding Models** (向量嵌入)
- OpenAI: `text-embedding-3-large`, `text-embedding-3-small`, `text-embedding-ada-002`
- 用途: RAG向量化

### 2. **Chat Models** (对话)
- OpenAI: `gpt-4o`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`
- SiliconFlow: `deepseek-chat`, `qwen-plus` 等
- Mistral: `mistral-large-latest` 等
- 用途: Chatbot对话生成

### 3. **Catalog Models** (文档分析)
- OpenAI: `gpt-4o-mini`, `gpt-3.5-turbo` (小模型，性价比高)
- 用途: 文档摘要/关键词/分类

### 4. **OCR Models** (文档转换)
- Mistral: `mistral-ocr-latest`
- SiliconFlow: `deepseek-ai/DeepSeek-OCR`
- 用途: PDF → Markdown

## .env 配置结构

```env
# ===================================
# OpenAI Configuration
# ===================================
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_TIMEOUT_SECONDS=60

# ===================================
# SiliconFlow Configuration
# ===================================
SILICONFLOW_API_KEY=...
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_TIMEOUT_SECONDS=60

# ===================================
# Mistral Configuration
# ===================================
MISTRAL_API_KEY=...
MISTRAL_BASE_URL=https://api.mistral.ai/v1
MISTRAL_TIMEOUT_SECONDS=60

# ===================================
# AI Model Selection
# ===================================
# Embedding (RAG)
RAG_EMBEDDING_PROVIDER=openai
RAG_EMBEDDING_MODEL=text-embedding-3-large

# Chat (Conversational AI)
CHATBOT_PROVIDER=openai
CHATBOT_MODEL=gpt-4o
CHATBOT_TEMPERATURE=0.7
CHATBOT_MAX_TOKENS=1000

# Catalog (Document Analysis)
CATALOG_PROVIDER=openai
CATALOG_MODEL=gpt-4o-mini

# OCR (Document Conversion)
OCR_PROVIDER=mistral
OCR_MODEL=mistral-ocr-latest
```

## Settings UI 设计

### AI Settings 页面新增部分

```
┌─────────────────────────────────────┐
│ AI Provider Configuration           │
├─────────────────────────────────────┤
│                                     │
│ 🔹 Embedding (RAG Vectorization)   │
│   Provider: [OpenAI ▼]             │
│   Model:    [text-embedding-3-large▼]│
│                                     │
│ 🔹 Chatbot (Conversations)         │
│   Provider: [OpenAI ▼]             │
│   Model:    [gpt-4o ▼]             │
│   Temp:     [0.7]  Tokens: [1000]  │
│                                     │
│ 🔹 Cataloging (Document Analysis)  │
│   Provider: [OpenAI ▼]             │
│   Model:    [gpt-4o-mini ▼]        │
│                                     │
│ 🔹 OCR (PDF → Markdown)            │
│   Provider: [Mistral ▼]            │
│   Model:    [mistral-ocr-latest ▼] │
│                                     │
│ [Save Configuration]                │
└─────────────────────────────────────┘
```

## 实现步骤

### Phase 1: 配置结构重构
1. 创建 `ai_actuarial/config/ai_providers.py` 定义Provider配置类
2. 更新 `config/settings.py` 添加新配置项
3. 创建Provider工厂类

### Phase 2: Settings UI
1. 在 `templates/settings.html` 添加AI Settings部分
2. 创建API endpoint保存配置
3. 前端动态加载可用模型列表

### Phase 3: 集成
1. 更新 `chatbot/config.py` 读取新配置
2. 更新 `rag/config.py` 读取新配置
3. 更新 `catalog_llm.py` 读取新配置

## 模型列表管理

```python
# ai_actuarial/config/ai_providers.py

PROVIDER_MODELS = {
    "openai": {
        "embedding": [
            "text-embedding-3-large",
            "text-embedding-3-small",
            "text-embedding-ada-002"
        ],
        "chat": [
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo"
        ],
        "catalog": [
            "gpt-4o-mini",
            "gpt-3.5-turbo"
        ]
    },
    "siliconflow": {
        "chat": [
            "deepseek-chat",
            "qwen-plus"
        ],
        "ocr": [
            "deepseek-ai/DeepSeek-OCR"
        ]
    },
    "mistral": {
        "chat": [
            "mistral-large-latest"
        ],
        "ocr": [
            "mistral-ocr-latest"
        ],
        "catalog": [
            "mistral-small-latest"
        ]
    }
}
```

## API Endpoints

### GET /api/settings/ai-providers
返回可用的provider和模型列表

### POST /api/settings/ai-config
保存AI配置

### GET /api/settings/ai-config
获取当前AI配置

## 优势
1. ✅ 灵活选择不同场景的最优模型
2. ✅ 成本优化（小任务用小模型）
3. ✅ 支持备用provider（容错）
4. ✅ 集中管理，配置清晰

## 实施优先级
- **P1**: 基础配置结构 (本次实现)
- **P2**: Settings UI (下一版本)
- **P3**: Provider自动切换和容错
