# 文件格式选择器实现工作计划

## 一、现状分析

### 1.1 现有参数支持情况

✅ **后端已支持文件格式过滤**

程序中已有完整的文件格式参数支持链路：

1. **基础配置类** (`ai_actuarial/collectors/base.py`)
   - `CollectionConfig` 类包含 `file_exts: list[str] | None` 参数
   - 用于传递文件扩展名过滤列表

2. **爬虫模块** (`ai_actuarial/crawler.py`)
   - `SiteConfig` 类包含 `file_exts` 参数
   - 默认支持格式：`{".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}`
   - 在 `scan_page_for_files()` 方法中使用：
     ```python
     exts = {e.lower() for e in (cfg.file_exts or [])} or DEFAULT_FILE_EXTS
     ```
   - 文件过滤逻辑：`self._is_file_url(url, exts)` 检查 URL 扩展名是否在允许列表中

3. **收集器模块**
   - **URLCollector** (`collectors/url.py`): 将 `config.file_exts` 传递给 `SiteConfig`
   - **FileCollector** (`collectors/file.py`): 在导入时根据 `extensions` 过滤本地文件
   - **ScheduledCollector**: 使用默认配置的 `file_exts`
   - **AdhocCollector** (Quick Check): 使用默认配置的 `file_exts`

4. **全局配置** (`config/sites.yaml`)
   ```yaml
   defaults:
     file_exts:
     - .pdf
     - .doc
     - .docx
     - .ppt
     - .pptx
     - .xls
     - .xlsx
   ```

### 1.2 Web API 当前实现

在 `ai_actuarial/web/app.py` 中：

- **URL Collection** (第443行): 从 `site_config['defaults'].get('file_exts')` 读取默认值
- **File Import** (第478行): 从前端 `data.get("extensions")` 读取用户输入
- **Web Search** (第539行): 未实现 file_exts 传递（目前使用默认值）
- **Quick Check** (第620行): 从 `site_config['defaults'].get('file_exts')` 读取默认值

### 1.3 问题诊断

❌ **前端缺少 UI 控件**

4个任务的模态框中都缺少文件格式选择器：
1. URL Collection (`/collection/url` 页面) - 需要添加
2. File Import (`/collection/file` 页面) - 需要添加
3. Web Search & Collect (`tasks.html` 中的 `#web-search-modal`) - 需要添加
4. Quick Site Check (`tasks.html` 中的 `#quick-check-modal`) - 需要添加

---

## 二、实现方案

### 2.1 前端 UI 设计

**统一的文件格式选择器组件**

```html
<div class="form-group">
    <label>File Formats:</label>
    <div class="format-checkboxes">
        <label class="format-option">
            <input type="checkbox" name="formats" value="pdf" checked>
            <span class="format-label">PDF</span>
        </label>
        <label class="format-option">
            <input type="checkbox" name="formats" value="doc">
            <span class="format-label">DOC</span>
        </label>
        <label class="format-option">
            <input type="checkbox" name="formats" value="docx" checked>
            <span class="format-label">DOCX</span>
        </label>
        <label class="format-option">
            <input type="checkbox" name="formats" value="ppt">
            <span class="format-label">PPT</span>
        </label>
        <label class="format-option">
            <input type="checkbox" name="formats" value="pptx">
            <span class="format-label">PPTX</span>
        </label>
        <label class="format-option">
            <input type="checkbox" name="formats" value="xls">
            <span class="format-label">XLS</span>
        </label>
        <label class="format-option">
            <input type="checkbox" name="formats" value="xlsx">
            <span class="format-label">XLSX</span>
        </label>
        <label class="format-option" title="HTML - Will download large amounts of webpage source code">
            <input type="checkbox" name="formats" value="html">
            <span class="format-label">HTML ⚠️</span>
        </label>
    </div>
    <small class="format-hint">HTML - Will download large amounts of webpage source code</small>
</div>
```

**默认选中策略**
- ✅ PDF, DOCX 默认勾选（最常用的文档格式）
- ⬜ DOC, PPT, PPTX, XLS, XLSX 不勾选（按需选择）
- ⬜ HTML 不勾选（特殊需求，会下载大量网页源代码）

