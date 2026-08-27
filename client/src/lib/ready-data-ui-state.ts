export interface ReadyDataPublication {
  publication_id?: string | null;
  profile?: string | null;
  profile_version?: string | null;
  status?: string | null;
  authoritative_source_version_kind?: string | null;
  authoritative_source_version_id?: string | null;
  observed_index_version_id?: string | null;
  current_ready_index_version_id?: string | null;
  index_consumed_by_builder?: boolean;
  artifact_digest?: string;
  doc_count?: number;
  section_count?: number;
  built_at?: string | null;
  validated_at?: string | null;
  published_at?: string | null;
  smoke_status?: string | null;
  smoke_checked_at?: string | null;
}

export interface ReadyDataPublicationState {
  publication_revision?: number | null;
  serving_status?: "missing" | "ready" | "stale" | "failed" | "unavailable" | null;
  serving_usable?: boolean;
  serving_stale?: boolean;
  automation_state?: string;
  last_error?: string | null;
  latest_operation_kind?: string | null;
  latest_operation_state?: string | null;
  latest_operation_at?: string | null;
  latest_operation_error?: string | null;
  active_publication_id?: string | null;
  previous_publication_id?: string | null;
  active_publication?: ReadyDataPublication | null;
  previous_publication?: ReadyDataPublication | null;
}

export type ReadyDataServingStatus = "missing" | "ready" | "stale" | "failed" | "unavailable";

export interface ReadyDataServingState {
  status: ReadyDataServingStatus;
  usable: boolean;
  stale: boolean;
  source: "publication_state" | "legacy_manifest";
}

export interface ReadyDataOperationState {
  kind: string;
  status: string;
  error: string;
  at: string | null;
  source: "publication_state" | "manifest" | "legacy_automation";
}

export interface AgenticReadyManifest {
  kb_id: string;
  profile: string;
  status: "missing" | "ready" | "building" | "failed" | "stale" | "unavailable";
  usable: boolean;
  output_dir?: string;
  built_at?: string;
  doc_count?: number;
  section_count?: number;
  error_message?: string;
  stale_reason?: string;
  fallback_mode?: string;
  current_doc_count?: number;
  latest_source_at?: string | null;
  serving_stale?: boolean;
  stale_confirmed?: boolean;
  stale_severity?: string;
  stale_reasons?: string[];
  source_state?: Record<string, unknown> | null;
  event_generation?: number | null;
  pending_evaluation_generation?: number | null;
  evaluated_generation?: number | null;
  automation_state?: string;
  automatic_build_enabled?: boolean;
  automatic_publish_enabled?: boolean;
  pending_generation?: number | null;
  running_generation?: number | null;
  last_attempt_publication_id?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  latest_operation_kind?: string | null;
  latest_operation_state?: string | null;
  latest_operation_at?: string | null;
  latest_operation_error?: string | null;
  authoritative_source_version_kind?: string | null;
  authoritative_source_version_id?: string | null;
  observed_index_version_id?: string | null;
  current_ready_index_version_id?: string | null;
  index_consumed_by_builder?: boolean;
  ready_build_input?: {
    contract_version?: number;
    index_version_id: string;
    expected_source_snapshot_fingerprint: string;
  } | null;
  artifact_digest?: string;
  smoke_status?: string | null;
  smoke_checked_at?: string | null;
  publication_revision?: number | null;
  publication_state?: ReadyDataPublicationState;
}

export interface ReadyDataAutomationResponse {
  kb_id?: string;
  profile?: string;
  automation?: {
    automation_state?: string;
    automatic_build_enabled?: boolean;
    automatic_publish_enabled?: boolean;
    pending_evaluation_generation?: number | null;
    running_generation?: number | null;
    last_attempt_publication_id?: string | null;
    last_success_at?: string | null;
    last_error?: string | null;
  };
}

export interface ReadyDataRouteState {
  kbId: string;
  epoch: number;
}

export interface ReadyDataRouteToken {
  kbId: string;
  epoch: number;
}

