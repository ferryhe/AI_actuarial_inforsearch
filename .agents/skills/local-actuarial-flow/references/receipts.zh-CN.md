# 回执与日报 JSON 合同（v1）

## 单站轮次回执

每个最终执行结果保存一个 JSON 文件，目录由调用者自行管理。此仓库脚本只读取，不生成采集回执。推荐同一逻辑回执复制到多个文件时保持内容不变；同一个 slot/site 出现字段不同的两份文件会拒绝，不选择“看起来更新”的那份。重跑应原子替换该 slot/site 的 final receipt，不能追加重试快照并重复计数。

```json
{
  "schema_version": 1,
  "receipt_id": "2026-10-25T12:00:00Z/aae",
  "slot_start_utc": "2026-10-25T12:00:00Z",
  "site_id": "aae",
  "run_status": "partial",
  "stages": {
    "downloaded": {"status": "succeeded", "count": 2},
    "new_versions": {"status": "succeeded", "count": 1},
    "duplicates": {"status": "succeeded", "count": 1},
    "enriched": {"status": "pending", "count": null},
    "ai_candidates": {"status": "unknown", "count": null},
    "china_ack": {"status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0, "ready_status": "succeeded"},
    "overseas_ack": {"status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0, "ready_status": "pending"}
  }
}
```

`receipt_id` 固定为 UTC slot 起始时间和 site ID，中间用 `/`。slot 必须落在 Unix epoch 起算的两小时 UTC 边界，且站点必须属于该组；不接受 Istituto 的 receipt，因为该站当前为 hold。顶层必须有 `schema_version=1`、`run_status`、`receipt_id`、`slot_start_utc`、`site_id`；`stages` 内阶段字段可省略，但不完整阶段按 unknown 处理，禁止默认为成功或 0。非整数、负数、无时区时间、错误来源组及冲突副本都会拒绝。

IABA/EAA 的 `monitor_only` 回执只报告结构检查的 `run_status`；`stages` 必须省略或为空对象，不提供下载、入库、enrichment、AI 候选或中国/海外目标确认阶段。若 monitor-only 回执带任一 stage payload，工具会拒绝整份回执，避免报告把实际采集或发布观察静默丢弃。当前 v1 不为结构检查提供计数阶段。

`downloaded/new_versions/duplicates/enriched/ai_candidates` 的 `count` 必须是**本轮**计数，不是累计数据库总量。每个状态只能是 `succeeded`、`partial`、`failed`、`pending`、`unknown`。两目标的 `acknowledged/pending/failed` 是本轮目标写入/回读结果；`ready_status` 独立表示该目标索引的 Ready 状态，使用同一组状态枚举，缺字段按 `unknown`。回执中的 acknowledgement 成功不等于目标已 Ready。日报在 `china_ack` 与 `overseas_ack` 下分别提供 `ready_status_counts`。所有这些是回执中的 run observation，不构成唯一文章数或当前跨日积压。要报告当前积压，未来需按目标 + `content_version_id` 做去重并读取/保存最新终态；不能从计数快照推导。

## 命令

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --at 2026-10-25T09:00:00-04:00 --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-24 --receipts reports/receipts/ --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-24 --receipts reports/receipts/ --json
```

`plan --at` 返回该时刻所在两小时 UTC bucket 的单组计划。`status` 返回美东当地日计划中的每个监控项/轮次，未读到回执为 `not_run`；hold 项显示 `hold`。`report --date` 目标由次日美东 09:00 触发，汇总指定前一日的实际回执。IABA/EAA 的低频 `monitor_only` 回执与 collection 阶段分栏；其到期频率尚未实现，因此不把无回执推断为漏跑。每个计数会带已知/unknown receipt 数；若应运行 collection 回执缺失，或阶段字段未知、失败、partial，完整日 `complete_day_run_sum` 是 `null`。各目标 acknowledgement 状态与 Ready 统计分开显示，旧回执中缺少 `ready_status` 时会计为 `unknown`。阶段 run sum 仍可能跨监控项或轮次重复同一内容。

需要 Python 3.10+ 和 `America/New_York` IANA 时区数据；Windows 如缺数据，在同一 Python 环境安装 `tzdata`。工具不改主应用依赖。

工具当前无 Hub 写入。`writes_hub_or_servers=false` 和 `executes_collection=false` 是输出合同，不是待打开的开关。
