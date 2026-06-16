# Webcrawl 逻辑分析与建议

**创建时间**: 2026-03-06  
**作者**: GitHub Copilot  
**对应代码**: `ai_actuarial/crawler.py`，`config/sites.yaml`

---

## 1. 爬虫如何工作（整体流程）

### 1.1 入口与初始化

`crawl_site(cfg: SiteConfig)` 是核心方法，流程如下：

```
1. 检查 stop_check 信号
2. 尝试读取 {site_url}/sitemap.xml
   ├─ 成功 → 用 sitemap 里的 URL 作为初始队列（最多 max_pages 条）
   └─ 失败 → 用 cfg.url 作为唯一起点
3. BFS 宽度优先循环（deque）
4. 每个 URL 处理完后 sleep_with_jitter(delay_seconds)
```

### 1.2 BFS 主循环逻辑（`crawl_site` 核心）

```
while page_queue 非空 AND pages_fetched < max_pages:
    (url, depth) = queue.popleft()
    
    ① 跳过检查:
       - 已在 seen_pages → skip
       - 不在同域名 (same_domain) → skip
       - _should_exclude_url(url) → skip
    
    ② 发起 HTTP 请求，记 pages_fetched += 1
    ③ mark_page_seen(final_url)  # 去重记录
    
    ④ 如果 final_url 是文件 URL（扩展名匹配）:
       - file_exists(url) → skip（URL 去重）
       - _download_file() → 临时文件 + SHA256
       - _should_exclude_url(final_url 或 filename) → skip
       - _handle_file() → SHA256 去重 → 存DB
       - continue（不再解析 HTML）
    
    ⑤ 否则（HTML 页面）:
       - is_relevant = any(keyword in page_text)    ← 重要判断
       - 若 collect_page_content AND is_relevant → 保存页面文本
       - 提取所有链接 _extract_links(html, content_selector)
       
       ─ 对每个 (link, link_text):
         ● 排除检查（URL/文件名 keyword + prefix）
         ● 若 link 是文件 URL:
             ┌ keywords 存在 AND NOT (is_relevant OR link_matches_keywords)
             │  → skip【关键过滤点！】
             └ file_exists() → skip
             下载并保存
         ● 若 link 是页面 URL:
             └ depth+1 <= max_depth AND is_relevant → 入队列
                                          ↑【关键判断：页面必须相关才继续爬】
```

---

## 2. 各机制详解

### 2.1 链接发现（`_extract_links`）

- 正则匹配所有 `<a href="...">text</a>` 标签
- 如果配置了 `content_selector`，先用 BeautifulSoup 将 HTML 缩减到匹配元素（需安装 bs4）
- 降级：如果 bs4 不可用，`content_selector` 被忽略，回退到全页面匹配
- URL 标准化：相对路径 → 绝对路径

### 2.2 文件格式判断（`_is_file_url`）

```python
def _is_file_url(self, url: str, exts: set[str]) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in exts)
```

- **纯 URL 路径扩展名匹配**，不检查 Content-Type
- 默认扩展名：`.pdf .doc .docx .ppt .pptx .xls .xlsx`
- 通过 `sites.yaml` 的 `file_exts` 字段覆盖

**风险**：某些网站的 PDF 链接不带扩展名（如 `/download?id=123`），会被漏掉。

### 2.3 关键词过滤机制（两层）

#### 层 1：页面内容相关性（`is_relevant`）
```python
page_text = html_to_text(html).lower()
is_relevant = any(k in page_text for k in keywords) if keywords else True
```
- 检查**整个页面文本**是否包含任意关键词
- `is_relevant=True` → 允许：  
  1. 保存页面内容（若 `collect_page_content`）  
  2. 将子页面加入爬取队列（`depth+1 <= max_depth`）

#### 层 2：链接级关键词匹配（`_link_matches_keywords`）
```python
def _link_matches_keywords(self, url, text, keywords):
    base = os.path.basename(url)
    hay = f"{url} {base} {text}".lower()
    return any(k in hay for k in keywords)
```
- 检查 **链接 URL + 文件名 + 链接文本** 是否包含关键词

#### 文件链接下载决策（组合逻辑）：
```python
if keywords and not (is_relevant or self._link_matches_keywords(link, link_text, keywords)):
    continue  # 跳过此文件
```
**⚠️ 只有满足以下任一条件才会下载文件：**
1. 当前页面文本包含关键词（`is_relevant=True`），OR
2. 文件链接的 URL/文本本身包含关键词

### 2.4 排除词过滤（`exclude_keywords` / `exclude_prefixes`）

