# 每日中文长文解读

本功能只生成并保存有证据的稿件，不发布微信。`ready` 表示稿件结构、证据引用和国内阅读链接通过校验；对外发布前仍需编辑逐条核对事实。

使用现有任务入口 `POST /api/collections/run`，请求 `{"type":"article_interpretation"}`。后台串行处理最多三个规范来源。`GET /api/tasks/active`、任务历史和 `POST /api/tasks/stop/{task_id}` 沿用原生任务接口。停止允许当前篇完成，不启动下一篇。`{"type":"article_interpretation","retry_id":"<interpretation_id>"}` 只重试该稿，链接失败复用已经保存的正文。

CLI：`ai-actuarial article-interpretation run --json`、`retry <id> --json`、`get [id] --json`。CLI 使用既有 HTTP gateway 和身份，不另建凭据。只读 `GET /api/article-interpretations?file_url=<encoded canonical URL>` 或 `interpretation_id=<id>` 返回稿件、证据及 `is_current` / `reader_eligible`。正文更新、隐藏或删除使旧稿失去当前展示资格，历史正文保留。没有产物时返回空数组。展示端应只把 `reader_eligible=true` 的稿件作为当前解读，并原样消费 `china_article_url`。

文章详情页读取接口只返回当前可展示稿件的读者字段（标题、正文、生成时间、原文版本、出处和已核验国内链接）；失败记录、内部尝试与路由信息不进入该响应。中文界面按文章 URL 读取，英文界面不请求。复制与 Markdown/HTML 下载使用这条读者响应中的同一稿件版本。

作者只从当前原文 Markdown 的明确标题页署名结构中提取，并把原文片段与姓名一起放入同一次生成输入；模型返回值必须与这些姓名和顺序完全一致，之后才写入当前解读的 `references.authors`。无法识别的格式保持空，不从机构、正文、致谢或 URL 推测。读接口、详情页及两种导出只传递已保存作者。

每个环境默认没有自动计划。部署时由操作者在既有配置中确认环境，再通过现有计划入口配置。以下只是未启用的建议，仓库不创建或启用实际计划：

```yaml
article_interpretation:
  environment: china  # 本地/海外省略此项，默认 local
  china_base_url: https://aiactuary.cn
  timezone: Asia/Shanghai
scheduled_tasks:
  - name: Daily Article Interpretation
    type: article_interpretation
    enabled: false
    interval: daily at 10:00
    timezone: Asia/Shanghai
    params: {}
```

仅国内允许启用一个计划；注册和配置写入均检查这个约束。计划配置、时区和下一次执行时间由现有 schedule status 提供，轮次回执保存时区、观察到的下一次执行时间、来源、选文理由与失败原因。不要在海外开启镜像生成。首次部署应先确认当前国内数据库、读者路由及下一次执行时间，再由运维人员启用；本变更不执行部署。

选择按规范 `source_key` 固定顺序轮转，每源最多一篇；没有新文章时允许历史文章，日期不明保持不明。未删除、下载路径非空且目录状态正常是原生可见性合同。正文必须与 raw SHA 对应，且有研究/方法/案例的实质材料；通知、目录、缺正文、明显提取失败会记录跳过。标题、摘要不能替代正文。相同 raw SHA + Markdown SHA 的跨来源文献只生成一个成功稿；身份同时保留 canonical URL。旧成功版本不重新选择，改版保留前稿。

正文证据按章节分配，优先结论、局限、结果、方法、案例，保存每段原文字符区间、章节、段落及可识别页码，并记录未覆盖章节。输出逐段绑定证据，数字、公式、引文做原文匹配；推断及自行举例须明确标注。自动校验不能代替事实编辑。长文默认 1500–3000 中文字符，短稿必须说明原因。

