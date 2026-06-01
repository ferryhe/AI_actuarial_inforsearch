# Project Status

- Date: 2026-06-01
- Branch: `fix/rag-dashscope-embedding-batch-limit`
- Baseline: `origin/main` at `ee3464e`.
- Scope: Fix RAG indexing failures where DashScope/Qwen `text-embedding-v3` rejects embedding API batches larger than 10 while `embedding_batch_size` could be configured as 64 from YAML/env/default sources.
- PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/131
- Remote state checked after creation: PR open, non-draft, merge state clean; `python-smoke` succeeded; Copilot left two in-scope comments.
- Follow-up fixes: provider/model-specific cap table now only caps supported provider `qwen` with model `text-embedding-v3` to 10; unsupported `dashscope` provider test was removed/replaced; shared default/cap constants live in `ai_actuarial/rag/defaults.py`; `scripts/migrate_env_to_yaml.py` prepends repo root to `sys.path` so documented standalone `--help`/execution keeps working.
- Diagnostics: `RAGConfig` records configured vs effective embedding batch size, config source, and limit reason for warning logs.
- Regression tests cover YAML, env, other Qwen models staying uncapped, non-Qwen providers, YAML env fallback, and actual `EmbeddingGenerator` batching of 25 chunks into 10/10/5.
- Verification completed locally after fixes: `python -m pytest tests/test_rag_runtime.py tests/test_yaml_config.py -q` (24 passed); `python scripts/migrate_env_to_yaml.py --help` (pass); `git diff --check` (pass); `python -m py_compile ai_actuarial/rag/config.py ai_actuarial/rag/defaults.py config/yaml_config.py scripts/migrate_env_to_yaml.py tests/test_rag_runtime.py` (pass).
- Codex CLI review: first review found standalone migration script import breakage; fixed and reverified.
- Follow-up threshold fix: Qwen `text-embedding-v3` now also uses an effective/default `similarity_threshold` of 0.02 while preserving/validating the configured value; OpenAI and other Qwen models remain unchanged. `ai_config.embeddings.similarity_threshold` is the single YAML source; `ai_config.chatbot.similarity_threshold` is deprecated/ignored with a warning. `RAG_SIMILARITY_THRESHOLD` remains the environment override. Chat retrieval applies the effective cap at runtime and API metadata reports the effective threshold after retrieval/no-results.
- Threshold verification: focused threshold/config tests passed (`tests/test_chatbot_core.py::TestChatbotConfig` 20 passed; `tests/test_rag_runtime.py::TestRagRuntime` 18 passed); combined focused run passed (38 passed); `py_compile` on touched runtime files passed; `git diff --check` passed; Codex final review PASS. Broader `tests/test_chatbot_core.py` still has one unrelated pre-existing prompt expectation failure (`RETRIEVED INFORMATION` vs `UNTRUSTED CONTEXT FROM KNOWLEDGE BASE`).
