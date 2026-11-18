---
name: local-actuarial-flow
description: 规划和核查本仓库 32 个精算资料监控项的每日轮换、Hub 入库、双语分类、回执与两站同步。供本机和服务器核查原站发布日期、网页变化及周报的新发布与历史补录。
---

# 本机精算资料采集流程

先读 [本机运行指南](references/runtime.zh-CN.md) 和 [工作流与改造边界](references/workflow.zh-CN.md)；修复单项来源时读 [32 项目录](references/sites.zh-CN.md)，实现或读取回执时读 [每日回执、失败队列与日报合同](references/receipts.zh-CN.md)。独立调查公开来源页面或附件时，按 [web-listening 探索工具说明](references/web-listening-exploration.zh-CN.md) 使用隔离版本；其证据不等于每日采集成功。

## 网页和周报的时效核查

本机和服务器使用同一份核查口径。优先复用 Hub 已存原件、网页快照及两站公开 API。

- **查原始发布日期。** 按规范 URL 核对原页的发布日期、`datePublished` 或 `article:published_time`，可用官方目录、发布公告或 PDF 交叉印证。记录来源 URL、原件版本、证据及日期精度。采集日、入库日、修改日和事件日各自保留。证据冲突或缺失的日期记为待核。
- **核对网页和附件。** 已存同一 PDF 时复用原件，将论文页和公告页关联到它。缺失附件走现有采集入口。首次成功快照作为比较基线。后续在相同页面范围比较正文和附件链接，用 SHA-256 核对同址 PDF 是否换版。导航、时间戳等模板差异只记作检查。确认正文或附件实质变化后再保存新内容版本，修订日期另记。
- **核对周报。** 对已关闭的 UTC 周，检查 `/api/weekly-updates/latest` 对应的入库成员和中英文导读，加 `published_only=true` 查询该期文件可查看按原站发布日期倒序的已核实新发布。对正在进行的周，以 `/api/files` 的 `first_seen_from` 和 `first_seen_before` 查看入库候选。周报按 `first_seen` 保留入库记录。原始发布日期能确认到日且落在本期的资料才进入新发布推荐。日期粒度太粗时保留待核。证实的实质修订单列为网页变化。
- **写公开导读。** 历史补录保留在资料库。需要交代时在末尾合并一句「本期另有历史资料补录」。没有核实的新发布时用「本期暂无核实的新发布」。只读预览见 [周报导读维护](../../../docs/weekly-reader-maintenance.md)。

## 离线 helper

`scripts/local_flow.py` 仅读取最终 v2 JSON 回执、给出每日轮换计划、日报和最多两项研究建议。它不访问网站、运行采集器、写 Hub/两站，也不写 case ledger 或启用 Scheduler。基线是美东每日 06:00 固定六项；失败重试最多另加两个不同监控项。连续七个自然日计划覆盖 32 个监控项，但计划覆盖不证明实际执行或成功。IABA/EAA 是 monitor-only，Istituto 保留 baseline 位置并 hold。

```powershell
python .agents/skills/local-actuarial-flow/scripts/local_flow.py plan --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py status --date 2026-10-25 --receipts reports/local-automation-state/receipts --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --case-ledger reports/local-automation-state/cases/ledger.json --json
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --format markdown --language zh
python .agents/skills/local-actuarial-flow/scripts/local_flow.py report --date 2026-10-25 --receipts reports/local-automation-state/receipts --format markdown --language en
```

`report` 默认输出 JSON；`--json` 保持兼容，JSON 数据与 schema 不受语言选项影响。Markdown 默认中文；`--language zh|en` 只选择人类可读日报的语言，不改变汇总范围或状态。语言优先级为：显式 CLI 参数 > 用户明确指定的报告语言 > 对话语言 > 中文回退。预算暂停中文用语固定为“30次访问预算用完，下次继续”，英文为 “The 30-request budget is exhausted; continue next time.” `--format markdown` 输出日报，开头先给执行结论、可见产出、主要阻塞/预算暂停和建议。提供 `--runtime-output <同日run-daily.json>` 时，摘要只把与当前运行精确匹配的非预览回执计作本次结果；旧回执、预览、监控项和保留项不得算成本次采集成功。未提供运行清单时，摘要可汇总同日回执中的已知数量和错误，但必须标明本次运行覆盖未知。建议应区分计划内未运行与已运行但缺回执：前者核实是否应执行，后者核对当前回执。实际来源/转换/目标错误应与纯预算暂停分开呈现，建议仅供后续核查，不表示已提高预算、清理数据或改变发布规则。运行证据只补充执行可见性，不写 case ledger，也不能关闭故障。日报按美东 09:00 触发时由调用端提供前一自然日。没有运行明细时，缺回执不能证明未运行；缺字段是未知，不是成功或零。AI 发布入库确认与两端可搜索状态分开记录。回执格式、Case ledger 的原子更新及状态定义见每日合同。

