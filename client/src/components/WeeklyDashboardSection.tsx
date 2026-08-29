import { getCanonicalDisplayName } from "../pages/chat/displayName";
import {
  buildWeeklyDashboardView,
  buildWeeklyDatabasePath,
  formatWeeklyDateTime,
  type WeeklyDashboardData,
} from "../lib/weekly-dashboard";

interface WeeklyDashboardSectionProps {
  data: WeeklyDashboardData | null;
  lang: string;
  t: (key: string) => string;
  onOpenFile: (url: string) => void;
}

export function WeeklyDashboardSection({
  data,
  lang,
  t,
  onOpenFile,
}: WeeklyDashboardSectionProps) {
  if (!data) {
    return (
      <section className="min-w-0">
        <h2 className="text-lg font-semibold mb-3">{t("dashboard.this_week_additions")}</h2>
        <div className="space-y-2">
          {[...Array(4)].map((_, index) => (
            <div key={index} className="h-14 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      </section>
    );
  }

  if (data.status !== "ready" || !data.snapshot) {
    const unavailable = data.status === "unavailable";
    return (
      <section className="min-w-0">
        <h2 className="text-lg font-semibold mb-3">{t("dashboard.this_week_additions")}</h2>
        <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
          <p className="font-medium text-muted-foreground">
            {t(unavailable ? "dashboard.snapshot_unavailable" : "dashboard.no_weekly_snapshot")}
          </p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            {t(unavailable ? "dashboard.snapshot_unavailable_desc" : "dashboard.no_weekly_snapshot_desc")}
          </p>
        </div>
      </section>
    );
  }

  const view = buildWeeklyDashboardView(data, lang, t);
  const snapshot = data.snapshot;
  const metadata: Array<[string, string, string | null]> = [
    [t("dashboard.weekly_period_start"), view.periodStart, snapshot.period_start],
    [t("dashboard.weekly_period_end"), view.periodEnd, snapshot.period_end],
    [t("dashboard.snapshot_generated_at"), view.snapshotGeneratedAt, snapshot.generated_at],
    [t("dashboard.explanation_generated_at"), view.explanationGeneratedAt, data.explanation?.generated_at ?? null],
  ];

  return (
    <section className="min-w-0 overflow-hidden" data-testid="weekly-dashboard-section">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-lg font-semibold min-w-0">{t("dashboard.this_week_additions")}</h2>
        <a
          href={buildWeeklyDatabasePath(snapshot)}
          className="text-xs text-primary hover:underline shrink-0"
          data-testid="weekly-view-all"
        >
          {t("dashboard.view_all")}
        </a>
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 border-b border-border p-4 text-xs">
          {metadata.map(([label, value, exact]) => (
            <div key={label} className="min-w-0">
              <div className="text-muted-foreground">{label}</div>
              {exact ? (
                <time className="block font-medium break-words [overflow-wrap:anywhere]" dateTime={exact} title={exact}>
                  {value}
                </time>
              ) : (
                <span className="block font-medium break-words [overflow-wrap:anywhere]">{value}</span>
              )}
            </div>
          ))}
          <div>
            <div className="text-muted-foreground">{t("dashboard.weekly_status")}</div>
            <div className="font-medium">{t("dashboard.status_published")}</div>
          </div>
          <div>
            <div className="text-muted-foreground">{t("dashboard.weekly_file_count")}</div>
            <div className="font-medium tabular-nums">{view.fileCount}</div>
          </div>
        </div>

        <div className="border-b border-border p-4 min-w-0">
          <h3 className="text-sm font-semibold mb-2">{t("dashboard.weekly_explanation")}</h3>
          <p
            className="text-sm text-muted-foreground whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
            data-testid={`weekly-explanation-${view.explanationState}`}
          >
            {view.explanationText}
          </p>
        </div>

        {data.filesUnavailable ? (
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
      </div>
    </section>
  );
}
