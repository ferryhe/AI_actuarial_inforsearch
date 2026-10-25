# 32 个监控项的脚本审计与轮换建议

口径：这里的 **32** 是配置中的监控项/site ID，不是 32 个唯一域名或 32 个机构。入口 hostname 去重为 **29**；SOA 和 CIA 各有专题条目，CAS 还跨期刊 hostname。每项从原仓库忽略的证据快照 `reports/local-automation-20261025/audit-source/workspace/sites/<site_id>/` 静态审读 `collect.py`、`playbook.md`、`filters.json`、`status.json`；采集器只能证明被读的代码行为，不代表本机完整运行成功。这些快照不属于新 clone 中可直接执行的源码。旧 `status.json` 是历史记录，不是本次轮次回执。源清单映射和原型目录文件都已按 32 项对齐，全部 filter regex 可编译。

入口探测是另一个证据面：每个监控项仅探测一个入口 GET，没有执行站点 collector、发现列表、下载文件或写库。30 项返回了网页响应；IFoA 配置的 `www.actuaries.org.uk` 返回 HTTP 503，但另测的规范无 `www` `https://actuaries.org.uk/` 返回响应；Istituto 为 placeholder/demo，当前 hold。IAA 主页可达，但这不等于它的 sitemap 已完整枚举。任何入口 `200` 都不能作为附件、分页、正文覆盖或 Hub 入库的验收。

轮换组只为每两小时的离线 `plan` 平均摊开四项。`collect` 是待实现执行端的全流程候选动作；`monitor_only` 只做低频结构监控且不下载、不入库、不进 AI 发布；`hold` 只显示覆盖位置，不执行。IABA 和 EAA 为 monitor-only，Istituto hold。各自具体到期节奏目前没有持久游标实现；不要把 16 小时组周期误读成每项都需完整抓取。