单站 HTTP 请求默认上限为 30；只有瑞士监控项可通过 `run-site --request-limit 60` 显式提高到 60。达到请求上限会留下可恢复游标并报告 `partial`。只有纯预算暂停时不创建失败研究 case；同时出现的真实站点/文章错误仍保留并进入常规研究队列。来源复用/目标重试最多处理 24 篇，模型富信息工作仍最多 8 篇；超出部分会在后续运行轮转处理。

CIA、CCA 与法国站只在尚未处理的 frontier 后缀中稳定优先有效公开附件；已处理前缀、失败历史与请求预算保持不变。瑞士及其他站点维持原队列顺序。

## 本机运行入口

跟踪源码 `ai_actuarial.local_collection_runtime` 提供 bounded live collection、Hub live-capture 入库、Luna 双语分类/日期补全、国内与海外目标增量同步、独立回执与任何阶段的恢复。只使用单独的 `config.local.json`，不要把连接文件路径或主机地址写入共享例子。操作命令、试跑顺序和范围限制见 [本机运行指南](references/runtime.zh-CN.md)。该 CLI 不安装或启用计划任务；现有 06:00/09:00 automation 由外部 owner 单独管理。

## AI 发布与文章日期

只有 Hub 有序 `categories[0].key == "AI"` 且 `source_primary_category == "AI"` 的精确版本可进入 China/Overseas AI serving bucket。第二至第四类及其原始证据保留顺序并随目标 metadata 保存；不得因为任一后续类别是 AI 就发布，也不得改写 Hub primary metadata 来取得发布资格。实时文章、缓存对象、历史查询/count、目标 payload 与 pending retry 必须使用同一首类规则。

Hub reader 会原样返回既有注释；少数历史注释的首类 `evidence` 为空。只在精确版本/Markdown/result-digest 绑定已验证的既有记录回填或重试时保留这个空数组，不得补造引文。新生成或新写入的分类仍必须有 1–3 条通过 Markdown 核验的引文，后续类别也必须有证据。

目标 `files.published_time` 只投影已验证 `date_facts.publication_date.value`，保留 year/month/day 精度。Hub 的日期语义名为 `publication`、`revision`、`document_version`；原样保留这些字段，但只从 `publication_date` 槽位投影。unknown/null 保持新记录的日期为空，不用 revision、document-version、事件、crawl 或 HTTP Last-Modified 回退。对现存文件做 metadata backfill 时保留原 zh/en 包和 extra fields；Hub 日期 unknown 时保留已有目标日期并报告为未验证的 legacy 值。回填与清理命令、exact manifest 及 resumable index/Ready 合同见 [本机运行指南](references/runtime.zh-CN.md)。

真实失败的修复闭环：用回执 case ID 和证据复现；判断是临时网络/服务问题还是 DOM、URL、分页、CLI、过滤器/分类规则变更；对本仓库可维护的实际脚本、playbook 或 skill 做最小修改；跑聚焦测试和低流量真实验证，再交 fresh reviewer；下一日用新的真实回执确认恢复。每日日报后最多研究两项；同一 case 和证据不得每天重复研究。外部源仍不可用时保留未解决和退避建议。不得编辑 skill/报告把状态改成成功，也不得修改 ignored 历史快照冒充已部署修复。

入口响应、离线测试、历史 `status.json` 和计划项都不是采集回执。采集内容入库、两站增量发布及适配器若尚未有真实回执，必须明确写阻塞，不能声称完成。运行需要 Python 3.10+ 与 `America/New_York` 时区数据；Windows 缺失时在使用的 Python 环境安装 `tzdata`。
