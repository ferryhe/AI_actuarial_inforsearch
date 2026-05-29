# Project Status

- Date: 2026-05-29
- Branch: `chore/slim-runtime-requirements`
- Baseline: latest `origin/main`.
- Scope: Slim standard runtime dependencies, remove local embedding/GPU-heavy optional packages from the default install path, document Java as an OS prerequisite for OpenDataLoader, and remove the private host path from `AGENTS.md`.
- `requirements.txt` is grouped by runtime area and no longer directly includes `keybert`, `sentence-transformers`, `marker-pdf`, or explicit GPU-heavy packages. It keeps OpenAI/ChatGPT-compatible, Mistral, OpenDataLoader, MarkItDown, Docling Slim plus CPU PDF backend pieces, and core FastAPI/RAG/vector-search dependencies.
- Java is documented as a system prerequisite for OpenDataLoader in `requirements.txt` comments and README quick-start requirements; Docker installs `default-jre-headless` because pip cannot install a JVM.
- Docker no longer installs explicit torch/torchvision/easyocr/onnxruntime side packages or the old `mistralai==1.0.0` override.
- Catalog keyword extraction now always uses the lightweight deterministic path after removing KeyBERT, filters common English stop words, and the catalog version was bumped to `v3-light-keywords` so existing catalog rows can be reprocessed instead of sharing the old `v2-keybert` version.
- `AGENTS.md` now identifies the repo as the current checkout root instead of exposing a host-specific absolute checkout path.
- `DoclingEngine` keeps the `docling` engine usable in the slim runtime by using a CPU text fallback for PDF files when the optional full Docling model stack is not installed; full `DocumentConverter` remains available when those optional dependencies are installed separately.
- Focused verification completed locally: `python -m pip install --dry-run --no-deps -r requirements.txt`, full dependency dry-run with a forbidden GPU/package parse, 13 focused pytest tests, `git diff --check`, dependency/path searches.
- Local Codex review gate found and prompted fixes for the KeyBERT determinism/version issue, Java package availability, the plain `docling` heavy transitive dependency path, the Docling Slim PDF backend gap, and lightweight keyword stop-word filtering; fixes implemented.
- Final local Codex review gate reruns timed out twice after 15 minutes each: `codex review --uncommitted` and `codex review --base origin/main`. This is recorded as a tooling blocker before PR publication.
- PR #127 created from `chore/slim-runtime-requirements`; GitHub `python-smoke` passed and Copilot PR review produced no actionable comments.
