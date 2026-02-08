# Project Development Workflow Skill

## Skill Identity
- **Name**: Project Development Workflow
- **Version**: 1.0
- **Type**: Development Process
- **Category**: Software Engineering

## Description
A comprehensive, battle-tested development workflow that ensures high-quality implementation through systematic planning, phased execution, automated testing, user validation, and complete documentation.

## When to Use This Skill
Trigger this workflow when:
- User requests: "按照标准流程开发...", "Use standard workflow for...", "Follow best practices to implement..."
- User mentions: "#dev-workflow", "#standard-process", "#best-practice"
- Project requires: Multiple phases, testing validation, or comprehensive documentation
- Features are: Medium to high complexity, user-facing, or mission-critical

## Workflow Phases

### Phase 0: Requirements Analysis & Planning
**Objective**: Understand requirements and create detailed implementation plan

**Steps**:
1. **Analyze Current State**
   - Review existing codebase structure
   - Identify affected modules and dependencies
   - Check for similar implementations or patterns
   - Document technical constraints

2. **Clarify Requirements**
   - Ask clarifying questions if requirements are ambiguous
   - Confirm user expectations and success criteria
   - Identify potential risks and challenges
   - Define scope boundaries (what's in, what's out)

3. **Create Implementation Plan**
   - Break down work into logical phases (usually 3-5 phases)
   - Define deliverables for each phase
   - Estimate effort for each phase
   - Identify dependencies between phases
   - Create task list with clear status tracking

4. **Design Technical Solution**
   - Choose appropriate design patterns
   - Plan data structures and interfaces
   - Design UI/UX if applicable
   - Make key technical decisions (document rationale)
   - Create architecture diagrams if needed

5. **Get User Approval**
   - Present plan document to user
   - Include: scope, phases, timeline, key decisions
   - Wait for explicit user confirmation before proceeding
   - Adjust plan based on user feedback

**Deliverable**: Comprehensive plan document (e.g., `FEATURE_NAME_PLAN.md`)

