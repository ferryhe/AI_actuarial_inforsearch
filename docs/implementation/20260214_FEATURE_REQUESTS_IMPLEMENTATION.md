# 功能需求实施总结

**日期**: 2026-02-14  
**需求来源**: 用户反馈  
**状态**: 部分已实施，部分待实施

---

## ✅ 已完成功能

### 1. 多AI Provider配置方案
**状态**: 已完成设计文档

详细设计见: [20260214_MULTI_AI_PROVIDER_DESIGN.md](./20260214_MULTI_AI_PROVIDER_DESIGN.md)

**实施计划**:
- Phase 1: 配置结构重构 (下一版本)
- Phase 2: Settings UI实现 
- Phase 3: Provider自动切换和容错

---

### 2. File Details页面添加AI解释按钮
**状态**: ✅ 已完成实施

**实现内容**:
1. 在Delete按钮右侧添加"AI Explain Document"按钮
2. 只在有markdown内容时显示
3. 点击后跳转到Chat页面并自动触发文档解释
4. 使用sessionStorage传递文档内容和元数据

**文件修改**:
- `ai_actuarial/web/templates/file_view.html`
  - 添加AI解释按钮
  - 添加`explainWithAI()`函数
  - 在加载markdown后显示按钮

- `ai_actuarial/web/templates/chat.html`
  - 添加`checkAIExplainMode()`函数
  - 自动检测并触发文档解释

**使用流程**:
```
File Details Page → Click "AI Explain Document" 
→ Navigate to Chat Page 
→ Auto-start conversation with document content
```

---

## 📋 待实施功能

### 3. Chat页面添加文档解释功能
**状态**: 设计建议

**推荐设计方案A: 侧栏集成（推荐）**

```
┌─────────────────────────────────────────┐
│ 💬 AI Chat Assistant                     │
├───────────┬─────────────────────────────┤
│           │ 🔍 Document Explorer        │
│ Convs     │ ┌─────────────────────────┐│
│ List      │ │ Category: [All ▼]       ││
│           │ │ Keywords: [________]  🔍││
│ ◉ Conv1   │ └─────────────────────────┘│
│ ○ Conv2   │                             │
│ ○ Conv3   │ 📄 Available Documents      │
│           │ ┌─────────────────────────┐│
│ [+ New]   │ │ ☑ SOA_Report_2024.pdf  ││
│           │ │ ☐ CIA_Guidelines.pdf    ││
│           │ │ ☐ Actuarial_Exam.pdf    ││
│           │ └─────────────────────────┘│
│           │ [💬 Explain Selected]       │
├───────────┴─────────────────────────────┤
│ Chat Messages...                        │
└─────────────────────────────────────────┘
```

**推荐设计方案B: 对话界面上方**

```
┌─────────────────────────────────────────┐
│ 💬 AI Chat Assistant                     │
├─────────────────────────────────────────┤
│ ┌─ Quick Actions ─────────────────────┐│
│ │ 📄 Explain Document:                ││
│ │    [Select Document ▼] [Explain]   ││
│ │ 🔍 Filter: Cat[All▼] KW[______]    ││
│ └─────────────────────────────────────┘│
├─────────────────────────────────────────┤
│ Conversations │ Chat Messages           │
│ ○ Conv1       │                         │
│ ○ Conv2       │ User: Hello...          │
│               │ AI: Hi...               │
└─────────────────────────────────────────┘
```

**推荐方案**: **方案A**  
理由:
- 更直观，文档选择与对话分离
- 可以多选文档进行对比
- 不占用聊天区域空间

**实施步骤**:
1. 修改`templates/chat.html`布局
2. 添加文档筛选API endpoint
3. 添加文档选择器组件
4. 实现"Explain Selected"功能

---

### 4. KB详情页跳转优化
**状态**: 需要查找代码

**需求**:
- 从KB详情页点击文件 → 进入File Detail页面  
- File Detail页面的返回按钮 → 返回KB详情页（而不是Database页面）
- 去掉文件列表最后的"View"按钮

**实施方案**:
1. 找到KB详情页模板文件（可能是`rag_detail.html`）
2. 修改文件链接，添加`return_to`参数
3. 去掉View按钮，使整行可点击

**代码示例**:
```html
<!-- 修改前 -->
<a href="/file/{{ file.url }}">{{ file.name }}</a>
<a href="/file/{{ file.url }}" class="btn">View</a>

<!-- 修改后 -->
<a href="/file/{{ file.url }}?return_to={{ request.path }}" 
   class="file-row-link">
   {{ file.name }}
</a>
<!-- 去掉View按钮 -->
```

**待查找**:
- KB详情页模板位置
- 文件列表渲染代码

---

### 5. 全文档总结功能（限Markdown）
**状态**: 技术方案

