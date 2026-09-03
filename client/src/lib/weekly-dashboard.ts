import { apiGet } from "./api";

const WEEKLY_HOME_PREVIEW_LIMIT = 6;
const WEEKLY_FILES_PAGE_LIMIT = 500;

export interface WeeklySnapshot {
  id: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  status: "published" | "superseded" | "failed";
  file_count: number;
  metadata: Record<string, unknown>;
}

interface WeeklySnapshotDetail extends WeeklySnapshot {
  summary_markdown: string;
}

export interface WeeklySnapshotFile {
  url: string;
  title?: string | null;
  original_filename?: string | null;
  first_seen: string;
  category?: string | null;
  keywords?: unknown;
  summary?: string | null;
}

interface WeeklyExplanation {
  snapshot_id: string;
  status: "missing" | "complete" | "failed";
  explanation_zh: string;
  explanation_en: string;
  generated_at: string | null;
}

export interface WeeklyDashboardData {
  status: "ready" | "no_snapshot" | "unavailable";
  snapshot: WeeklySnapshot | null;
  files: WeeklySnapshotFile[];
  filesUnavailable: boolean;
  explanation: WeeklyExplanation | null;
  explanationUnavailable: boolean;
}

interface LatestWeeklySnapshotResponse {
  summary: WeeklySnapshot | null;
}

interface WeeklySnapshotFilesResponse {
  snapshot_id: string;
  files: WeeklySnapshotFile[];
  total: number;
  limit: number;
  offset: number;
  included_count?: number;
  truncated?: boolean;
}

interface WeeklyExplanationResponse {
  explanation: WeeklyExplanation | null;
}

interface WeeklyUpdateListResponse {
  summaries: WeeklySnapshot[];
  total: number;
  limit: number;
  offset: number;
}

interface WeeklySnapshotDetailEnvelope {
  summary: WeeklySnapshotDetail;
}

export type GetJson = <T>(url: string) => Promise<T>;
type WeeklyExplanationState = "complete" | "missing" | "empty" | "unavailable" | "failed";

export function resolveCachedListLoadState<T>(
  response: { files?: T[]; total?: number } | null,
  cached: { files?: T[]; total?: number } | null,
): { files: T[]; total: number; loadError: boolean } {
  const available = response ?? cached;
  return available
    ? { files: available.files || [], total: available.total ?? 0, loadError: false }
    : { files: [], total: 0, loadError: true };
}

export async function loadLatestWeeklyDashboard(
  get: GetJson = apiGet,
): Promise<WeeklyDashboardData> {
  let latest: LatestWeeklySnapshotResponse;
  try {
    latest = await get<LatestWeeklySnapshotResponse>("/api/weekly-updates/latest");
  } catch {
    return {
      status: "unavailable",
      snapshot: null,
      files: [],
      filesUnavailable: true,
      explanation: null,
      explanationUnavailable: true,
    };
  }

  const snapshot = latest.summary;
  if (!snapshot) {
    return {
      status: "no_snapshot",
      snapshot: null,
      files: [],
      filesUnavailable: false,
      explanation: null,
      explanationUnavailable: false,
    };
  }

  const snapshotId = encodeURIComponent(snapshot.id);
  const [filesResult, explanationResult] = await Promise.allSettled([
    get<WeeklySnapshotFilesResponse>(
      `/api/weekly-updates/${snapshotId}/files?limit=${WEEKLY_HOME_PREVIEW_LIMIT}&offset=0`,
    ),
    get<WeeklyExplanationResponse>(`/api/weekly-updates/${snapshotId}/explanation`),
  ]);

  return {
    status: "ready",
    snapshot,
    files: filesResult.status === "fulfilled"
      ? (filesResult.value.files || []).slice(0, WEEKLY_HOME_PREVIEW_LIMIT)
      : [],
    filesUnavailable: filesResult.status === "rejected",
    explanation: explanationResult.status === "fulfilled"
      ? explanationResult.value.explanation
      : null,
    explanationUnavailable: explanationResult.status === "rejected",
  };
}

async function loadAllWeeklySnapshotFiles(
  snapshotId: string,
  get: GetJson,
): Promise<WeeklySnapshotFile[]> {
  const files: WeeklySnapshotFile[] = [];
  let offset = 0;
  let total: number | null = null;

  while (total === null || offset < total) {
    const page = await get<WeeklySnapshotFilesResponse>(
      `/api/weekly-updates/${snapshotId}/files?limit=${WEEKLY_FILES_PAGE_LIMIT}&offset=${offset}`,
    );
    const pageFiles = Array.isArray(page.files) ? page.files : [];
    files.push(...pageFiles);

    const responseTotal = Number(page.total);
    total = Number.isSafeInteger(responseTotal) && responseTotal >= 0
      ? responseTotal
      : offset + pageFiles.length;
    if (pageFiles.length === 0) break;
    offset += pageFiles.length;
  }

  return files;
}