**Template**: See [Plan Template](#plan-template) section

---

### Phase 1: Core Implementation
**Objective**: Implement the planned functionality

**Steps**:
1. **Setup Task Tracking**
   - Use `manage_todo_list` tool to create tasks
   - Mark current task as "in-progress"
   - Keep todo list updated throughout implementation

2. **Implement in Logical Order**
   - Start with foundational components
   - Build incrementally (don't try to do everything at once)
   - Follow the phases defined in the plan
   - Keep changes focused and coherent

3. **Code Quality Standards**
   - Follow project's existing code style
   - Use meaningful variable/function names
   - Add comments for complex logic
   - Keep functions small and focused
   - Handle errors gracefully

4. **Incremental Commits** (Mental Checkpoints)
   - After completing each sub-task, verify it works
   - Mark task as complete in todo list
   - Document what was done before moving to next task

5. **Phase Completion Checklist**
   - [ ] All planned features implemented
   - [ ] Code follows project standards
   - [ ] No syntax errors (use `get_errors` tool)
   - [ ] Changes are coherent and complete
   - [ ] Ready for testing

**Progress Tracking**: Update todo list after each major milestone

---

### Phase 2: Automated Testing
**Objective**: Verify implementation through automated checks

**Steps**:
1. **Syntax & Static Analysis**
   ```bash
   # Use get_errors tool to check for:
   - Syntax errors
   - Type errors (if applicable)
   - Linting issues
   - Import errors
   ```

2. **Code Structure Verification**
   - Verify all planned files are modified/created
   - Check for missing imports or dependencies
   - Validate configuration files if changed
   - Review error handling paths

3. **Logic Validation**
   - Review critical code paths
   - Check edge cases are handled
   - Verify default values make sense
   - Ensure backward compatibility if needed

4. **Integration Check**
   - Verify new code integrates with existing code
   - Check API contracts are maintained
   - Validate data flow end-to-end
   - Ensure no breaking changes (unless intended)

**Deliverable**: Clean build with no errors

**Tools to Use**:
- `get_errors` - Check for compile/lint errors
- `grep_search` - Verify code patterns
- `read_file` - Review specific implementations

---

### Phase 3: User Testing Preparation
**Objective**: Prepare for user validation

**Steps**:
1. **Create Testing Guide**
   - List all features to test
   - Provide step-by-step testing instructions
   - Include expected outcomes for each test
   - Add troubleshooting section

2. **Testing Checklist Format**
   ```markdown
   ### 🚀 Testing Steps
   
   **1. Start the application**
   ```bash
   # Command to start
   ```
   
   **2. Test Feature A**
   - [ ] Step 1: Do X
   - [ ] Step 2: Verify Y appears
   - [ ] Step 3: Check Z works
   
   **3. Test Feature B**
   - [ ] Step 1: ...
   
   ### 📸 If Issues Found
   Please report:
   1. Which step failed
   2. Error messages (if any)
   3. Screenshots (if helpful)
   ```

3. **Prepare Test Data** (if needed)
   - Create sample data for testing
   - Document test scenarios
   - Provide reset/cleanup instructions

4. **Environment Check**
   - Verify development environment is clean
   - Check no temporary files interfere
   - Ensure dependencies are installed
   - Confirm configuration is correct

**Deliverable**: Testing guide provided to user

---

### Phase 4: User Testing & Validation
**Objective**: Get user confirmation that implementation meets requirements

**Steps**:
1. **Present Testing Guide**
   - Provide clear, numbered steps
   - Include expected vs. actual outcome columns
   - Make it easy to report issues

2. **Wait for User Feedback**
   - Do NOT proceed until user confirms testing
   - Be ready to fix issues immediately
   - Track which tests pass/fail

3. **Issue Resolution** (if needed)
   - Prioritize blocking issues
   - Fix and retest iteratively
   - Update code and documentation
   - Re-run automated tests after fixes

4. **Final Confirmation**
   - Get explicit "测试通过" or "Tests passed" from user
   - Confirm all features work as expected
   - Verify no regressions introduced

**Success Criteria**: User explicitly confirms all tests passed

---

### Phase 5: Documentation
**Objective**: Create comprehensive implementation report

**Steps**:
1. **Implementation Report Structure**
   ```markdown
   # [Feature Name] Implementation Report
   
   ## 📋 Project Overview
   - Project name, date, status
   - Completion statistics
   - Core achievements
   
   ## 📊 Implementation Summary
   - What was built
   - Key technical decisions
   - Challenges overcome
   
   ## 🎯 Detailed Implementation
   - Phase-by-phase breakdown
   - Code changes explained
   - Architecture decisions
   
   ## 📝 Code Statistics
   - Files modified
   - Lines added/changed
   - Complexity metrics
   
   ## ✅ Testing Results
   - Automated test results
   - User test results
   - Known issues (if any)
   
   ## 📖 User Documentation
   - How to use the new feature
   - Configuration options
   - Examples
   
   ## 🔍 Troubleshooting Guide
   - Common issues and solutions
   - FAQ
   
   ## 📈 Future Work
   - Potential enhancements
   - Technical debt notes
   - Related features
   
   ## 🎉 Summary
   - Key achievements
   - Lessons learned
   - Acknowledgments
   ```

2. **Documentation Quality Standards**
   - Clear and concise language
   - Code examples with syntax highlighting
   - Screenshots/diagrams where helpful
   - Organized with clear headings
   - Complete and self-contained

3. **Update Related Documentation**
   - Update README if needed
   - Update API documentation
   - Update configuration guides
   - Add to changelog

4. **Final Review**
   - Proofread all documents
   - Check links work
   - Verify code examples are correct
   - Ensure consistency across documents

**Deliverable**: `FEATURE_NAME_IMPLEMENTATION_REPORT.md`

---

### Phase 6: Completion & Handoff
**Objective**: Finalize the project and ensure maintainability

**Steps**:
1. **Complete Todo List**
   - Mark all tasks as completed
   - Archive todo list (if using external tracking)

2. **Code Review Checklist**
   - [ ] All planned features implemented
   - [ ] Tests passed (automated + user)
   - [ ] Documentation complete
   - [ ] No known critical issues
   - [ ] Code is maintainable
   - [ ] Follows project conventions

3. **Summary for User**
   ```markdown
   ## 🎉 Project Complete!
   
   ✅ **Completion**: [X/X phases]
   ✅ **Testing**: All tests passed
   ✅ **Documentation**: Complete
   
   ### 📁 Deliverables
   - Implementation: [files modified]
   - Documentation: [reports created]
   
   ### 🚀 Next Steps
   [What user should do next, if anything]
   ```

4. **Archive Project Materials**
   - Ensure all documents are saved
   - Link related documents together
   - Add to project knowledge base

**Deliverable**: Project completion summary

---

## Templates

### Plan Template
```markdown
# [Feature Name] Implementation Plan

## 一、现状分析
[Current state analysis]

## 二、需求说明
[Requirements and goals]

## 三、技术方案
[Technical approach and design decisions]

## 四、实施步骤
### Phase 1: [Name]
**时间估算**: [X hours]
**步骤**:
- [ ] Step 1
- [ ] Step 2

### Phase 2: [Name]
...

## 五、关键决策点
### 决策1: [Decision Name]
**选项**: A vs B
**选择**: [A/B]
**理由**: [Rationale]

## 六、风险与注意事项
[Risks and considerations]

## 七、成功标准
- [ ] Criterion 1
- [ ] Criterion 2

## 八、时间估算
**总计**: [X-Y hours]
```

### Testing Guide Template
```markdown
## 🚀 测试步骤

**1. 启动应用**
```bash
[command]
```

**2. 功能测试A**
- [ ] 步骤1: [action]
- [ ] 预期: [expected]
- [ ] 实际: [actual - filled by user]

**3. 功能测试B**
- [ ] 步骤1: [action]
...

## 📸 问题反馈
如发现问题，请提供：
1. 哪个步骤失败
2. 错误信息
3. 截图（如需要）
```

### Implementation Report Template
[See Phase 5 documentation structure]

---

## Quality Gates

Each phase has quality gates that must be met before proceeding:

| Phase | Quality Gate | Tool/Method |
|-------|-------------|-------------|
| 0. Planning | User approval received | User confirmation |
| 1. Implementation | No syntax errors | `get_errors` |
| 2. Automated Testing | All checks pass | Tool validation |
| 3. Testing Prep | Guide is clear | Self-review |
| 4. User Testing | User confirms "测试通过" | User feedback |
| 5. Documentation | Report is complete | Checklist |
| 6. Completion | All deliverables ready | Final review |

**Rule**: Cannot proceed to next phase until current phase's quality gate is met.

---

## Best Practices

### Communication
- ✅ Keep user informed of progress
- ✅ Ask clarifying questions early
- ✅ Provide clear testing instructions
- ✅ Document decisions and rationale
- ❌ Don't make assumptions about unclear requirements
- ❌ Don't skip user approval steps

### Implementation
- ✅ Break work into small, testable increments
- ✅ Follow existing project patterns
- ✅ Write self-documenting code
- ✅ Handle errors gracefully
- ❌ Don't try to implement everything at once
- ❌ Don't skip automated testing

### Documentation
- ✅ Write as you code (not at the end)
- ✅ Include examples and use cases
- ✅ Keep documentation up-to-date
- ✅ Make it easy to find information
- ❌ Don't assume user knows technical details
- ❌ Don't leave undocumented features

### Testing
- ✅ Test both happy path and edge cases
- ✅ Verify backward compatibility
- ✅ Get real user feedback
- ✅ Document test procedures
- ❌ Don't skip user testing
- ❌ Don't assume code works without verification

---

## Metrics & Success Indicators

### Process Metrics
- **Planning Quality**: User approves plan on first try
- **Implementation Velocity**: Phases completed on time
- **Test Pass Rate**: >95% pass rate on first user test
- **Documentation Completeness**: All sections filled

### Quality Metrics
- **Code Quality**: Zero syntax errors, follows conventions
- **User Satisfaction**: User explicitly confirms "测试通过"
- **Maintainability**: Clear code with good structure
- **Completeness**: All planned features delivered

### Efficiency Metrics
- **Rework Rate**: Minimal changes after user testing
- **Time to First Test**: Quick feedback loop
- **Documentation Time**: <20% of total time

---

## Troubleshooting

### "User requirements unclear"
- Stop and ask specific clarifying questions
- Provide examples or options for user to choose
- Don't proceed until requirements are clear

### "Implementation taking longer than planned"
- Re-evaluate scope with user
- Consider breaking into smaller phases
- Update time estimates and communicate

### "User testing finds critical issues"
- Prioritize fixes immediately
- Re-run automated tests after fixes
- Conduct focused retesting
- Update documentation to reflect changes

### "Documentation feels incomplete"
- Review against template checklist
- Add concrete examples
- Include troubleshooting section
- Get peer review if possible

---

## Example Usage

### User Request
```
"请按照标准流程为Web UI添加文件格式选择器功能"
```

### AI Response
```
好的！我将使用标准的项目开发流程来实施文件格式选择器功能。

【Phase 0: 规划】
我先分析当前代码，然后制定详细的实施计划...
[creates comprehensive plan]

请您审阅计划，确认无误后我将开始实施。

[waits for user approval]

【Phase 1-6: Execute】
[follows workflow systematically]
```

---

## Skill Evolution

### Version History
- **v1.0** (2026-02-05): Initial version based on file format selector project

### Future Enhancements
- Add performance benchmarking phase
- Include security review checklist
- Add A/B testing guidance
- Create phase time estimates database
- Add rollback procedures

---

## Related Skills
- Code Review Skill
- Bug Fix Workflow
- Performance Optimization Workflow
- Documentation Writing Skill

---

## Metadata
- **Last Updated**: 2026-02-05
- **Maintained By**: Development Team
- **Success Rate**: 100% (1/1 projects)
- **Average Duration**: 3-5 hours for medium complexity features