export interface ReadyDataRequestToken extends ReadyDataRouteToken {
  requestId: number;
}

export interface ReadyDataManifestEpisode {
  version: number;
  profile: string;
}

export interface ReadyDataManifestEpisodeDecision {
  applicable: boolean;
  authoritative: boolean;
  applied: ReadyDataManifestEpisode | null;
}

export function syncReadyDataRoute(
  current: ReadyDataRouteState,
  kbId: string,
): ReadyDataRouteState {
  if (current.kbId === kbId) return current;
  return { kbId, epoch: current.epoch + 1 };
}

export function captureReadyDataRoute(
  current: ReadyDataRouteState,
  mounted: boolean,
  kbId: string,
): ReadyDataRouteToken | null {
  if (!mounted || current.kbId !== kbId) return null;
  return { kbId, epoch: current.epoch };
}

export function isReadyDataRouteCurrent(
  current: ReadyDataRouteState,
  mounted: boolean,
  token: ReadyDataRouteToken | null,
): boolean {
  return Boolean(
    token
    && mounted
    && current.kbId === token.kbId
    && current.epoch === token.epoch,
  );
}

export function captureReadyDataRequest(
  current: ReadyDataRouteState,
  mounted: boolean,
  kbId: string,
  requestId: number,
): ReadyDataRequestToken | null {
  const route = captureReadyDataRoute(current, mounted, kbId);
  return route ? { ...route, requestId } : null;
}

export function isReadyDataRequestCurrent(
  current: ReadyDataRouteState,
  mounted: boolean,
  token: ReadyDataRequestToken | null,
  latestRequestId: number,
): boolean {
  return Boolean(
    token
    && token.requestId === latestRequestId
    && isReadyDataRouteCurrent(current, mounted, token),
  );
}

export async function runReadyDataRouteMutation<T>(options: {
  request: () => Promise<T>;
  isCurrent: () => boolean;
  onSuccess: (response: T) => void | Promise<void>;
  onError: (error: unknown) => void | Promise<void>;
  onSettled?: () => void;
}): Promise<void> {
  try {
    const response = await options.request();
    if (!options.isCurrent()) return;
    await options.onSuccess(response);
  } catch (error) {
    if (!options.isCurrent()) return;
    await options.onError(error);
  } finally {
    if (options.isCurrent()) options.onSettled?.();
  }
}

export const runReadyDataRouteRequest = runReadyDataRouteMutation;

export function selectReadyDataMutationProfile(
  kbId: string,
  manifest: AgenticReadyManifest | null,
  metaKbId: string | undefined,
  metaProfile: string | undefined,
): string {
  if (manifest?.kb_id === kbId && canonicalReadyDataProfile(manifest.profile)) {
    return canonicalReadyDataProfile(manifest.profile);
  }
  if (metaKbId === kbId && canonicalReadyDataProfile(metaProfile)) {
    return canonicalReadyDataProfile(metaProfile);
  }
  return "general";
}

