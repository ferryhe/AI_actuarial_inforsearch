import { apiGet } from "./api";
import { formatDateTime, formatUtcIso } from "./date-format";
import { localizedCatalogMetadata } from "./bilingual-metadata";
import { getCanonicalDisplayName } from "@/pages/chat/displayName";

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
  bilingual_metadata?: unknown;
}

interface WeeklyExplanation {
  snapshot_id: string;
  status: "missing" | "complete" | "failed";
  generation_mode?: "ai" | "empty" | "fallback" | null;
  explanation_zh: string;
  explanation_en: string;
  generated_at: string | null;
}

export interface WeeklyDashboardData {
  status: "ready" | "no_snapshot" | "unavailable";
  snapshot: WeeklySnapshot | null;
  files: WeeklySnapshotFile[];
  filesPreviewLimit?: number;
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

  const data: WeeklyDashboardData = {
    status: "ready",
    snapshot,
    filesPreviewLimit: WEEKLY_HOME_PREVIEW_LIMIT,
    files: filesResult.status === "fulfilled"
      ? (filesResult.value.files || []).slice(0, WEEKLY_HOME_PREVIEW_LIMIT)
      : [],
    filesUnavailable: filesResult.status === "rejected",
    explanation: explanationResult.status === "fulfilled"
      ? explanationResult.value.explanation
      : null,
    explanationUnavailable: explanationResult.status === "rejected",
  };
  const urls = weeklyRecommendationUrls(data);
  let offset = data.files.length;
  const total = filesResult.status === "fulfilled" ? filesResult.value.total : 0;
  while (offset < total && urls.some((url) => !data.files.some((file) => weeklyGuideUrl(file.url) === url))) {
    try {
      const page = await get<WeeklySnapshotFilesResponse>(
        `/api/weekly-updates/${snapshotId}/files?limit=${WEEKLY_FILES_PAGE_LIMIT}&offset=${offset}`,
      );
      const next = page.files || [];
      if (!next.length) break;
      data.files.push(...next);
      offset += next.length;
    } catch {
      // Keep all members read so far if a later page is unavailable.
      break;
    }
  }
  data.files = orderWeeklyFiles(data.files, urls).slice(0, WEEKLY_HOME_PREVIEW_LIMIT);
  return data;
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
  return formatDateTime(value, lang, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function formatWeeklyPeriodUtcTitle(
  start: string | null | undefined,
  end: string | null | undefined,
): string | undefined {
  const startIso = formatUtcIso(start);
  const endIso = formatUtcIso(end);
  return startIso && endIso ? `${startIso} – ${endIso} (UTC)` : undefined;
}

export function formatWeeklyShortDate(value: string | null | undefined, lang: string): string {
  return formatDateTime(value, lang, {
    month: "short",
    day: "numeric",
  });
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

export function localizedWeeklyFileMetadata(file: WeeklySnapshotFile, lang: string) {
  return localizedCatalogMetadata(file.bilingual_metadata, lang, {
    title: file.title,
    summary: file.summary,
    category: file.category,
    keywords: normalizePublicKeywords(file.keywords),
  });
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
  return formatDateTime(value, lang, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
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
  recommendedCount: number;
}

function weeklyGuideUrl(url: string): string {
  return url.replace(/\(/g, "%28").replace(/\)/g, "%29").replace(/ /g, "%20");
}

function weeklyRecommendationUrls(data: WeeklyDashboardData): string[] {
  const explanation = data.explanation;
  if (explanation?.snapshot_id !== data.snapshot?.id || !explanation
    || !["complete", "failed"].includes(explanation.status)) return [];
  // Saved guides use the list-link format produced by the server's _render_guide.
  const guide = explanation.explanation_en || explanation.explanation_zh;
  return [...new Set([...guide.matchAll(/^- \[(?:\\.|[^\]\\])*\]\((https?:\/\/\S+)\)\s*$/gm)]
    .map((match) => match[1]))].slice(0, 3);
}

function frozenWeeklyRecommendationFiles(data: WeeklyDashboardData): WeeklySnapshotFile[] | null {
  const snapshot = data.snapshot;
  const explanation = data.explanation;
  if (!snapshot || !explanation || explanation.snapshot_id !== snapshot.id || !explanation.generated_at) {
    return null;
  }
  const metadata = snapshot.metadata;
  const owner = metadata.weekly_recommendation_cards_v1_owner;
  const projections = metadata.weekly_recommendation_cards_v1;
  if (!owner || typeof owner !== "object" || !Array.isArray(projections)) return null;
  const guideOwner = owner as Record<string, unknown>;
  if (guideOwner.snapshot_id !== snapshot.id || guideOwner.guide_generated_at !== explanation.generated_at) {
    return null;
  }

  const urls = weeklyRecommendationUrls(data);
  if (!urls.length || projections.length !== urls.length) return null;
  const projectionByUrl = new Map<string, Record<string, unknown>>();
  for (const value of projections) {
    if (!value || typeof value !== "object") return null;
    const projection = value as Record<string, unknown>;
    const url = typeof projection.url === "string" ? weeklyGuideUrl(projection.url) : "";
    if (!url || projectionByUrl.has(url)) {
      return null;
    }
    if (typeof projection.first_seen !== "string"
      || (projection.original_filename !== null && typeof projection.original_filename !== "string")
      || typeof projection.title !== "string" || !Array.isArray(projection.keywords)
      || projection.keywords.some((keyword) => typeof keyword !== "string")
      || (projection.category !== null && typeof projection.category !== "string")
      || (projection.summary !== null && typeof projection.summary !== "string")
      || (projection.bilingual_metadata !== null
        && (typeof projection.bilingual_metadata !== "object" || Array.isArray(projection.bilingual_metadata)))) {
      return null;
    }
    projectionByUrl.set(url, projection);
  }
  if (projections.some((value, index) => {
    const projection = value as Record<string, unknown>;
    return weeklyGuideUrl(projection.url as string) !== urls[index];
  })) return null;
  if (urls.some((url) => !projectionByUrl.has(url))) return null;

  const filesByUrl = new Map(data.files.map((file) => [weeklyGuideUrl(file.url), file]));
  const recommendations = urls.map((url) => {
    const projection = projectionByUrl.get(url)!;
    const existing = filesByUrl.get(url);
    return {
      ...existing,
      url: existing?.url || projection.url as string,
      first_seen: projection.first_seen as string,
      original_filename: projection.original_filename as string | null,
      title: projection.title as string,
      category: projection.category as string | null,
      keywords: projection.keywords as string[],
      summary: projection.summary as string | null,
      bilingual_metadata: projection.bilingual_metadata,
    };
  });
  const nonRecommendations = data.files.filter((file) => !projectionByUrl.has(weeklyGuideUrl(file.url)));
  return [...recommendations, ...nonRecommendations];
}

function orderWeeklyFiles(files: WeeklySnapshotFile[], urls: string[]): WeeklySnapshotFile[] {
  const byUrl = new Map(files.map((file) => [weeklyGuideUrl(file.url), file]));
  const recommended = urls.flatMap((url) => byUrl.has(url) ? [byUrl.get(url)!] : []);
  const selected = new Set(recommended);
  return [...recommended, ...files.filter((file) => !selected.has(file))];
}

export function buildWeeklyDashboardView(
  data: WeeklyDashboardData,
  lang: "en" | "zh" | string,
  t: (key: string) => string,
): WeeklyDashboardView {
  const explanation = data.explanation?.snapshot_id === data.snapshot?.id ? data.explanation : null;
  const selected = lang === "zh" ? explanation?.explanation_zh : explanation?.explanation_en;
  const recommendationUrls = weeklyRecommendationUrls(data);
  const frozenFiles = frozenWeeklyRecommendationFiles(data);
  const orderedFiles = orderWeeklyFiles(frozenFiles || data.files, recommendationUrls);
  const files = data.filesPreviewLimit
    ? orderedFiles.slice(0, data.filesPreviewLimit)
    : orderedFiles;
  let explanationState: WeeklyExplanationState;
  let explanationText: string;

  if (data.status === "ready" && data.snapshot?.file_count === 0) {
    explanationState = "empty";
    explanationText = lang === "zh" ? "本周暂无新资料。" : "No new material this week.";
  } else if (data.explanationUnavailable) {
    explanationState = "unavailable";
    explanationText = t("dashboard.explanation_unavailable");
  } else if (!explanation || explanation.status === "missing") {
    explanationState = "missing";
    explanationText = t("dashboard.explanation_missing");
  } else if (explanation.status === "failed") {
    explanationState = "failed";
    explanationText = t("dashboard.files_unavailable");
  } else if (!String(selected || "").trim()) {
    explanationState = "empty";
    explanationText = t("dashboard.explanation_empty");
  } else {
    explanationState = "complete";
    explanationText = String(selected).trim();
  }

  const loadedRecommendationUrls = new Set(data.files.map((file) => weeklyGuideUrl(file.url)));
  const savedRecommendationsAvailable = recommendationUrls.length > 0
    && recommendationUrls.every((url) => loadedRecommendationUrls.has(url));
  const canBuildRecommendations = frozenFiles !== null
    || (!data.filesUnavailable && savedRecommendationsAvailable);
  const recommendations = data.snapshot?.file_count && canBuildRecommendations
    && ["complete", "failed"].includes(explanationState)
    ? files.slice(0, recommendationUrls.length)
    : [];
  if (recommendations.length) {
    const escape = (value: string) => value.replace(/([\\`*{}\[\]<>#.!_+()\-])/g, "\\$1").replace(/\r?\n/g, " ");
    const items = recommendations.map((file) => {
      const metadata = localizedWeeklyFileMetadata(file, lang);
      const title = getCanonicalDisplayName({ ...file, title: metadata.title }, t("dashboard.untitled_material"));
      const topics = metadata.keywords.slice(-3).map(escape);
      return { title: escape(title), focus: topics.join(lang === "zh" ? "、" : ", "), topics };
    });
    const themes = [...new Set(items.flatMap((item) => item.topics))].join(lang === "zh" ? "、" : ", ");
    const count = lang === "zh" ? `本周发现 ${data.snapshot!.file_count} 篇文章。` : `This week, we discovered ${data.snapshot!.file_count} articles.`;
    const focus = themes
      ? (lang === "zh" ? `本周重点包括：${themes}。` : `This week's highlights cover ${themes}.`)
      : (lang === "zh" ? "这些文章的主题信息尚未提供。" : "Topic details are unavailable for these articles.");
    const heading = lang === "zh" ? "本周推荐阅读以下文章：" : "Recommended reading this week:";
    explanationText = [count, focus, heading, ...items.map((item, index) => lang === "zh"
      ? `${index + 1}. ${item.title}：${item.focus ? `适合希望了解${item.focus}主题具体内容的读者。` : "适合希望了解该文具体内容的读者。"}`
      : `${index + 1}. ${item.title}: ${item.focus ? `for readers who want to explore ${item.focus} in detail.` : "for readers who want to review the article's details."}`)].join("\n\n");
  }

  return {
    snapshot: data.snapshot,
    files,
    fileCount: data.snapshot?.file_count ?? 0,
    filesUnavailable: data.filesUnavailable,
    explanationState,
    explanationText,
    recommendedCount: recommendations.length,
  };
}
