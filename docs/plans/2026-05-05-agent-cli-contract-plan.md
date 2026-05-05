# AI_actuarial_inforsearch 到模块化 CLI 架构的抽取计划 Implementation Plan

> **For Hermes/Codex:** Use the project-isolated Codex worker pattern. Read `AGENTS.md` and `.hermes/project-status.md` before each run. Do not commit, push, or open PRs without explicit approval.

**Goal:** 明确哪些代码/概念迁出到 md_to_rag，哪些保留在旧系统。

**Architecture:** 不大规模重构产品；以文档/adapter/fixture 方式支持 md_to_rag 抽取，保持 FastAPI/React 主链路稳定。

**Tech Stack:** Project-native stack plus CLI-first JSON/JSONL manifests. Python projects should use Typer/Pydantic where already present; TypeScript projects should preserve pnpm/OpenAPI workflow.

---

## Context

This repository is one module in the broader agent-operated knowledge pipeline:

```text
web_listening -> doc_to_md -> md_to_rag -> rag_to_agent/domain adapters -> ai_interface
```

Current project role: 旧的一体化信息检索/RAG 产品，作为经验和可抽取代码来源。

Current planning scope: 冻结为参考系统；将 RAG/chunk/embedding/index 经验抽取到 md_to_rag，不继续承担新架构中心。

## Non-Negotiable Contracts

1. CLI outputs must be machine-readable and stable (`--json` where applicable).
2. Artifacts must be path-portable and manifest-driven.
3. Reruns must be idempotent.
4. Every derived artifact must preserve provenance back to its input.
5. Secrets/API keys must never be written into manifests or committed files.
6. Cross-repo integration happens through files/manifests/tool specs, not hidden imports.

## Proposed Tasks

### Task 1: RAG 模块 inventory

**Objective:** 列出 ai_actuarial/rag、chatbot/retrieval、storage_v2_rag 可抽象概念。

**Files:**
- Modify/Create project-specific files identified during the task.
- Update tests or fixtures for the changed contract.

**Steps:**
1. Inspect the current implementation and write down exact files touched.
2. Add or update the smallest contract/test fixture first.
3. Implement the minimal change.
4. Run the focused verification command.
5. Update `.hermes/project-status.md` with result and next action.

**Verification:** 运行相关 tests/test_rag_*。

### Task 2: 抽取候选清单

**Objective:** docs/plans 中写明 semantic_chunking、embeddings、vector_store 哪些可复制，哪些需解耦。

**Files:**
- Modify/Create project-specific files identified during the task.
- Update tests or fixtures for the changed contract.

**Steps:**
1. Inspect the current implementation and write down exact files touched.
2. Add or update the smallest contract/test fixture first.
3. Implement the minimal change.
4. Run the focused verification command.
5. Update `.hermes/project-status.md` with result and next action.

**Verification:** 标注 ai_runtime/config/storage 依赖。

### Task 3: 准备 sample markdown fixture

**Objective:** 选择真实 SOA 小文档，用作 md_to_rag ingest/chunk/embed 测试。

**Files:**
- Modify/Create project-specific files identified during the task.
- Update tests or fixtures for the changed contract.

**Steps:**
1. Inspect the current implementation and write down exact files touched.
2. Add or update the smallest contract/test fixture first.
3. Implement the minimal change.
4. Run the focused verification command.
5. Update `.hermes/project-status.md` with result and next action.

**Verification:** 不复制 secrets，不带运行时 DB。

### Task 4: 保持旧系统兼容

**Objective:** 任何抽取不改变现有 FastAPI/React contract。

**Files:**
- Modify/Create project-specific files identified during the task.
- Update tests or fixtures for the changed contract.

**Steps:**
1. Inspect the current implementation and write down exact files touched.
2. Add or update the smallest contract/test fixture first.
3. Implement the minimal change.
4. Run the focused verification command.
5. Update `.hermes/project-status.md` with result and next action.

**Verification:** 跑 focused RAG tests 和真实数据 smoke。

### Task 5: 后续 deprecation plan

**Objective:** 当 md_to_rag 稳定后，AI_actuarial 可选择外部调用而非内置 RAG。

**Files:**
- Modify/Create project-specific files identified during the task.
- Update tests or fixtures for the changed contract.

**Steps:**
1. Inspect the current implementation and write down exact files touched.
2. Add or update the smallest contract/test fixture first.
3. Implement the minimal change.
4. Run the focused verification command.
5. Update `.hermes/project-status.md` with result and next action.

**Verification:** 形成 ADR。


---

## Acceptance Criteria

- A Codex worker can understand this repo's boundary from `AGENTS.md`.
- A future implementation branch can start from this plan without needing cross-chat context.
- The module's input/output contract is explicit enough for the next module in the chain.
- All new behavior is testable through CLI commands and fixture manifests.

## Recommended First PR

Start with documentation/contracts and fixture-only changes. Do not implement all runtime behavior in the first PR. The first PR should make the intended contract reviewable before code follows.