**当前问题**:
- Chat系统基于RAG chunk查询，无法总结完整文档
- 用户问"帮我总结XXX文件"时，AI只能用检索到的fragments回答

**解决方案**:

#### 方案A: 直接传递完整Markdown（推荐）

**新增API Endpoint**:
```python
# chat_routes.py

@bp.route("/api/chat/explain-document", methods=["POST"])
def explain_document():
    """
    Explain a complete document with full markdown content.
    
    Request:
    {
        "file_url": "...",
        "mode": "summary",  # summary, detailed, tutorial
        "conversation_id": "..." (optional)
    }
    """
    data = request.json
    file_url = data.get("file_url")
    mode = data.get("mode", "summary")
    
    # Get markdown content from database
    storage = Storage(db_path)
    markdown_data = storage.get_markdown_content(file_url)
    
    if not markdown_data:
        return jsonify({"error": "No markdown content"}), 404
    
    # Truncate if too long (avoid token limits)
    content = markdown_data['markdown_content']
    max_length = 15000  # ~4K tokens
    if len(content) > max_length:
        content = content[:max_length] + "\n\n[Content truncated...]"
    
    # Build prompt
    prompt = build_document_summary_prompt(content, mode)
    
    # Generate response (no RAG retrieval)
    response = llm_client.generate_direct(prompt)
    
    return jsonify({
        "success": True,
        "response": response
    })
```

**提示词模板**:
```python
def build_document_summary_prompt(content, mode):
    if mode == "summary":
        return f"""
Please provide a concise summary of this document:

{content}

Summary should include:
1. Main topic and purpose
2. Key findings or conclusions (3-5 points)
3. Target audience
4. Practical implications
"""
    elif mode == "detailed":
        return f"""
Please provide a detailed analysis of this document:

{content}

Analysis should cover:
1. Document structure and organization
2. Main arguments and supporting evidence
3. Methodologies or frameworks used
4. Key data or examples
5. Conclusions and recommendations
6. Limitations or caveats
"""
    # ... other modes
```

#### 方案B: 智能分段总结（适用于超长文档）

**流程**:
1. 将markdown按章节分段（h2/h3标题）
2. 对每段生成摘要
3. 汇总所有段落摘要，生成总体总结

**优势**:
- 可处理超长文档
- 保留结构层次
- Token消耗可控

#### 方案C: 命令关键词触发

在当前Chat系统中添加特殊命令识别:
```
用户: @summarize SOA_Report_2024.pdf
→ 系统识别@summarize命令
→ 查找文档markdown
→ 调用专门的总结API
→ 返回完整总结而非RAG片段
```

**推荐顺序**:
1. **Phase 1**: 实现方案A（从File Detail触发）✅ 已完成
2. **Phase 2**: 实现方案B（Chat内命令触发）
3. **Phase 3**: 实现方案C（长文档智能分段）

---

## 🎯 总体实施优先级

| 需求 | 优先级 | 状态 | 预计工作量 |
|------|-------|------|-----------|
| 1. 多AI Provider | P2 | 设计完成 | 3-5天 |
| 2. File Detail AI解释 | P1 | ✅ 已完成 | 完成 |
| 3. Chat文档解释器 | P1 | 设计建议 | 2-3天 |
| 4. KB详情页跳转 | P2 | 待实施 | 0.5天 |
| 5. 全文档总结 | P1 | 待实施 | 1-2天 |

---

## 📝 下一步行动

### 立即可做（优先级P1）:
1. ✅ 测试File Detail AI解释功能
2. 实施需求4: KB详情页跳转优化（简单）
3. 实施需求5: 全文档总结API（方案A基础实现）

### 后续版本（优先级P2）:
1. 实施需求3: Chat文档解释器UI
2. 实施需求1: 多AI Provider配置系统

---

## 🧪 测试检查清单

### File Detail AI解释功能测试:
- [ ] 有markdown内容时按钮显示
- [ ] 无markdown内容时按钮不显示
- [ ] 点击按钮正确跳转到Chat
- [ ] Chat页面自动创建新对话
- [ ] 自动发送解释请求
- [ ] 返回正确的文档解释
- [ ] sessionStorage正确清理

### 浏览器测试:
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari (如适用)

---

## 📚 相关文档

- [多AI Provider设计](./20260214_MULTI_AI_PROVIDER_DESIGN.md)
- [Chatbot配置](../ai_actuarial/chatbot/config.py)
- [Chat路由](../ai_actuarial/web/chat_routes.py)
- [File View模板](../ai_actuarial/web/templates/file_view.html)
- [Chat模板](../ai_actuarial/web/templates/chat.html)

---

**更新时间**: 2026-02-14  
**维护者**: AI Team
