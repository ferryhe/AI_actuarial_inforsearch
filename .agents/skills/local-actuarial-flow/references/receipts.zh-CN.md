# 每日回执、失败队列与日报合同（v2）

## 每站每日回执

每个真实执行过的监控项，每个美东自然日只保存一份最终 JSON 回执，按 `date_local/site_id` 唯一标识。重跑时原子替换该站当日的 final receipt，并把总尝试次数记入 `attempt_count`；不要追加多份回执以重复统计。字节语义相同的副本会去重，字段冲突则整批拒绝。该目录只放 v2 回执；v1 两小时回执不会换算成每日尝试，请移到隔离目录后再运行。

```json
{
  "schema_version": 2,
  "receipt_id": "2026-10-25/iaa",
  "date_local": "2026-10-25",
  "site_id": "iaa",
  "run_status": "partial",
  "reason": "分页扫描在第 3 页失败",
  "evidence": ["https://example.org/research?page=3"],
  "attempt_count": 1,
  "stages": {
    "downloaded": {"status": "succeeded", "count": 2},
    "new_versions": {"status": "succeeded", "count": 1},
    "duplicates": {"status": "succeeded", "count": 1},
    "enriched": {"status": "succeeded", "count": 1},
    "ai_candidates": {"status": "succeeded", "count": 0},
    "china_ack": {"status": "unknown"},
    "overseas_ack": {"status": "unknown"}
  }
}
```

`run_status` 只能是 `succeeded`、`partial` 或 `failed`。后两种必须给 `reason`；任何阶段为 `partial` 或 `failed` 时必须给该阶段 `error`，唯一例外是 `downloaded.status=partial` 且 `downloaded.request_budget.paused=true` 的纯预算暂停。它仍须有回执级 `reason` 和预算证据，但阶段 `error` 留空，表示没有观察到真实失败。若同时发生来源错误，阶段 `error` 必须保留错误文本，不能用预算信息覆盖。`request_budget` 形状为 `{"used":30,"cap":30,"paused":true,"frontier_remaining":5}`；它描述此轮实际请求和已保留的游标，不代表采集成功。纯预算暂停让站点保持 `partial`，但不会生成失败研究 case；已有真实 source、Hub、model 或 target 错误仍会生成对应 case。可用 `evidence` 保存来源 URL、日志定位符或目标回读证据。缺阶段按 `unknown`，不能当成成功或零。写入端必须先汇总该自然日同站所有尝试，再原子替换 final receipt：`attempt_count` 是当日尝试总数，count 和 ack 的 `acknowledged/pending/failed` 是当日各次运行观察的累计；阶段 `status`、目标 ack/Ready 状态和失败理由/evidence 表示最新一次尝试的终态。不能用最后一次重试的 0 覆盖当天先前已计数的资料。计数不是库内当前总量或唯一文章数；同一资料可跨重试或监控项重复发现。`downloaded`、`new_versions`、`duplicates`、`enriched` 和 `ai_candidates` 的 count 为非负整数或 `null`。`new_versions` 和 `enriched` 可附 `pending_count`，表示本站所有未完成文章中本轮未选入有界处理批次的数量；即使使用 `--exact-url`，也仍按本站未完成总数减去本轮实际选中数计算，不代表精确 URL 之外的文章被处理。它是最新状态，不随每日尝试累计。该调度计数不包含本轮已选中、但仍有失败、目标确认或 Ready 工作的文章，因此不能单独表示整个队列已完成。离线 status/report 会显示预算暂停和 pending article 计数。

目标发布分别记录 `china_ack` 和 `overseas_ack`。ack 的累计 `acknowledged/pending/failed` 计数覆盖本日尝试；ack 的 `status` 与 `ready_status` 表示最近一次尝试的写入/回读与索引 Ready 结果，缺省 Ready 为 `unknown`。Ready 为 `partial`/`failed` 时要提供 `ready_error`，证据放 `ready_evidence`。例如 ack succeeded 而 overseas Ready pending 时，日报会将本站标为 `partial`，但不伪装成已确认的站点故障；缺失/unknown 不能关闭旧 Ready failure。AI 候选确认为 0 时，缺少两端 ack 不算失败。

