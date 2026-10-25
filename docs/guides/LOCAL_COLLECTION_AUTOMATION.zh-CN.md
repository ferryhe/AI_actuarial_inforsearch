# 本机资料轮换采集与日报规划

新增的 `$local-actuarial-flow` skill 汇总 32 个监控项（入口 hostname 去重 29 个）的脚本审计、每日轮换和美东日报合同。目标是美东每日 06:00 排六个固定 baseline，最多另排两个 distinct 失败补采；任何连续七天的计划 baseline 均覆盖全部 32 项。美东 09:00 报告前一自然日，逐站标出真实成功、partial、failed、not_run 或 hold，并列最近七日计划与实际覆盖。IABA/EAA 是结构检查 `monitor_only`；Istituto 保留轮换位置但 `hold`。这些是离线计划，不运行采集、不接 Hub/线上两站，也不创建或启用 Scheduler。历史 `reports/` 操作脚本只在忽略的本机报告目录中，未跟踪进新 clone；skill references 说明可复用边界和待实现接点。

全链路建议、每站风险/改造建议、JSON 回执合同与当前阻塞见 [skill](../../.agents/skills/local-actuarial-flow/SKILL.md) 及其 references。最近的站点入口 probe 只测各站一个入口：30 个收到响应，IFoA 的已配置 `www` 入口 503 但规范无 `www` 入口可达，Istituto 返回 placeholder/demo。单个入口响应不代表附件、正文或覆盖完整。

两站服务器 2026-10-25 的只读配置显示 `Scheduled Collection=false`；本机 Docker 未启动，无法连接 local Hub。必须先完成 source/Hub adapters、固定历史路径的双语 runner 参数化、按任一规范 AI 类别注释而非单类/关键词筛选，以及国内/海外独立增量发布和 Ready 验收，才可评估真实启用。旧 `replace_articles.py` 是清空式替换，禁止用于周期更新；旧全局噪音规则也会误删 25 类范围内教育/考试/会议资料。详见 skill references。

运行需要 Python 3.10+ 和 `America/New_York` IANA 时区数据；若 Windows Python 缺少该数据库，请在工具所用 Python 环境安装 `tzdata`。回执为 v2 每日自然日格式；旧 v1 两小时回执应隔离，helper 会拒绝混用。单次离线运行示例：

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --date 2026-10-25 --receipts PATH --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-25 --receipts PATH --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts PATH --case-ledger PATH --json
```

回执缺失表示 `not_run` 或 `not_scheduled`，计数缺失表示 `unknown`；国内/海外 acknowledgement 表示本轮写入/回读结果，两端的 `ready_status_counts` 独立记录本站索引 Ready 状态，ack 成功不代表索引已就绪。最新收集阶段成功不关闭旧 Ready 故障；只有对应 Ready 阶段新的 succeeded 回执才关闭。目标回执中的 pending/failed 是每轮观察数，不等于去重后的当前积压。

日报同时给出 `case_updates`、`research_queue` 与最多两项 `suggested_research`。Case ledger 初始内容是 `{"schema_version":1,"cases":[]}`；调用端根据输出原子更新：`close`/`supersede` 必须写成 `state=closed`，`open`/`update`/`observe`/`preserve`/`reopen` 写成 `state=active`。研究完成后记录 `last_researched_date` 和当时的 `last_researched_fingerprint`；证据变化时保留旧研究日期及旧指纹，直到新证据实际研究完成再更新。helper 只读 ledger，不做研究或修复；同一证据已研究过才会从建议队列暂时移除，出现新证据则重新入队。失败按 site/stage 跨日保留，只有对应阶段有明确成功回执才关闭；下载成功不能清掉历史 Ready 故障。计划和回执报告不是采集或同步验收证据，真实生产 source/Hub/serving adapters 仍待实现。
