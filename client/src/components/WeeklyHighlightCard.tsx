import { useState } from "react";
import { getCanonicalDisplayName } from "@/pages/chat/displayName";
import {
  formatWeeklyShortDate,
  groupWeeklyFiles,
  normalizePublicCategory,
  normalizePublicKeywords,
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
  const displayName = getCanonicalDisplayName(file, t("dashboard.untitled_material"));
  const category = normalizePublicCategory(file.category);
  const keywords = normalizePublicKeywords(file.keywords);
  const summary = normalizePublicMetadataText(file.summary);

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
          dateTime={file.first_seen}
          title={file.first_seen}
        >
          {formatWeeklyShortDate(file.first_seen, lang)}
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
  const groups = grouped ? groupWeeklyFiles(view.files, t("weekly.uncategorized")) : [];
  const fileIndexes = new Map(view.files.map((file, index) => [file.url, index]));

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
        <span
          className="inline-flex items-center rounded-full bg-primary/10 text-primary text-xs font-medium px-2.5 py-1"
          data-testid="weekly-new-count"
        >
          {t("dashboard.new_materials_count").replace("{count}", String(view.fileCount))}
        </span>
        <p
          className="text-sm text-muted-foreground whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
          data-testid={`weekly-explanation-${view.explanationState}`}
        >
          {view.explanationText}
        </p>
      </div>

      {view.filesUnavailable ? (
        <p className="p-4 text-sm text-muted-foreground">{t("dashboard.files_unavailable")}</p>
      ) : view.files.length === 0 ? (
        <div className="p-8 text-center">
          <p className="font-medium text-muted-foreground">{t("dashboard.no_weekly_files")}</p>
          <p className="text-xs text-muted-foreground/70 mt-1">{t("dashboard.no_weekly_files_desc")}</p>
        </div>
      ) : (
        <div className="min-w-0">
          {grouped ? groups.map((group, groupIndex) => {
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
          }) : view.files.map((file, index) => (
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
            {t("dashboard.view_all")}
          </a>
        </div>
      ) : null}
    </div>
  );
}
