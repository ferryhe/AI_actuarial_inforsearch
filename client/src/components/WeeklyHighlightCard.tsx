import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import { getCanonicalDisplayName } from "@/pages/chat/displayName";
import { formatUtcIso } from "@/lib/date-format";
import {
  formatWeeklyShortDate,
  groupWeeklyFiles,
  localizedWeeklyFileMetadata,
  normalizePublicCategory,
  normalizePublicMetadataText,
  type WeeklyDashboardView,
  type WeeklySnapshotFile,
} from "@/lib/weekly-dashboard";
import { WeeklyGroupDisclosure } from "./WeeklyGroupDisclosure";

interface WeeklyHighlightCardProps {
  view: WeeklyDashboardView;
  lang: string;
  t: (key: string) => string;
  onOpenFile: (url: string) => void;
  /** Bottom "View all" destination. Omit to hide the footer link. */
  databasePath?: string | null;
  /** Group files by their primary category for the full Weekly detail view. */
  grouped?: boolean;
}

interface WeeklyArticleCardProps {
  file: WeeklySnapshotFile;
  index: number;
  lang: string;
  t: (key: string) => string;
  onOpenFile: (url: string) => void;
}

function WeeklyArticleCard({ file, index, lang, t, onOpenFile }: WeeklyArticleCardProps) {
  const metadata = localizedWeeklyFileMetadata(file, lang);
  const displayName = getCanonicalDisplayName(
    { ...file, title: metadata.title },
    t("dashboard.untitled_material"),
  );
  const category = normalizePublicCategory(metadata.category);
  const keywords = metadata.keywords;
  const summary = normalizePublicMetadataText(metadata.summary);
  const displayDate = file.published_time || file.first_seen;
  const utcIso = formatUtcIso(displayDate);

  return (
    <button
      type="button"
      onClick={() => onOpenFile(file.url)}
      className="block w-full min-w-0 border-t border-border px-4 py-3 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
      data-testid={`weekly-file-row-${index}`}
    >
      <span className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <span className="text-sm font-medium break-words [overflow-wrap:anywhere]" title={displayName}>
          {displayName}
        </span>
        <time
          className="text-xs text-muted-foreground whitespace-nowrap"
          dateTime={file.published_time || utcIso || undefined}
          title={file.published_time || (utcIso ? `${utcIso} (UTC)` : undefined)}
        >
          {formatWeeklyShortDate(displayDate, lang)}
        </time>
      </span>
      {category ? (
        <span className="mt-2 block min-w-0 text-xs text-muted-foreground" data-testid={`weekly-category-${index}`}>
          <span className="font-medium text-foreground/70">{t("weekly.category")}: </span>
          <span className="break-words [overflow-wrap:anywhere]">{category}</span>
        </span>
      ) : null}
      {keywords.length > 0 ? (
        <span className="mt-1 block min-w-0 text-xs text-muted-foreground" data-testid={`weekly-keywords-${index}`}>
          <span className="font-medium text-foreground/70">{t("weekly.keywords")}: </span>
          <span className="break-words [overflow-wrap:anywhere]">{keywords.join(", ")}</span>
        </span>
      ) : null}
      {summary ? (
        <span className="mt-1 block min-w-0 text-xs leading-relaxed text-muted-foreground" data-testid={`weekly-summary-${index}`}>
          <span className="font-medium text-foreground/70">{t("weekly.summary")}: </span>
          <span className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{summary}</span>
        </span>
      ) : null}
    </button>
  );
}

