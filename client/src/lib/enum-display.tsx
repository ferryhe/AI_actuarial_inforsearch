export type EnumCategory = "status" | "task_type" | "error_stage" | "error_code" | "role" | "kb_status" | "kb_mode" | "kb_profile" | "kb_reason" | "credential_status" | "credential_source";
type Translate = (key: string) => string;

const keys: Record<EnumCategory, Record<string, string>> = {
  status: { ...Object.fromEntries(["running", "success", "completed", "succeeded", "pending", "queued", "stopping", "error", "failed", "stopped"].map((value) => [value, `enum.status.${value}`])), idle: "tasks.pipeline.idle", completed_with_errors: "tasks.pipeline.completed_with_errors" },
  task_type: { ...Object.fromEntries(["scheduled", "web_crawl", "adhoc_url", "file_import", "web_search", "web_listening", "catalog", "markdown", "chunk", "create_kb", "rag_index", "weekly_summary", "recategory", "site_config"].map((value) => [value, `tasks.type.${value}`])), quick_check: "tasks.type.web_crawl", markdown_conversion: "tasks.type.markdown", chunk_generation: "tasks.type.chunk", embedding_generation: "tasks.type.chunk", ready_data_build: "tasks.type.ready_data_build", rag_indexing: "tasks.type.rag_index", search: "tasks.type.web_search", url: "tasks.type.adhoc_url", file: "tasks.type.file_import" },
  error_stage: Object.fromEntries(["catalog", "embedding", "markdown"].map((value) => [value, `enum.error_stage.${value}`])),
  error_code: Object.fromEntries(["catalog_failed", "file_not_found", "provider_error", "provider_count_mismatch", "invalid_embedding_vector", "conversion_failed", "markdown_update_failed", "index_launch_failed"].map((value) => [value, `enum.error_code.${value}`])),
  role: { registered: "users.role_registered", premium: "users.role_premium", operator: "users.role_operator", admin: "users.role_admin", operator_ai: "users.role_operator_ai_legacy" },
  kb_status: { needs_reindex: "enum.kb_status.needs_reindex", building: "enum.kb_status.building", ready: "enum.kb_status.ready", unavailable: "enum.kb_status.unavailable" },
  kb_mode: { manual: "knowledge.mode_manual", category: "knowledge.mode_category", all: "knowledge.mode_all" },
  kb_profile: { general: "knowledge.manifest_profile_general", regulation: "knowledge.manifest_profile_regulation", formula: "knowledge.manifest_profile_formula" },
  kb_reason: Object.fromEntries(["embedding_incompatible", "content_dirty", "binding_dirty", "index_missing", "index_building", "published_stale_but_servable", "publish_failed", "serving_disabled", "healthy"].map((value) => [value, `knowledge.kb_status.${value}`])),
  credential_status: { active: "settings.status_active", inactive: "settings.status_inactive" },
  credential_source: { db: "enum.credential_source.db", env: "enum.credential_source.env", missing: "enum.credential_source.missing" },
};

export function resolveEnumLabel(category: EnumCategory, value: string | undefined, t: Translate): string {
  return value && Object.prototype.hasOwnProperty.call(keys[category], value) ? t(keys[category][value]) : t("enum.unknown");
}

export function canInspectEnumRaw(role?: string): boolean {
  return role === "operator" || role === "admin" || role === "operator_ai";
}

export function EnumDisplay({ category, value, t }: {
  category: EnumCategory;
  value?: string;
  t: Translate;
}) {
  return <>{resolveEnumLabel(category, value, t)}</>;
}

export function EnumDiagnostic({ category, value, t, canInspectRaw = false }: {
  category: EnumCategory;
  value?: string;
  t: Translate;
  canInspectRaw?: boolean;
}) {
  if (!value || Object.prototype.hasOwnProperty.call(keys[category], value) || !canInspectRaw) return null;
  return <details className="text-[10px] text-muted-foreground" onClick={(event) => event.stopPropagation()}>
    <summary>{t("enum.diagnostic_details")}</summary><code>{value}</code>
  </details>;
}
