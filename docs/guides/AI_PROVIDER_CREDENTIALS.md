# AI Provider Credentials

AI provider credentials use a three-part model:

- Provider registry: built-in provider metadata and capability flags.
- Credential instance: encrypted provider credentials stored in the `api_tokens` table.
- Function binding: `config/sites.yaml -> ai_config` selects provider, model, and optional credential id.

Do not store provider API keys in `sites.yaml`. Keep `.env` for bootstrap/system values such as `TOKEN_ENCRYPTION_KEY`, database paths, and optional temporary provider keys that can be imported into the database.

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
