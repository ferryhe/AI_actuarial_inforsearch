# 开发日志 — 2026-03-06

**分支**: `feature/ui-model-from-aiconfig-and-crawl-analysis`  
**作者**: GitHub Copilot + Ferry He  
**时间**: 2026-03-06

---

## 工作摘要

本次提交包含两个独立但同属一个 feature 分支的改动：

1. **UI 改进**：将 Catalog / Chunk 任务弹窗的 Provider 下拉框改为只读展示，统一从 AI Config 读取已配置的模型，消除重复配置。
2. **爬虫核心修复**：修复 `crawler.py` 中因 `is_relevant` 双重门槛导致文件被漏爬的 bug，新增 `allow_url_patterns` 字段，更新 SOA AI Bulletin 站点配置。

---

## 变更详情

### 1. Catalog / Chunk UI 模型选择简化

**背景**：用户在 Settings → AI Config 设置好 catalog / chunk 模型后，Catalog 批量任务弹窗（`tasks.html`）和文件详情页弹窗（`file_view.html`）仍显示独立的 Provider 下拉框，导致需要重复配置且容易不一致。

**修改内容**：

| 文件 | 修改说明 |
|------|----------|
| `ai_actuarial/web/templates/tasks.html` | `catalog-provider-select` dropdown → hidden input + 只读展示段，`loadCatalogProviders()` 改为读 `/api/config/ai-models` |
| `ai_actuarial/web/templates/file_view.html` | `file-catalog-provider` dropdown → hidden input + 只读展示段，`loadFileCatalogProviders()` 完全重写（~60行 → ~20行）|
| `ai_actuarial/web/templates/modals/chunk_profile_management_modal.html` | 移除硬编码 Chunk Model 下拉框（gpt-4/gpt-4o/gpt-3.5-turbo），改为提示文字 |
| `ai_actuarial/web/static/js/i18n.js` | 新增6个双语 i18n key：`fv.catalog_ai_config_info`、`tasks.catalog_ai_config_info`、`cp.model_auto_inherit` |

**效果**：Provider 信息直接从 `/api/config/ai-models` 拉取，展示格式如 `OpenAI — gpt-4o-mini`，`provider` 值通过 hidden input 传给后端，不再允许前端独立修改。

---

### 2. 爬虫核心 Bug 修复：`is_relevant` 双重门槛

**背景**：测试目标为 SOA AI Bulletin 页面，预期应下载 8 个 PDF 文件，实际全部漏掉。

```
目标页: https://www.soa.org/resources/research-reports/2025/research-ai-bulletin/
示例文件（漏掉）: 2026-03-ait170-ai-bulletin.pdf
```

**根本原因（3层叠加）**：

1. **`is_relevant` 误判**：页面写的是 "AI" / "Actuarial Intelligence"，而 `keywords` 要求 "artificial intelligence" 全词 → `is_relevant = False`
2. **文件下载被拦**：旧逻辑 `not (is_relevant OR link_matches_keywords)` — 两个都 False → 所有 PDF 被 skip
3. **子页面入队被拦**：旧逻辑 `if depth+1 <= max_depth and is_relevant` — `is_relevant=False` → 月度子页面永不入队，depth=2 的 PDF 永远找不到
4. **附加**：`exclude_keywords` 含 12 个过宽词（`edu`、`exam`、`fall`、`spring` 等），误伤合法研究 URL
5. **附加**：`cli.py` 和 `app.py` 构建 `SiteConfig` 时漏传 `content_selector` 和 `allow_url_patterns`

**修改内容**：

#### `ai_actuarial/crawler.py`

```python
# SiteConfig 新增字段
allow_url_patterns: list[str] | None = None

# crawl_site() 编译正则
allow_patterns = [re.compile(p) for p in (cfg.allow_url_patterns or [])]

# 文件下载过滤（解除 is_relevant 门槛，有 allow_patterns 时完全放行）
# 旧：if keywords and not (is_relevant or self._link_matches_keywords(...)):
# 新：
if not allow_patterns and keywords and not self._link_matches_keywords(link, link_text, keywords):
    continue

# 子页面入队（移除 is_relevant 要求，有 allow_patterns 时按正则过滤范围）
# 旧：if depth + 1 <= cfg.max_depth and is_relevant:
# 新：
if depth + 1 <= cfg.max_depth:
    if allow_patterns:
        if any(p.search(link) for p in allow_patterns):
            page_queue.append((link, depth + 1))
    else:
        page_queue.append((link, depth + 1))
```

#### `ai_actuarial/cli.py`

```python
# SiteConfig 构造器补传两个之前漏传的字段
content_selector=s.get("content_selector"),
allow_url_patterns=s.get("allow_url_patterns"),
```

#### `ai_actuarial/web/app.py`

```python
# scheduled collection SiteConfig 补传
allow_url_patterns=s.get('allow_url_patterns'),
```

#### `config/sites.yaml`（SOA AI Bulletin 条目）

```yaml
# 旧
max_depth: 1
max_pages: 80
content_selector: 'main, article, ...'
exclude_keywords: [curriculum, edu, exam, fall, newsletter, solution, solutions, spring, ...]  # 12条

# 新
max_depth: 2
max_pages: 100
allow_url_patterns:
  - /resources/research-reports/2025/research-ai-bulletin
  - /globalassets/
exclude_keywords:
  - newsletter
  - news letter
```

**设计思路**：`allow_url_patterns` 用 URL 正则白名单替代关键词控制爬取范围，职责更清晰，不会被"AI"/"Actuarial Intelligence"等同义词误判。有 `allow_url_patterns` 时，文件下载不再需要关键词匹配，直接信任 URL 路径。

---

### 3. 爬虫逻辑分析文档（新建）

新增 `docs/20260306_webcrawl_logic_analysis.md`，内容包含：

- BFS 完整流程图
- 各机制详解（链接发现、文件格式判断、两层关键词过滤、排除词、去重逻辑）
- 根因分析：SOA AI Bulletin 文件漏爬的3层原因
- 7条改进建议（解耦关键词过滤、URL 白名单、精确化排除词、Content-Type 感知等）
- 与 Scrapy / Crawlee / Firecrawl 的特性对比表
- 立即可操作的配置调优示例

---

## 待测试

- [ ] Quick Site Check：`https://www.soa.org/resources/research-reports/2025/research-ai-bulletin/`，期望下载 8 个 AI Bulletin PDF（含 `2026-03-ait170-ai-bulletin.pdf`）
- [ ] 验证 tasks.html / file_view.html 的 provider 展示读到正确的 AI Config 值
- [ ] 验证 chunk profile 创建弹窗不再显示 chunk model 下拉框

## 下一步计划

- Phase 3：对其他重点站点（SOA 主站、IAA、CAS）补充 `allow_url_patterns` 和 `content_selector`
- 清理 SOA 系列站点中过宽的 `edu`/`exam` 排除词
