# AI Provider Credentials

AI provider credentials use a three-part model:

- Provider registry: built-in provider metadata and capability flags.
- Credential instance: encrypted provider credentials stored in the `api_tokens` table.
- Function binding: `CONFIG_PATH -> ai_config` selects provider, model, and optional credential id. The tracked `config/sites.yaml` is only the development/bootstrap template.

Do not store provider API keys in `sites.yaml`. Keep `.env` for bootstrap/system values such as `TOKEN_ENCRYPTION_KEY`, `FASTAPI_SESSION_SECRET`, and optional temporary provider keys that can be imported into the database. The active SQLite path should come from `CONFIG_PATH -> paths.db`; `DB_PATH` is only a fallback when that YAML path is absent.

Search engine status, CLI search, and live model discovery prefer encrypted DB credentials. Environment provider keys remain supported as bootstrap/fallback values, but they should not be the long-term source of runtime secrets.

## Agentic RAG Credential Behavior

Agentic RAG does not add a new provider credential type.

- Building ready_data manifests reads the configured SQLite database and existing catalog/chunk records.
- Agentic read tools and `/api/agentic-rag/*` endpoints operate on local ready_data artifacts.
- The current Agentic Chat path uses deterministic ready_data evidence and returns `model="agentic-ready-data"` in metadata; it does not call an external LLM.
- The Agentic eval smoke in CI uses committed fixtures and does not require provider keys.

Provider credentials are still required for the surrounding product capabilities that create and use the source data:

- embeddings and standard vector RAG indexing;
- standard Chat LLM answer generation;
- cataloging/summarization flows when configured to call an AI provider;
- OCR/document extraction providers when enabled.

In practice, configure credentials exactly as before from Settings, then build Agentic ready_data from the KBs that already have catalog/chunk data.

## Credential IDs

Supported credential id forms:

- `openai:llm:instance:default`: stable credential instance id. Recommended for config binding.
- `openai:llm:db:123`: database row id. Kept for backward compatibility and debugging.
- `openai:llm:env`: explicitly use environment fallback.

Legacy `openai:llm:default` is treated as an instance id for compatibility, but new config should use `openai:llm:instance:default`.

## Example

```yaml
ai_config:
  embeddings:
    provider: openai
    model: text-embedding-3-large
    credential_id: openai:llm:instance:default
    batch_size: 64
    similarity_threshold: 0.4
    cache_enabled: true
```

If a bound credential id cannot be parsed, does not match the provider/category, cannot be found, or cannot be decrypted, the runtime reports `credential_source=missing` with a non-sensitive `credential_error`.

## Weekly Explanation Routing

Weekly explanations always inherit `provider`, `model`, and `credential_id` from
`ai_config.chatbot`. Their own section stores only generation policy such as the
versioned prompt, timeout, temperature, and token limit:

```yaml
ai_config:
  chatbot:
    provider: openai
    model: gpt-5.4-mini
    credential_id: openai:llm:instance:default
  weekly_explanation:
    prompt_version: weekly-explanation-v1
    timeout_seconds: 60
    temperature: 0
    max_tokens: 1200
```

Older `weekly_explanation` route fields are ignored at runtime and a warning names
the deprecated fields without logging their values. Saving weekly explanation
policy removes those legacy fields. The Settings API rejects new weekly route
writes and directs operators to update the Chat route instead.

Weekly generation audit data records the effective provider, model, and stable
credential identifier. It never records the credential value.