`ready_status` 还可以是 worker 明确返回的 `not_required`。它只表示该次请求没有要求或没有执行 native Ready 检查，不代表 Ready succeeded。若存在 AI 首类候选，回执保持未完成；该值不会关闭旧 Ready case，也不会单独生成网页故障 case。不能把 ACK、容量预检或 `not_required` 改写为可搜索成功。

### 可选真实运行指标

运行时可在 v2 回执新增可选的顶层 `telemetry`。旧回执没有该字段时，各指标是未知，不能换算成零。示例：

```json
{
  "telemetry": {
    "elapsed_seconds": 74.2,
    "source": {
      "request_count": 12,
      "pages_visited": 4,
      "links_discovered": 7,
      "files_by_type": {"html": 2, "pdf": 1, "other": 0},
      "file_ids": ["<url-and-raw-sha-identity>"],
      "page_ids": ["<hashed-canonical-page-url>"],
      "link_ids": ["<hashed-frontier-identity>"]
    },
    "database": {"new_version_ids": ["<content-version-id>"], "duplicate_version_ids": []},
    "enrichment": {"succeeded_count": 1, "succeeded_ids": ["<content-version-id>"]},
    "conversion": {
      "succeeded_count": 1,
      "failed_count": 0,
      "succeeded_ids": ["<url-and-raw-sha-identity>"],
      "failed_ids": []
    },
    "ai_first_candidate_count": 1,
    "ai_first_candidate_ids": ["<content-version-id>"],
    "targets": {
      "china": {
        "acknowledged_ids": ["<target-version-identity>"],
        "ready_status": "succeeded",
        "ready_ids": ["<target-version-identity>"],
        "invalidated_ready_ids": []
      }
    }
  }
}
```

计数口径：`request_count` 按运行时发出的 HTTP 请求计，预算包含每一跳重定向；`pages_visited` 只数成功读取的非附件页面/目录/API 前沿，不能把仅发现的链接当成已访问页面；`links_discovered` 是解析后新加入队列的候选链接/条目。`files_by_type` 是当日各次运行成功收集的 HTML、PDF 和其他文件观察数。站点当日重跑时，阶段 `count` 和 `telemetry` 数值累计各次观察；ID 列表按身份去重，因此日报同时给出观察总数和唯一项数。数据库 ID 是 Hub 内容版本，下载/转换 ID 绑定规范 URL 与原件 SHA；页面/链接 ID 为哈希，不保存原始 URL。

转换统计只记录本机 `_convert_article` 实际成功或失败的调用。已复用 Hub Markdown 不算一次转换；转换成功后模型超时、引文校验失败或摘要保存失败归入富信息/分类阶段，不能伪装成转换失败。`ai_first_candidate_count/ids` 只由当前 `categories[0].key == "AI"` 且 Hub primary 为 AI 的实时判定生成。旧 `ai_candidates.count` 可能使用任一类别含 AI 的旧口径；不能从旧计数或回执日期推断 AI 首类。

`targets.*.acknowledged_ids` 是当日各次确认身份的并集。`ready_ids` 保留当日已由 native Ready 明确确认的身份，即使后续重试不需要重新构建 Ready；`invalidated_ready_ids` 只在目标状态明确回到待确认/失败时移除对应身份。`ready_status` 表示最新尝试，始终独立于累计 Ready 身份集合。`not_required` 不会合成 Ready 身份。整轮 `run-daily.elapsed_seconds` 包含本轮站点运行和已配置的 backlog reconcile；每站回执中的 `elapsed_seconds` 是该站全部同日尝试耗时之和。

IABA/EAA 仅允许记录结构检查：`stages` 必须包含 `monitor`，且不能含下载、入库、enrichment、AI 或 publish 阶段。结构失败要在 `monitor` 中提供 `error` 和可用证据。Istituto 仍为 hold，不应生成执行回执。monitor-only 回执不能充作采集成功或入库数量。

## Case ledger 与失败恢复

空 ledger 的唯一初始内容为：

```json
{"schema_version":1,"cases":[]}
```

