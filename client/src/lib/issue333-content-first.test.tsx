import assert from "node:assert/strict";
import { Children, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { WeeklyGroupDisclosure } from "../components/WeeklyGroupDisclosure";
import { WeeklyHighlightCard } from "../components/WeeklyHighlightCard";
import {
  buildWeeklyDashboardView,
  formatWeeklyShortDate,
  groupWeeklyFiles,
  loadLatestWeeklyDashboard,
  loadWeeklyUpdateDetail,
  normalizePublicCategory,
  normalizePublicKeywords,
  resolveCachedListLoadState,
  type WeeklyDashboardData,
  type WeeklySnapshotFile,
} from "./weekly-dashboard";

const snapshot = {
  id: "snapshot / 333",
  period_start: "2026-09-01T00:00:00+00:00",
  period_end: "2026-09-08T00:00:00+00:00",
  generated_at: "2026-09-08T02:00:00+00:00",
  status: "published" as const,
  file_count: 503,
  metadata: {},
};

const allFiles: WeeklySnapshotFile[] = Array.from({ length: 503 }, (_, index) => ({
  url: `https://example.test/report-${index}.pdf`,
  title: `Report ${index}`,
  original_filename: `report-${index}.pdf`,
  first_seen: "2026-09-03T15:16:17+00:00",
  category: index === 0 ? " ; Risk & Capital ; AI " : index === 1 ? "Risk & Capital" : null,
  keywords: index === 0 ? ["capital", "scenario"] : [],
  summary: index === 0 ? "A complete public summary." : null,
}));

const translations: Record<string, string> = {
  "dashboard.explanation_missing": "Not generated",
  "dashboard.explanation_empty": "Generated with no text",
  "dashboard.explanation_unavailable": "Unavailable",
  "dashboard.explanation_failed": "Generation failed",
  "dashboard.new_materials_count": "{count} new materials",
  "dashboard.files_unavailable": "Files unavailable",
  "dashboard.no_weekly_files": "No files",
  "dashboard.no_weekly_files_desc": "No files in this period",
  "dashboard.untitled_material": "Untitled material",
  "weekly.category": "Category",
  "weekly.keywords": "Keywords",
  "weekly.summary": "Summary",
  "weekly.uncategorized": "Uncategorized",
  "weekly.group_count": "Articles: {count}",
};
const t = (key: string) => translations[key] || key;

async function main(): Promise<void> {
  const homeCalls: string[] = [];
  const home = await loadLatestWeeklyDashboard(async <T,>(url: string): Promise<T> => {
    homeCalls.push(url);
    if (url === "/api/weekly-updates/latest") return { summary: snapshot } as T;
    if (url.includes("/files?")) {
      return {
        snapshot_id: snapshot.id,
        files: allFiles.slice(0, 6),
        total: allFiles.length,
        limit: 6,
        offset: 0,
        included_count: 6,
        truncated: true,
      } as T;
    }
    if (url.endsWith("/explanation")) return { explanation: null } as T;
    throw new Error(`Unexpected GET ${url}`);
  });
  assert.equal(home.files.length, 6);
  assert.equal(home.snapshot?.file_count, 503);
  assert.ok(homeCalls.some((url) => url.endsWith("/files?limit=6&offset=0")));

  const detailFileCalls: string[] = [];
  const detail = await loadWeeklyUpdateDetail(snapshot.id, async <T,>(url: string): Promise<T> => {
    if (url.endsWith("/explanation")) return { explanation: null } as T;
    if (url.endsWith(encodeURIComponent(snapshot.id))) return { summary: snapshot } as T;
    if (url.includes("/files?")) {
      detailFileCalls.push(url);
      const parsed = new URL(url, "https://app.test");
      const limit = Number(parsed.searchParams.get("limit"));
      const offset = Number(parsed.searchParams.get("offset"));
      const files = allFiles.slice(offset, offset + limit);
      return {
        snapshot_id: snapshot.id,
        files,
        total: allFiles.length,
        limit,
        offset,
        included_count: files.length,
        truncated: offset + files.length < allFiles.length,
      } as T;
    }
    throw new Error(`Unexpected GET ${url}`);
  });
  assert.equal(detail.files.length, 503);
  assert.deepEqual(
    detailFileCalls.map((url) => new URL(url, "https://app.test").searchParams.get("offset")),
    ["0", "500"],
  );

  await assert.rejects(
    () => loadWeeklyUpdateDetail("detail-failure", async <T,>(url: string): Promise<T> => {
      if (url.endsWith("/detail-failure")) throw new Error("detail request failed");
      if (url.includes("/files?")) {
        return { files: [], total: 0, limit: 500, offset: 0 } as T;
      }
      if (url.endsWith("/explanation")) return { explanation: null } as T;
      throw new Error(`Unexpected GET ${url}`);
    }),
    /detail request failed/,
  );

  const partialDetail = await loadWeeklyUpdateDetail(
    "partial-files",
    async <T,>(url: string): Promise<T> => {
      if (url.endsWith("/partial-files")) return { summary: snapshot } as T;
      if (url.includes("/files?")) throw new Error("files unavailable");
      if (url.endsWith("/explanation")) return { explanation: null } as T;
      throw new Error(`Unexpected GET ${url}`);
    },
  );
  assert.equal(partialDetail.status, "ready");
  assert.equal(partialDetail.filesUnavailable, true);
  assert.equal(partialDetail.explanationUnavailable, false);

  const failedDatabaseLoad = resolveCachedListLoadState<{ url: string }>(null, null);
  assert.deepEqual(failedDatabaseLoad, { files: [], total: 0, loadError: true });
  const trueEmptyDatabaseLoad = resolveCachedListLoadState<{ url: string }>(
    { files: [], total: 0 },
    null,
  );
  assert.deepEqual(trueEmptyDatabaseLoad, { files: [], total: 0, loadError: false });
  const cachedDatabaseLoad = resolveCachedListLoadState(
    null,
    { files: [{ url: "https://example.test/cached.pdf" }], total: 1 },
  );
  assert.deepEqual(cachedDatabaseLoad, {
    files: [{ url: "https://example.test/cached.pdf" }],
    total: 1,
    loadError: false,
  });

  assert.equal(formatWeeklyShortDate("2026-09-03T15:16:17+00:00", "en"), "Sep 3");
  assert.equal(formatWeeklyShortDate("2026-09-03T15:16:17+00:00", "zh"), "9月3日");
  assert.equal(normalizePublicCategory(" ; "), "");
  assert.equal(normalizePublicCategory(" ; Risk & Capital ; AI "), "; Risk & Capital ; AI");
  assert.deepEqual(normalizePublicKeywords([" alpha ", "", 3]), ["alpha"]);
  assert.deepEqual(normalizePublicKeywords('{"unexpected":true}'), []);

  const groupedFiles = [allFiles[0], allFiles[1], { ...allFiles[2], category: " ; " }];
  const groups = groupWeeklyFiles(groupedFiles, "Uncategorized");
  assert.deepEqual(groups.map((group) => [group.label, group.files.length]), [
    ["Risk & Capital", 2],
    ["Uncategorized", 1],
  ]);
  assert.equal(groups[0].files[0].category, " ; Risk & Capital ; AI ");

  const homeMarkup = renderToStaticMarkup(
    <WeeklyHighlightCard
      view={buildWeeklyDashboardView(home, "en", t)}
      lang="en"
      t={t}
      onOpenFile={() => undefined}
    />,
  );
  assert.equal((homeMarkup.match(/data-testid="weekly-file-row-/g) || []).length, 6);
  assert.match(homeMarkup, /Category/);
  assert.match(homeMarkup, /Risk &amp; Capital ; AI/);
  assert.match(homeMarkup, /Keywords/);
  assert.match(homeMarkup, /capital/);
  assert.match(homeMarkup, /Summary/);
  assert.match(homeMarkup, /A complete public summary\./);
  assert.match(
    homeMarkup,
    /<time[^>]+dateTime="2026-09-03T15:16:17\+00:00"[^>]+title="2026-09-03T15:16:17\+00:00"[^>]*>Sep 3<\/time>/,
  );

  const missingMetadata: WeeklyDashboardData = {
    ...home,
    files: [{ ...allFiles[2], category: " ; ", keywords: { unusable: true }, summary: " " }],
  };
  const missingMarkup = renderToStaticMarkup(
    <WeeklyHighlightCard
      view={buildWeeklyDashboardView(missingMetadata, "en", t)}
      lang="en"
      t={t}
      onOpenFile={() => undefined}
    />,
  );
  assert.doesNotMatch(missingMarkup, />Category:</);
  assert.doesNotMatch(missingMarkup, />Keywords:</);
  assert.doesNotMatch(missingMarkup, />Summary:</);
  assert.doesNotMatch(missingMarkup, /null|undefined/);

  const groupedMarkup = renderToStaticMarkup(
    <WeeklyHighlightCard
      view={{ ...buildWeeklyDashboardView(detail, "en", t), files: groupedFiles }}
      lang="en"
      t={t}
      onOpenFile={() => undefined}
      grouped
    />,
  );
  assert.equal((groupedMarkup.match(/data-testid="weekly-group-toggle-/g) || []).length, 2);
  assert.equal((groupedMarkup.match(/aria-expanded="true"/g) || []).length, 2);
  assert.equal((groupedMarkup.match(/data-testid="weekly-file-row-/g) || []).length, 3);
  assert.match(groupedMarkup, /Articles: 1/);
  assert.match(groupedMarkup, /Articles: 2/);
  assert.match(groupedMarkup, /Uncategorized/);

  let collapsed = false;
  const renderDisclosure = () => WeeklyGroupDisclosure({
    groupIndex: 0,
    groupId: "weekly-category-group-runtime",
    label: "Risk & Capital",
    count: 1,
    collapsed,
    onToggle: () => {
      collapsed = !collapsed;
    },
    children: <button data-testid="runtime-weekly-article">Article</button>,
  });
  const clickDisclosure = (tree: ReactElement<{ children?: ReactNode }>) => {
    const toggle = Children.toArray(tree.props.children)[0] as ReactElement<{
      onClick: () => void;
    }>;
    toggle.props.onClick();
  };

  const expandedDisclosure = renderDisclosure();
  const expandedMarkup = renderToStaticMarkup(expandedDisclosure);
  assert.match(expandedMarkup, /aria-expanded="true"/);
  assert.match(expandedMarkup, /id="weekly-category-group-runtime"/);
  assert.match(expandedMarkup, /data-testid="runtime-weekly-article"/);

  clickDisclosure(expandedDisclosure);
  const collapsedDisclosure = renderDisclosure();
  const collapsedMarkup = renderToStaticMarkup(collapsedDisclosure);
  assert.match(collapsedMarkup, /aria-expanded="false"/);
  assert.match(collapsedMarkup, /id="weekly-category-group-runtime"[^>]*hidden=""/);
  assert.match(collapsedMarkup, /data-testid="runtime-weekly-article"/);

  clickDisclosure(collapsedDisclosure);
  const reopenedMarkup = renderToStaticMarkup(renderDisclosure());
  assert.match(reopenedMarkup, /aria-expanded="true"/);
  assert.match(reopenedMarkup, /id="weekly-category-group-runtime"/);
  assert.match(reopenedMarkup, /data-testid="runtime-weekly-article"/);

  console.log("Issue #333 content-first executable assertions passed");
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