生成每篇上限：选中文章后 240 秒、两次 provider 调用、每次 90 秒、累计 provider 180 秒；原文证据 24000 字符、全部输入 32000 字符、输出 6000 tokens。Chat 的 provider/model/credential 和已声明模型限制沿用 `ai_runtime`；长文有自己的输出预算，不沿用 Chat 短回答的 `max_tokens`。UTF-8 字节数作为未知 tokenizer 的保守 token 上界，配置只能降低这些上限。证据不足时跳过，不补写。SDK 内部重试和自动长度恢复关闭；超时不再重试。默认轮次最多六次 provider 调用、15 分钟，调用次数和耗时保存。生成预算按 raw SHA + Markdown SHA 的正文版本累计，跨尝试、提示词和模型路由不重置；手动生成重试只使用首次选文后 240 秒和原未完成轮次的剩余额度。原轮次已 complete 或 budget_exhausted 时，不再启动模型生成。任何一项耗尽即记录当前稿件 budget_exhausted，不再为它调用模型；单篇额度耗尽后推进下一来源，整轮仅因 900 秒、六次调用或全局凭据故障停止。已有正文且链接或当前版本校验失败时，可另做有界链接校验，独立保存回执，模型调用和耗时均为零，不改原生成轮次预算。

任务、API 和 CLI 入口仍为同步调用。解读请求独占一个异步 SDK 客户端与传输，复用 Chat 的模型参数构造规则；绝不关闭共享 Chat 客户端。一次请求的单调时钟绝对截止时间受剩余 90/180/240/900 秒额度限制，并在同一额度内预留取消、关闭时间。超时后等待请求取消和所属客户端关闭，再结束本次调用或进入下一来源；关闭失败则停轮。实际耗时包含清理，超时或未确认结束的调用至少扣除预留额度，不退还调用次数。周报原有超时路径保持原样。测试注入点须实现可协作取消的 `async generate(messages, *, deadline)`；不支持忽略取消的协程、阻塞同步生成器或将阻塞调用转移到后台线程。

配方 v3 为解读请求启用 JSON 对象模式；DeepSeek 解读请求关闭 thinking，将有限的 completion 预算留给正文。其他 provider 使用原有参数。配方版本、有效模式和 token 上限进入 fingerprint、逐次调用记录及轮次回执。Chat 路由和 Chat 自身的 thinking 行为沿用既有设置；旧配方未完成稿恢复时继续使用其保存的调用模式。

配方 v4 进一步把当期数据库 `canonical_sources` 的中英文名与来源键放入输入、coverage、fingerprint、出处和槽位回执。原文证据确有对应机构身份时才能原样引用规范名；pending 和非 active 来源不生成，不使用来源字符串作为机构名后备。读接口同时提供当前 Registry 名称。数字使用精确 Decimal 比较千分位、明确的数量级及币种；年/月/周/日/小时等时间单位分别比较，不暗中换算。歧义逗号只保留原拼写，未知格式拒绝；翻译标题、标签和概念不能以引号冒充原文直引。

原生 PostgreSQL migration `0005_article_interpretations.sql` 新增三张表，稿件与原文 Markdown、目录摘要分离。进程持有一个数据库会话锁，完成槽位和 cursor 在同一事务提交；重启优先恢复未完成轮次。同日重触发复用回执，显式 `round_key` 仅供 service 隔离测试；HTTP 和原生任务忽略客户端提供的轮次键及日历时区，固定使用 Asia/Shanghai 当日键。凭据故障停止并保留当前位置。崩溃时未返回的 provider 调用按预留时间和一次调用计费，不因重启刷新预算。

备份继续使用原生 schema dump/restore，包含所有新表；无需额外导出机制。恢复后用只读 API 核对正文、证据、版本及当前资格。回退时先停用该计划并停止任务，并保留当前数据库备份。旧应用会拒绝较高的 schema version；需要回退时，应把迁移前原生备份恢复到单独的空数据库后再切换配置，或使用兼容当前 schema 的修复版本。不要删除新增表、历史稿件或降低已记录的 schema version；恢复旧备份不是迁移后新数据的无损回退。
