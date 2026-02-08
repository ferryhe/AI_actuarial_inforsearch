# 如何使用项目开发工作流 Skill

## 📋 简介

本文档说明如何配置和使用**标准项目开发工作流 Skill**，这是一个经过实战验证的系统化开发流程，确保高质量的功能实现。

---

## 🎯 Skill 概述

### 什么是 Skill？

Skill 是一个标准化的工作流程模板，定义了：
- ✅ 清晰的阶段划分（6个阶段）
- ✅ 每个阶段的具体步骤
- ✅ 质量门槛和验收标准
- ✅ 最佳实践和注意事项
- ✅ 文档模板和检查清单

### 核心工作流

```
Phase 0: 需求分析与规划 → 生成详细计划文档
    ↓
Phase 1: 核心功能实施 → 编写代码
    ↓
Phase 2: 自动化测试 → 语法检查、静态分析
    ↓
Phase 3: 测试准备 → 创建测试指南
    ↓
Phase 4: 用户测试 → 获取用户反馈
    ↓
Phase 5: 文档编写 → 生成实施报告
    ↓
Phase 6: 项目收尾 → 交付总结
```

---

## 🚀 配置方法

### 方法一：文件系统配置（推荐）

#### 1. 创建 Skill 目录结构

```bash
your-project/
├── .github/
│   └── copilot-skills/
│       └── project-development-workflow.md  # Skill 定义文件
└── docs/
    └── HOW_TO_USE_DEV_WORKFLOW_SKILL.md    # 使用说明（本文档）
```

#### 2. 放置 Skill 文件

将提供的两个文件放入对应目录：
- `project-development-workflow.md` → `.github/copilot-skills/`
- `HOW_TO_USE_DEV_WORKFLOW_SKILL.md` → `docs/`

#### 3. GitHub Copilot 自动识别

GitHub Copilot 会自动扫描 `.github/copilot-skills/` 目录，加载自定义 Skill。

**验证配置**:
在聊天中输入：
```
@workspace 显示可用的 skills
```
或
```
@workspace 使用 project development workflow skill
```

---

### 方法二：通过 .copilot-instructions 配置

#### 1. 创建配置文件

在项目根目录创建 `.copilot-instructions.md`：

```markdown
# Project Instructions

## Custom Skills

### Project Development Workflow

This project uses a standardized development workflow. For any feature development request:

1. **Always follow these phases**:
   - Phase 0: Requirements Analysis & Planning
   - Phase 1: Core Implementation
   - Phase 2: Automated Testing
   - Phase 3: User Testing Preparation
   - Phase 4: User Testing & Validation
   - Phase 5: Documentation
   - Phase 6: Completion & Handoff

2. **Reference**: See `.github/copilot-skills/project-development-workflow.md`

3. **Trigger keywords**: 
   - "按照标准流程", "use standard workflow", "follow best practices"
   - "#dev-workflow", "#standard-process"

4. **Quality gates**: Do not proceed to next phase without completing current phase's gate

## Example Usage

User: "请按照标准流程添加新功能X"
AI: "好的！我将使用标准项目开发流程，首先进行需求分析和规划..."
```

#### 2. GitHub Copilot 读取配置

Copilot 会自动读取 `.copilot-instructions.md` 并遵循其中的指示。

---

### 方法三：聊天窗口引用（临时使用）

如果不想配置文件，可以在聊天中临时引用：

```
@workspace 参考 .github/copilot-skills/project-development-workflow.md 中的流程，
按照标准工作流实施 [功能描述]
```

或者附加文件：
```
请按照附件中的标准流程开发功能X
[Attach: project-development-workflow.md]
```

---

## 📖 使用方法

### 基本用法

#### 触发 Skill

**方法1: 使用关键词**
```
请按照标准流程为系统添加用户权限管理功能
```

**方法2: 使用标签**
```
#dev-workflow 实现数据导出功能
```

**方法3: 明确引用**
```
使用 project development workflow skill 来开发报表生成模块
```

#### AI 的响应流程

1. **识别触发**: AI 识别到使用标准流程的请求
2. **执行 Phase 0**: 
   - 分析现状
   - 询问澄清问题
   - 创建详细计划文档
   - **等待用户确认**
3. **执行 Phase 1-6**: 
   - 按阶段实施
   - 每个阶段完成后标记
   - 遇到质量门槛时停止等待确认
4. **生成文档**: 创建完整的实施报告

