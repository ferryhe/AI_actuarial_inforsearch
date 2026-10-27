# 本机采集与双端发布运行指南

本指南对应跟踪代码 `ai_actuarial.local_collection_runtime`。CLI 默认输出 JSON，`--json` 可显式声明机器读取。所有命令均从仓库根目录运行；本地私有配置默认路径为 `reports/local-automation-state/config.local.json`，共享示例为 [local-runtime-config.example.json](local-runtime-config.example.json)。不要把 DSN、密钥或登录态复制到示例文件。

## 准备与只读检查

配置文件的 `schema_version` 为 1，需提供 `data_root`、`state_root`、`hub_connection_file` 和 `targets`。Hub 连接文件仅允许保存在本地私有目录。`targets.china.host` 与 `targets.overseas.host` 使用已授权的 SSH 主机别名；可选 `sudo: true` 为 Docker 命令添加 `sudo -n`（现有中国主机需要），`container` 默认为 `ai-api`，`timeout_seconds` 默认为 21600。每次 SSH 调用使用 `BatchMode=yes`、`ServerAliveInterval=30` 和 `ServerAliveCountMax=3`：长时间无输出的原生任务期间每 30 秒发送一次 SSH keepalive，若连续 3 次未获响应，约 90 秒后按现有失败路径报错；六小时 subprocess 超时保持不变。Keepalive 只维持/检测连接，不确认目标写入；Swiss60 现场的确切网络掉点未被证明。只有实际 worker 返回的逐项 ACK 以及 Ready 回读会更新成功状态，SQL/索引探针不能替代 ACK。登录后的本机 Codex CLI 以 Luna/high 运行模型补全；也可用 `codex_executable` 指向已认证可执行文件。

```powershell
python -m ai_actuarial.local_collection_runtime preflight --config reports/local-automation-state/config.local.json --json
python -m ai_actuarial.local_collection_runtime plan --date 2026-10-25 --json
python -m ai_actuarial.local_collection_runtime preflight --config reports/local-automation-state/config.local.json --remote --json
```

`preflight` 不运行采集或写入目标，会读取 Hub schema/status、AI backlog 和当前目标 profile/capacity。若 schema 显示待迁移，先完成独立 review，再显式运行 additive v3 migration：

```powershell
python -m ai_actuarial.local_collection_runtime apply-hub-schema --config reports/local-automation-state/config.local.json --json
```

它为新 live capture 记录来源类型，不生成虚假的 SQLite v16 snapshot，也不改写历史不可变 snapshot。历史 annotations/exclusions 由迁移前 shape check 保护。

目标文件的 `source_site` 原样保留来源提供的名称：历史 v16 记录可能是机构显示名称（例如 `Actuarial Association of Europe (AAE)`），新采集记录使用注册表 `site_id`。两者都不是需要统一成 slug 的外键；未知历史来源保持 `null`，不得从 URL 推断。

## 小流量单站试跑

先做只读下载/候选预览，再对同一站运行至多一篇的真实单站试跑。`--article-limit 1` 限制本次新增或重试的模型富信息工作。`--exact-url` 用于复核已知来源 URL；抓取仍经过站点 host、include/exclude、robots 与内容验证。

```powershell
python -m ai_actuarial.local_collection_runtime run-site --site soa-ai-bulletin-focused --date 2026-10-25 --preview --article-limit 1 --json
python -m ai_actuarial.local_collection_runtime run-site --site soa-ai-bulletin-focused --date 2026-10-25 --article-limit 1 --json
```

实现/回归测试也覆盖 IAA 当前论文和 CAS secondary-AI PDF，可按相同入口做低流量验收：

```powershell
python -m ai_actuarial.local_collection_runtime run-site --site iaa --date 2026-10-25 --exact-url https://actuaries.org/app/uploads/2026/10/AITF_Professional_Considerations_Paper_Final_Approved.pdf --source-page-url https://actuaries.org/paper/professional-considerations-for-actuaries-interacting-with-artificial-intelligence/ --article-limit 1 --preview --json
python -m ai_actuarial.local_collection_runtime run-site --site cas --date 2026-10-25 --exact-url https://forum.casact.org/article/74931-nonlife-insurance-risk-classification-using-categorical-embedding.pdf --article-limit 1 --preview --json
```

预览会执行有界来源 GET 并可保存本地状态/CAS，但不写 Hub、运行模型、改目标数据库或写每日最终回执。非预览单站运行才执行 Hub、metadata、两端 Storage/native KB/Ready 和 v2 回执写入。默认每站每轮最多 30 个 HTTP 请求且请求间隔至少 0.5 秒（瑞士站的 60 请求例外见下文）；运行状态、列表游标、失败重试、原文件 CAS 与模型幂等目录均在本地 `state_root`/`data_root`。