export function canonicalReadyDataProfile(value: unknown): string {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function canonicalReadyDataServingStatus(value: unknown): ReadyDataServingStatus | null {
  if (["missing", "ready", "stale", "failed", "unavailable"].includes(String(value))) {
    return value as ReadyDataServingStatus;
  }
  return null;
}

export function resolveReadyDataServingState(
  manifest: AgenticReadyManifest | null | undefined,
): ReadyDataServingState {
  const projection = manifest?.publication_state;
  const projectedStatus = canonicalReadyDataServingStatus(projection?.serving_status);
  if (projectedStatus && typeof projection?.serving_usable === "boolean") {
    return {
      status: projectedStatus,
      usable: projection.serving_usable,
      stale: typeof projection.serving_stale === "boolean"
        ? projection.serving_stale
        : projectedStatus === "stale",
      source: "publication_state",
    };
  }

  const usable = Boolean(manifest?.usable);
  const legacyStale = Boolean(manifest?.serving_stale);
  const rawStatus = manifest?.status;
  const status = rawStatus === "building"
    ? (usable ? (legacyStale ? "stale" : "ready") : "missing")
    : canonicalReadyDataServingStatus(rawStatus) || "unavailable";
  return {
    status,
    usable,
    stale: legacyStale || status === "stale",
    source: "legacy_manifest",
  };
}

export function resolveReadyDataOperationState(
  manifest: AgenticReadyManifest | null | undefined,
): ReadyDataOperationState {
  const projection = manifest?.publication_state;
  if (typeof projection?.latest_operation_state === "string") {
    const status = normalizeReadyAutomationStatus(projection.latest_operation_state);
    return {
      kind: typeof projection.latest_operation_kind === "string"
        ? projection.latest_operation_kind
        : "none",
      status,
      error: status === "failed" && typeof projection.latest_operation_error === "string"
        ? projection.latest_operation_error
        : "",
      at: typeof projection.latest_operation_at === "string"
        ? projection.latest_operation_at
        : null,
      source: "publication_state",
    };
  }
  if (typeof manifest?.latest_operation_state === "string") {
    const status = normalizeReadyAutomationStatus(manifest.latest_operation_state);
    return {
      kind: typeof manifest.latest_operation_kind === "string"
        ? manifest.latest_operation_kind
        : "none",
      status,
      error: status === "failed" && typeof manifest.latest_operation_error === "string"
        ? manifest.latest_operation_error
        : "",
      at: typeof manifest.latest_operation_at === "string"
        ? manifest.latest_operation_at
        : null,
      source: "manifest",
    };
  }
  const status = normalizeReadyAutomationStatus(
    manifest?.automation_state,
    manifest?.status,
  );
  return {
    kind: status === "idle" ? "none" : "automation",
    status,
    error: status === "failed" && typeof manifest?.last_error === "string"
      ? manifest.last_error
      : "",
    at: null,
    source: "legacy_automation",
  };
}

export function resolveReadyDataManifestEpisode(
  kbId: string,
  incoming: AgenticReadyManifest | null | undefined,
  version: number,
  latestApplied: ReadyDataManifestEpisode | null,
): ReadyDataManifestEpisodeDecision {
  const profile = canonicalReadyDataProfile(incoming?.profile);
  const applicable = Boolean(
    incoming
    && incoming.kb_id === kbId
    && profile
    && Number.isSafeInteger(version)
    && version > 0,
  );
  if (!applicable) {
    return { applicable: false, authoritative: false, applied: latestApplied };
  }
  const authoritative = !latestApplied || version >= latestApplied.version;
  return {
    applicable: true,
    authoritative,
    applied: authoritative ? { version, profile } : latestApplied,
  };
}

function sameReadyDataManifestProfile(
  current: AgenticReadyManifest,
  incoming: AgenticReadyManifest,
): boolean {
  const currentProfile = canonicalReadyDataProfile(current.profile);
  const incomingProfile = canonicalReadyDataProfile(incoming.profile);
  return Boolean(currentProfile) && currentProfile === incomingProfile;
}

export function normalizeReadyAutomationStatus(status: unknown, legacyServingStatus?: unknown) {
  if ((status === undefined || status === null || status === "disabled" || status === "idle")
    && legacyServingStatus === "building") return "building";
  if (status === undefined || status === null || status === "disabled") return "idle";
  if ([
    "idle",
    "pending",
    "running",
    "building",
    "awaiting_publish",
    "awaiting_manual_confirmation",
    "succeeded",
    "failed",
  ].includes(String(status))) return String(status);
  return "failed";
}

export function isReadyDataAutomationBusy(status: unknown): boolean {
  return ["pending", "running", "building"].includes(String(status));
}

export function readyDataOperationKindTranslationKey(kind: unknown): string {
  switch (String(kind ?? "").trim().toLowerCase()) {
    case "build":
      return "knowledge.ready_operation_build";
    case "publish":
    case "publication":
      return "knowledge.ready_operation_publish";
    case "rollback":
      return "knowledge.ready_operation_rollback";
    case "automation":
      return "knowledge.ready_operation_automation";
    default:
      return "knowledge.ready_operation_none";
  }
}

export function mergeConfirmedReadyDataAutomation(
  current: AgenticReadyManifest | null,
  kbId: string,
  profile: string,
  response: ReadyDataAutomationResponse,
): AgenticReadyManifest {
  const automation = response.automation || {};
  const base: AgenticReadyManifest = current || {
    kb_id: kbId,
    profile,
    status: "missing",
    usable: false,
    fallback_mode: "standard",
  };
  const buildEnabled = typeof automation.automatic_build_enabled === "boolean"
    ? automation.automatic_build_enabled
    : Boolean(base.automatic_build_enabled);
  const publishEnabled = buildEnabled && (
    typeof automation.automatic_publish_enabled === "boolean"
      ? automation.automatic_publish_enabled
      : Boolean(base.automatic_publish_enabled)
  );
  return {
    ...base,
    kb_id: kbId,
    profile: canonicalReadyDataProfile(response.profile || profile) || "general",
    automation_state: normalizeReadyAutomationStatus(
      automation.automation_state ?? base.automation_state,
      base.status,
    ),
    automatic_build_enabled: buildEnabled,
    automatic_publish_enabled: publishEnabled,
    pending_generation: automation.pending_evaluation_generation ?? null,
    running_generation: automation.running_generation ?? null,
    last_attempt_publication_id: automation.last_attempt_publication_id ?? null,
    last_success_at: automation.last_success_at ?? null,
    last_error: automation.last_error ?? null,
  };
}

export function mergeConfirmedReadyDataAutomationForKb(
  current: AgenticReadyManifest | null | undefined,
  peer: AgenticReadyManifest | null | undefined,
  kbId: string,
  profile: string,
  response: ReadyDataAutomationResponse,
): AgenticReadyManifest {
  const normalizedProfile = canonicalReadyDataProfile(profile) || "general";
  const currentForProfile = (
    current && canonicalReadyDataProfile(current.profile) === normalizedProfile
  ) ? current : null;
  const peerForProfile = (
    peer && canonicalReadyDataProfile(peer.profile) === normalizedProfile
  ) ? peer : null;
  const base = selectReadyDataManifestUpdate(
    currentForProfile,
    peerForProfile,
    kbId,
    false,
  );
  return mergeConfirmedReadyDataAutomation(
    base,
    kbId,
    normalizedProfile,
    response,
  );
}

export function readyDataPublicationRevision(
  manifest: AgenticReadyManifest | null | undefined,
): number | null {
  const values = [
    manifest?.publication_revision,
    manifest?.publication_state?.publication_revision,
  ].filter(
    (value): value is number => (
      typeof value === "number"
      && Number.isSafeInteger(value)
      && value >= 0
    ),
  );
  return values.length ? Math.max(...values) : null;
}

function readyDataNonNegativeInteger(value: unknown): number | null {
  return typeof value === "number"
    && Number.isSafeInteger(value)
    && value >= 0
    ? value
    : null;
}

function readyDataSourceGeneration(
  manifest: AgenticReadyManifest | null | undefined,
): number | null {
  const nested = manifest?.source_state;
  const nestedGeneration = nested && typeof nested === "object"
    ? readyDataNonNegativeInteger(nested.event_generation)
    : null;
  const directGeneration = readyDataNonNegativeInteger(manifest?.event_generation);
  if (directGeneration === null) return nestedGeneration;
  if (nestedGeneration === null) return directGeneration;
  return Math.max(directGeneration, nestedGeneration);
}

function readyDataEvaluatedGeneration(
  manifest: AgenticReadyManifest | null | undefined,
): number | null {
  const nested = manifest?.source_state;
  const nestedGeneration = nested && typeof nested === "object"
    ? readyDataNonNegativeInteger(nested.evaluated_generation)
    : null;
  const directGeneration = readyDataNonNegativeInteger(manifest?.evaluated_generation);
  if (directGeneration === null) return nestedGeneration;
  if (nestedGeneration === null) return directGeneration;
  return Math.max(directGeneration, nestedGeneration);
}

export function compareReadyDataManifestMonotonicFreshness(
  current: AgenticReadyManifest | null | undefined,
  incoming: AgenticReadyManifest | null | undefined,
): -1 | 0 | 1 {
  if (!current || !incoming || current.kb_id !== incoming.kb_id) return 0;
  if (!sameReadyDataManifestProfile(current, incoming)) return 0;
  const pairs = [
    [readyDataPublicationRevision(current), readyDataPublicationRevision(incoming)],
    [readyDataSourceGeneration(current), readyDataSourceGeneration(incoming)],
    [readyDataEvaluatedGeneration(current), readyDataEvaluatedGeneration(incoming)],
  ] as const;
  let hasHigher = false;
  let hasLower = false;
  for (const [currentValue, incomingValue] of pairs) {
    if (currentValue === null || incomingValue === null) continue;
    if (incomingValue > currentValue) hasHigher = true;
    if (incomingValue < currentValue) hasLower = true;
  }
  if (hasHigher && !hasLower) return 1;
  if (hasLower && !hasHigher) return -1;
  return 0;
}

export function resolveReadyDataSafeMutationManifestEpisode(
  kbId: string,
  current: AgenticReadyManifest | null | undefined,
  incoming: AgenticReadyManifest | null | undefined,
  version: number,
  latestApplied: ReadyDataManifestEpisode | null,
): ReadyDataManifestEpisodeDecision {
  const episode = resolveReadyDataManifestEpisode(
    kbId,
    incoming,
    version,
    latestApplied,
  );
  if (!episode.applicable || !current || !incoming) return episode;
  const freshness = compareReadyDataManifestMonotonicFreshness(current, incoming);
  if (freshness < 0) {
    return { ...episode, authoritative: false, applied: latestApplied };
  }
  if (freshness > 0) {
    return {
      ...episode,
      authoritative: true,
      applied: {
        version: Math.max(version, latestApplied?.version || 0),
        profile: canonicalReadyDataProfile(incoming.profile),
      },
    };
  }
  return episode;
}

const READY_DATA_LATEST_OPERATION_KEYS = [
  "latest_operation_kind",
  "latest_operation_state",
  "latest_operation_at",
  "latest_operation_error",
] as const satisfies readonly (keyof AgenticReadyManifest & keyof ReadyDataPublicationState)[];

const READY_DATA_DYNAMIC_STATE_KEYS = [
  "status",
  "usable",
  "fallback_mode",
  "current_doc_count",
  "latest_source_at",
  "error_message",
  "stale_reason",
  "serving_stale",
  "stale_confirmed",
  "stale_severity",
  "stale_reasons",
  "source_state",
  "event_generation",
  "pending_evaluation_generation",
  "evaluated_generation",
  "automation_state",
  "automatic_build_enabled",
  "automatic_publish_enabled",
  "pending_generation",
  "running_generation",
  "last_attempt_publication_id",
  "last_success_at",
  "last_error",
  ...READY_DATA_LATEST_OPERATION_KEYS,
  "current_ready_index_version_id",
  "ready_build_input",
  "smoke_status",
  "smoke_checked_at",
] as const satisfies readonly (keyof AgenticReadyManifest)[];

function mergeAuthoritativeReadyDataDynamicState(
  current: AgenticReadyManifest,
  incoming: AgenticReadyManifest,
): AgenticReadyManifest {
  const merged = { ...current } as AgenticReadyManifest;
  const mergedRecord = merged as unknown as Record<string, unknown>;
  const currentRecord = current as unknown as Record<string, unknown>;
  const incomingRecord = incoming as unknown as Record<string, unknown>;
  let changed = false;
  for (const key of READY_DATA_DYNAMIC_STATE_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(incoming, key)) continue;
    const value = incomingRecord[key];
    if (Object.is(currentRecord[key], value)) continue;
    mergedRecord[key] = value;
    changed = true;
  }
  if (merged.publication_state) {
    let mergedPublicationState = merged.publication_state;
    for (const key of READY_DATA_LATEST_OPERATION_KEYS) {
      if (!Object.prototype.hasOwnProperty.call(incoming, key)) continue;
      const value = incomingRecord[key];
      if (Object.is(mergedPublicationState[key], value)) continue;
      if (mergedPublicationState === merged.publication_state) {
        mergedPublicationState = { ...merged.publication_state };
      }
      mergedPublicationState[key] = value as never;
      changed = true;
    }
    if (mergedPublicationState !== merged.publication_state) {
      merged.publication_state = mergedPublicationState;
    }
  }
  return changed ? merged : current;
}

