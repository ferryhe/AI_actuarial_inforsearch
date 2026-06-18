# AI Actuarial Info Search

[English](README.md) | [简体中文](README.zh-CN.md)

AI Actuarial Info Search 是面向精算和保险研究场景的 FastAPI + React 文档智能平台，用于发现、下载、编目、转换、搜索并问答公开网站文档和浏览器上传的本地文件。

## 当前状态

`main` 已体现 2026 产品整合与飞书计划路线图的最终状态：

- **运行时：** FastAPI 是唯一 `/api/*` 权威入口；React/Vite 是唯一维护中的产品 UI。旧 server-rendered/Replit 时代工作流已退出当前产品。
- **安全/RBAC：** session/token 鉴权、细粒度权限、upload-batch 文件导入、公共 URL SSRF 防护、登录/注册限流，以及 Chat 文档上下文边界控制已启用。
- **客户产品面：** Dashboard 优先展示客户关心的来源、分类、来自后端 weekly summary 的最新周报新增、资料详情和问 Agent 入口；后台处理指标放在 admin/ops 页面，不再作为首页主内容。
- **Markdown 转换：** 由 `config/markdown_conversion.yaml` 和 Settings 管理工具顺序、格式路由、付费/API 工具开关和 tuning；付费/API 工具默认不自动触发。
- **采集自动化：** 支持配置站点爬取、搜索服务兜底、浏览器上传文件导入、typed 定时任务、`weekly_summary`、`full_pipeline`，以及 web-listening 规则 draft/validate/materialize。
- **周报新增：** `/api/weekly-updates` 和 `/api/weekly-updates/latest` 基于 `files.first_seen` 汇总新发现资料；默认 weekly task 使用 `relative_period: previous_week` 覆盖已完成的 UTC ISO 周。
- **RAG 和 Chat：** 标准向量 RAG 与 Agentic RAG 并存。Chat 已转为知识库优先体验，保留会话历史，支持标准多知识库 Chat 和单个 ready KB 的 Agentic 模式。
- **路线图完成：** Agentic RAG PR #133-#145、整合 PR #147-#154，以及飞书计划 managed PR-A 到 PR-I（#156-#164）均已合并；当前没有未完成的 managed-roadmap PR。

## 功能集

### 发现、导入和编目

- 爬取精算和保险组织网站。
- 通过 Brave/SerpAPI 等搜索服务扩展发现范围。
- 下载 PDF、Word、PowerPoint、Excel 和 HTML 来源。
- 通过浏览器选择并上传本地文件/文件夹。
- 使用 SHA-256 去重，并增量生成摘要、关键词和分类。
- 基于新发现文件生成 weekly update 摘要。

### Markdown 转换

- 使用本地或 API 引擎将文档转换为 Markdown。
- 通过 `config/markdown_conversion.yaml` 或 Settings 配置转换行为。
- 按格式路由工具、调整 scan/page 限制，并让付费/API 工具保持 opt-in。

### Web-listening 规则

- 根据来源 URL 和采集目标生成 `web-listening-agent-rule.v1` YAML 草稿。
- 在应用前校验 rule YAML。
- 将校验后的规则 materialize 为 acquisition profile、定时 `full_pipeline` monitor task、section selection 和 monitor scope 配置。

### RAG、Agentic RAG 和 Chat

- 管理 RAG 知识库、文件、分类、chunk profile 和索引任务。
- 使用标准向量 RAG 与知识库对话。
- 单次文档对比最多选择 3 个文档来源。
- 为知识库构建 `general`、`regulation`、`formula` 三种 Agentic RAG `ready_data` 清单。
- 在 Chat 中使用 Agentic RAG，对单个 ready KB 返回确定性证据、结构化引用和可检查 tool trace。
- 直接使用 ready-data summary、title、section、relation、formula、table、calculation-term 工具。

### 管理和运维

- 从 Settings 保存 AI/search provider credential 为数据库加密凭据。
- 通过 React UI 管理站点、schedule、任务、日志、用户、安全设置、模型目录和知识库。
- 生产密钥放在 `.env`/环境变量和加密 DB credential 中，不提交到 YAML。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js `^20.19.0` 或 `>=22.12.0`，用于 Vite 7 前端工具链
- 使用 OpenDataLoader PDF 转换时，`PATH` 中需要 Java 11+
- 启用 session 登录时需要 `FASTAPI_SESSION_SECRET`
- provider credential 存入数据库时需要稳定的 `TOKEN_ENCRYPTION_KEY`

