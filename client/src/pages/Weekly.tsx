import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useTranslation } from "@/components/Layout";
import { buildFileDetailPath } from "@/lib/navigation";
import {
  buildWeeklyDashboardView,
  buildWeeklyDatabasePath,
  formatWeeklyPeriodLabel,
  loadWeeklyUpdateDetail,
  loadWeeklyUpdateList,
  type WeeklyDashboardData,
  type WeeklySnapshot,
} from "@/lib/weekly-dashboard";
import { WeeklyHighlightCard } from "@/components/WeeklyHighlightCard";

export default function Weekly() {
  const { t, lang } = useTranslation();
  const [, navigate] = useLocation();

  const [summaries, setSummaries] = useState<WeeklySnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WeeklyDashboardData | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    loadWeeklyUpdateList()
      .then((items) => {
        if (cancelled) return;
        setSummaries(items);
        if (items.length > 0) {
          setSelectedId(items[0].id);
        }
      })
      .catch(() => {
        if (!cancelled) setError(t("weekly.load_error"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetail(null);
    setDetailError(false);
    loadWeeklyUpdateDetail(selectedId)
      .then((data) => {
        if (!cancelled) {
          setDetail(data);
          setDetailError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  return (
    <div className="space-y-6" data-testid="weekly-page">
      <div>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="weekly-title">
          {t("weekly.title")}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
          {t("weekly.subtitle")}
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" data-testid="weekly-error">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2" data-testid="weekly-loading">
          {[...Array(6)].map((_, index) => (
            <div key={index} className="h-12 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : summaries.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center" data-testid="weekly-empty">
          <p className="font-medium text-muted-foreground">{t("weekly.no_highlights")}</p>
          <p className="text-xs text-muted-foreground/70 mt-1">{t("weekly.no_highlights_desc")}</p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-[320px_1fr] gap-4 items-start">
          <aside className="rounded-xl border border-border bg-card overflow-hidden" data-testid="weekly-list">
            <ul>
              {summaries.map((item) => {
                const active = item.id === selectedId;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className={`w-full text-left px-4 py-3 border-b last:border-b-0 border-border transition-colors ${
                        active ? "bg-primary/10" : "hover:bg-muted/30"
                      }`}
                      data-testid={`weekly-item-${item.id}`}
                    >
                      <div className="text-sm font-medium break-words">
                        {formatWeeklyPeriodLabel(item.period_start, item.period_end, lang)}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {t("dashboard.new_materials_count").replace("{count}", String(item.file_count))}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          <section className="min-w-0" data-testid="weekly-detail">
            {detailLoading ? (
              <div className="space-y-2">
                {[...Array(4)].map((_, index) => (
                  <div key={index} className="h-14 rounded-lg bg-muted animate-pulse" />
                ))}
              </div>
            ) : detail && detail.snapshot ? (
              <div className="space-y-3">
                <h2 className="text-lg font-semibold">
                  {formatWeeklyPeriodLabel(detail.snapshot.period_start, detail.snapshot.period_end, lang)}
                </h2>
                <WeeklyHighlightCard
                  view={buildWeeklyDashboardView(detail, lang, t)}
                  lang={lang}
                  t={t}
                  onOpenFile={(url) => navigate(buildFileDetailPath(url, "/weekly"))}
                  databasePath={buildWeeklyDatabasePath(detail.snapshot)}
                />
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
                <p className="font-medium text-muted-foreground">
                  {detailError ? t("weekly.detail_error") : t("weekly.no_highlights")}
                </p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