export function selectReadyDataManifestUpdate(
  current: AgenticReadyManifest | null | undefined,
  incoming: AgenticReadyManifest | null | undefined,
  kbId: string,
  authoritative: boolean,
): AgenticReadyManifest | null {
  const scopedCurrent = current?.kb_id === kbId ? current : null;
  if (incoming === undefined) return scopedCurrent;
  if (incoming === null) return authoritative ? null : scopedCurrent;
  if (incoming.kb_id !== kbId) return scopedCurrent;
  if (!scopedCurrent) return incoming;
  if (!sameReadyDataManifestProfile(scopedCurrent, incoming)) {
    return authoritative ? incoming : scopedCurrent;
  }

  const currentRevision = readyDataPublicationRevision(scopedCurrent);
  const incomingRevision = readyDataPublicationRevision(incoming);
  if (currentRevision !== null || incomingRevision !== null) {
    if (currentRevision === null) return incoming;
    if (incomingRevision === null) return scopedCurrent;
    if (incomingRevision > currentRevision) return incoming;
    if (incomingRevision < currentRevision) return scopedCurrent;
    const currentHasPublicProjection = Boolean(scopedCurrent.publication_state);
    const incomingHasPublicProjection = Boolean(incoming.publication_state);
    if (currentHasPublicProjection && !incomingHasPublicProjection) {
      return authoritative
        ? mergeAuthoritativeReadyDataDynamicState(scopedCurrent, incoming)
        : scopedCurrent;
    }
    if (!currentHasPublicProjection && incomingHasPublicProjection) return incoming;
    return authoritative ? incoming : scopedCurrent;
  }
  return authoritative ? incoming : scopedCurrent;
}

