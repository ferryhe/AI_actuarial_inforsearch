import { getCanonicalDisplayName } from "../pages/chat/displayName";
import {
  formatWeeklyDateTime,
  type WeeklyDashboardView,
} from "../lib/weekly-dashboard";

interface WeeklyHighlightCardProps {
  view: WeeklyDashboardView;
  lang: string;
  t: (key: string) => string;
  onOpenFile: (url: string) => void;
  /** Bottom "View all" destination. Omit to hide the footer link. */
  databasePath?: string | null;
}

export function WeeklyHighlightCard({
  view,
  lang,
  t,
  onOpenFile,
  databasePath,
}: WeeklyHighlightCardProps) {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
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
        <div>
          <div className="hidden sm:grid grid-cols-[minmax(0,1fr)_180px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            <span>{t("table.title")}</span>
            <span>{t("table.date")}</span>
          </div>
          {view.files.map((file, index) => {
            const displayName = getCanonicalDisplayName(file, t("dashboard.untitled_material"));
            return (
              <button
                key={file.url}
                type="button"
                onClick={() => onOpenFile(file.url)}
                className="grid w-full min-w-0 grid-cols-1 sm:grid-cols-[minmax(0,1fr)_180px] gap-1 sm:gap-4 px-4 py-3 border-t border-border text-left hover:bg-muted/30 transition-colors"
                data-testid={`weekly-file-row-${index}`}
              >
                <span className="text-sm font-medium break-words [overflow-wrap:anywhere]" title={displayName}>
                  {displayName}
                </span>
                <time className="text-xs text-muted-foreground" dateTime={file.first_seen} title={file.first_seen}>
                  {formatWeeklyDateTime(file.first_seen, lang)}
                </time>
              </button>
            );
          })}
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
