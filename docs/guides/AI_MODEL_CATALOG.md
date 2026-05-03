# AI Model Catalog

This guide describes how the Settings model dropdowns are populated and how the list refreshes.

## Sources

The model catalog is defined in `ai_actuarial/llm_models.py`.

It has two layers:

- Curated fallback lists in `DEFAULT_MODELS`. These are available offline and keep Settings usable when provider APIs are unavailable.
- Live discovery for providers with a model-list API. The cache refreshes on first access, then again after 24 hours.

The current live discovery path prefers encrypted DB credentials for each provider and falls back to environment variables when a DB credential is not configured. It supports:

- OpenAI through encrypted DB credentials.
- Mistral through encrypted DB credentials.
- SiliconFlow through encrypted DB credentials.
- OpenAI-compatible providers when their DB credential or environment key is set, including OpenRouter, DeepSeek, ZhipuAI, Moonshot/Kimi, Qwen/DashScope, MiniMax, VolcEngine, Tencent Cloud, BaiduYiyan, XunFei Spark, Google Cloud (`GOOGLE_CLOUD_API_KEY`), and Hugging Face (`HUGGINGFACE_API_KEY`).
- Local OpenAI-compatible servers (`vllm`, `localai`) only when `VLLM_BASE_URL` or `LOCALAI_BASE_URL` is explicitly set.

Live discovery classifies returned model ids into app capabilities:

- `chatbot` and `catalog` for text/chat models.
- `embeddings` for embedding model ids such as `text-embedding-*`, `embed*`, `bge*`, `gte*`, and `e5*`.
- `ocr` for OCR/document extraction model ids.

Image, video, audio, realtime, moderation, transcription, TTS, and rerank models are filtered out of the general chat/catalog dropdowns.

## Refreshing

Automatic refresh:

- `initialize_models()` warms the cache during application startup.
- Any read through `llm_models.get_available_models()` refreshes the cache when it is empty or older than 24 hours.
- If a provider request fails, the app logs a warning and keeps using the fallback list.

Manual refresh:

```bash
curl "http://127.0.0.1:8000/api/config/model-catalog?refresh=true"
curl "http://127.0.0.1:8000/api/config/ai-models?refresh=true"
```

Programmatic refresh:

```python
from ai_actuarial.llm_models import refresh_models

refresh_models()
```

## Operational Notes

- The catalog refresh does not write secrets or provider responses to disk; it only updates the process memory cache.
- Runtime credential binding comes from `config/sites.yaml` plus encrypted DB credentials. Environment provider keys are supported only as temporary bootstrap/fallback values.
- For production, prefer provider aliases such as `gpt-5.5`, `mistral-small-latest`, or `qwen3-max` only when you accept provider-side alias movement. Use dated or snapshot model ids when deterministic behavior matters.

## References

- OpenAI models: https://developers.openai.com/api/docs/models
- Mistral models: https://docs.mistral.ai/models/overview
- Anthropic Opus models: https://www.anthropic.com/claude/opus
- Anthropic Sonnet models: https://www.anthropic.com/claude/sonnet
- Anthropic Haiku models: https://www.anthropic.com/claude/haiku
- Google Gemini models: https://ai.google.dev/gemini-api/docs/models
- Google Gemini embeddings: https://ai.google.dev/gemini-api/docs/embeddings
- Alibaba Cloud Model Studio models: https://www.alibabacloud.com/help/en/model-studio/models
- Alibaba Cloud embeddings: https://www.alibabacloud.com/help/en/model-studio/embedding-rerank-model/
- Moonshot/Kimi models: https://platform.moonshot.cn/docs/introduction
- Cohere models: https://docs.cohere.com/v1/docs/models
- SiliconFlow models: https://docs.siliconflow.cn/quickstart/models
- ZhipuAI GLM models: https://docs.bigmodel.cn/cn/guide/models/text/glm-4.5
- DeepSeek updates: https://api-docs.deepseek.com/updates/
- MiniMax API models: https://platform.minimax.io/docs/api-reference/api-overview
- OpenRouter model API: https://openrouter.ai/docs/api-reference/models/get-models
