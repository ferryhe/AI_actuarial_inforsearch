import { apiGet } from "./api";

export const WEEKLY_PREVIEW_LIMIT = 8;

export interface WeeklySnapshot {
  id: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  status: "published" | "superseded" | "failed";
  file_count: number;
  metadata: Record<string, unknown>;
}

export interface WeeklySnapshotDetail extends WeeklySnapshot {
  summary_markdown: string;
}

export interface WeeklySnapshotFile {
  url: string;
  title?: string | null;
  original_filename?: string | null;
  first_seen: string;
}

export interface WeeklyExplanation {
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
export type WeeklyExplanationState = "complete" | "missing" | "empty" | "unavailable" | "failed";

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
      `/api/weekly-updates/${snapshotId}/files?limit=${WEEKLY_PREVIEW_LIMIT}&offset=0`,
    ),
    get<WeeklyExplanationResponse>(`/api/weekly-updates/${snapshotId}/explanation`),
  ]);

  return {
    status: "ready",
    snapshot,
    files: filesResult.status === "fulfilled"
      ? (filesResult.value.files || []).slice(0, WEEKLY_PREVIEW_LIMIT)
      : [],
    filesUnavailable: filesResult.status === "rejected",
    explanation: explanationResult.status === "fulfilled"
      ? explanationResult.value.explanation
      : null,
    explanationUnavailable: explanationResult.status === "rejected",
  };
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
    get<WeeklySnapshotFilesResponse>(
      `/api/weekly-updates/${snapshotId}/files?limit=${WEEKLY_PREVIEW_LIMIT}&offset=0`,
    ),
    get<WeeklyExplanationResponse>(`/api/weekly-updates/${snapshotId}/explanation`),
  ]);

  const snapshot = detailResult.status === "fulfilled" ? detailResult.value.summary : null;
  return {
    status: snapshot ? "ready" : "unavailable",
    snapshot,
    files: filesResult.status === "fulfilled"
      ? (filesResult.value.files || []).slice(0, WEEKLY_PREVIEW_LIMIT)
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
    files: data.files.slice(0, WEEKLY_PREVIEW_LIMIT),
    fileCount: data.snapshot?.file_count ?? 0,
    filesUnavailable: data.filesUnavailable,
    explanationState,
    explanationText,
  };
}
