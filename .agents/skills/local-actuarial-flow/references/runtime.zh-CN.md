# 本机采集与双端发布运行指南

本指南对应跟踪代码 `ai_actuarial.local_collection_runtime`。CLI 默认输出 JSON，`--json` 可显式声明机器读取。离线日报默认 JSON；`--format markdown` 可输出精简中文摘要。所有命令均从仓库根目录运行；本地私有配置默认路径为 `reports/local-automation-state/config.local.json`，共享示例为 [local-runtime-config.example.json](local-runtime-config.example.json)。不要把 DSN、密钥或登录态复制到示例文件。

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

PDF 转换允许 pypdf 可用空密码解锁的公开文件；确实需要用户密码的文件仍记录为转换失败。页数和提取 Markdown 大小继续受运行时上限约束。

```powershell
python -m ai_actuarial.local_collection_runtime run-site --site iaa --date 2026-10-25 --exact-url https://actuaries.org/app/uploads/2026/10/AITF_Professional_Considerations_Paper_Final_Approved.pdf --source-page-url https://actuaries.org/paper/professional-considerations-for-actuaries-interacting-with-artificial-intelligence/ --article-limit 1 --preview --json
python -m ai_actuarial.local_collection_runtime run-site --site cas --date 2026-10-25 --exact-url https://forum.casact.org/article/74931-nonlife-insurance-risk-classification-using-categorical-embedding.pdf --article-limit 1 --preview --json
```

预览会执行有界来源 GET 并可保存本地状态/CAS，但不写 Hub、运行模型、改目标数据库或写每日最终回执。非预览单站运行才执行 Hub、metadata、两端 Storage/native KB/Ready 和 v2 回执写入。默认每站每轮最多 30 个 HTTP 请求且请求间隔至少 0.5 秒（瑞士站的 60 请求例外见下文）；运行状态、列表游标、失败重试、原文件 CAS 与模型幂等目录均在本地 `state_root`/`data_root`。

`run-site --exact-url` 只捕获经过本站规则验证的指定 URL，并保留既有同站重定向处理；不会给精确重放注入普通站点发现种子，也不会改变普通发现游标。

`run-site --preview` 返回码为 0（已观察阶段成功，目标 Ready 状态保持 unknown）、2（观察到失败）或 3（观察到部分完成）；预览不把未执行的下游阶段当成失败或成功。实际 `run-site` 仍以最终回执区分成功与非成功，分别返回 0 和 2。

默认 `--request-limit 30`，其他站点最多显式设到 30。瑞士站可将单次 HTTP 上限设到 60；抓取仍按原 0.6 秒站点间隔，限额时保存 frontier/cursor，不能发出第 61 个请求。对同一批未完成文章，每次最多做 24 篇既有 Hub 复用/目标重试，再独立选择最多 8 篇需要模型补全的文章；本地文章游标会轮转，避免持续失败的旧重试挡住后续新文献。回执在 `downloaded.request_budget` 保存 `used`、`cap`、`paused` 和 `frontier_remaining`；`new_versions`/`enriched.pending_count` 及离线日报显示本站未完成文章中本轮未选中的数量；`--exact-url` 仍显示本站积压减去本次精确 URL 实际选中数，不会处理其他文章。该计数是调度提示：不包含本轮已选中但仍失败、等待目标确认或 Ready 的文章，也不能单独证明整个队列已清空；需结合阶段错误和 target ack/Ready 状态判断。纯预算暂停仍为 `partial`，但不占失败研究名额；伴随的真实来源、模型或目标错误仍按各自失败阶段报告。