export function selectReadyDataManifestEpisodeUpdate(
  current: AgenticReadyManifest | null | undefined,
  incoming: AgenticReadyManifest | null | undefined,
  kbId: string,
  decision: ReadyDataManifestEpisodeDecision,
  responseTimeMerged = false,
): AgenticReadyManifest | null {
  if (decision.applicable && !decision.authoritative && !current) return null;
  if (
    responseTimeMerged
    && decision.applicable
    && !decision.authoritative
    && current
    && incoming
    && current.kb_id === kbId
    && incoming.kb_id === kbId
    && sameReadyDataManifestProfile(current, incoming)
  ) {
    return incoming;
  }
  return selectReadyDataManifestUpdate(
    current,
    incoming,
    kbId,
    decision.authoritative,
  );
}

export interface ReadyDataKnowledgeListItem {
  id?: string;
  kb_id?: string;
  manifest_profile?: string;
  agentic_ready_manifest?: AgenticReadyManifest;
}

export type ReadyDataManifestAuthority = boolean | ((kbId: string) => boolean);

function readyDataKnowledgeListItemId(item: ReadyDataKnowledgeListItem): string {
  return String(item.kb_id || item.id || item.agentic_ready_manifest?.kb_id || "").trim();
}

export function mergeReadyDataKnowledgeList<T extends ReadyDataKnowledgeListItem>(
  current: readonly T[],
  incoming: readonly T[],
  manifestAuthority: ReadyDataManifestAuthority = true,
): T[] {
  const currentByKbId = new Map(
    current
      .map((item) => [readyDataKnowledgeListItemId(item), item] as const)
      .filter(([kbId]) => Boolean(kbId)),
  );
  return incoming.map((item) => {
    const kbId = readyDataKnowledgeListItemId(item);
    if (!kbId) return item;
    const existing = currentByKbId.get(kbId);
    const manifestAuthoritative = typeof manifestAuthority === "function"
      ? manifestAuthority(kbId)
      : manifestAuthority;
    const manifest = selectReadyDataManifestUpdate(
      existing?.agentic_ready_manifest,
      item.agentic_ready_manifest,
      kbId,
      manifestAuthoritative,
    );
    return {
      ...item,
      manifest_profile: manifestAuthoritative
        ? (item.manifest_profile ?? manifest?.profile)
        : (existing?.manifest_profile ?? manifest?.profile ?? item.manifest_profile),
      agentic_ready_manifest: manifest || undefined,
    } as T;
  });
}