**CSS 样式建议**
```css
.format-checkboxes {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-top: 8px;
}

.format-option {
    display: flex;
    align-items: center;
    cursor: pointer;
    padding: 5px;
    border: 1px solid #ddd;
    border-radius: 4px;
    transition: background 0.2s;
}

.format-option:hover {
    background: #f0f0f0;
}

.format-option input[type="checkbox"] {
    margin-right: 5px;
}

.format-label {
    font-size: 0.9em;
    font-weight: 500;
}

.format-hint {
    display: block;
    margin-top: 8px;
    color: #ff6b6b;
    font-size: 0.85em;
    font-style: italic;
// 获取选中的文件格式（带校验）
function getSelectedFormats(formElement) {
    const checkboxes = formElement.querySelectorAll('input[name="formats"]:checked');
    const formats = Array.from(checkboxes).map(cb => '.' + cb.value);
    
    // 校验：如果没有选中任何格式，返回null让后端使用默认值
    if (formats.length === 0) {
        return null;
    }
    
    return formats;
}

// 重置格式选择器为默认状态（PDF和DOCX）
function resetFormatSelector(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    const checkboxes = modal.querySelectorAll('input[name="formats"]');
    checkboxes.forEach(cb => {
        // 只选中 pdf 和 docx
        cb.checked = (cb.value === 'pdf' || cb.value === 'docx');
    });
}

// 使用示例
function startWebSearch(event) {
    event.preventDefault();
    const form = event.target;
    const formats = getSelectedFormats(form);
    
    // formats 可能为 null，后端会使用默认值
    const data = {
        query: form.query.value,
        engine: form.engine.value,
        count: form.count.value,
        site: form.site.value,
        file_exts: formats  // null 或 ['.pdf', '.docx', ...]
    };
    
    // 提交到 API...
    // 成功后关闭模态框并重置
    // closeModal('web-search-modal');
}

// 修改closeModal函数，关闭时重置格式选择器
function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
    resetFormatSelector(modalId);  // 关闭时重置为默认选中{
        query: form.query.value,
        engine: form.engine.value,
        count: form.count.value,
        site: form.site.value,
        file_exts: formats  // 新增字段
    };
    
    // 提交到 API...
}
```

### 2.3 后端 API 修改

#### 2.3.1 Web Search 任务 (app.py 第539行附近)

**现状**
```python
config_obj = CollectionConfig(
    name=data.get("name", "Web Search & Collect"),
    source_type="search",
    check_database=True,
    keywords=site_config['defaults'].get('keywords', []),
    file_exts=site_config['defaults'].get('file_exts', []),  # 硬编码默认值
    metadata={...}
)
```

**修改为**
```python
# 获取前端传来的格式，如果为None或空列表则使用默认值
user_formats = data.get("file_exts")
if user_formats:  # 确保不是None也不是空列表
    file_exts = user_formats
else:
    file_exts = site_config['defaults'].get('file_exts', [])

# 额外校验：确保file_exts不为空
if not file_exts:
    file_exts = ['.pdf', '.docx']  # 最小默认值

config_obj = CollectionConfig(
    name=data.get("name", "Web Search & Collect"),
    source_type="search",
    check_database=True,
    keywords=site_config['defaults'].get('keywords', []),
    file_exts=file_exts,  # 使用用户选择或默认值（确保不为空）
    metadata={...}
)
```

#### 2.3.2 URL Collection 任务 (app.py 第443行附近)

**类似修改**
```python
user_formats = data.get("file_exts")
file_exts = user_formats if user_formats else site_config['defaults'].get('file_exts', [])

config_obj = CollectionConfig(
    name=data.get("name", "URL Collection"),
    source_type="url",
    check_database=data.get("check_database", True),
    keywords=site_config['defaults'].get('keywords', []),
    file_exts=file_exts,  # 使用用户选择
    exclude_keywords=site_config['defaults'].get('exclude_keywords', []),
    metadata={"urls": urls}
)
```

#### 2.3.3 Quick Check 任务 (app.py 第620行附近)

