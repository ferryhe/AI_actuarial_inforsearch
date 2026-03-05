# 开发日志 - 2026-03-05 - i18n PR Copilot Review 修复

## 📋 概述

- **任务**: 处理 PR #42 (feature/i18n-zh-en) 中 GitHub Copilot 自动审查提出的 6 条 Comment
- **分支**: `feature/i18n-zh-en`
- **日期**: 2026-03-05
- **状态**: ✅ 已完成

---

## ✅ 已完成任务

### 问题 1 & 5 — `scheduled_tasks.html`：`<label>` 含嵌套 tooltip `<i>` 元素

**Copilot 原始 Comment**:
> `data-i18n` is applied on a `<label>` that contains a nested tooltip `<i>` element. Since `i18n.js` translates by assigning `el.textContent`, this will wipe out the `<i>` node (and the tooltip). Wrap only the translatable text in a child `<span data-i18n="…">…</span>` and keep the `<i>` outside the translated node.

**问题根因**: `i18n.js` 的 `applyTranslations()` 对所有 `[data-i18n]` 元素直接执行 `el.textContent = t(key)`，这会**清空元素所有子节点**，导致 tooltip `<i>` 元素被删除。

**修复方式**: 将 `data-i18n` 从 `<label>` 移到包裹纯文本的内层 `<span>`，`<i>` 保留在外层。

**涉及改动** (`ai_actuarial/web/templates/scheduled_tasks.html`)：
- `sched.max_pages`（手动触发区）
- `sched.max_depth`（手动触发区）
- `sched.modal_max_pages`（Add/Edit 站点 Modal）
- `sched.modal_max_depth`（Add/Edit 站点 Modal）
- `sched.modal_keywords`（Add/Edit 站点 Modal）
- `sched.modal_excl_kw`（Add/Edit 站点 Modal）
- `sched.modal_excl_pfx`（Add/Edit 站点 Modal）

**修复前**:
```html
<label for="max-pages" data-i18n="sched.max_pages">Max Pages <i class="tooltip-icon" ...>(i)</i>:</label>
```

**修复后**:
```html
<label for="max-pages"><span data-i18n="sched.max_pages">Max Pages</span> <i class="tooltip-icon" ...>(i)</i>:</label>
```

---

### 问题 3 & 4 — `settings.html`：`<p>` 含 `<code>` 子元素 + `data-i18n`

**Copilot 原始 Comment**:
> `data-i18n` is applied to a help paragraph that includes `<code>.env</code>` markup. Since translations are applied via `textContent`, this will strip the `<code>` nodes and lose formatting.

**修复方式**: 将 `data-i18n` 移至包裹纯文字部分的 `<span>`，`<code>` 保留在外层 `<p>` 中。同时将 i18n.js 对应翻译字符串更新为仅含纯文字部分（不含 `<code>` 内容）。

**涉及改动** (`ai_actuarial/web/templates/settings.html`)：

**修复前**:
```html
<p class="module-help" data-i18n="stg.ai_filter_kw_help">
  Used to decide whether a document is AI-related (e.g. in AI-only flows). 
  This single list is also copied to <code>ai_keywords</code> to avoid drift.
</p>
```

**修复后**:
```html
<p class="module-help">
  <span data-i18n="stg.ai_filter_kw_help">Used to decide whether a document is AI-related (e.g. in AI-only flows). This single list is also copied to</span> <code>ai_keywords</code> to avoid drift.
</p>
```

同样修复了 `stg.model_providers_help`（含 `<code>.env</code>`）。

---

### 问题 6 — `settings.html`：`<label>` 同时含外层 `data-i18n` 和嵌套 `<span data-i18n>`

**Copilot 原始 Comment**:
> This `<label>` has `data-i18n` but also contains a nested `<span data-i18n="stg.optional">…</span>`. When translations are applied, `i18n.js` will set the label's `textContent`, removing the nested `<span>` entirely.

**修复方式**: 删除 `<label>` 上的 `data-i18n`，为 "Base URL" 文字单独添加一个 `<span data-i18n="stg.base_url">`，`(optional)` span 保持不变。

**修复前**:
```html
<label for="new-provider-baseurl" data-i18n="stg.base_url">
  Base URL <span style="..." data-i18n="stg.optional">(optional)</span>
</label>
```

**修复后**:
```html
<label for="new-provider-baseurl">
  <span data-i18n="stg.base_url">Base URL</span> <span style="..." data-i18n="stg.optional">(optional)</span>
</label>
```

---

### 问题 2 — `tests/test_i18n.py`：`_KEY_PATTERN` 正则漏匹配双引号 value