export function WeeklyHighlightCard({
  view,
  lang,
  t,
  onOpenFile,
  databasePath,
  grouped = false,
}: WeeklyHighlightCardProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set());
  const renderFiles = view.filesUnavailable
    ? view.files.slice(0, view.recommendedCount)
    : view.files;
  const groupByCategory = grouped && !view.publicationOnly;
  const groups = groupByCategory ? groupWeeklyFiles(renderFiles.slice(view.recommendedCount), t("weekly.uncategorized")) : [];
  const fileIndexes = new Map(renderFiles.map((file, index) => [file.url, index]));

  function toggleGroup(key: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="min-w-0 rounded-xl border border-border bg-card overflow-hidden">
      <div className="p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          <span
            className="inline-flex items-center rounded-full bg-primary/10 text-primary font-medium px-2.5 py-1"
            data-testid="weekly-new-count"
          >
            {t(view.publicationOnly ? "weekly.verified_publication_count" : "dashboard.new_materials_count").replace("{count}", String(view.fileCount))}
          </span>
          {view.publicationOnly && view.snapshot ? (
            <>
              <span>{t("weekly.collected_materials_count").replace("{count}", String(view.snapshot.file_count))}</span>
              {view.backfillCount === undefined ? null : (
                <>
                  <span>{t("weekly.backfill_count").replace("{count}", String(view.backfillCount))}</span>
                  <span>{t("weekly.other_intake_count").replace("{count}", String(view.snapshot.file_count - view.fileCount - view.backfillCount))}</span>
                </>
              )}
              <span>{t("weekly.recommended_count").replace("{count}", String(view.guideRecommendationCount ?? "—"))}</span>
            </>
          ) : null}
        </div>
        {view.explanationState === "failed" ? (
          <p className="text-xs text-muted-foreground">{t("dashboard.explanation_failed")}</p>
        ) : null}
        <div
          className="text-sm leading-relaxed text-muted-foreground break-words [overflow-wrap:anywhere] [&_a]:text-primary [&_a]:underline [&_p]:my-2 [&_ul]:space-y-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:space-y-3 [&_ol]:list-decimal [&_ol]:pl-5"
          data-testid={`weekly-explanation-${view.explanationState}`}
        >
          <ReactMarkdown remarkPlugins={[remarkBreaks]}>{view.explanationText}</ReactMarkdown>
        </div>
      </div>

      {view.filesUnavailable ? (
        <p className="p-4 text-sm text-muted-foreground">{t("dashboard.files_unavailable")}</p>
      ) : null}
      {renderFiles.length === 0 ? (
        view.filesUnavailable || view.publicationOnly ? null : <div className="p-8 text-center">
          <p className="font-medium text-muted-foreground">{t("dashboard.no_weekly_files")}</p>
          <p className="text-xs text-muted-foreground/70 mt-1">{t("dashboard.no_weekly_files_desc")}</p>
        </div>
      ) : (
        <div className="min-w-0">
          {groupByCategory ? renderFiles.slice(0, view.recommendedCount).map((file, index) => (
            <WeeklyArticleCard
              key={file.url}
              file={file}
              index={index}
              lang={lang}
              t={t}
              onOpenFile={onOpenFile}
            />
          )) : null}
          {groupByCategory ? groups.map((group, groupIndex) => {
            const collapsed = collapsedGroups.has(group.key);
            const groupId = `weekly-category-group-${groupIndex}`;
            return (
              <WeeklyGroupDisclosure
                key={group.key}
                groupIndex={groupIndex}
                groupId={groupId}
                label={group.label}
                count={t("weekly.group_count").replace("{count}", String(group.files.length))}
                collapsed={collapsed}
                onToggle={() => toggleGroup(group.key)}
              >
                {group.files.map((file) => (
                  <WeeklyArticleCard
                    key={file.url}
                    file={file}
                    index={fileIndexes.get(file.url) ?? 0}
                    lang={lang}
                    t={t}
                    onOpenFile={onOpenFile}
                  />
                ))}
              </WeeklyGroupDisclosure>
            );
          }) : renderFiles.map((file, index) => (
            <WeeklyArticleCard
              key={file.url}
              file={file}
              index={index}
              lang={lang}
              t={t}
              onOpenFile={onOpenFile}
            />
          ))}
        </div>
      )}

      {databasePath ? (
        <div className="border-t border-border p-3 flex justify-end">
          <a
            href={databasePath}
            className="text-xs text-primary hover:underline shrink-0"
            data-testid="weekly-view-all-database"
          >
            {t(view.publicationOnly ? "weekly.view_collected" : "dashboard.view_all")}
          </a>
        </div>
      ) : null}
    </div>
  );
}