排除词在以下 **多个位置** 生效：

| 位置 | 说明 |
|------|------|
| ① BFS 循环头部 | 过滤待爬页面 URL |
| ② 下载后重定向 URL | final_url 的二次检查 |
| ③ 链接遍历时 | 每条链接按排除词检查 |
| ④ `_handle_file` 内部 | 文件名的 exclude_keywords 检查（第二道防线） |
| ⑤ `_should_exclude_url` | 统一检查 URL 关键词 + 文件名前缀 |

注：排除词是**子字符串匹配**（非全词匹配），如 `exam` 会匹配 `examination`。

### 2.5 与内部系统的对比/去重

```python
# URL 去重（已爬页面）
seen_pages: set[str]  # 本次爬取内存 set

# 文件 URL 去重（跨次爬取）
storage.file_exists(url)  # 检查 DB URL

# 内容去重（防止同文件多URL）
storage.file_exists_by_hash(sha256)  # 检查 DB SHA256

# 软链接复用（相同内容）
storage.get_blob(sha256)  # 若 blob 存在则硬链接
```

### 2.6 配置参数与效果对照

| 参数 | 类型 | 作用 |
|------|------|------|
| `max_pages` | int | 最大**页面请求次数**（包含 HTML + 文件下载），默认 200 |
| `max_depth` | int | BFS 最大深度，从 seed URL 算起，默认 2 |
| `delay_seconds` | float | 请求间隔（会加随机抖动），默认 0.5s |
| `keywords` | list[str] | 关键词列表（低字母匹配），为空则无过滤 |
| `file_exts` | list[str] | 下载文件的扩展名，默认 pdf/doc/docx/ppt/pptx/xls/xlsx |
| `exclude_keywords` | list[str] | URL/文件名排除词（命中即跳过） |
| `exclude_prefixes` | list[str] | 文件名前缀排除（如 `book` 跳过 `book_*.pdf`） |
| `collect_page_content` | bool | 是否将 HTML 页面文本保存为 Markdown |
| `content_selector` | str | CSS 选择器，仅从匹配区域提取链接（需 bs4） |

---

## 3. 为什么改了逻辑之后找不到文件了

### 3.1 根本原因：双重关键词门槛

当前逻辑对文件的过滤是 **AND 逻辑**（同时满足两个条件之一才能下载）：
- 页面要么相关（`is_relevant`），要么链接本身带关键词

**常见失败场景：**

```
场景 A：目录/索引页
  - SOA 的研究列表页（.../research/topics/）本身只有导航文字
  - is_relevant = False（页面无 AI/ML 关键词）
  - PDF 链接文字是"Download"或文件名 "2024_AI_report.pdf" 
    → link_matches_keywords 可能匹配，但若文件名是 "research-123.pdf" → 漏掉！

场景 B：子页面被拦截
  - 若导航中间页（depth=1）is_relevant=False
  - 该页面下的子页面（depth=2）永远不会被加入队列
  - 实际目标 PDF 在 depth=2 的页面上 → 永远找不到

场景 C：排除词过于宽泛
  - "exam" 也匹配 "examination"、"example"、"examiner"
  - "education" 也匹配 URL 路径含 /education/ 的合法研究页
```

### 3.2 具体分析：SOA 案例

当前 SOA 的 `exclude_keywords` 包含 `edu`，这会导致：
- SOA 的 URL `/research/education-and-professional-development/ai-survey/` 会被排除
- 因为 URL 中含有 `edu`（`examination` 同理）

### 3.3 max_pages 不足

`max_pages` 默认 200，但 SOA 首页 `/soa.org/` 可能需要爬 500+ 页才能覆盖所有 AI 相关研究。若 `pages_fetched >= max_pages` 时还有未探索的研究子目录，后面的文件都会错过。

---

## 4. 建议与改进方案

### 建议 1：解耦「关键词过滤」与「页面爬取决策」（高优先级）

**现状问题**：子页面只在 `is_relevant` 时才入队，用关键词作为爬取门槛太严格。

**建议改法**：
```python
# 当前（过于严格）
if depth + 1 <= cfg.max_depth and is_relevant:
    page_queue.append((link, depth + 1))

# 建议（总是爬子页面，只在下载时过滤）
if depth + 1 <= cfg.max_depth:
    page_queue.append((link, depth + 1))
```
这样爬取更全面，只在**下载文件时**用关键词过滤。  
代价：会爬更多页面，需相应增加 `max_pages`。

### 建议 2：放宽文件下载的关键词要求