export function isReadyDataKnowledgeListManifestAuthoritative(
  requestVersion: number,
  latestAppliedVersion: number,
): boolean {
  return requestVersion >= latestAppliedVersion;
}

export function mergeReadyDataKnowledgeManifest<T extends ReadyDataKnowledgeListItem>(
  current: readonly T[],
  kbId: string,
  incoming: AgenticReadyManifest | null | undefined,
  authoritative: boolean,
): T[] {
  return current.map((item) => {
    if (readyDataKnowledgeListItemId(item) !== kbId) return item;
    const manifest = selectReadyDataManifestUpdate(
      item.agentic_ready_manifest,
      incoming,
      kbId,
      authoritative,
    );
    return {
      ...item,
      manifest_profile: authoritative
        ? (manifest?.profile ?? item.manifest_profile)
        : (item.manifest_profile ?? manifest?.profile),
      agentic_ready_manifest: manifest || undefined,
    } as T;
  });
}

export function readyDataManifestAfterLoad(
  current: AgenticReadyManifest | null,
  next: AgenticReadyManifest | null,
  succeeded: boolean,
  preserveCurrentOnError: boolean,
): AgenticReadyManifest | null {
  if (succeeded) {
    const kbId = next?.kb_id || current?.kb_id || "";
    return kbId
      ? selectReadyDataManifestUpdate(current, next, kbId, true)
      : next;
  }
  return preserveCurrentOnError ? current : null;
}