report 的 `failure_cases` 是按 site/stage 跨回执折叠后仍未由该阶段明确成功关闭的 case；`case_updates` 会输出 `open`、`update`、`observe`、`reopen`、`close`、`preserve` 或 `supersede` 操作。后来只有下载成功或 Ready 字段缺失/unknown 时，旧 Ready case 仍留在重试和研究队列。`research_queue` 只包含尚未以同一证据指纹研究过的 case，`suggested_research` 最多两项。调用端写回 ledger 时，`close` 和 `supersede` 必须设 `state=closed`；其余 `open/update/observe/preserve/reopen` 设 `state=active`。研究完成后保存 `last_researched_date` 和当时的 `last_researched_fingerprint`；证据变更时保留旧研究日期和指纹，确保尚未研究的新证据不会被标成已研究。helper 只读 ledger，从不替 agent 写入、执行研究、改脚本或采集。报告后由 agent 原子应用 case updates 和研究时间，避免每天重复研究同一无新证据的故障。只有对应失败阶段有新 `succeeded` 证据才可关闭 case；其他阶段成功、字段缺失或 unknown 都要保留。无回执只表示 `not_run`/计划缺口，不能创建网页故障 case。

## 命令

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --case-ledger reports/local-automation-state/cases/ledger.json --format markdown --language zh
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --format markdown --language en
```

`plan` 显示 06:00 美东固定六项 baseline 和最多两个不同站点的额外失败重试。每日日期锚定，不按 DST 小时滚动；连续任意七个自然日的 baseline 计划覆盖 32 项。失败重试有日期轮转游标，不改变 baseline；这代表计划覆盖，不能保证实际运行或成功覆盖。hold 占一个 baseline 位置但不计为尝试或成功。monitor-only 项只做结构检查。

`status` 对全部 32 项列出 `succeeded`、`partial`、`failed`、`not_run`、`not_scheduled` 或 `hold`，并给计划位置、原因、失败阶段和证据。planned 项缺回执是 `not_run`（调度缺口），不是网页失败。计划外回执、单站多次尝试以及总 distinct site/attempt 数超过 8 都会在 `budget_exceptions` 分别列明，绝不静默丢掉。

`report` 默认仍输出 JSON；`--format markdown` 输出人类可读表，`--language zh|en` 选择中文或英文（默认 zh），仅影响 Markdown，不改变 JSON、数据范围或状态。偏好优先级为显式 CLI 参数、用户明确指定的报告语言、对话语言、中文回退。中文 30 请求预算提示固定使用“30次访问预算用完，下次继续”，英文对应 “The 30-request budget is exhausted; continue next time.” `--json` 保持兼容。Markdown 开头的执行摘要应简述整体完成度、可见产出、主要阻塞/纯预算暂停和建议。传入 `--runtime-output` 后，只有与当前非预览运行精确匹配的回执可作为本次结果；同日较早回执保留为历史，不可替代失败或缺失的当前尝试。未提供运行输出时可按日期展示已有回执数量和错误，但须明确当前运行关联未知；不得把它们写成本次运行成功。建议把计划内未运行与已尝试但缺回执分开：前者核实是否应执行，后者核对当前回执。预览、monitor-only 和 hold 分开说明，不计入来源采集。实际来源、转换、目标错误不可被预算提示遮盖；纯预算暂停单列。缺少指标保持未知。建议仅为后续检查，不表示已执行重试、提升预算、删除数据或更改发布规则。可选 `--runtime-output` 读取同日期 `run-daily` JSON，指出有运行证据但缺 final receipt 的站点并显示实际整轮耗时。运行输出只提供可见性，不参与失败 case 折叠、关闭或研究队列。报告包含当日计划/实际站点、来源请求/页面/新链接、文件类型、Hub 新增/重复、转换、AI 首类候选、国内/海外入库及可搜索状态和逐站停止阶段。观察统计包括同日重跑，唯一计数只从精确身份集合生成。`ack` 与各自的 Ready 状态分开；pending/unknown/not_required 不被误报为成功或网页故障。跨日积压需未来按目标和 `content_version_id` 去重读取，不能把多份回执快照直接相加。

需要 Python 3.10+ 和可用的 `America/New_York` IANA 时区数据；Windows 如缺数据，在同一 Python 环境安装 `tzdata`。helper 只规划、读取 JSON 并输出 JSON 或 Markdown，不访问网站、Hub 或目标服务，不写 ledger，也不启用定时任务。
