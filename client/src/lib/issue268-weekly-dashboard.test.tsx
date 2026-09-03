import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { WeeklyDashboardSection } from "../components/WeeklyDashboardSection";
import {
  buildWeeklyDashboardView,
  buildWeeklyDatabasePath,
  loadLatestWeeklyDashboard,
  type WeeklyDashboardData,
} from "./weekly-dashboard";
import {
  buildDatabaseLocation,
  buildFilesParams,
  parseDatabaseQueryState,
} from "./database-query";
import { getCanonicalDisplayName } from "../pages/chat/displayName";
import { buildFileDetailPath, buildFilePreviewPath } from "./navigation";

const translations: Record<string, Record<string, string>> = {
  en: {
    "dashboard.explanation_missing": "Not generated",
    "dashboard.explanation_empty": "Generated with no text",
    "dashboard.explanation_unavailable": "Unavailable",
    "dashboard.explanation_failed": "Generation failed",
  },
  zh: {
    "dashboard.explanation_missing": "尚未生成",
    "dashboard.explanation_empty": "已生成但无内容",
    "dashboard.explanation_unavailable": "暂不可用",
    "dashboard.explanation_failed": "生成失败",
  },
};
const tFor = (lang: "en" | "zh") => (key: string) => translations[lang][key] || key;

const snapshot = {
  id: "snapshot / 268",
  period_start: "2026-03-09T00:00:00+00:00",
  period_end: "2026-03-16T00:00:00+00:00",
  generated_at: "2026-03-16T02:00:00+00:00",
  status: "published" as const,
  file_count: 12,
  metadata: {},
};
const apiFiles = Array.from({ length: 10 }, (_, index) => ({
  url: `https://example.test/files/report-${index}.pdf`,
  title: index === 0 ? "A very long current title ".repeat(20) : `Report ${index}`,
  original_filename: `original-${index}.pdf`,
  first_seen: `2026-03-${String(10 + index).padStart(2, "0")}T00:00:00+00:00`,
}));

const calls: string[] = [];
const fakeGet = async <T,>(url: string): Promise<T> => {
  calls.push(url);
  if (url === "/api/weekly-updates/latest") return { summary: snapshot } as T;
  if (url.includes("/files?")) {
    return { snapshot_id: snapshot.id, files: apiFiles, total: 12, limit: 8, offset: 0 } as T;
  }
  if (url.endsWith("/explanation")) {
    return {
      explanation: {
        snapshot_id: snapshot.id,
        status: "complete",
        explanation_zh: "中文说明",
        explanation_en: "English explanation",
        generated_at: "2026-03-16T02:05:00+00:00",
      },
    } as T;
  }
  throw new Error(`Unexpected GET ${url}`);
};

