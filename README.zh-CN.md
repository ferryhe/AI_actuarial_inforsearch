# AI Actuarial Info Search

[English](README.md) | [简体中文](README.zh-CN.md)

AI Actuarial Info Search 用于帮助精算和保险团队发现、下载、编目、转换并问答检索 AI 相关文档，数据来源可以是公开机构网站，也可以是浏览器选择的本地文件。

当前正式产品栈是 **FastAPI + React**：

| 产品面 | 技术栈 | 本地地址 | 角色 |
| --- | --- | --- | --- |
| 产品 API | Python + FastAPI | `http://127.0.0.1:8000/api/*` | 产品 API 唯一权威入口 |
| 产品 UI | React 19 + TypeScript + Vite | `http://127.0.0.1:5173` | 当前维护的 Web 界面 |

旧的服务端 HTML 运行时和 Replit workflow 文件已经退出当前项目结构。React 页面只应调用原生 FastAPI 端点。

## 当前状态

2026 安全/RBAC rollout 已经合入 `main`：

- 文件导入面向浏览器选择的本地文件/文件夹，使用 upload batch；当前 `type=file` 任务必须带 `upload_batch_id`，不能直接读取任意服务器 `directory_path`。
- 公共 URL 抓取已加入 SSRF 防护、重定向复验和不安全地址拒绝。
- 权限已拆分 `sites.write`、`schedule.write`、`tasks.run` 和 admin-only 服务器文件系统辅助权限。
- Chat/RAG 文档对比最多选择 3 个文档来源，限制上下文大小，返回裁剪提示，并在 prompt 中把检索/文档上下文标为不可信。
- 登录/注册在 session mutation 前按 IP 限流，前端对 429 和 5xx 展示友好提示。
- 本 README 更新时没有打开的安全 rollout PR；PR #118-#122 均已合并。

## 功能

- 爬取精算和保险组织网站。
- 通过 Brave、SerpAPI 等搜索服务扩展发现范围。
- 下载 PDF、Word、PowerPoint、Excel 和 HTML 来源。
- 通过浏览器选择并上传本地文件/文件夹。
- 使用 SHA256 去重。
- 增量编目文件，生成摘要、关键词和分类。
- 使用本地或 API 引擎将文档转换为 Markdown。
- 管理 RAG 知识库、chunk profile 和索引任务。
- 基于检索增强生成和文档对话；单次文档对比最多 3 个选择来源。
- 在 Settings 中配置 AI/search provider credential。
- 通过 React UI 管理 dashboard、database、tasks、settings、knowledge、chat、logs、users 和 file detail 工作流。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- 使用 OpenDataLoader PDF 转换时，需要 PATH 中有 Java 11+
- 如果启用邮箱/session 登录，需要 `FASTAPI_SESSION_SECRET`
- 如果 provider credential 存入数据库，需要稳定的 `TOKEN_ENCRYPTION_KEY`
- Provider credential 建议从 Settings 保存为数据库加密 credential

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

## 配置

主要配置来源有三类：

- `config/sites.yaml`：非密钥运行配置，包括 AI routing、路径、RAG、搜索、scheduled tasks 和 `features`。
- 数据库加密 credential：provider API key、base URL 等，从 Settings 管理。
- `.env`：进程密钥和部署级覆盖项。

不要把 provider API key 提交到 YAML，也不要长期放在 `.env`。建议从 Settings 保存为加密 credential，再在 `sites.yaml` 中绑定稳定 credential id，例如 `openai:llm:instance:default`。

重要变量：

- `TOKEN_ENCRYPTION_KEY`：数据库中保存 provider credential 时必需。
- `FASTAPI_SESSION_SECRET`：session 登录必需。
- `FASTAPI_SESSION_COOKIE_SECURE`：HTTPS 部署设为 `true`；如果省略，在生产环境且启用鉴权时默认开启。
- `BOOTSTRAP_ADMIN_TOKEN`：可选的本地/admin bootstrap token。
- `FASTAPI_CORS_ORIGINS`：部署后允许访问 API 的浏览器 origin。
- `TRUST_PROXY`：只有当 API 只能被可信反向代理直连时才设为 `true`。
- `CONFIG_WRITE_AUTH_TOKEN`、`LOGS_READ_AUTH_TOKEN`、`FILE_DELETION_AUTH_TOKEN`：兼容 token，除非明确需要 `X-Auth-Token`，否则可不启用。

鉴权、全局日志、文件删除、限流、CSRF、错误详情和安全响应头等功能开关在 `config/sites.yaml -> features` 中，也可以从 Settings 修改。如果进程环境变量设置了同名部署覆盖，Settings 会将该值标记为 locked。

## 鉴权和权限

- `features.require_auth=true`：用户必须通过 session 或 token 登录。
- `features.require_auth=false`：访客只读。
- 运行任务、管理 schedule、写 settings、下载和删除文件、写站点配置都需要相应权限。
- `operator` 可以管理站点。`files.import.server` 只保留给 admin-only 的服务器文件系统辅助能力，不属于普通浏览器上传流程。
- 本地 admin 恢复 token 可通过 `BOOTSTRAP_ADMIN_TOKEN` 配置；真实 token 不要提交到仓库。

## 文件导入和任务

普通用户导入文件时，应在浏览器中选择文件或文件夹。前端会从用户自己的机器 staging upload batch，服务端不会读取用户电脑上的任意路径。

`type=file` collection run 必须带 `upload_batch_id`。只传 `directory_path` 的请求会被拒绝；不要把任意服务器路径导入写成普通 operator 工作流。

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

支持的 interval 包括 `daily`、`weekly`、`daily at 02:00`、`every 6 hours`、`every 30 minutes`。

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
├─ docs/                   # 架构、指南、历史计划和报告
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
```

## 更多说明

- [Documentation Index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API Migration Status](docs/API_MIGRATION_STATUS.md)
- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [AI Model Catalog](docs/guides/AI_MODEL_CATALOG.md)
- [Rate Limiting](docs/rate-limit-config.md)
- [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)

## 输出文件

- 下载文件：`data/files/`
- SQLite 数据库：以 `config/sites.yaml -> paths.db` 为准，缺省 fallback 为 `data/index.db`
- Catalog 输出：`data/catalog.jsonl`、`data/catalog.md`
- 更新日志：`data/updates/`
- 应用日志：`data/app.log`
- 任务日志：`data/task_logs/*.log`
