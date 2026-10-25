---
name: local-actuarial-flow
description: 规划和审查本机精算资料监控项的轮换采集、Hub 入库、双语分类、两站 AI 增量同步与日报；仅适用于本仓库已登记的 32 个监控项。
---

# 本机精算资料采集流程

先读 [工作流与改造边界](references/workflow.zh-CN.md)；处理单项时再查 [32 项目录](references/sites.zh-CN.md)，实现回执时读 [回执与日报合同](references/receipts.zh-CN.md)。

## 当前可运行范围

`scripts/local_flow.py` 只离线规划两小时轮换、读取最终 JSON 回执并生成状态/日报 JSON。它不访问网站，不运行采集器，不写 Hub 或海外/国内服务，也不启用计划任务。当前全链路因本地 Hub 与 source/serving adapters 未接好而未激活。不得把入口页探测、历史 `status.json`、离线测试或“未运行”算作采集成功。IABA/EAA 是低频 `monitor_only`，Istituto 是 `hold`；组计划不替代逐项 cadence 配置。

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --at 2026-10-25T09:00:00-04:00 --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-24 --receipts PATH --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-24 --receipts PATH --json
```

日报计划在美东每日 09:00 汇总前一美东自然日的实际轮次回执。计划按 UTC 连续两小时边界轮转，八组各四个监控项，连续计划覆盖周期为 16 小时；DST 日当地自然日可能覆盖 11 或 13 个边界。Istituto 当前为单项 `hold`，仍留在组表中。失败项不阻塞同组其他项或后续轮次。Helper 没有持久游标或漏槽补偿，不能保证停机后的实际完整覆盖。

需要 Python 3.10+ 和 `America/New_York` IANA 时区数据。Windows Python 若没有该数据库，请在所用 Python 环境安装 `tzdata`；helper 不改主应用依赖。

只有实际 final receipt 才能计数。相同 slot/site 的字节语义相同回执去重，冲突回执拒绝；缺计数为 unknown，缺回执为 `not_run`，不能写成成功的零。回执中的计数是本轮观测，重复内容可能跨站或跨轮出现；China/overseas pending/failed 是各轮观测，不是去重后的当前积压。

日报在 China/overseas 两端分别报告写入/回读 acknowledgement 与索引 `ready_status`；ack 成功不代表 Ready。旧回执缺少 `ready_status` 时按 `unknown` 计，不推断索引已就绪。
