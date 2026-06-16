# Phase 1.3 环境安装与全量测试通过 - 实现报告

## Project Overview

- 项目：AI Actuarial InfoSearch
- 日期：2026-02-12
- 状态：完成（环境依赖就绪 + 全量自动化测试通过）
- 目标：
  - 安装并校验测试依赖
  - 跑通全量自动化测试
  - 记录可复现的执行命令与结果

## Environment Setup

- Python：3.12.6
- 虚拟环境：`.venv`
- 关键依赖：
  - `flask`
  - `pytest`
  - `pytest-cov`
  - `pytest-mock`
  - `tiktoken`

安装命令：

```powershell
C:\PyProject\AI_actuarial_inforsearch\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
C:\PyProject\AI_actuarial_inforsearch\.venv\Scripts\python.exe -m pip install tiktoken
```

## Code Fixes Included

本轮为测试通过所做的关键修复：

- `ai_actuarial/storage.py`
  - 为 `catalog_items` 补齐迁移列：`rag_chunk_count`、`rag_indexed_at`
- `ai_actuarial/web/rag_routes.py`
  - 修复文件预览 API 调用错误：`get_file` -> `get_file_by_url`
- `tests/test_file_preview.py`
  - 修正状态码断言（与 API 语义一致：200/404/400）
- `pytest.ini`
  - 增加 `pythonpath = .`，降低本地导入失败风险

## Full Test Result

执行命令：

```powershell
C:\PyProject\AI_actuarial_inforsearch\.venv\Scripts\python.exe -m pytest -q
```

执行结果：

- `collected 70 items`
- `70 passed`
- `0 failed`

## Reproduction Checklist

1. 进入项目根目录：`C:\PyProject\AI_actuarial_inforsearch`
2. 安装依赖：
   - `C:\PyProject\AI_actuarial_inforsearch\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
   - `C:\PyProject\AI_actuarial_inforsearch\.venv\Scripts\python.exe -m pip install tiktoken`
3. 运行测试：
   - `C:\PyProject\AI_actuarial_inforsearch\.venv\Scripts\python.exe -m pytest -q`
4. 期望结果：`70 passed`

## Summary

- 测试环境已可稳定执行。
- 当前分支全量测试已通过（70/70）。
- 修复点覆盖了文件预览 API、数据库迁移兼容和测试断言一致性。

## 增量 UI 调整（本次）

- `Database` 页面：
  - 新增文件序号列（分页连续编号）。
  - 首页仅保留 `Markdown` 标记，移除 `Chunk` 标记展示。
- `File Details` 页面（Markdown 区域上方）：
  - 新增 `Chunk` / `Index` 两条状态信息，显示 embedding model、生成时间、chunk 数。
  - 当缺少 chunk/index 时，提供一键提交 `Chunk+Index` 任务按钮。
- 时间显示：
  - `Updated` 时间统一为本地时区展示，精确到秒。
