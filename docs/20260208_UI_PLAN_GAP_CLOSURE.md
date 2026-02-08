# 20260208_UI_PLAN_GAP_CLOSURE.md

**Date:** 2026-02-08
**Scope:** 补齐 UI 改进计划中未完成项 + 文档编码统一 + README 功能化重写

---

## 完成内容

1. **文档统一编码**
   - 所有 `*.md` 文件统一为 `UTF-8 with BOM`，在 Windows/PowerShell 默认编码下可正确显示。

2. **Typography 体系补齐**
   - 新增字号、字重、行高变量，并在 `body` 与 `h1-h4` 使用。

3. **表单验证反馈**
   - 新增表单错误样式（`.input-error`, `.field-error`, `.form-error`）。
   - `tasks.html` 表单增加统一的前端验证逻辑（基于 HTML5 validity）。

4. **DataTable 列宽拖拽**
   - 支持列头拖拽调整列宽，拖拽宽度会保存到列配置中，排序/重渲染后仍可保持。

5. **DataTable 行内编辑（前端）**
   - 支持列级 `editable` 开关，单元格内容可编辑。
   - 提供 `onCellEdit` 回调，方便后续接后端保存。
   - **注意**：当前仅在前端更新数据，不会自动保存到后端。

6. **README 功能化重写**
   - 移除操作步骤，仅保留功能与能力概览，反映最终项目定位。

---

## 关键文件

- `ai_actuarial/web/static/css/style.css`
- `ai_actuarial/web/static/js/main.js`
- `ai_actuarial/web/templates/tasks.html`
- `ai_actuarial/web/templates/database.html`
- `README.md`
- 所有 `*.md` 文档（编码统一）

---

## 验证清单（你需要测试）

1. **Database 页面表格**
   - 列头拖拽调整宽度，排序后列宽保持不丢失。
   - 正常排序、选择、导出功能未回归。

2. **Tasks 页面表单**
   - 必填字段为空时，出现红色提示与错误样式。
   - 修正后错误提示消失，任务可正常提交。

3. **文档显示**
   - PowerShell `Get-Content` 或编辑器中查看中文与符号不再乱码。

---

## 说明

- 行内编辑为前端能力，若需要持久化请新增 API 并在 `onCellEdit` 中提交更新。
- 列宽拖拽默认关闭，需要在 DataTable 配置中设置 `resizable: true`。

---

**Status:** Ready for review