`run-site --exact-url` 只捕获经过本站规则验证的指定 URL，并保留既有同站重定向处理；不会给精确重放注入普通站点发现种子，也不会改变普通发现游标。

`run-site --preview` 返回码为 0（已观察阶段成功，目标 Ready 状态保持 unknown）、2（观察到失败）或 3（观察到部分完成）；预览不把未执行的下游阶段当成失败或成功。实际 `run-site` 仍以最终回执区分成功与非成功，分别返回 0 和 2。

默认 `--request-limit 30`，其他站点最多显式设到 30。瑞士站可将单次 HTTP 上限设到 60；抓取仍按原 0.6 秒站点间隔，限额时保存 frontier/cursor，不能发出第 61 个请求。对同一批未完成文章，每次最多做 24 篇既有 Hub 复用/目标重试，再独立选择最多 8 篇需要模型补全的文章；本地文章游标会轮转，避免持续失败的旧重试挡住后续新文献。回执在 `downloaded.request_budget` 保存 `used`、`cap`、`paused` 和 `frontier_remaining`；`new_versions`/`enriched.pending_count` 及离线日报显示本站未完成文章中本轮未选中的数量；`--exact-url` 仍显示本站积压减去本次精确 URL 实际选中数，不会处理其他文章。该计数是调度提示：不包含本轮已选中但仍失败、等待目标确认或 Ready 的文章，也不能单独证明整个队列已清空；需结合阶段错误和 target ack/Ready 状态判断。纯预算暂停仍为 `partial`，但不占失败研究名额；伴随的真实来源、模型或目标错误仍按各自失败阶段报告。

本次修复使用了以下经过核验的站点入口和旧 frontier 修补：CIA 从 `/publications/` 与现有 WordPress REST 队列发现资料，只有公开 `dl_file.php` 同时带 `p` 和 `fid` 时才视作附件，并继续拒绝 `/private-files/`；CCA 使用 `/professional-resources/papers` 与 `/professional-resources/technical-resource-library-main`；法国站使用当前 `/se-documenter/memoires/memoires-d-actuariat-4651` 和 `/se-documenter/supports-des-presentations-39`，再识别真实 `doc_id > 1` 的公开文件链接。法国已保存前沿会保留已消费前缀和其他待处理资料，只移除已观察到的失效 memoir 路径；当前 memoir 列表若尚未成功访问，会在一次性 v2 修补中先于待处理附件检查，之后仍按原附件优先顺序轮转。兼容修补不重置历史已存文章。

```powershell
python -m ai_actuarial.local_collection_runtime run-site --site cia-research-publications --date 2026-10-27 --article-limit 1 --preview --json
python -m ai_actuarial.local_collection_runtime run-site --site cca --date 2026-10-27 --article-limit 1 --preview --json
python -m ai_actuarial.local_collection_runtime run-site --site france --date 2026-10-27 --article-limit 1 --preview --json
python -m ai_actuarial.local_collection_runtime run-site --site swiss-association-of-actuaries --date 2026-10-27 --request-limit 60 --article-limit 8 --preview --json
```

移除 `--preview` 才会执行完整 Hub、模型、目标和回执流程。`--request-limit 60` 仅对 `swiss-association-of-actuaries` 有效；其他站点传入大于 30 的值会失败。

## 日常与目标 backlog

```powershell
python -m ai_actuarial.local_collection_runtime run-daily --date 2026-10-25 --preview --json
python -m ai_actuarial.local_collection_runtime run-daily --date 2026-10-25 --json
python -m ai_actuarial.local_collection_runtime reconcile-targets --limit 10 --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
```

每日计划为六项 baseline、最多两个不同失败重试；hold 保留位置但不执行。每次目标写入按 URL/Hub version/content fingerprint 单独确认；中国 AI 与 all 两个现有 KB 使用各自已配置 profile，海外只更新 AI KB。失败的文章 acknowledgement、chunk/embed/binding 与 Ready 阶段可单独续跑，目标之间不互相代替。任何 AI 类别都可进入 AI serving bucket；完整顺序类别和来源 primary category 留在 bilingual payload 的 Hub evidence 中。目标容量使用原生 80% gate。旧全量替换脚本、清空/重建旧目录和向量复制不属于本运行入口。

Chunk/embed 恢复会针对当前 URL 幂等重跑原生 chunk generation，并把该任务返回的确切 `chunk_set_id` 列表与当前 KB `embedding_identity_key` 传给 embedding generation；不会按 URL/profile 在历史 ready sets 中猜选。该阶段失败时 pending URL 保留，重试完成 chunk、embedding 和 binding 后才继续完整 KB index 与 Ready。

`run-daily` 不是 Scheduler。日报 09:00 触发和任务开关继续沿用现有 automation owner；本地运行 CLI 不迁移或新建调度。首次真实写入和 automation 启用须由独立 review/验收流程批准。
