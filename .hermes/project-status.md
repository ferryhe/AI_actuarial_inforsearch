# Project Status

- Date: 2026-06-01
- Branch: `fix/rag-dashscope-embedding-batch-limit`
- Baseline: `origin/main` at `ee3464e`.
- Scope: Fix RAG indexing failures where DashScope/Qwen `text-embedding-v3` rejects embedding API batches larger than 10 while `embedding_batch_size` could be configured as 64 from YAML/env/default sources.
- Implementation: `RAGConfig.__post_init__` now caps `embedding_batch_size` to 10 for `qwen`/`dashscope` providers and logs a warning when the configured value is reduced.
- Regression tests added for YAML, env, constructor/default paths, non-DashScope providers, and actual `EmbeddingGenerator` batching of 25 chunks into 10/10/5.
- Verification completed locally: `python -m pytest tests/test_rag_runtime.py -q` (10 passed); `git diff --check`; `python -m py_compile ai_actuarial/rag/config.py tests/test_rag_runtime.py`; delegate read-only review PASS; Codex CLI review PASS.
