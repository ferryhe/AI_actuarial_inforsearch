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

`run_status` 只能是 `succeeded`、`partial` 或 `failed`。后两种必须给 `reason`；任何阶段为 `partial` 或 `failed` 时必须给该阶段 `error`。可用 `evidence` 保存来源 URL、日志定位符或目标回读证据。缺阶段按 `unknown`，不能当成成功或零。写入端必须先汇总该自然日同站所有尝试，再原子替换 final receipt：`attempt_count` 是当日尝试总数，count 和 ack 的 `acknowledged/pending/failed` 是当日各次运行观察的累计；阶段 `status`、目标 ack/Ready 状态和失败理由/evidence 表示最新一次尝试的终态。不能用最后一次重试的 0 覆盖当天先前已计数的资料。计数不是库内当前总量或唯一文章数；同一资料可跨重试或监控项重复发现。`downloaded`、`new_versions`、`duplicates`、`enriched` 和 `ai_candidates` 的 count 为非负整数或 `null`。

目标发布分别记录 `china_ack` 和 `overseas_ack`。ack 的累计 `acknowledged/pending/failed` 计数覆盖本日尝试；ack 的 `status` 与 `ready_status` 表示最近一次尝试的写入/回读与索引 Ready 结果，缺省 Ready 为 `unknown`。Ready 为 `partial`/`failed` 时要提供 `ready_error`，证据放 `ready_evidence`。例如 ack succeeded 而 overseas Ready pending 时，日报会将本站标为 `partial`，但不伪装成已确认的站点故障；缺失/unknown 不能关闭旧 Ready failure。AI 候选确认为 0 时，缺少两端 ack 不算失败。

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
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --case-ledger reports/local-automation-state/cases/ledger.json --json
```

`plan` 显示 06:00 美东固定六项 baseline 和最多两个不同站点的额外失败重试。每日日期锚定，不按 DST 小时滚动；连续任意七个自然日的 baseline 计划覆盖 32 项。失败重试有日期轮转游标，不改变 baseline；这代表计划覆盖，不能保证实际运行或成功覆盖。hold 占一个 baseline 位置但不计为尝试或成功。monitor-only 项只做结构检查。

`status` 对全部 32 项列出 `succeeded`、`partial`、`failed`、`not_run`、`not_scheduled` 或 `hold`，并给计划位置、原因、失败阶段和证据。planned 项缺回执是 `not_run`（调度缺口），不是网页失败。计划外回执、单站多次尝试以及总 distinct site/attempt 数超过 8 都会在 `budget_exceptions` 分别列明，绝不静默丢掉。

`report` 包含当日站点明细、每阶段本轮观察统计、最近七日逐日 planned/attempted/succeeded/partial/failed/not_run/held 列表与数量、计划与真实覆盖差异，以及失败研究队列。`ack` 与各自的 `ready_status` 分开计数；pending/unknown 不被误报为外部故障。跨日积压需未来按目标和 `content_version_id` 去重读取，不能把多份回执快照直接相加。

需要 Python 3.10+ 和可用的 `America/New_York` IANA 时区数据；Windows 如缺数据，在同一 Python 环境安装 `tzdata`。helper 只规划和读取 JSON，不访问网站、Hub 或目标服务，不写 ledger，也不启用定时任务。