---

### 高级用法

#### 1. 自定义阶段

如果某个项目不需要全部6个阶段，可以明确指定：

```
使用标准流程但跳过 Phase 4（用户测试），因为这是内部工具
```

#### 2. 调整质量门槛

```
使用标准流程，但 Phase 2 的自动化测试只需要检查语法错误即可
```

#### 3. 指定优先级

```
按标准流程开发，但优先完成核心功能（Phase 1），文档可以后续补充
```

#### 4. 多功能并行

```
使用标准流程分别实施以下三个功能：
1. 用户登录
2. 数据导入
3. 报表导出

请为每个功能创建独立的计划和追踪
```

---

## ✅ 验证配置是否生效

### 测试步骤

**1. 简单测试**
```
@workspace 请说明标准开发流程包含哪些阶段
```

**期望回答**: 列出 Phase 0-6 的名称和简要说明

**2. 实际测试**
```
按照标准流程为系统添加一个简单的"关于"页面
```

**期望行为**:
- ✅ AI 首先分析现状
- ✅ AI 提出澄清问题或直接创建计划
- ✅ AI 生成 `ABOUT_PAGE_PLAN.md` 文档
- ✅ AI 等待用户确认后才继续
- ✅ AI 使用 `manage_todo_list` 工具追踪进度
- ✅ AI 在实施后创建测试指南
- ✅ AI 等待用户测试反馈
- ✅ AI 最后生成实施报告

**3. 检查文档生成**

完成后应该生成以下文件：
```
ABOUT_PAGE_PLAN.md
ABOUT_PAGE_IMPLEMENTATION_REPORT.md
```

---

## 🎓 最佳实践

### 对于用户

#### 1. 清晰的需求描述

**好的示例**:
```
按照标准流程实施：
在 Web UI 的任务页面添加文件格式选择器，支持用户选择要下载的文件类型（PDF、DOCX等）。
默认选中 PDF 和 DOCX，关闭模态框后自动重置选择。
```

**不好的示例**:
```
加个文件格式选项
```

#### 2. 及时反馈

- ✅ **Phase 0**: 审阅计划后明确回复 "确认" 或提出修改意见
- ✅ **Phase 4**: 测试后明确回复 "测试通过" 或详细说明问题
- ❌ 不要长时间不回复，AI 会等待确认

#### 3. 参与决策

当 AI 提出多个方案时：
```
AI: "对于格式选择器，有两种方案：
     A. 使用模态框
     B. 使用独立页面
     请选择一个方案。"

用户: "选择方案 A，更符合现有设计风格"
```

#### 4. 提供充分的测试反馈

**好的反馈**:
```
测试结果：
✅ 功能1正常
✅ 功能2正常
❌ 功能3失败：点击"保存"按钮无反应，浏览器控制台显示 "TypeError: xxx"
```

**不好的反馈**:
```
不太行
```

### 对于 AI（自我提醒）

#### 1. 严格遵循阶段顺序
- ❌ 不要在 Phase 0 未完成时开始编码
- ❌ 不要跳过用户测试直接生成报告
- ✅ 每个阶段完成后明确标记

#### 2. 等待明确确认
- ✅ Phase 0 后等待 "确认" 或 "OK" 或 "开始"
- ✅ Phase 4 后等待 "测试通过" 或 "Tests passed"
- ❌ 不要假设用户已经确认

#### 3. 保持透明沟通
- ✅ 说明当前处于哪个阶段
- ✅ 说明下一步要做什么
- ✅ 说明为什么需要用户确认

#### 4. 使用工具追踪进度
- ✅ 使用 `manage_todo_list` 工具
- ✅ 及时更新任务状态
- ✅ 在报告中显示完成进度

---

## 📊 常见场景

### 场景1: 新功能开发

**用户请求**:
```
按标准流程为系统添加用户权限管理功能
```

**工作流**:
1. AI 分析现有用户系统
2. AI 询问权限粒度、角色定义等问题
3. AI 创建 `USER_PERMISSION_PLAN.md`
4. **用户确认计划**
5. AI 实施（Phase 1-2）
6. AI 创建测试指南
7. **用户执行测试**
8. AI 生成 `USER_PERMISSION_IMPLEMENTATION_REPORT.md`

**预计时间**: 4-8 小时（取决于复杂度）

### 场景2: UI 优化

**用户请求**:
```
用标准流程优化数据库搜索页面的交互体验
```