本次修复使用了以下经过核验的站点入口和旧 frontier 修补：CIA 从 `/publications/` 与现有 WordPress REST 队列发现资料，只有公开 `dl_file.php` 同时带 `p` 和 `fid` 时才视作附件，并继续拒绝 `/private-files/`；CCA 使用 `/professional-resources/papers` 与 `/professional-resources/technical-resource-library-main`；SOA 删除已确认返回 404 的 `/research/soa-research/` seed，并在下一次普通发现时从已保存队列和重试队列移除该地址；法国站使用当前 `/se-documenter/memoires/memoires-d-actuariat-4651` 和 `/se-documenter/supports-des-presentations-39`，再识别真实 `doc_id > 1` 的公开文件链接。法国已保存前沿会保留已消费前缀和其他待处理资料，只移除已观察到的失效 memoir 路径；当前 memoir 列表若尚未成功访问，会在一次性 v2 修补中先于待处理附件检查，之后仍按原附件优先顺序轮转。兼容修补不重置历史已存文章。

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
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --format markdown
```

每日计划为六项 baseline、最多两个不同失败重试；hold 保留位置但不执行。每次目标写入按 URL/Hub version/content fingerprint 单独确认；中国 AI 与 all 两个现有 KB 使用各自已配置 profile，海外只更新 AI KB。失败的文章 acknowledgement、chunk/embed/binding 与 Ready 阶段可单独续跑，目标之间不互相代替。只有有序 `categories[0].key == "AI"` 的 Hub 版本能进入 AI serving bucket；第二至第四类及其证据继续原样保存在 Hub enrichment 中。实时、缓存、历史 backlog、pending 重试和 target worker 都复核同一首类规则。目标容量使用原生 80% gate。旧全量替换脚本、清空/重建旧目录和向量复制不属于本运行入口。

`run-daily` JSON 带整轮 `elapsed_seconds`，每站回执另存站点耗时和采集漏斗。要让离线报告区分“已运行但回执缺失”，将当次 stdout 以 UTF-8 JSON 保存，并用同日期参数传给 helper：

```powershell
$runLines = & python -m ai_actuarial.local_collection_runtime run-daily --date 2026-10-29 --json
[System.IO.File]::WriteAllText("reports/local-automation-state/daily/2026-10-29-run-daily.json", ($runLines -join "`n"), [System.Text.UTF8Encoding]::new($false))
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-29 --receipts reports/local-automation-state/receipts --runtime-output reports/local-automation-state/daily/2026-10-29-run-daily.json --format markdown
```

`--runtime-output` 仅为日报补充执行、异常和总耗时证据，不改变回执或 case ledger。没有传运行输出时，无回执不能证明未运行；计划与实际收据站点仍分开显示。报告中的观察数会累加同日重试，唯一数按回执中的精确身份集合去重。旧回执没有的请求、页面、文件类型、转换或分类指标显示“未记录”，不能填成零。AI 首类仅读取运行时明确记录的首类候选，不能从旧版任意类别 AI 候选或日期推断。

### 独立来源故障探索（web-listening 3.3.0）

来源站点失败且需要单独复现公开页面或附件时，可运行隔离安装的 `web-listening 3.3.0`。该版本要求 Python 3.12；从仓库私有目录选择这个明确的可执行文件，不调用全局 `web-listening` 0.1.0，不自动安装或升级：

```powershell
$exploreCli = 'C:\Project\AI_actuarial_inforsearch\reports\local-automation-tools\web-listening-3.3.0\venv\Scripts\web-listening.exe'
& $exploreCli list-exploration-tools --json
& $exploreCli read-page --url https://www.e-caa.org.cn/ --method http --output-dir reports/readable-local-flow/exploration/caa-http --allowed-domain www.e-caa.org.cn --timeout-seconds 30 --max-http-bytes 2097152 --json
& $exploreCli read-page --url https://www.e-caa.org.cn/ --method browser --browser-channel chrome --output-dir reports/readable-local-flow/exploration/caa-browser --allowed-domain www.e-caa.org.cn --max-requests 30 --max-dom-bytes 2097152 --max-http-bytes 2097152 --json
& $exploreCli download-file --url https://example.org/report.pdf --output-dir reports/readable-local-flow/exploration/pdf --allowed-domain example.org --max-bytes 41943040 --json
& $exploreCli extract-pdf --input reports/readable-local-flow/exploration/pdf/report.pdf --output-dir reports/readable-local-flow/exploration/pdf-text --source-url https://example.org/report.pdf --json
& $exploreCli collect --urls-file reports/readable-local-flow/exploration/urls.txt --kind page --method http --output-dir reports/readable-local-flow/exploration/collect --allowed-domain www.e-caa.org.cn --json
```

`read-page` 支持 `http` 或 `browser`；HTTP 示例是一条页面读取，用超时和响应字节上限控制；`--max-requests` 只限制浏览器路线，浏览器页面资源也占预算。只有静态 HTTP 无法呈现链接时才使用浏览器。`download-file`/`collect` 输出及 `extract-pdf` 文本都是本地探索证据。探索 CLI 不继承 formal AccessGateway 控制，也不调用本仓库 production bounded crawler；production crawler 自有站点 host/path 白名单和每站 30 HTTP 请求预算。探索命令只用于手动单来源故障调查，不批量执行，也不写 Hub、目标、日回执或 AI 候选。浏览器结果中的 attempt 记录可能包含未实际发送的拦截请求；不要把 attempt 行数当作 HTTP 请求数。探索结果和采集成功、Hub 新增、AI 首类发布统计完全分开。

### 发布日期投影与目标清理

目标 `files.published_time` 只从已验证的 `date_facts.publication_date.value` 投影。原始 ISO 精度保持为 `YYYY`、`YYYY-MM` 或 `YYYY-MM-DD`；缺失/unknown 对新记录保持 `null`，不得用 revision、document-version、事件日期、HTTP Last-Modified 或抓取日期补值。常规发布对日期或 enrichment-only 更新会重建完整索引与 Ready；原件 bytes、Markdown 和 KB membership 未变化时不重跑 chunk/embed。已有语言包、summary、keywords 和 `hub_binding` 等额外字段会保留；旧目标若已有发布日期而 Hub 发布日期未知，则保留目标值并报告为 `legacy_preserved_unverified`。

只对已存在的保留文件做批量类别/日期回填时，使用下面的独立 metadata-only 入口。它逐条核对目标 URL/raw SHA、目标现存 Markdown 与 Hub Markdown binding、AI 首类及有序分类/日期证据、目标既有 `published_time` 和完整 KB membership。它不会读取/传输原件，不创建或重分类文件，也不执行 chunk、embedding、索引或 Ready。已变更的 KB 会写入可恢复的 pending index-refresh ledger；随后同一目标的 `cleanup-targets --apply` 会合并这批 KB 和清理涉及的 KB，在全部回填及清理完成后每个 KB 刷新一次 index/Ready。每份 manifest 最多 100 条，按目标与批次拆开，dry-run 默认开启。

```powershell
python -m ai_actuarial.local_collection_runtime backfill-target-metadata --target overseas --manifest reports/local-automation-state/overseas-metadata-manifest-1.json --config reports/local-automation-state/config.local.json --json
python -m ai_actuarial.local_collection_runtime backfill-target-metadata --target overseas --manifest reports/local-automation-state/overseas-metadata-manifest-1.json --config reports/local-automation-state/config.local.json --apply --json
```

manifest 结构示例：

```json
{
  "schema_version": 1,
  "records": [
    {
      "url": "https://example.org/actuarial-ai-paper.pdf",
      "raw_sha256": "<64 lowercase hex characters>",
      "content_version_id": 123,
      "markdown_text_variant_id": 456,
      "markdown_sha256": "<64 lowercase hex characters>",
      "hub_markdown_sha256": "<64 lowercase hex characters>",
      "hub_markdown_sha256_kind": "raw_utf8",
      "source_primary_category": "AI",
      "categories": [
        {"key": "AI", "evidence": ["artificial intelligence"]},
        {"key": "Pricing", "evidence": ["insurance pricing"]}
      ],
      "date_facts": {
        "publication_date": {
          "semantic": "publication",
          "value": "2024-12",
          "precision": "month",
          "evidence": "Published December 2024",
          "location": "page 1"
        },
        "revision_date": null,
        "document_version_date": null
      },
      "date_review_status": "complete",
      "date_review_reason": null,
      "date_review_unresolved": [],
      "source_signature": "<64 lowercase hex characters>",
      "result_sha256": "<64 lowercase hex characters>",
      "expected_published_time": "2023-06"
    }
  ]
}
```

manifest 每条记录必须包含 `url`、`raw_sha256`、正整数 `content_version_id`/`markdown_text_variant_id`、`markdown_sha256`、`hub_markdown_sha256`/`hub_markdown_sha256_kind`、`source_primary_category: "AI"`、1–4 个有序 `categories`、三字段 `date_facts`、日期审核字段及 `source_signature`/`result_sha256`。正常注释的每类需有 1–3 条 exact quote evidence；仅对已存 Hub 注释中首类证据为空的 legacy 记录，可原样保留空数组。Hub 日期字段的语义映射为 `publication_date -> publication`、`revision_date -> revision`、`document_version_date -> document_version`，保留该语义值；`files.published_time` 只读取 `date_facts.publication_date.value`。目标 worker 会对每条回填或新发布记录重新计算 `result_sha256`；对当前 Hub writer 生成的新注释，也会按 content version、Markdown variant/hash 与 primary category 重新计算 `source_signature`。历史 v2 注释的签名使用旧输入，精简 manifest 不含重算它所需的字段，因此本机回填命令会在发往目标前按 exact URL/raw SHA 重新读取 Hub，并逐项比对版本、Markdown、类别、日期、签名和结果摘要；目标保留该历史签名原值，不声称在目标端重算了它。不得从 Markdown 猜引文或填入占位引文。`expected_published_time` 必须明确包含目标读回值（可为 `null`），防止 audit 后目标被并发修改；若重放时其值已等于同一份已验证的发布日期，命令接受幂等重试。回填只更新 native `hub_enrichment` 及已验证的 `files.published_time`，保留原来的 zh/en 包及所有 extra fields。已知日期按其 year/month/day 精度投影；未知日期保留已存在的旧值并标记 `legacy_preserved_unverified`，没有旧值则继续为 `null`。

`published_time` 是 native 文件字段；是否可按日期排序还取决于对应列表/API 的排序字段 allowlist。不要仅凭数据库列存在就承诺 UI 或 API 支持；先检查当前 endpoint allowlist。当前本机流程不改 UI/API 排序。

仅当父级清单逐条绑定了 exact URL、raw SHA、正整数 Hub `content_version_id` 和有序首类类别时，才能运行窄范围目标清理。中国和海外需使用各自从只读 inventory 生成的 manifest，不要把一端 URL 集合直接套到另一端。Hub reader 原样保留的历史首类证据可为空；其他类别仍需 1–3 条证据，不生成替代 quote。manifest schema 为：

```json
{
  "schema_version": 1,
  "records": [
    {
      "url": "https://example.org/research.pdf",
      "raw_sha256": "<64 lowercase hex characters>",
      "hub_evidence": {
        "content_version_id": 123,
        "url": "https://example.org/research.pdf",
        "raw_sha256": "<same SHA-256>",
        "primary_category": "Pricing",
        "categories": [
          {"key": "Pricing", "evidence": []},
          {"key": "AI", "evidence": ["exact source quote"]}
        ]
      }
    }
  ]
}
```

空数组只代表 Hub 中已持久化的 legacy 首类证据；manifest 仍须由精确 URL/raw-SHA/version 读回生成，并核对 ordered primary。不得仅凭空 evidence 直接扩大删除范围。

先使用默认 dry-run 核对每条目标 URL/SHA、当前 catalog 状态、KB membership、容量和已有 pending URL：

```powershell
python -m ai_actuarial.local_collection_runtime cleanup-targets --target china --manifest reports/local-automation-state/china-cleanup-manifest.json --config reports/local-automation-state/config.local.json --json
```

只有该只读报告逐条匹配后才加 `--apply`。命令会通过 native manager 从中国 `ai`/`all` 或海外 `ai` membership 移除精确 URL，用 `Storage.mark_file_deleted` 隐藏目标 catalog 记录，并用空 chunk URL 列表重建受影响的 native index/Ready。它不删除 Hub/CAS 原件、源历史、用户、聊天或模型。如果目标 URL 已不存在或已 retired，重放是幂等的；若 index/Ready 失败，命令会明确报告已完成的清理、pending KB 与错误，之后用相同 manifest 重试。若容量预检已达到 80% gate，命令在目标文件或 membership 修改前停止；运行中的 Ready 若之后遇到容量错误，也不会冒报成功。

Chunk/embed 恢复会针对当前 URL 幂等重跑原生 chunk generation，并把该任务返回的确切 `chunk_set_id` 列表与当前 KB `embedding_identity_key` 传给 embedding generation；不会按 URL/profile 在历史 ready sets 中猜选。该阶段失败时 pending URL 保留，重试完成 chunk、embedding 和 binding 后才继续完整 KB index 与 Ready。

`run-daily` 不是 Scheduler。日报 09:00 触发和任务开关继续沿用现有 automation owner；本地运行 CLI 不迁移或新建调度。首次真实写入和 automation 启用须由独立 review/验收流程批准。