**类似修改**
```python
user_formats = data.get("file_exts")
file_exts = user_formats if user_formats else site_config['defaults'].get('file_exts', [])

sc = SiteConfig(
    name=site_name,
    url=site_url,
    max_pages=data.get("max_pages", 10),
    max_depth=data.get("max_depth", 1),
    keywords=data.get("keywords", []),
    file_exts=file_exts,  # 使用用户选择
    exclude_keywords=site_config['defaults'].get('exclude_keywords', []),
    exclude_prefixes=site_config['defaults'].get('exclude_prefixes', [])
)
```

#### 2.3.4 File Import 任务

File Import 任务已经有 `extensions` 参数处理，需要确保与新的命名一致：

```python
# 当前代码 (第478行附近)
extensions = data.get("extensions", [])

# 为保持一致性，可以同时支持两个字段名
extensions = data.get("extensions") or data.get("file_exts") or []
```

---

## 三、实施步骤现有模态框
- [ ] Web Search Modal (`#web-search-modal`) - 在 "Site Filter" 字段后添加格式选择器
- [ ] Quick Check Modal (`#quick-check-modal`) - 在 "Depth" 字段后添加格式选择器
- [ ] 添加统一的 CSS 样式到 `<style>` 块（包括 `.format-hint` 样式）

**步骤1.2** - 创建两个新的模态框（使用选项B）
- [ ] 创建 `URL Collection Modal` (`#url-collection-modal`)
  - 参考现有模态框的 HTML 结构
  - 添加 URL 输入区域（textarea，支持多行输入）
  - 添加文件格式选择器（默认选中 PDF 和 DOCX）
  - 添加 "Check Database" checkbox 选项
- [ ] 创建 `File Import Modal` (`#file-import-modal`)
  - 添加目录路径输入框
  - 添加文件格式选择器（复用相同的 HTML 结构）
  - 添加 "Recursive" checkbox（是否递归子目录）
- [ ] 修改卡片1和2的点击事件：
  ```javascript
  // 从 onclick="location.href='/collection/url'"
  // 改为 onclick="openUrlCollectionModal()"
  ```(File Import 页面)
  - 添加目录选择输入框
  - 添加文件扩展名过滤（复用格式选择器）
  - 添加递归选项 checkbox
  - **或者** 复用现有逻辑，检查是否已有这些页面

### Phase 2: JavaScript 逻辑 (0.5-1小时)

**步骤2.1** - 在 `tasks.html` 的 `<script>` 部分添加辅助函数

```javascript
// 添加到 tasks.html 的 <script> 块末尾

// 获取选中的文件格式（带校验）
function getSelectedFormats(formElement) {
    const checkboxes = formElement.querySelectorAll('input[name="formats"]:checked');
    if (checkboxes.length === 0) {
        // 如果用户没选任何格式，返回 null 让后端使用默认值
        return null;
    }
    return Array.from(checkboxes).map(cb => '.' + cb.value);
}

// 重置格式选择器为默认状态（PDF和DOCX）
function resetFormatSelector(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    const checkboxes = modal.querySelectorAll('input[name="formats"]');
    checkboxes.forEach(cb => {
        cb.checked = (cb.value === 'pdf' || cb.value === 'docx');
    });
}
```

**步骤2.2** - 修改 `closeModal()` 函数，添加重置逻辑
```javascript
function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
    resetFormatSelector(modalId);  // 关闭时重置为默认选中
}
```

**步骤2.3** - 修改现有的提交函数
- [ ] `startWebSearch()` - 添加 `file_exts: getSelectedFormats(form)` 到 data 对象
- [ ] `startQuickCheck()` - 添加 `file_exts: getSelectedFormats(form)` 到 data 对象

**步骤2.3** - 为新页面创建提交函数 (如果需要)
- [ ] URL Collection 页面的表单提交
- [ ] File Import 页面的表单提交

### Phase 3: 后端 API 修改 (1-1.5小时)

**步骤3.1** - 修改 `ai_actuarial/web/app.py`

在 `@app.route('/api/collections/run', methods=['POST'])` 处理函数中：

- [ ] **第443行** - URL Collection 处理逻辑
  ```python
  # 在创建 config_obj 之前添加
  user_formats = data.get("file_exts")
  file_exts = user_formats if user_formats else site_config['defaults'].get('file_exts', [])
  ```

- [ ] **第478行** - File Import 处理逻辑
  ```python
  # 修改 extensions 获取逻辑，兼容新旧字段名
  extensions = data.get("extensions") or data.get("file_exts") or []
  ```