async function main(): Promise<void> {
const loaded = await loadLatestWeeklyDashboard(fakeGet);
assert.equal(loaded.status, "ready");
assert.equal(loaded.files.length, 6);
assert.equal(loaded.snapshot?.file_count, 12);
assert.deepEqual(calls, [
  "/api/weekly-updates/latest",
  "/api/weekly-updates/snapshot%20%2F%20268/files?limit=6&offset=0",
  "/api/weekly-updates/snapshot%20%2F%20268/explanation",
]);
assert.ok(calls.every((url) => !/generate|retry/i.test(url)));

const unavailableData = await loadLatestWeeklyDashboard(async <T,>(url: string): Promise<T> => {
  if (url === "/api/weekly-updates/latest") return { summary: snapshot } as T;
  throw new Error("read unavailable");
});
assert.equal(unavailableData.status, "ready");
assert.equal(unavailableData.snapshot?.file_count, 12);
assert.equal(unavailableData.filesUnavailable, true);
assert.equal(unavailableData.explanationUnavailable, true);

const callsBeforeLocaleSwitch = calls.length;
const englishView = buildWeeklyDashboardView(loaded, "en", tFor("en"));
const chineseView = buildWeeklyDashboardView(loaded, "zh", tFor("zh"));
assert.equal(englishView.explanationText, "English explanation");
assert.equal(chineseView.explanationText, "中文说明");
assert.equal(englishView.fileCount, 12);
assert.equal(chineseView.fileCount, 12);
assert.equal(calls.length, callsBeforeLocaleSwitch, "locale switching must not perform another request");

const viewAll = new URL(buildWeeklyDatabasePath(snapshot), "https://app.test");
assert.equal(viewAll.pathname, "/database");
assert.equal(viewAll.searchParams.get("snapshot_id"), snapshot.id);
assert.equal(viewAll.searchParams.get("first_seen_from"), snapshot.period_start);
assert.equal(viewAll.searchParams.get("first_seen_before"), snapshot.period_end);
assert.equal(viewAll.searchParams.get("order_by"), "first_seen");
assert.equal(viewAll.searchParams.get("order_dir"), "desc");

for (const [data, lang, expectedState, expectedText] of [
  [{ ...loaded, explanation: { ...loaded.explanation!, status: "missing" as const } }, "en", "missing", "Not generated"],
  [{ ...loaded, explanation: { ...loaded.explanation!, explanation_zh: "" } }, "zh", "empty", "已生成但无内容"],
  [{ ...loaded, explanationUnavailable: true }, "en", "unavailable", "Unavailable"],
  [{ ...loaded, explanation: { ...loaded.explanation!, status: "failed" as const } }, "zh", "failed", "生成失败"],
] as const) {
  const view = buildWeeklyDashboardView(data, lang, tFor(lang));
  assert.equal(view.explanationState, expectedState);
  assert.equal(view.explanationText, expectedText);
  assert.equal(view.fileCount, 12);
  assert.equal(view.files.length, 6);
}

const longTitle = "L".repeat(600);
assert.equal(getCanonicalDisplayName({ title: ` ${longTitle} ` }, "Fallback"), longTitle);
assert.equal(
  getCanonicalDisplayName({ title: " UnKnOwN ", original_filename: " original.pdf " }, "Fallback"),
  "original.pdf",
);
assert.equal(
  getCanonicalDisplayName({ title: "", original_filename: "UNKNOWN", filename: " named.pdf " }, "Fallback"),
  "named.pdf",
);
assert.equal(
  getCanonicalDisplayName({ url: "https://example.test/reports/encoded%20report.pdf?x=1" }, "Fallback"),
  "encoded report.pdf",
);
assert.equal(getCanonicalDisplayName({ title: "unknown", filename: " UNKNOWN " }, "本地回退"), "本地回退");

const parsed = parseDatabaseQueryState(
  "?snapshot_id=snapshot-268&first_seen_from=2026-03-09T00%3A00%3A00%2B00%3A00"
  + "&first_seen_before=2026-03-16T00%3A00%3A00%2B00%3A00&order_by=first_seen&order_dir=desc&page=3",
);
assert.equal(parsed.offset, 40);
assert.equal(parsed.orderBy, "first_seen");
const changed = {
  ...parsed,
  offset: 20,
  query: "reserving",
  source: "alpha",
  category: "Risk",
  includeDeleted: true,
};
const apiParams = buildFilesParams(changed);
const location = buildDatabaseLocation(changed);
for (const params of [apiParams, new URL(location, "https://app.test").searchParams]) {
  assert.equal(params.get("snapshot_id"), "snapshot-268");
  assert.equal(params.get("first_seen_from"), snapshot.period_start);
  assert.equal(params.get("first_seen_before"), snapshot.period_end);
  assert.equal(params.get("order_by"), "first_seen");
  assert.equal(params.get("query"), "reserving");
  assert.equal(params.get("source"), "alpha");
  assert.equal(params.get("category"), "Risk");
  assert.equal(params.get("include_deleted"), "true");
}
const roundTrip = parseDatabaseQueryState(new URL(location, "https://app.test").search);
assert.equal(buildFilesParams({ ...roundTrip, offset: 40 }).get("snapshot_id"), "snapshot-268");
assert.equal(
  new URL(buildFileDetailPath("https://example.test/report.pdf", location), "https://app.test").searchParams.get("from"),
  location,
);
assert.equal(
  new URL(buildFilePreviewPath("https://example.test/report.pdf", location), "https://app.test").searchParams.get("from"),
  location,
);

const componentData = loaded as WeeklyDashboardData;
const markup = renderToStaticMarkup(
  <WeeklyDashboardSection
    data={componentData}
    lang="en"
    t={(key) => ({
      ...translations.en,
      "dashboard.this_week_additions": "Latest weekly additions",
      "dashboard.view_all": "View all",
      "dashboard.new_materials_count": "{count} new materials",
      "dashboard.files_unavailable": "Files unavailable",
      "dashboard.no_weekly_files": "No files",
      "dashboard.no_weekly_files_desc": "No files in this period",
      "dashboard.untitled_material": "Untitled material",
      "table.title": "Title",
      "table.date": "First seen",
    } as Record<string, string>)[key] || key}
    onOpenFile={() => undefined}
  />,
);
assert.equal((markup.match(/data-testid="weekly-file-row-/g) || []).length, 6);
assert.match(markup, /12 new materials/);
assert.match(markup, /English explanation/);
assert.match(markup, /break-words/);
assert.match(markup, /overflow-wrap:anywhere/);

const missingExplanationMarkup = renderToStaticMarkup(
  <WeeklyDashboardSection
    data={{
      ...componentData,
      explanation: { ...componentData.explanation!, status: "missing", generated_at: null },
    }}
    lang="en"
    t={tFor("en")}
    onOpenFile={() => undefined}
  />,
);
assert.match(missingExplanationMarkup, /Not generated/);

const failedMarkup = renderToStaticMarkup(
  <WeeklyDashboardSection
    data={{ ...componentData, explanation: { ...componentData.explanation!, status: "failed" } }}
    lang="zh"
    t={(key) => ({
      ...translations.zh,
      "dashboard.this_week_additions": "最新周报新增资料",
      "dashboard.view_all": "查看全部",
      "dashboard.new_materials_count": "新增 {count} 份材料",
      "dashboard.files_unavailable": "文件不可用",
      "dashboard.no_weekly_files": "暂无文件",
      "dashboard.no_weekly_files_desc": "本周期没有文件",
      "dashboard.untitled_material": "未命名资料",
      "table.title": "标题",
      "table.date": "首次发现",
    } as Record<string, string>)[key] || key}
    onOpenFile={() => undefined}
  />,
);
assert.match(failedMarkup, /生成失败/);
assert.match(failedMarkup, /新增 12 份材料/);
assert.equal((failedMarkup.match(/data-testid="weekly-file-row-/g) || []).length, 6);

console.log("Issue #268 weekly dashboard executable assertions passed");
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