### 启动 API

```bash
pip install -r requirements.txt
python -m ai_actuarial api --host 127.0.0.1 --port 8000
```

### 启动 React UI

```bash
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。Vite 会把 `/api/*` 代理到 `http://127.0.0.1:8000`。

如果 `http://127.0.0.1:5173/` 返回 `404`，通常说明另一个 Node/Vite 进程占用了该端口。请在本仓库目录运行 `npm run dev`，并使用 Vite 输出的地址。

## 核心配置

当前有四类配置来源：

- `config/sites.yaml`：非密钥运行配置，包括站点、路径、AI routing、RAG、搜索、schedule、feature switches 和 web-listening materialized 配置。
- `config/markdown_conversion.yaml`：Markdown 转换工具顺序、格式路由、付费工具开关和 tuning。
- 数据库加密 credential：provider API key、base URL 等，从 Settings 管理。
- `.env` / 进程环境：部署密钥和生产级显式覆盖项。

不要把 provider API key 提交到 YAML，也不要长期放在 `.env`。建议从 Settings 保存为加密 credential，再在 `sites.yaml` 中绑定稳定 credential id，例如 `openai:llm:instance:default`。

重要变量：

- `FASTAPI_SESSION_SECRET`：session 登录必需。
- `TOKEN_ENCRYPTION_KEY`：解密数据库 provider credential 必需，必须保持稳定。
- `BOOTSTRAP_ADMIN_TOKEN`：可选的本地/admin 恢复 token。
- `FASTAPI_CORS_ORIGINS`：部署后允许访问 API 的浏览器 origin。
- `TRUST_PROXY`：只有当 API 只能被可信反向代理直连时才设为 `true`。
- `CONFIG_WRITE_AUTH_TOKEN`、`LOGS_READ_AUTH_TOKEN`、`FILE_DELETION_AUTH_TOKEN`：兼容 token，除非明确需要 `X-Auth-Token`，否则可不启用。

鉴权、全局日志、文件删除、限流、CSRF、错误详情和安全响应头等功能开关在 `config/sites.yaml -> features` 中，也可以从 Settings 修改。如果进程环境变量设置了同名部署覆盖，Settings 会将该值标记为 locked。

SQLite 路径以 `config/sites.yaml -> paths.db` 为准；`DB_PATH` 只是 YAML 路径缺失时的 fallback。

## 鉴权和权限

- `features.require_auth=true`：用户必须通过 session 或 token 登录。
- `features.require_auth=false`：访客只读。
- 运行任务、管理 schedule、写 settings、下载、删除文件、写站点配置都需要对应权限。
- `operator` 可以管理站点。`files.import.server` 只保留给 admin-only 的服务器文件系统辅助能力，不属于普通浏览器上传流程。
- 本地 admin 恢复 token 可通过 `BOOTSTRAP_ADMIN_TOKEN` 配置；真实 token 不要提交到仓库。

## 文件导入和任务

普通用户导入文件时，应在浏览器中选择文件或文件夹。前端会从用户自己的机器 staging upload batch，服务端不会读取用户电脑上的任意路径。

`type=file` collection run 必须带 `upload_batch_id`。只传 `directory_path` 的请求会被拒绝；不要把任意服务器路径导入写成普通 operator 工作流。

在 **Tasks -> Configured Tasks** 中，`parameters` 必须是合法 JSON。支持的 interval 包括 `daily`、`weekly`、`daily at 02:00`、`every 6 hours`、`every 30 minutes`。

常见任务参数：

```json
{}
```

只对某个已配置站点做 catalog：

```json
{
  "site": "Society of Actuaries (SOA)",
  "batch": 50,
  "max_chars": 12000,
  "retry_errors": false
}
```

运行某个已配置站点的爬取：

```json
{
  "site": "Casualty Actuarial Society (CAS)"
}
```

运行已完成 UTC ISO 周的 weekly summary：

```json
{
  "relative_period": "previous_week",
  "max_files": 500
}
```

## Agentic RAG

Agentic RAG 是建立在现有 catalog、chunks、知识库注册表和 Chat 产品之上的结构化证据层。它不替代标准向量 RAG；当前两种模式并存：

| 模式 | 入口 | 数据依赖 | 主要约束 |
| --- | --- | --- | --- |
| 标准 RAG | `/api/chat/query` 默认 `rag_mode` | 向量索引和检索 chunk | 允许多知识库和直接选中文档上下文 |
| Agentic RAG Chat | `/api/chat/query` 且 `rag_mode="agentic"` | 一个 ready KB manifest | 必须且只能选择一个 ready KB；不能混用直接文档上下文 |
| Agentic read APIs | `/api/agentic-rag/*` | KB manifest 或允许的显式 `output_dir` | 返回确定性工具结果/答案 |

知识库带有 `manifest_profile`：

| Profile | 主要 artifact | 适用场景 |
| --- | --- | --- |
| `general` | `doc_catalog.jsonl`、`sections.jsonl`、`ready_data_manifest.json` | 通用研究/内部文档 |
| `regulation` | 通用 artifact，加 aliases、summaries、structured sections、relations | 法规、标准、合规文档 |
| `formula` | regulation artifact，加 formula cards、structured tables、calculation terms | 精算公式和计算密集型文档 |

CLI 构建 ready-data 清单：

```bash
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile formula --validate
```

运行确定性 eval smoke：

```bash
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

更多 profile、API、UI 行为、存储路径和 eval 命令见 [Agentic RAG Guide](docs/guides/AGENTIC_RAG.md)。

## 安全状态

- 生产安全值应通过服务器本地环境变量配置，见 [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md)。
- 限流由 FastAPI middleware 实现，见 [Rate Limiting](docs/rate-limit-config.md)。
- Chat/RAG 选中文档上下文会被限制大小，并在进入 LLM 前标记为不可信。
- 公共 URL 抓取会检查 unsafe scheme、私有/保留 IP、重定向目标变化和 DNS/IP 漂移。
- 登录/注册页对限流和系统错误显示友好提示，不暴露内部异常。

维护中的安全清单见 [Security Policy](SECURITY.md)。

## 项目结构

```text
AI_actuarial_inforsearch/
├─ ai_actuarial/           # Python 核心包和 FastAPI API
├─ client/                 # React + TypeScript 前端
├─ config/                 # YAML 配置
├─ data/                   # 本地运行数据、下载文件、日志和 SQLite DB
├─ doc_to_md/              # 文档转 Markdown 引擎
├─ docs/                   # 当前文档和历史归档
├─ scripts/                # 维护脚本
├─ tests/                  # Python 和源码级测试
├─ vite.config.ts          # Vite 开发服务器和构建配置
├─ package.json            # Node 依赖和脚本
└─ requirements.txt        # Python 运行依赖
```

## 诊断

诊断 secret/credential 状态，且不输出明文密钥：

```bash
python scripts/diagnose_secrets_runtime.py --json
```

生成 `TOKEN_ENCRYPTION_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 构建和测试

```bash
npm run build
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_auth_react_source.py tests/test_fastapi_chat_endpoints.py tests/test_tasks_react_source.py -q
python -m pytest tests/test_markdown_conversion_config.py tests/test_web_listening_rule.py tests/test_weekly_updates.py tests/test_task_runtime_full_pipeline.py -q
python -m pytest tests/agentic_rag/test_eval.py tests/agentic_rag/test_planner_agentic_loop.py -q
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

## 更多说明

- [Documentation Index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API Migration Status](docs/API_MIGRATION_STATUS.md)
- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [AI Model Catalog](docs/guides/AI_MODEL_CATALOG.md)
- [Agentic RAG Guide](docs/guides/AGENTIC_RAG.md)
- [Rate Limiting](docs/rate-limit-config.md)
- [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)
- [历史文档归档](docs/archive/README.md)

## 输出文件

- 下载文件：`data/files/`
- SQLite 数据库：以 `config/sites.yaml -> paths.db` 为准，缺省 fallback 为 `data/index.db`
- Agentic ready data：默认位于 DB 邻近的 `agentic_ready_data/` 目录
- 应用日志：`data/app.log`
- 任务日志：`data/task_logs/*.log`