- [ ] **第539行** - Web Search 处理逻辑
  ```python
  # 添加 file_exts 参数获取
  user_formats = data.get("file_exts")
  file_exts = user_formats if user_formats else site_config['defaults'].get('file_exts', [])
  
  # 在 config_obj 中使用
  config_obj = CollectionConfig(
      ...,
      file_exts=file_exts,
      ...
  )
  ```

- [ ] **第620行** - Quick Check 处理逻辑
  ```python
  # 在创建 SiteConfig 之前添加
  user_formats = data.get("file_exts")
  file_exts = user_formats if user_formats else site_config['defaults'].get('file_exts', [])
  
  # 在 SiteConfig 中使用
  sc = SiteConfig(
      ...,
      file_exts=file_exts,
      ...
  )
  ```

**步骤3.2** - 添加路由 (如果创建了新页面)
```python
@app.route('/collection/url')
def url_collection_page():
    return render_template('url_collection.html')

@app.route('/collection/file')
def file_import_page():
    return render_template('file_import.html')
```

### Phase 4: 测试验证 (1小时)

**步骤4.1** - 功能测试
- [ ] 测试 Web Search 任务
  - 只选择 PDF，验证只下载 PDF 文件
  ✅ 最终决策**: **选项B** - 使用模态框实现，保持界面一致性

**具体实施**:
1. 修改卡片1和2的 `onclick` 事件，从跳转页面改为打开模态框
2. 为 URL Collection 和 File Import 创建新的模态框（类似现有的 Web Search Modal）
3. 所有5个任务统一使用模态框交互，用户体验一致
4. 如果后续需求复杂，再考虑迁移到独立页面
- [ ] 测试 File Import (如果实现了新页面)

**步骤4.2** - 边界测试
- [ ] 所有格式都不选 - 应使用默认值
- [ ] 选择单一格式 - 应只下载该格式
- [ ] 选择所有格式 - 应下载所有支持的格式
- [ ] 选择不存在的格式（如 HTML）- 验证爬虫不下载 HTML 页面

**步骤4.3** - UI/UX 测试
- [ ] 格式选择器在不同屏幕尺寸下的显示
- [ ] Checkbox 状态在模态框关闭后是否重置
- [ ] 表单提交后的状态反馈

---

## 四、关键决策点

### 决策1: 是否需要创建独立的 collection 页面？
✅ 最终决策**: **选项A** - 使用带点格式（`.pdf`）