```python
# 当前（要求满足其一）
if keywords and not (is_relevant or self._link_matches_keywords(link, link_text, keywords)):
    continue

# 建议选项 A：仅用链接级匹配（不要求页面本身相关）
if keywords and not self._link_matches_keywords(link, link_text, keywords):
    continue

# 建议选项 B：完全去掉关键词门槛，仅依赖 exclude 过滤
# （适合已用 URL 路径白名单的场景）
```

### 建议 3：使用 URL 路径白名单替代关键词翻页

参考 Scrapy / Crawlee 的做法：用 `allow_url_patterns`（正则白名单）控制爬取范围，比关键词更精准：

```yaml
# 建议新增字段（需代码支持）
sites:
- name: Society of Actuaries (SOA)
  url: https://www.soa.org/
  allow_url_patterns:
    - /research/
    - /resources/research-reports/
    - /topics/artificial-intelligence
```

### 建议 4：精确化排除词（避免误伤）

当前 `exam` 会匹配 `examination`、`example`；`edu` 会匹配合法研究 URL。建议：

```yaml
# 当前（误伤风险高）
exclude_keywords:
  - edu
  - exam

# 建议（用更具体的词或路径模式）  
exclude_keywords:
  - /exam/
  - /education/professional-development
  - newsletter
  - brochure
```

> 注意：当前排除词是子字符串匹配，建议在代码层面支持全词边界(`\b`)或路径前缀匹配。

### 建议 5：增加 `content_selector` 覆盖（中优先级）

很多学术站点的研究文章链接都在特定 `<div class="content">` 或 `<main>` 里，nav / header / footer 里的链接大多是无关导航。已配置 `content_selector` 的站点（如 SOA AI Bulletin）效果更好，建议对主要站点都配上：

```yaml
- name: Society of Actuaries (SOA)
  content_selector: 'main, .content-area, article, [role="main"]'
```

### 建议 6：增大重点站点的 max_pages 和 max_depth

```yaml
- name: Society of Actuaries (SOA)
  max_pages: 500   # 从 200 → 500
  max_depth: 3     # 从 2 → 3（覆盖更深层研究页）
```

### 建议 7：Content-Type 感知的文件发现

某些站点用 URL `/download?id=123` 提供 PDF（URL 无扩展名）。建议增加 HEAD 请求检测，或检查链接的 `rel="document"`, `type="application/pdf"` 属性：

```python
# 在 _extract_links 中额外检查 link type 属性
match_type = match.group('type')  # type="application/pdf"
if match_type and 'pdf' in match_type.lower():
    # treat as file link even without extension
```

---

## 5. 与流行爬虫框架的对比参考

| 特性 | 当前爬虫 | Scrapy | Crawlee (Node.js) | Firecrawl |
|------|----------|--------|------------------|-----------| 
| 爬取策略 | BFS（手动 deque） | Request Queue | RequestQueue | 托管云爬虫 |
| URL 过滤 | 关键词子字符串 | 正则 `allow`/`deny` | `glob`/`regexp` | AI 语义过滤 |
| 文件发现 | URL 扩展名 | MIME + 扩展名 | 可自定义 | 自动 |
| 动态页面 | ❌ 不支持 JS | 需 Splash 插件 | 内置 Playwright | 内置 Playwright |
| 深度控制 | 硬 max_depth | `DEPTH_LIMIT` | globs | 托管 |
| 并发 | 单线程序列 | 异步多并发 | 异步多并发 | 云端 |
| 内容提取 | trafilatura | Selector | Cheerio | LLM |

**核心建议**：当前爬虫是单线程同步，适合小规模爬取。若需大规模，考虑引入 `aiohttp` + `asyncio` 或集成 Scrapy。

---

## 6. 推荐的配置调优（立即可操作）

针对当前找不到文件的问题，建议在 `sites.yaml` 做以下调整：

```yaml
# 对 SOA AI 专题页（已有，需调整）
- name: SOA AI Topic Landing (Focused)
  url: https://www.soa.org/research/topics/artificial-intelligence-topic-landing/
  max_pages: 200      # 保持不变
  max_depth: 4        # 2 → 4，确保能进入子研究页面
  content_selector: 'main, .content-area, [role="main"]'   # 新增
  keywords:
  - artificial intelligence
  - machine learning
  - generative ai
  - large language model
  # 注意：keywords 为空则无关键词过滤，全抓
  exclude_keywords:
  - newsletter
  - brochure
  # 移除 edu、exam、spring、fall，太宽泛
```

同时建议在代码层面修改：将子页面入队的 `is_relevant` 判断放宽为可配置选项（`require_relevance_for_subpages: bool`），默认关闭。