**Copilot 原始 Comment**:
> `_KEY_PATTERN` only matches keys whose values begin with a single-quoted string (`'key': 'value'`). In `i18n.js` some values use double quotes (e.g. `tasks.search_query_ph`), so those keys are omitted from `en_keys`/`zh_keys` and the parity test can miss missing translations.

**修复位置**: `tests/test_i18n.py` 第 40 行

**修复前**:
```python
_KEY_PATTERN = re.compile(r"'([a-z][a-z0-9_.]+)':\s*'", re.ASCII)
```

**修复后**:
```python
_KEY_PATTERN = re.compile(r"'([a-z][a-z0-9_.]+)':\s*['\"]", re.ASCII)
```

这样同时匹配值为单引号或双引号开头的键，确保 `tasks.search_query_ph` 等使用双引号的键也能被 parity 测试捕获。

---

### i18n.js 翻译字符串同步更新

由于 `stg.ai_filter_kw_help` 和 `stg.model_providers_help` 的 HTML 结构调整，对应翻译字符串同步更新为仅包含 `<span>` 内的纯文字部分（不含被移出的 `<code>` 标签内容）：

| Key | 修改前结尾 | 修改后结尾 |
|-----|-----------|-----------|
| `stg.ai_filter_kw_help` (EN) | `...in AI-only flows).` | `...This single list is also copied to` |
| `stg.ai_filter_kw_help` (ZH) | `...仅 AI 流程中）。` | `...此列表同时被复制到` |
| `stg.model_providers_help` (EN) | `...Add API keys for LLM providers.` | `...Providers set via` |
| `stg.model_providers_help` (ZH) | `...添加 LLM 供应商的 API 密钥。` | `...通过` |

---

## 🧪 用户测试清单

切换语言（EN ↔ 中文）时验证以下页面元素正常工作：

### `scheduled_tasks.html`
- [ ] **手动触发区** - "Max Pages" 和 "Max Depth" 标签文字正确切换语言
- [ ] **手动触发区** - 点击 `(i)` tooltip 图标仍然可以弹出/关闭 tooltip（不被 textContent 清除）
- [ ] **Add/Edit Site Modal** - 所有含 tooltip 的标签（Max Pages、Max Depth、Keywords、Exclude Keywords、Exclude Prefixes）文字正确切换
- [ ] **Add/Edit Site Modal** - 上述标签的 `(i)` tooltip 图标在语言切换后仍可点击使用

### `settings.html`
- [ ] **AI Filter Keywords 区域** - 帮助文字 "Used to decide whether..." 正确翻译，段尾的 `ai_keywords` 代码块保留原样显示
- [ ] **Model Providers 区域** - 帮助文字含 `.env` 代码块，`<code>.env</code>` 不被语言切换清除
- [ ] **Add Provider Form** - "Base URL" 标签文字正确翻译，旁边的 "(optional)" 也正确翻译

### `test_i18n.py`
- [ ] 运行 `python -m pytest tests/test_i18n.py -v` → 59 passed

---

## 📊 改动统计

| 文件 | 改动类型 | 描述 |
|------|---------|------|
| `ai_actuarial/web/templates/scheduled_tasks.html` | 修复 | 7 处 `<label data-i18n>` → `<label><span data-i18n>` |
| `ai_actuarial/web/templates/settings.html` | 修复 | 2 处 `<p data-i18n>`含`<code>`、1处`<label data-i18n>`含嵌套span |
| `ai_actuarial/web/static/js/i18n.js` | 同步更新 | 4 条翻译字符串（EN + ZH 各 2 条）截断至纯文字部分 |
| `tests/test_i18n.py` | 修复 | `_KEY_PATTERN` 正则新增 `"` 支持 |

**总计**: 4 文件，~15 行变更（等幅替换，净增量为 0）

---

## 🔍 技术决策说明

**为何不采用 `innerHTML` 方案？**

Copilot comment 同时提到了两种方案：
1. 用 `<span>` 隔离纯文字（选用）
2. 添加 `data-i18n-html` 属性 + `innerHTML` 赋值路径

方案 1 更安全：`innerHTML` 方案需要确保翻译值中无 XSS 风险，且需要修改 `i18n.js` 核心逻辑。方案 1 只需模板层调整，改动范围小、风险低，是本次 PR 范围内的最小修复。

---

## ⏭️ 后续步骤

- 待 PR #42 合并后，如需在其他模板继续添加 `data-i18n`，遵循本次修复的模式：**含子节点的元素不直接加 `data-i18n`，只对纯文字叶节点加**。