**实施细节**:
1. **前端处理**: JavaScript 中添加点号：`'.' + cb.value`
2. **提交前校验**: 
   ```javascript
   const formats = getSelectedFormats(form);
   // 如果formats为null，后端使用默认配置
   // 确保不会传递空数组[]
  ✅ 最终决策**: **包含 HTML 选项但默认不选中**

**UI 实现**:
1. 在 HTML checkbox 的 label 上添加 `title` 属性：
   ```html
   <label class="format-option" title="HTML - Will download large amounts of webpage source code">
       <input type="checkbox" name="formats" value="html">
       <span class="format-label">HTML ⚠️</span>
   </label>
   ```
2. 在格式选择器下方添加提示文字：
   ```html
   <small class="format-hint">HTML - Will download large amounts of webpage source code</small>
   ```
3. 使用警告图标 ⚠️ 增强视觉提示
4. 默认不选中，用户需要主动勾选如 `['.pdf', '.docx']`）
**选项A**: 创建 `/collection/url` 和 `/collection/file` 独立页面
- ✅ 优点: 可以提供更详细的配置选项
- ✅ 优点: 与 Scheduled Tasks 页面风格统一
- ❌ 缺点: 需要更多开发工作
- ❌ 缺点: 需要维护额外的模板文件

**选项B**: 继续使用模态框，但增强功能
- ✅ 优点: 快速实现，与当前设计一致
- ✅ 优点: 用户体验更流畅（无页面跳转）
- ❌ 缺点: 模态框空间有限
- ❌ 缺点: 复杂配置可能显得拥挤

**推荐**: **选项B** - 先在模态框中实现，如果后续需求复杂再迁移到独立页面

**依据**:
1. 当前卡片1和2点击后跳转到 `/collection/url` 和 `/collection/file`，但这两个路由不存在
2. 可以先创建简单的独立页面，或者将卡片点击改为打开模态框
3. 建议修改卡片1和2的 `onclick` 为打开模态框，保持一致性

### 决策2: 文件格式的存储格式
✅ 最终决策**: 
- ✅ PDF (最常见的文档格式)
- ✅ DOCX (Word 文档格式)
- ⬜ DOC (Word 旧版格式，按需)
- ⬜ PPT (PowerPoint 旧版格式，按需)
- ⬜ PPTX (PowerPoint 新版格式，按需)
- ⬜ XLS (Excel 旧版格式，按需)
- ⬜ XLSX (Excel 新版格式，按需)
- ⬜ HTML (特殊需求，会下载大量网页源代码)

**理由**: 
1. PDF 是最通用的文档分享格式
2. DOCX 是 Word 的主流格式
3. 其他格式按需选择，避免下载过多不需要的文件
4. 用户可以根据实际需求勾选 PPT、Excel 等
### 决策3: HTML 格式是否包含在选项中？

**分析**:
- 爬虫的 `DEFAULT_FILE_EXTS` 不包含 `.html`
- Web Search 任务通常返回的是网页 URL，需要提取链接后才下载文件
- 如果用户选择 HTML，可能会下载大量网页内容（而非文档文件）

**推荐**: **包含 HTML 选项但默认不选中**
- 用于特殊需求（如需要保存网页快照）
- 明确告知用户 HTML 会下载网页源代码
- 或者添加提示文字："HTML - 用于下载网页内容"

### 决策4: 默认选中的格式

**推荐组合**: 
- ✅ PDF (最常见的文档格式)
- ✅ DOCX (Word 新版格式)
- ✅ PPTX (PowerPoint 新版格式)
- ✅ XLSX (Excel 新版格式)
- ✅ 已解决：前端校验返回 `null`，后端使用默认配置
- ✅ 已解决：后端额外校验，确保 `file_exts` 至少有 `['.pdf']`
- ✅ 已解决：添加 英文UI 提示："未选择时使用默认配置（PDF, DOC, DOCX...）"

❗ **格式选择的持久性**
- ✅ 已决策：每次关闭模态框都重置为默认选中状态（PDF + DOCX）
- 实现方式：`closeModal()` 函数中调用 `resetFormatSelector()`
- 优点：避免用户忘记上次的选择，每次都是干净的状态
- 用户仍可以在提交前修改
---

## 五、风险与注意事项

### 5.1 技术风险

❗ **Web Search 任务的特殊性**
- Web Search 返回的是 URL 列表，然后交给 Crawler 下载
- 确保 `file_exts` 参数正确传递到 Crawler 的 `scan_page_for_files()` 方法
- 需要验证 search.py 模块的 URL 过滤逻辑

❗ **File Import 的扩展名匹配**
- 当前代码使用 `exts` 集合匹配：`path.suffix.lstrip('.').lower() in exts`
- 确保前端传递的格式（如 `['.pdf', '.docx']`）与匹配逻辑兼容
- 可能需要在后端统一处理（去除点号或添加点号）

❗ **数据库查询的影响**
- `check_database=True` 时，系统会跳过已存在的文件
- 用户更改格式过滤后，可能期望重新下载之前跳过的文件
- 需要明确用户的使用场景：
  - 场景1: 第一次爬取，选择特定格式避免下载无用文件
  - 场景2: 补充爬取，只下载新格式的文件

### 5.2 用户体验风险

❗ **用户不选择任何格式**
- 当前设计：返回 `null`，后端使用默认配置
- 可能的困惑：用户以为会"下载所有格式"或"不下载任何文件"
- 解决方案：添加 UI 提示："未选择时使用默认配置（PDF, DOC, DOCX...）"

❗ **格式选择的持久性**
- 用户关闭模态框后，选择是否重置？
- 建议：每次打开模态框都重置为默认选中状态，避免用户忘记上次的选择

### 5.3 兼容性问题

❗ **config/sites.yaml 的优先级**
- 全局配置中的 `file_exts` 是默认值
- 用户在 UI 中的选择应该覆盖默认值
- 确保后端逻辑：`user_formats if user_formats else defaults`

❗ **旧版浏览器支持**
- `Array.from()` 需要 IE 11+ 或现代浏览器
- `querySelectorAll()` 兼容性良好
- Grid 布局需要 IE 10+ 或添加 fallback

---

## 六、成功标准

### 6.1 功能完整性
- [x] 4个任务的模态框都包含文件格式选择器
- [ ] 格式选择器的默认状态正确（PDF/DOCX/PPTX/XLSX 选中）
- [ ] 用户选择传递到后端 API
- [ ] 后端正确使用用户选择的格式过滤文件

### 6.2 用户体验
- [ ] UI 美观，与现有设计风格一致
- [ ] 操作直观，用户一目了然
- [ ] 提供清晰的提示（如"未选择时使用默认配置"）
- [ ] 支持多选和取消选择

### 6.3 代码质量
- [ ] 代码遵循现有项目风格
- [ ] 适当的注释说明参数用途
- [ ] 前后端逻辑清晰，易于维护
- [ ] 日志记录关键操作（如使用了哪些格式）

---

## 七、时间估算

| 阶段 | 任务 | 预估时间 |
|------|------|----------|
| Phase 1 | 前端 UI 实现 | 1-1.5小时 |
| Phase 2 | JavaScript 逻辑 | 0.5-1小时 |
| Phase 3 | 后端 API 修改 | 1-1.5小时 |
| Phase 4 | 测试验证 | 1小时 |
| **总计** | | **3.5-5小时** |

**注**: 时间估算假设：
- 开发者熟悉 Flask 和 JavaScript
- 无重大技术障碍
- 测试环境已配置好
- 不包括代码审查和部署时间

---

## 八、后续优化建议

### 8.1 短期优化 (Phase 5, 可选)
1. **格式预设配置**
   - 添加快捷按钮："仅文档"（PDF+DOCX）、"仅表格"（XLSX）、"全部Office"
   - 用户可以一键选择常用组合

2. **格式使用统计**
   - 在数据库中记录每个任务实际下载的文件格式分布
   - 在 History 中显示："下载了 15 个 PDF, 3 个 DOCX"

3. **智能推荐**
   - 根据站点类型推荐格式（如学术网站推荐 PDF，企业网站推荐 DOCX/PPTX）

### 8.2 长期规划
1. **自定义格式支持**
   - 允许用户添加其他格式（如 `.zip`, `.csv`, `.json`）
   - 需要更新 Crawler 的文件处理逻辑

2. **按站点保存格式偏好**
   - 记住用户对特定站点的格式选择
   - 下次访问时自动应用

3. **批量配置**
   - 在 Scheduled Tasks 中为所有站点统一配置格式偏好

---

## 九、实施检查清单

在开始实施前，请确认：

- [ ] 阅读并理解了现有代码的文件格式过滤机制
- [ ] 确认了 4 个任务的当前实现位置（模态框或独立页面）
- [ ] 决定了 UI 设计方案（模态框 vs 独立页面）
- [ ] 准备好测试环境和测试数据
- [ ] 确认了默认选中的格式组合
- [ ] 了解了后端 API 的参数传递方式

开始实施后：

- [ ] 每完成一个 Phase 进行一次测试
- [ ] 记录遇到的问题和解决方案
- [ ] 更新相关文档（如 README.md）
- [ ] 考虑添加用户使用说明
- [ ] 准备演示视频或截图

---

## 十、参考资料

### 代码位置快速索引
- 配置类: `ai_actuarial/collectors/base.py` - `CollectionConfig`
- 爬虫核心: `ai_actuarial/crawler.py` - `scan_page_for_files()`
- Web API: `ai_actuarial/web/app.py` - `/api/collections/run`
- 前端模态框: `ai_actuarial/web/templates/tasks.html`
- 全局配置: `config/sites.yaml` - `defaults.file_exts`

### 相关文档
- `UI_IMPROVEMENT_PLAN.md` - Section 3 (文件格式选择器)
- `UI_IMPLEMENTATION_REPORT.md` - Phase 3 延期说明
- `README.md` - 项目整体架构

---

**文档版本**: v1.0  
**创建日期**: 2026-02-05  
**作者**: GitHub Copilot  
**状态**: 待审核 ⏳