export async function loadWeeklyUpdateList(
  get: GetJson = apiGet,
): Promise<WeeklySnapshot[]> {
  const list = await get<WeeklyUpdateListResponse>("/api/weekly-updates");
  const summaries = (list.summaries || []).slice();
  summaries.sort((a, b) => {
    const aEnd = Date.parse(a.period_end) || 0;
    const bEnd = Date.parse(b.period_end) || 0;
    if (bEnd !== aEnd) return bEnd - aEnd;
    return (Date.parse(b.generated_at) || 0) - (Date.parse(a.generated_at) || 0);
  });
  return summaries;
}

export async function loadWeeklyUpdateDetail(
  id: string,
  get: GetJson = apiGet,
): Promise<WeeklyDashboardData> {
  const snapshotId = encodeURIComponent(id);
  const [detailResult, filesResult, explanationResult] = await Promise.allSettled([
    get<WeeklySnapshotDetailEnvelope>(`/api/weekly-updates/${snapshotId}`),
    loadAllWeeklySnapshotFiles(snapshotId, get),
    get<WeeklyExplanationResponse>(`/api/weekly-updates/${snapshotId}/explanation`),
  ]);

  if (detailResult.status === "rejected") throw detailResult.reason;
  const snapshot = detailResult.value.summary;
  return {
    status: snapshot ? "ready" : "unavailable",
    snapshot,
    files: filesResult.status === "fulfilled"
      ? filesResult.value
      : [],
    filesUnavailable: filesResult.status === "rejected",
    explanation: explanationResult.status === "fulfilled"
      ? explanationResult.value.explanation
      : null,
    explanationUnavailable: explanationResult.status === "rejected",
  };
}

export function buildWeeklyDatabasePath(snapshot: WeeklySnapshot): string {
  const params = new URLSearchParams({
    snapshot_id: snapshot.id,
    first_seen_from: snapshot.period_start,
    first_seen_before: snapshot.period_end,
    order_by: "first_seen",
    order_dir: "desc",
  });
  return `/database?${params.toString()}`;
}

export function formatWeeklyDateTime(value: string | null | undefined, lang: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(parsed);
}

export function formatWeeklyShortDate(value: string | null | undefined, lang: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

export function normalizePublicMetadataText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function normalizePublicCategory(value: unknown): string {
  const category = normalizePublicMetadataText(value);
  return category.split(";").some((part) => Boolean(part.trim())) ? category : "";
}

export function normalizePublicKeywords(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .filter((item): item is string => typeof item === "string")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (typeof value !== "string" || !value.trim()) return [];

  const text = value.trim();
  if (text.startsWith("[")) {
    try {
      return normalizePublicKeywords(JSON.parse(text));
    } catch {
      return [];
    }
  }
  if (text.startsWith("{")) return [];
  return text.split(/[,;]/).map((item) => item.trim()).filter(Boolean);
}

export interface WeeklyFileGroup {
  key: string;
  label: string;
  files: WeeklySnapshotFile[];
}

export function groupWeeklyFiles(
  files: WeeklySnapshotFile[],
  uncategorizedLabel: string,
): WeeklyFileGroup[] {
  const groups = new Map<string, WeeklyFileGroup>();
  for (const file of files) {
    const category = normalizePublicCategory(file.category);
    const primaryCategory = category.split(";").map((part) => part.trim()).find(Boolean);
    const label = primaryCategory || uncategorizedLabel;
    const existing = groups.get(label);
    if (existing) {
      existing.files.push(file);
    } else {
      groups.set(label, { key: label, label, files: [file] });
    }
  }
  return [...groups.values()];
}

function formatWeeklyDate(value: string | null | undefined, lang: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

export function formatWeeklyPeriodLabel(
  start: string | null | undefined,
  end: string | null | undefined,
  lang: string,
): string {
  const startLabel = formatWeeklyDate(start, lang);
  const endLabel = formatWeeklyDate(end, lang);
  if (startLabel === "—" && endLabel === "—") return "—";
  return `${startLabel} – ${endLabel}`;
}

export interface WeeklyDashboardView {
  snapshot: WeeklySnapshot | null;
  files: WeeklySnapshotFile[];
  fileCount: number;
  filesUnavailable: boolean;
  explanationState: WeeklyExplanationState;
  explanationText: string;
}

export function buildWeeklyDashboardView(
  data: WeeklyDashboardData,
  lang: "en" | "zh" | string,
  t: (key: string) => string,
): WeeklyDashboardView {
  const explanation = data.explanation;
  const selected = lang === "zh" ? explanation?.explanation_zh : explanation?.explanation_en;
  let explanationState: WeeklyExplanationState;
  let explanationText: string;

  if (data.explanationUnavailable) {
    explanationState = "unavailable";
    explanationText = t("dashboard.explanation_unavailable");
  } else if (!explanation || explanation.status === "missing") {
    explanationState = "missing";
    explanationText = t("dashboard.explanation_missing");
  } else if (explanation.status === "failed") {
    explanationState = "failed";
    explanationText = t("dashboard.explanation_failed");
  } else if (!String(selected || "").trim()) {
    explanationState = "empty";
    explanationText = t("dashboard.explanation_empty");
  } else {
    explanationState = "complete";
    explanationText = String(selected).trim();
  }

  return {
    snapshot: data.snapshot,
    files: data.files,
    fileCount: data.snapshot?.file_count ?? 0,
    filesUnavailable: data.filesUnavailable,
    explanationState,
    explanationText,
  };
}
