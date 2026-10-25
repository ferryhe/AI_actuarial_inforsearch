# 本机资料轮换采集与日报规划

新增的 `$local-actuarial-flow` skill 汇总了 32 个监控项（29 个唯一入口 hostname）的脚本审计、每两小时四项轮换和美东 09:00 前一日回执报告。当前只提供离线 `plan`、`status`、`report --json` helper；不运行采集、不接 Hub/线上两站；helper 本身不会创建或启用 Scheduler。连续计划八组轮转周期是 16 小时；IABA/EAA 是 `monitor_only`，Istituto 保留组内位置但 `hold`。单项低频策略和漏槽恢复尚未实现。历史 `reports/` 操作脚本只在忽略的原 checkout 报告目录中，未跟踪进本仓库或新 clone；skill reference 列出可复用边界和建议预算。

全链路建议、每站风险/改造建议、JSON 回执合同与当前阻塞见 [skill](../../.agents/skills/local-actuarial-flow/SKILL.md) 及其 references。最近的站点入口 probe 只测各站一个入口：30 个收到响应，IFoA 的已配置 `www` 入口 503 但规范无 `www` 入口可达，Istituto 返回 placeholder/demo。单个入口响应不代表附件、正文或覆盖完整。

两站服务器 2026-10-25 的只读配置显示 `Scheduled Collection=false`；本机 Docker 未启动，无法连接 local Hub。必须先完成 source/Hub adapters、固定历史路径的双语 runner 参数化、按任一规范 AI 类别注释而非单类/关键词筛选，以及国内/海外独立增量发布和 Ready 验收，才可评估真实启用。旧 `replace_articles.py` 是清空式替换，禁止用于周期更新；旧全局噪音规则也会误删 25 类范围内教育/考试/会议资料。详见 skill references。

运行需要 Python 3.10+ 和 `America/New_York` IANA 时区数据；若 Windows Python 缺少该数据库，请在工具所用 Python 环境安装 `tzdata`。单次离线运行示例：

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --at 2026-10-25T09:00:00-04:00 --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-24 --receipts PATH --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-24 --receipts PATH --json
```

回执缺失表示 `not_run`，计数缺失表示 `unknown`；国内/海外 acknowledgement 表示本轮写入/回读结果，两端的 `ready_status_counts` 独立记录本站索引 Ready 状态，ack 成功不代表索引已就绪。目标回执中的 pending/failed 是每轮观察数，不等于去重后的当前积压。helper 可以在本机离线运行，但这不表示采集全链路或定时已经启用。
