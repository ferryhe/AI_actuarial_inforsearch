import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { EnumDiagnostic, EnumDisplay, canInspectEnumRaw, resolveEnumLabel } from "./enum-display";

const messages = {
  en: { "enum.unknown": "Unknown status", "enum.diagnostic_details": "Diagnostic details", "enum.status.completed": "Completed", "enum.status.queued": "Queued", "enum.status.stopping": "Stopping", "tasks.pipeline.idle": "Idle", "tasks.pipeline.completed_with_errors": "Completed with errors", "tasks.type.catalog": "Catalog", "tasks.type.chunk": "Chunk & Embedding", "tasks.type.ready_data_build": "Ready Data Build", "users.role_operator": "Operator", "users.role_registered": "Registered", "users.role_premium": "Premium", "users.role_admin": "Administrator", "enum.credential_source.db": "Database", "enum.error_stage.catalog": "Catalog", "enum.error_code.file_not_found": "File not found", "enum.error_code.index_launch_failed": "Index launch failed", "enum.kb_status.ready": "Ready", "knowledge.mode_all": "All Files", "knowledge.manifest_profile_general": "General", "knowledge.kb_status.healthy": "Ready for Ask AI.", "settings.status_active": "active" },
  zh: { "enum.unknown": "未知状态", "enum.diagnostic_details": "诊断详情", "enum.status.completed": "已完成", "enum.status.queued": "排队中", "enum.status.stopping": "正在停止", "tasks.pipeline.idle": "空闲", "tasks.pipeline.completed_with_errors": "完成但有错误", "tasks.type.catalog": "编目", "tasks.type.chunk": "分块与嵌入", "tasks.type.ready_data_build": "就绪数据构建", "users.role_operator": "操作员", "users.role_registered": "注册用户", "users.role_premium": "Premium 用户", "users.role_admin": "管理员", "enum.credential_source.db": "数据库", "enum.error_stage.catalog": "编目", "enum.error_code.file_not_found": "找不到文件", "enum.error_code.index_launch_failed": "索引启动失败", "enum.kb_status.ready": "就绪", "knowledge.mode_all": "全部文件", "knowledge.manifest_profile_general": "通用", "knowledge.kb_status.healthy": "已可用于问 AI。", "settings.status_active": "启用" },
};
const translator = (locale: "en" | "zh") => (key: string) => messages[locale][key as keyof typeof messages.en] || key;

test("known enum values use the shared bilingual labels and unknown values do not leak", () => {
  for (const locale of ["en", "zh"] as const) {
    const t = translator(locale);
    assert.equal(resolveEnumLabel("status", "completed", t), locale === "en" ? "Completed" : "已完成");
    assert.equal(resolveEnumLabel("status", "queued", t), locale === "en" ? "Queued" : "排队中");
    assert.equal(resolveEnumLabel("status", "stopping", t), locale === "en" ? "Stopping" : "正在停止");
    assert.equal(resolveEnumLabel("status", "idle", t), locale === "en" ? "Idle" : "空闲");
    assert.equal(resolveEnumLabel("status", "completed_with_errors", t), locale === "en" ? "Completed with errors" : "完成但有错误");
    assert.equal(resolveEnumLabel("role", "registered", t), locale === "en" ? "Registered" : "注册用户");
    assert.equal(resolveEnumLabel("role", "premium", t), locale === "en" ? "Premium" : "Premium 用户");
    assert.equal(resolveEnumLabel("role", "admin", t), locale === "en" ? "Administrator" : "管理员");
    assert.equal(resolveEnumLabel("task_type", "catalog", t), locale === "en" ? "Catalog" : "编目");
    assert.equal(resolveEnumLabel("task_type", "embedding_generation", t), locale === "en" ? "Chunk & Embedding" : "分块与嵌入");
    assert.equal(resolveEnumLabel("task_type", "ready_data_build", t), locale === "en" ? "Ready Data Build" : "就绪数据构建");
    assert.equal(resolveEnumLabel("role", "operator", t), locale === "en" ? "Operator" : "操作员");
    assert.equal(resolveEnumLabel("credential_source", "db", t), locale === "en" ? "Database" : "数据库");
    assert.equal(resolveEnumLabel("error_stage", "catalog", t), locale === "en" ? "Catalog" : "编目");
    assert.equal(resolveEnumLabel("error_code", "file_not_found", t), locale === "en" ? "File not found" : "找不到文件");
    assert.equal(resolveEnumLabel("error_code", "index_launch_failed", t), locale === "en" ? "Index launch failed" : "索引启动失败");
    assert.equal(resolveEnumLabel("kb_status", "ready", t), locale === "en" ? "Ready" : "就绪");
    assert.equal(resolveEnumLabel("kb_mode", "all", t), locale === "en" ? "All Files" : "全部文件");
    assert.equal(resolveEnumLabel("kb_profile", "general", t), locale === "en" ? "General" : "通用");
    assert.equal(resolveEnumLabel("kb_reason", "healthy", t), locale === "en" ? "Ready for Ask AI." : "已可用于问 AI。");
    assert.equal(resolveEnumLabel("credential_status", "active", t), locale === "en" ? "active" : "启用");
    const unknown = renderToStaticMarkup(<><EnumDisplay category="status" value="mystery_internal_status" t={t} /><EnumDiagnostic category="status" value="mystery_internal_status" t={t} /></>);
    assert.match(unknown, new RegExp(locale === "en" ? "Unknown status" : "未知状态"));
    assert.doesNotMatch(unknown, /mystery_internal_status/);
  }
});

test("operator diagnostics are collapsed and gated to privileged viewers", () => {
  const t = translator("en");
  assert.equal(canInspectEnumRaw("registered"), false);
  assert.equal(canInspectEnumRaw("premium"), false);
  assert.equal(canInspectEnumRaw("operator"), true);
  assert.equal(canInspectEnumRaw("admin"), true);
  assert.equal(canInspectEnumRaw("operator_ai"), true);
  const customer = renderToStaticMarkup(<><EnumDisplay category="task_type" value="private_type" t={t} /><EnumDiagnostic category="task_type" value="private_type" t={t} /></>);
  assert.doesNotMatch(customer, /private_type|details/);
  const operator = renderToStaticMarkup(<><EnumDisplay category="task_type" value="private_type" t={t} /><EnumDiagnostic category="task_type" value="private_type" t={t} canInspectRaw /></>);
  assert.match(operator, /<details/);
  assert.match(operator, /private_type/);
  assert.match(renderToStaticMarkup(<EnumDisplay category="task_type" value="catalog" t={t} />), /Catalog/);
});