**工作流**:
1. AI 分析现有 UI 代码
2. AI 提出优化方案（可能包含 A/B 选项）
3. **用户选择方案**
4. AI 实施 UI 改动
5. AI 提供测试步骤（包含截图对比）
6. **用户确认 UI 符合预期**
7. AI 生成文档

**预计时间**: 2-4 小时

### 场景3: Bug 修复（简化流程）

**用户请求**:
```
用标准流程修复导出功能的编码问题，但可以简化测试阶段
```

**工作流**:
1. AI 分析 bug
2. AI 创建简要修复计划
3. AI 实施修复
4. AI 自动化测试
5. AI 提供简单测试步骤
6. **用户确认修复有效**
7. AI 生成简短报告

**预计时间**: 1-2 小时

### 场景4: 重构

**用户请求**:
```
按标准流程重构 storage.py 模块，提高可维护性
```

**工作流**:
1. AI 分析现有代码结构
2. AI 设计新的模块架构
3. **用户批准架构设计**
4. AI 逐步重构（保持功能不变）
5. AI 运行回归测试
6. **用户确认功能无损**
7. AI 生成重构报告（包含架构对比）

**预计时间**: 4-6 小时

---

## 🔧 故障排查

### 问题1: AI 没有遵循标准流程

**症状**: AI 直接开始编码，没有创建计划文档

**原因**:
- Skill 配置文件放置位置错误
- 请求中没有包含触发关键词
- .copilot-instructions.md 格式错误

**解决方法**:
1. 检查文件位置：`.github/copilot-skills/project-development-workflow.md`
2. 使用明确的触发词：
   ```
   请使用标准项目开发流程（project development workflow skill）实施功能X
   ```
3. 验证配置：
   ```
   @workspace 列出项目中配置的自定义 skills
   ```

### 问题2: AI 创建了计划但没有等待确认

**症状**: AI 创建计划后立即开始编码

**原因**: AI 误以为用户已经确认

**解决方法**:
1. 明确告知 AI：
   ```
   请等待我确认计划后再开始实施
   ```
2. 在 .copilot-instructions.md 中强调：
   ```markdown
   **CRITICAL**: Always wait for explicit user approval after Phase 0
   ```

### 问题3: 测试阶段被跳过

**症状**: AI 没有生成测试指南或没有等待用户测试

**原因**: 
- AI 认为功能太简单不需要测试
- 配置中未强调测试的必要性

**解决方法**:
1. 在请求中明确要求：
   ```
   按标准流程实施，请务必包含完整的用户测试阶段
   ```
2. 更新 .copilot-instructions.md：
   ```markdown
   Phase 4 (User Testing) is MANDATORY for all implementations
   ```

### 问题4: 文档生成不完整

**症状**: 实施报告缺少某些章节

**原因**: 
- 项目时间紧迫
- AI 认为某些章节不适用

**解决方法**:
1. 要求生成完整文档：
   ```
   请按照 project-development-workflow.md 中的模板生成完整的实施报告
   ```
2. 检查并补充缺失章节：
   ```
   报告中缺少"故障排查指南"章节，请补充
   ```

---

## 📈 效果评估

### 成功指标

使用标准流程后，项目应该达到：

| 指标 | 目标 | 说明 |
|------|------|------|
| **计划批准率** | >90% | 首次提交的计划被用户直接批准 |
| **首次测试通过率** | >95% | 用户第一次测试就通过 |
| **返工率** | <10% | 测试后需要修改的工作量占比 |
| **文档完整性** | 100% | 所有必要章节都包含 |
| **用户满意度** | >4.5/5 | 用户对实施质量的评价 |

### 对比效果

**使用标准流程前**:
- ❌ 需求理解不清晰，频繁返工
- ❌ 代码质量参差不齐
- ❌ 测试不系统，容易遗漏
- ❌ 文档滞后或缺失
- ⏱️ 总时间: 5-10 小时（包含返工）

**使用标准流程后**:
- ✅ 需求明确，减少误解
- ✅ 代码质量稳定
- ✅ 测试全面，问题及早发现
- ✅ 文档同步更新
- ⏱️ 总时间: 3-5 小时（高效完成）

### 真实案例

**案例**: 文件格式选择器功能
- **复杂度**: 中等
- **使用标准流程**: 是
- **阶段数**: 6
- **总耗时**: 3.5 小时
- **首次测试通过率**: 100%
- **文档完整性**: 100%
- **用户反馈**: "你太棒了！"