| 组 | site ID / 监控项 | 计划动作 | 对既有脚本与 playbook 的处理建议 |
|---|---|---|---|
| 1 | `iaa` / International Actuarial Association | collect | `collect.py` 目前把外部搜索/URL 转成候选；不可永久限制为 search-only，先用本机 Crawler 完整验证 sitemap 和真实枚举。 |
| 1 | `iaba` / International Association of Black Actuaries | monitor_only | 不进入每日下载或 AI 流程；低频复核 sitemap，有新增时再按同一 URL/SHA Hub 合同处理。 |
| 1 | `soa` / Society of Actuaries | collect | 低频扫主题链；与两个 SOA focused 监控项按规范 URL 去重，避免同一页面重复入库。 |
| 1 | `soa-ai-topic-landing` / SOA AI Topic Landing | collect | 修总请求数上限，再并入 SOA 父项周期并按 URL 去重。 |
| 2 | `soa-ai-bulletin-focused` / SOA AI Bulletin | collect | 并入 SOA 父站周期并按 URL 去重；保留来源页身份以区分发现来源。 |
| 2 | `cas` / Casualty Actuarial Society | collect | 每次传 `--refresh` 更新 sitemap；报告只计可采文件并拆分 research 页面，不把历史 `status.candidates` 当文件数。 |
| 2 | `aaa` / American Academy of Actuaries | collect | 保留 REST 全量核对并按 URL/SHA 幂等去重；`--since` 当前未约束 REST AI-resource 列表，增量上线前补更新时间过滤。 |
| 2 | `cia-ica` / Canadian Institute of Actuaries | collect | 候选写入前排除 `/private-files/`；`members_only` 标志会漏报，filters 路径规则需接到 collector。 |
| 3 | `cia-research-publications` / CIA Research & Publications | collect | 与父项候选 URL 完全重叠；合并或仅跑父项未覆盖栏目，并在导出前过滤 `/private-files/`。 |
| 3 | `cca` / Conference of Consulting Actuaries | collect | 固定 hub 重扫并拆开 research/uncertain；调整按关键词生效的全局 `proceedings` 排除，避免错删经确认的会议录资料。 |
| 3 | `aae` / Actuarial Association of Europe | collect | 保留 sitemap `lastmod` 作为变化线索；`/paper/` 只能召回，最终分类后才决定 AI 发布。 |
| 3 | `eaa` / European Actuarial Academy | monitor_only | 保留低频 sitemap 结构检查，核对跨域 URL；旧 research-only 规则要按已批准 Education/Events 范围校准，不能直接排除培训、教育类资料。 |
| 4 | `ifoa-uk` / Institute and Faculty of Actuaries | collect | 配置入口换成无 `www` canonical；保留旧 `www` PDF URL 作别名；每批上限 30 页并合并分页结果。 |
| 4 | `france` / Institut des Actuaires | collect | 逐批使用 `hub-limit` / `hub-skip` 并持久化 offset；论文详情页另接正文采集。 |
| 4 | `dav` / German Association of Actuaries | collect | 用 sitemap `lastmod` 驱动 `--since`；AI 路径正则只是召回预筛，最终按摘要/正文分类。 |
| 4 | `swiss-association-of-actuaries` / Swiss Association of Actuaries | collect | 低频最多抓 5 页；AI 演讲需有 core/context，或显式 `ai_related`，不能由 URL 单独定发布。 |
| 5 | `italy` / Ordine Nazionale degli Attuari | collect | 接通或移除当前未生效的 `--depth`；补 `/documenti/sezioni-statiche` 种子，低频轮询。 |
| 5 | `istituto-italiano-degli-attuari` / Istituto Italiano degli Attuari | hold | 探测返回 placeholder/demo；不进日常下载或发布，低频确认是否恢复或改用权威来源。仍保留组内位置和 coverage。 |
| 5 | `spain` / Instituto de Actuarios Españoles | collect | 修 canonical host；保存时间和分页游标后再增量过滤，继续复用 REST/sitemap 枚举。 |
| 5 | `australia` / Actuaries Institute | collect | 保留 `practiceAreas` / `tags` 作为候选召回字段；当前 `AI_RE` 未用于 candidates，最终 AI 标记需下游正文分类，再按 URL/SHA 去重。 |
| 6 | `iai` / Institute of Actuaries of India | collect | 核心 hub 每轮轻量检查；杂志按年份轮换，记录 URL/version，下载、抽取后由内容分类决定 AI 发布。 |
| 6 | `iaj` / Institute of Actuaries of Japan | collect | 低频轮询研究栏目，按 URL 增量；脚本发现的 page 要另接本机正文采集。 |
| 6 | `institute-of-actuaries-of` / Institute of Actuaries of Korea | collect | 配好本机项目 Python/PYTHONPATH；覆盖 `intlTrend` 最多 15 页或加 start-page 游标，正文页和附件需另接收集。 |
| 6 | `aict` / Actuarial Institute of Chinese Taipei | collect | 保持少量固定 hub 检查；`/re/` 被 playbook 标为 robots 禁止，未建立允许策略前不得抓对应候选；无 lastmod 游标。 |
| 7 | `caa` / China Association of Actuaries | collect | API 枚举与附件扫描分开计数；把确认附件接入 URL/标题候选管线。`filters.json` 当前不作用于 collector，历史 2 个候选不是脚本当轮产物。 |
| 7 | `ashk` / Actuarial Society of Hong Kong | collect | `collect.py` 外壳实际使用 `sudo docker`、固定容器及 `/tmp` 路径；需迁移为本机可配置调用/产物路径，再保持 `max-pages` 预算和统一 schema。 |
| 7 | `assa` / Actuarial Society of South Africa | collect | 建好本机 Python 项目路径；默认请求间隔 0.3 秒小于 playbook 的 0.5 秒，先修为不少于 0.5 秒，并有界分页。 |
| 7 | `task` / The Actuarial Society of Kenya | collect | 配置本机 Python/PYTHONPATH；单页低频扫描按 URL 去重。文件名/URL AI 规则只能召回候选，不能定最终发布。 |
| 8 | `ama` / Moroccan Association of Actuaries | collect | `--apply-filters` 只标记 take/skip，候选输出仍混有 skip；消费前按 take 建清单或修成过滤后产物，无日期游标。 |
| 8 | `iba-brazil` / Instituto Brasileiro de Atuária | collect | 配好本机 Python/PYTHONPATH 并验证完整枚举后，使用 REST 分页/时间增量；监控最多 15 页的上限，需确认无截断。 |
| 8 | `aca-colombia` / Asociación Colombiana de Actuarios | collect | 修复未接入的 `filters.json` include 白名单，再按 offset 分页；无 lastmod，执行轻量复扫并 URL/SHA 去重。 |
| 8 | `conac-mexico` / Colegio Nacional de Actuarios | collect | playbook 的 `--apply-filters` 不受支持，实际脚本也未写出 `--write-candidates` 文件；先修 CLI/产物合同，并让固定入口发现的正文页继续进入队列。 |

所有 32 项的 `collect.py` 只能发现/预分桶或转换候选，没有统一完成下载、Markdown、Hub 增量写入、双语摘要/分类、AI 双端同步和日报。IABA/EAA 等零候选仍可能是有效结果；不要因零候选触发无限重试。跨项同文必须用规范 URL 与原件 SHA 核验，不能以一条候选数等同新增版本数。
