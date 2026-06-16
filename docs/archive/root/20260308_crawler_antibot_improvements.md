# 爬虫反反爬改进说明

**时间**：2026-03-08

---

## 问题背景

多个主要精算协会网站（SOA、CAS、IAA、IABA、AAA、Swiss）因反爬虫机制而返回 0 文件：

| 网站 | 抓取结果 | 问题 |
|---|---|---|
| SOA (Society of Actuaries) | 0 文件 | 被反爬虫拦截 |
| CAS (Casualty Actuarial Society) | 0 文件 | 被反爬虫拦截 |
| IAA (国际精算协会) | 0 文件 | 无法访问 |
| IABA | 0 文件 | 被反爬虫拦截 |
| AAA (美国精算学会) | 1 页，0 文件 | 被反爬虫拦截 |
| Swiss Association | 561 页，0 文件 | 页面多但无文件 |

---

## 解决方案

### 方案一：curl_cffi Chrome 浏览器指纹模拟

**文件**：`ai_actuarial/crawler.py`、`requirements.txt`

将 `curl_cffi` 作为首选 HTTP 后端，模拟真实 Chrome 浏览器指纹，从而绕过大多数基于 User-Agent / TLS 指纹的反爬虫检测。失败时自动降级回 `urllib.request`。

```python
# _request() 和 _download_file() 均使用以下模式
resp = _curl_requests.get(url, impersonate="chrome", ...)
resp.raise_for_status()  # 4xx/5xx 时抛出异常，触发 urllib 降级
```

**关键细节**：
- `raise_for_status()` 确保 403/404 等错误响应不被当作有效内容处理
- 下载失败时，临时 `.part` 文件会被安全清理，然后再尝试 urllib 降级
- `curl_cffi` 不可用时，代码自动降级，无需修改配置

**依赖**：`requirements.txt` 新增 `curl_cffi>=0.7.0`

---

### 方案二：站点级搜索查询（绕过直接爬取）

**文件**：`ai_actuarial/crawler.py`（`SiteConfig`）、`ai_actuarial/cli.py`、`ai_actuarial/web/app.py`、`config/sites.yaml`

`SiteConfig` 新增 `queries` 字段，允许为每个网站配置专属的搜索查询，通过搜索引擎间接发现 PDF，绕过网站的直接访问限制。

#### 配置示例（`config/sites.yaml`）

```yaml
- name: Society of Actuaries (SOA)
  url: https://www.soa.org/
  queries:
    - site:soa.org artificial intelligence report filetype:pdf
    - site:soa.org machine learning research filetype:pdf
    - site:soa.org generative ai filetype:pdf
    - site:soa.org large language model filetype:pdf
```

已为以下 6 个问题网站配置站点级查询：

| 网站 | 查询数量 |
|---|---|
| International Actuarial Association (IAA) | 2 |
| International Association of Black Actuaries (IABA) | 2 |
| Society of Actuaries (SOA) | 4 |
| Casualty Actuarial Society (CAS) | 3 |
| American Academy of Actuaries (AAA) | 3 |
| Swiss Association of Actuaries | 3 |

#### 触发时机

- **CLI**（`cmd_update`）：爬取每个站点后立即执行站点级查询，需 `search.enabled: true`
- **Web 应用**（`scheduled` collection）：主爬取完成后，遍历有 `queries` 的站点执行搜索

---

## 修复的 Code Review 问题

| 问题 | 修复 |
|---|---|
| `_request()` 未验证 HTTP 状态码 | 添加 `resp.raise_for_status()`，4xx/5xx 触发 urllib 降级 |
| `_download_file()` 未验证 HTTP 状态码 | 同上，防止将错误 HTML 存储为有效文件 |
| CLI 站点查询缺少 `exclude_prefixes` | `SiteConfig` 构建时传入 `exclude_prefixes=site.exclude_prefixes or []` |
| Web 应用站点查询缺少 `exclude_prefixes` | 传入 `exclude_prefixes=sc.exclude_prefixes or site_config['defaults'].get('exclude_prefixes', [])` |
| Web 应用站点查询结果未计入 `CollectionResult` | 捕获 `scan_page_for_files()` 返回值，更新 `result.items_found` 和 `result.items_downloaded` |

---

## 全局搜索改进

`cli.py` 的全局搜索调用新增 `serper_key` 和 `tavily_key` 参数，之前这两个搜索引擎在全局搜索中被遗漏了。

---

## 测试

所有 8 个现有测试用例通过，无 CodeQL 安全告警。

```
tests/test_crawler_allow_patterns.py  8 passed
```

---

## 生效前提

站点级查询和搜索降级需要至少配置一个搜索 API 密钥：

| 环境变量 | 搜索引擎 |
|---|---|
| `BRAVE_API_KEY` | Brave Search |
| `SERPAPI_API_KEY` | SerpAPI (Google) |
| `SERPER_API_KEY` | Serper.dev (Google) |
| `TAVILY_API_KEY` | Tavily |
