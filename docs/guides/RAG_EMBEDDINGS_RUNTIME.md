# RAG Embeddings Runtime

RAG embeddings resolve through `resolve_ai_function_runtime("embeddings")`.

Resolution order:

1. Read `ai_config.embeddings` from `config/sites.yaml`.
2. If `credential_id` is present, resolve that exact credential.
3. If no credential is bound, use the default active DB credential for the provider/category.
4. If no DB credential exists, fall back to the provider environment variable.

Explicit credential ids are strict. A bad `credential_id` does not silently fall back to another credential.

## Diagnostics

Run:

```bash
python scripts/diagnose_embedding_runtime.py --config config/sites.yaml --json
```

The script prints only non-sensitive values:

- config and DB paths
- embeddings provider/model
- credential source/id/label/error
- whether an API key and base URL are present
- whether `TOKEN_ENCRYPTION_KEY` is configured
- decrypt status when the selected credential can be matched

It never prints provider API keys or `TOKEN_ENCRYPTION_KEY`.

## Common failures

- `credential_source=missing`: create/select a usable provider credential or fix `ai_config.embeddings.credential_id`.
- `credential_error=decrypt_failed`: check that API and worker use the same `TOKEN_ENCRYPTION_KEY`, then re-encrypt credentials if needed.
- `credential_error=credential_not_found`: the bound credential id does not exist in the DB used by the process.
- `configured=false`: RAG indexing and chat retrieval cannot initialize remote embeddings until credentials are fixed.