---

## 🎯 进阶技巧

### 1. 创建项目特定的 Skill 变体

如果某些流程经常用到，可以创建简化版：

```markdown
# Quick Feature Workflow
基于 Project Development Workflow 的简化版本：
- Phase 0: 简化为快速计划（5分钟）
- Phase 1-2: 合并实施和测试
- Phase 3-4: 简化为快速验证
- Phase 5: 生成简要报告

适用于: 小型功能、bug 修复、样式调整
```

### 2. 集成到 CI/CD

在 GitHub Actions 中引用 Skill：

```yaml
name: Feature Implementation
on:
  issues:
    types: [labeled]

jobs:
  implement:
    if: contains(github.event.issue.labels.*.name, 'feature')
    runs-on: ubuntu-latest
    steps:
      - uses: github/copilot-workspace@v1
        with:
          workflow: .github/copilot-skills/project-development-workflow.md
          issue: ${{ github.event.issue.number }}
```

### 3. 团队协作

多人项目中，指定角色：

```
使用标准流程开发功能 X：
- Phase 0-1: @developer-copilot（AI 实施）
- Phase 4: @qa-team（人工测试）
- Phase 5: @tech-writer（文档审阅）
```

### 4. 度量和优化

创建度量看板：

```markdown
# Development Metrics

| Feature | Phases | Time | Test Pass | Rework |
|---------|--------|------|-----------|--------|
| Feature A | 6/6 | 3.5h | ✅ | 0% |
| Feature B | 6/6 | 4.2h | ✅ | 5% |
| Feature C | 5/6 | 2.8h | ❌→✅ | 15% |

Average: 3.5h, 93% first-time pass rate
```

---

## 📚 相关资源

### 项目文档
- **Skill 定义**: `.github/copilot-skills/project-development-workflow.md`
- **使用指南**: 本文档
- **示例报告**: `FILE_FORMAT_SELECTOR_IMPLEMENTATION_REPORT.md`
- **示例计划**: `FILE_FORMAT_SELECTOR_PLAN.md`

### 外部资源
- [GitHub Copilot 自定义指令](https://docs.github.com/copilot/customizing-copilot)
- [软件开发最佳实践](https://martinfowler.com/)
- [敏捷开发方法](https://agilemanifesto.org/)

### 社区
- 项目 Issues: [报告问题或建议改进](https://github.com/your-repo/issues)
- 讨论区: [分享经验和最佳实践](https://github.com/your-repo/discussions)

---

## 🔄 Skill 更新

### 版本管理

Skill 文件使用语义化版本：
- **Major (1.x.x)**: 重大流程变更
- **Minor (x.1.x)**: 新增阶段或功能
- **Patch (x.x.1)**: 文档更新、小修复

### 更新流程

1. **提出改进**: 在 Issues 中描述改进建议
2. **讨论评审**: 团队讨论可行性
3. **更新文档**: 修改 Skill 定义文件
4. **测试验证**: 在实际项目中验证
5. **发布通知**: 更新版本号和 CHANGELOG

### 订阅更新

在 `.copilot-instructions.md` 中添加：

```markdown
## Skill Version Check

Current version: 1.0
Last checked: 2026-02-05

Check for updates: Ask "@workspace is there a new version of project-development-workflow skill?"
```

---

## ✨ 总结

### 关键要点

1. **配置简单**: 只需放置两个文件
2. **使用灵活**: 支持完整流程或自定义简化
3. **质量保证**: 内置质量门槛和检查点
4. **文档完善**: 自动生成标准化文档
5. **持续改进**: 版本化管理，不断优化

### 快速开始

```bash
# 1. 放置 Skill 文件
cp project-development-workflow.md .github/copilot-skills/

# 2. 验证配置
# 在 Copilot 聊天中输入：
@workspace 使用标准开发流程说明

# 3. 开始使用
# 在 Copilot 聊天中输入：
按照标准流程实施 [你的功能描述]
```

### 获取帮助

如有问题，请：
1. 查看本文档的"故障排查"章节
2. 搜索项目 Issues 看是否有类似问题
3. 创建新 Issue 详细描述问题
4. 联系项目维护者

---

**最后更新**: 2026-02-05  
**文档版本**: 1.0  
**维护者**: 开发团队  

🎉 祝您使用愉快！
