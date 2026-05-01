# AI Actuarial Info Search

[English](README.md) | [简体中文](README.zh-CN.md)

AI Actuarial Info Search 用于帮助精算和保险团队发现、下载、编目、转换并问答检索 AI 相关文档，数据来源可以是公开机构网站，也可以是本地文件。

当前正式产品栈是 **FastAPI + React**：

| 产品面 | 技术栈 | 本地地址 | 角色 |
| --- | --- | --- | --- |
| 产品 API | Python + FastAPI | `http://127.0.0.1:8000/api/*` | 产品 API 唯一权威入口 |
| 产品 UI | React 19 + TypeScript + Vite | `http://127.0.0.1:5173` | 当前维护的 Web 界面 |

旧的服务端 HTML 运行时和 Replit workflow 文件已经退出当前项目结构。React 页面只应调用原生 FastAPI 端点。

## 功能

- 爬取精算和保险组织网站。
- 通过 Brave、SerpAPI 等搜索服务扩展发现范围。
- 下载 PDF、Word、PowerPoint、Excel 和 HTML 来源。
- 使用 SHA256 去重。
- 增量编目文件，生成摘要、关键词和分类。
- 使用本地或 API 引擎将文档转换为 Markdown。
- 管理 RAG 知识库、chunk profile 和索引任务。
- 基于检索增强生成和文档对话。
- 配置 OpenAI、DeepSeek、Mistral 及兼容 provider。
- 通过 React UI 管理 dashboard、database、tasks、settings、knowledge、chat、logs、users 和 file detail 工作流。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- 可选 AI/search provider API key，放在环境变量或数据库加密 credential 中
- 如果 provider credential 存入数据库，需要稳定的 `TOKEN_ENCRYPTION_KEY`
- 如果启用邮箱/session 登录，需要 `FASTAPI_SESSION_SECRET`

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

## 鉴权

- `REQUIRE_AUTH=true`：用户必须通过 session 或 token 登录。
- `REQUIRE_AUTH=false`：访客只读。
- `FASTAPI_SESSION_COOKIE_SECURE=true`：将 session cookie 标记为仅 HTTPS 可用；如果省略，在 `FASTAPI_ENV=production` 且 `REQUIRE_AUTH=true` 时默认启用。
- 运行任务、管理 schedule、写 settings、下载和删除文件都需要对应 token 权限。
- 本地 admin token 可通过 `BOOTSTRAP_ADMIN_TOKEN` 配置；真实 token 不要提交到仓库。

## Scheduled Task Parameters 怎么填

在 **Tasks -> Configured Tasks** 中，`parameters` 必须是合法 JSON。Schedule 触发时，这个对象会传给原生后台任务。

常见示例：

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

导入本地文件：

```json
{
  "directory_path": "C:/path/to/files",
  "recursive": true,
  "extensions": ["pdf", "docx"],
  "target_subdir": "scheduled-imports"
}
```

抓取指定 URL：

```json
{
  "urls": [
    "https://example.org/report.pdf"
  ]
}
```

支持的 interval 包括 `daily`、`weekly`、`daily at 02:00`、`every 6 hours`、`every 30 minutes`。

## 项目结构

```text
AI_actuarial_inforsearch/
├─ ai_actuarial/           # Python 核心包和 FastAPI API
├─ client/                 # React + TypeScript 前端
├─ config/                 # YAML 配置
├─ data/                   # 本地运行数据、下载文件、日志和 SQLite DB
├─ doc_to_md/              # 文档转 Markdown 引擎
├─ docs/                   # 架构、指南、计划和报告
├─ scripts/                # 维护脚本
├─ tests/                  # Python 和源码级测试
├─ vite.config.ts          # Vite 开发服务器和构建配置
├─ package.json            # Node 依赖和脚本
└─ requirements.txt        # Python 运行依赖
```

## 配置

主要结构化配置在 `config/sites.yaml`。密钥应放在 `.env`、进程环境变量或数据库加密 credential 中。
运行时使用的 provider API key 建议保存为数据库中的加密 credential；`sites.yaml` 只绑定 AI 功能使用的 provider/model，以及可选 credential id，例如 `openai:llm:instance:default`。

重要变量：

- `TOKEN_ENCRYPTION_KEY`：数据库中保存 provider credential 时必需。
- `FASTAPI_SESSION_SECRET`：session 登录必需。
- `FASTAPI_SESSION_COOKIE_SECURE`：HTTPS 部署设为 `true`；`FASTAPI_ENV=production` 且启用鉴权时会默认开启。
- `BOOTSTRAP_ADMIN_TOKEN`：可选的本地/admin bootstrap token。
- `REQUIRE_AUTH`：设为 `true` 后启用完整鉴权。
- `BRAVE_API_KEY`、`SERPAPI_API_KEY`、`SERPER_API_KEY`、`TAVILY_API_KEY`：可选搜索 key。
- `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`MISTRAL_API_KEY`、`SILICONFLOW_API_KEY`：可选 AI/转换 key。

生成 `TOKEN_ENCRYPTION_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

诊断当前 embedding runtime，且不输出明文密钥：

```bash
python scripts/diagnose_embedding_runtime.py --config config/sites.yaml --json
```

更多说明：

- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [RAG Embeddings Runtime](docs/guides/RAG_EMBEDDINGS_RUNTIME.md)

## 构建和测试

```bash
npm run build
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
```

## 部署

Docker 和 Caddy 配置已经按 FastAPI + React 对齐：

- API container：FastAPI，端口 `5000`
- Frontend container：Vite dev/preview，端口 `5173`
- Caddy：`/api/*` 转发到 API，其余路由转发到 React

更多说明：

- [Architecture](docs/ARCHITECTURE.md)
- [API Migration Status](docs/API_MIGRATION_STATUS.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)

## 输出文件

- 下载文件：`data/files/`
- SQLite 数据库：`data/index.db`
- Catalog 输出：`data/catalog.jsonl`、`data/catalog.md`
- 更新日志：`data/updates/`
- 应用日志：`data/app.log`
- 任务日志：`data/task_logs/*.log`
