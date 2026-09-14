export const KB_STATUS_REASONS = [
  "embedding_incompatible",
  "content_dirty",
  "binding_dirty",
  "index_missing",
  "index_building",
  "published_stale_but_servable",
  "publish_failed",
  "serving_disabled",
  "healthy",
] as const;

type KbStatusReason = (typeof KB_STATUS_REASONS)[number];

export interface KbStatusReference {
  reason?: KbStatusReason | string;
  serving?: boolean;
  usable?: boolean;
}

export function needsReembed(kb: KbStatusReference): boolean {
  return kb.reason === "embedding_incompatible";
}

export function isAskAiAvailable(kb: KbStatusReference | undefined): boolean {
  return Boolean(kb && (kb.serving ?? kb.usable));
}

export function kbStatusMessageKey(reason?: string): string {
  return `knowledge.kb_status.${reason || "healthy"}`;
}
