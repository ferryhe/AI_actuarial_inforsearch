import {
  buildWeeklyDashboardView,
  buildWeeklyDatabasePath,
  type WeeklyDashboardData,
} from "../lib/weekly-dashboard";
import { WeeklyHighlightCard } from "./WeeklyHighlightCard";

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

  return (
    <section className="min-w-0 overflow-hidden" data-testid="weekly-dashboard-section">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-lg font-semibold min-w-0">{t("dashboard.this_week_additions")}</h2>
        <a
          href="/weekly"
          className="text-xs text-primary hover:underline shrink-0"
          data-testid="weekly-view-all"
        >
          {t("dashboard.view_all")}
        </a>
      </div>

      <WeeklyHighlightCard
        view={view}
        lang={lang}
        t={t}
        onOpenFile={onOpenFile}
        databasePath={buildWeeklyDatabasePath(snapshot)}
      />
    </section>
  );
}
