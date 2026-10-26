---
name: local-actuarial-flow
description: 规划和审查本机精算资料监控项的每日轮换、真实回执、Hub 入库、双语分类、两站 AI 增量同步与日报；适用于本仓库登记的 32 个监控项。
---

# 本机精算资料采集流程

先读 [本机运行指南](references/runtime.zh-CN.md) 和 [工作流与改造边界](references/workflow.zh-CN.md)；修复单项来源时读 [32 项目录](references/sites.zh-CN.md)，实现或读取回执时读 [每日回执、失败队列与日报合同](references/receipts.zh-CN.md)。

## 离线 helper

`scripts/local_flow.py` 仅读取最终 v2 JSON 回执、给出每日轮换计划、日报和最多两项研究建议。它不访问网站、运行采集器、写 Hub/两站，也不写 case ledger 或启用 Scheduler。基线是美东每日 06:00 固定六项；失败重试最多另加两个不同监控项。连续七个自然日计划覆盖 32 个监控项，但计划覆盖不证明实际执行或成功。IABA/EAA 是 monitor-only，Istituto 保留 baseline 位置并 hold。

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --case-ledger reports/local-automation-state/cases/ledger.json --json
```

日报按美东 09:00 触发时由调用端提供前一自然日。缺回执是 `not_run` 或 `not_scheduled`，不是源站失败；缺字段是 `unknown`，不是成功或零。AI 发布 acknowledgement 与各自 Ready 状态分开记录。回执格式、Case ledger 的原子更新及状态定义见每日合同。

## 本机运行入口

跟踪源码 `ai_actuarial.local_collection_runtime` 提供 bounded live collection、Hub live-capture 入库、Luna 双语分类/日期补全、国内与海外目标增量同步、独立回执与任何阶段的恢复。只使用单独的 `config.local.json`，不要把连接文件路径或主机地址写入共享例子。操作命令、试跑顺序和范围限制见 [本机运行指南](references/runtime.zh-CN.md)。该 CLI 不安装或启用计划任务；现有 06:00/09:00 automation 由外部 owner 单独管理。

真实失败的修复闭环：用回执 case ID 和证据复现；判断是临时网络/服务问题还是 DOM、URL、分页、CLI、过滤器/分类规则变更；对本仓库可维护的实际脚本、playbook 或 skill 做最小修改；跑聚焦测试和低流量真实验证，再交 fresh reviewer；下一日用新的真实回执确认恢复。每日日报后最多研究两项；同一 case 和证据不得每天重复研究。外部源仍不可用时保留未解决和退避建议。不得编辑 skill/报告把状态改成成功，也不得修改 ignored 历史快照冒充已部署修复。

入口响应、离线测试、历史 `status.json` 和计划项都不是采集回执。采集内容入库、两站增量发布及适配器若尚未有真实回执，必须明确写阻塞，不能声称完成。运行需要 Python 3.10+ 与 `America/New_York` 时区数据；Windows 缺失时在使用的 Python 环境安装 `tzdata`。
