# i18n 中英文界面切换 — 实现文档

> 分支：`feature/i18n-zh-en`  
> 日期：2026-03-05  
> 状态：✅ 已完成

---

## 1. 功能概述

在不引入任何前端框架（无 Vue / React）的前提下，为基于 **Flask + Jinja2 + Vanilla JS** 的 Web 界面实现：

| 功能 | 说明 |
|------|------|
| **自动检测** | 页面首次加载时读取 `navigator.language`；若以 `zh` 开头则默认中文，否则英文 |
| **手动切换** | 导航栏右上角新增 **语言切换按钮**（EN ↔ 中文） |
| **持久化记忆** | 手动切换结果写入 `localStorage.lang`，刷新或重新打开页面后保持 |
| **零闪烁** | `i18n.js` 在 `<head>` 内、`main.js` 前加载，避免英文内容先出现再切回中文 |
| **动态内容** | JS 动态渲染的表格标题等通过 `window.I18n.t(key)` 拉取翻译 |
| **事件通知** | 切换语言时派发 `langchange` CustomEvent，供其他模块监听 |

---

## 2. 文件变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `ai_actuarial/web/static/js/i18n.js` | **新建** | 核心 i18n 模块（约 230 行） |
| `ai_actuarial/web/templates/base.html` | 修改 | 加载 i18n.js；添加语言切换按钮；为导航、弹窗、Footer 添加 data-i18n 属性 |
| `ai_actuarial/web/templates/index.html` | 修改 | 为仪表板所有静态文字及动态 JS 内容添加翻译支持 |
| `ai_actuarial/web/static/js/main.js` | 修改 | `customConfirm()` 默认标题改用 `I18n.t()` |
| `ai_actuarial/web/static/css/style.css` | 修改 | 添加 `#lang-toggle-btn` 样式（含深色模式） |
| `tests/test_i18n.py` | **新建** | 28 个单元 + 集成测试 |

---

## 3. 核心模块：`i18n.js`

### 3.1 公开 API（`window.I18n`）

```javascript
// 获取当前语言的翻译值，不存在时 fallback 到 EN，再 fallback 到 key 本身
window.I18n.t('nav.dashboard')          // → 'Dashboard' or '仪表板'

// 切换到指定语言并持久化
window.I18n.setLang('zh')              // setLang('en') 同理

// 在 EN / ZH 之间来回切换
window.I18n.toggleLang()

// 获取当前语言代码
window.I18n.getCurrentLang()           // → 'en' | 'zh'

// 手动触发全量翻译（DOMContentLoaded 后自动调用一次）
window.I18n.applyTranslations()
```

### 3.2 翻译键规范

使用点分层级命名，格式 `<命名空间>.<功能>`：

```
nav.dashboard       nav.database     nav.chat
nav.tasks           nav.knowledge_bases  nav.settings
nav.login           nav.logout       nav.lang_toggle
modal.confirm_title modal.cancel     modal.confirm_ok
modal.auth_title    modal.auth_message   modal.auth_back
footer.copyright
index.welcome_title index.welcome_subtitle
index.total_files   index.cataloged_files  index.sources
index.active_tasks  index.quick_actions    index.recent_files
index.browse_db     index.browse_db_desc   index.task_center
index.kb            index.chat
table.title         table.source     table.date
common.back         common.save      common.delete     common.search
```

### 3.3 语言优先级

```
localStorage['lang']              ← 最高优先级（手动设置）
  ↓ 若不存在
navigator.language (zh-* → zh)   ← 浏览器自动检测
  ↓ 若非中文
'en'                              ← 默认
```

---

## 4. HTML 属性约定

| 属性 | 作用 | 示例 |
|------|------|------|
| `data-i18n="key"` | 替换元素的 `textContent` | `<a data-i18n="nav.dashboard">Dashboard</a>` |
| `data-i18n-placeholder="key"` | 替换 `placeholder` 属性 | `<input data-i18n-placeholder="common.search">` |
| `data-i18n-title="key"` | 替换 `title` 属性 | `<button data-i18n-title="theme.toggle_title">` |
| `data-i18n-aria-label="key"` | 替换 `aria-label` 属性 | `<button data-i18n-aria-label="theme.toggle_title">` |

---

## 5. 如何扩展新页面

**步骤 1** — 在 `i18n.js` 的 `en` 和 `zh` 字典中分别添加翻译键：

```javascript
// en dict
'mypage.heading': 'My Page',
'mypage.desc':    'Description here',

// zh dict  
'mypage.heading': '我的页面',
'mypage.desc':    '此处为描述',
```

**步骤 2** — 在对应模板中为静态文字加属性：

```html
<h2 data-i18n="mypage.heading">My Page</h2>
<p  data-i18n="mypage.desc">Description here</p>
```

**步骤 3** — 对于 JS 动态生成的内容使用 `t()`：

```javascript
const label = window.I18n ? window.I18n.t('mypage.heading') : 'My Page';
el.textContent = label;
```

**步骤 4** — 如需在语言切换时刷新动态内容，监听事件：

```javascript
document.addEventListener('langchange', function(e) {
    const lang = e.detail.lang; // 'en' | 'zh'
    rebuildTableHeaders();      // 你自己的重渲染逻辑
});
```

---

## 6. 测试方案

```
tests/test_i18n.py — 28 个测试，4 个测试类
├── TestI18nJsStructure   (8)  — 花括号平衡、API 完整性、EN/ZH 键一致性
├── TestBaseHtmlI18n       (8)  — base.html 属性检查
├── TestIndexHtmlI18n      (8)  — index.html 属性检查
└── TestI18nFlaskIntegration (4) — Flask test client 端到端验证
```

运行方式：

```bash
# 快速（跳过 Flask 集成测试）
pytest tests/test_i18n.py -k "not Integration" --override-ini=addopts= -q

# 完整
pytest tests/test_i18n.py --override-ini=addopts= -q
```

---

## 7. 设计决策

| 决策 | 理由 |
|------|------|
| Vanilla JS，不引入 vue-i18n / react-i18next | 项目使用 Flask + Jinja2，无前端构建工具；避免引入 npm 依赖 |
| `data-i18n` 属性，不服务端渲染翻译 | 无需服务端改动；支持客户端即时切换而不重新加载页面 |
| i18n.js 在 `<head>` 内同步加载 | 防止页面渲染后出现英文一闪而过的体验问题 |
| `DOMContentLoaded` 二次 `applyTranslations()` | 确保 head 内脚本执行时 body 尚未渲染完成的元素也能被翻译 |
| `localStorage['lang']` 键名简短 | 与已有 `localStorage['theme']` 键风格保持一致 |
| `nav.lang_toggle` 值为"对方语言" | 按钮显示"中文"表示可以切到中文，显示"EN"表示可以切到英文，符合主流惯例 |