export function selectEffectiveReadyDataManifest(
  kbId: string,
  dedicated: AgenticReadyManifest | null,
  metaKbId: string | undefined,
  nested: AgenticReadyManifest | null | undefined,
): AgenticReadyManifest | null {
  if (dedicated?.kb_id === kbId) return dedicated;
  if (metaKbId === kbId && nested?.kb_id === kbId) return nested;
  return null;
}

export function shouldPollReadyDataManifest(
  manifest: AgenticReadyManifest | null,
  attempts: number,
  maxAttempts: number,
): boolean {
  const state = normalizeReadyAutomationStatus(
    manifest?.automation_state,
    manifest?.status,
  );
  return ["pending", "running", "building"].includes(state) && attempts < maxAttempts;
}

export function scheduleReadyDataPoll<T>(
  callback: () => void,
  delay: number,
  setTimer: (callback: () => void, delay: number) => T,
  clearTimer: (handle: T) => void,
): () => void {
  const handle = setTimer(callback, delay);
  return () => clearTimer(handle);
}

export function readyDataRollbackErrorKey(status: number | undefined, refreshed: boolean) {
  if (status === 409) {
    return refreshed
      ? "knowledge.ready_rollback_conflict"
      : "knowledge.ready_rollback_conflict_refresh_failed";
  }
  return "knowledge.ready_rollback_failed";
}
