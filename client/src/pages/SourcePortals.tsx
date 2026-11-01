import { useEffect, useState } from "react";
import { Compass, ExternalLink } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet, formatApiErrorDetail } from "@/lib/api";

interface PortalUpdate {
  acquired_on: string;
  description_zh: string;
  description_en: string;
}

interface SourcePortal {
  portal_key: string;
  url: string;
  title_zh: string;
  title_en: string;
  institution_zh: string;
  institution_en: string;
  overview_zh: string;
  overview_en: string;
  updates: PortalUpdate[];
}

export default function SourcePortals() {
  const { lang, t } = useTranslation();
  const [portals, setPortals] = useState<SourcePortal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    apiGet<{ portals?: SourcePortal[] }>("/api/source-portals")
      .then((result) => {
        if (!cancelled) setPortals(result.portals || []);
      })
      .catch((reason) => {
        if (!cancelled) setError(formatApiErrorDetail(reason) || t("source_portals.load_error"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [retry, t]);

  const localized = (zh: string, en: string) => (lang === "zh" ? zh : en);
  const formatDate = (value: string) => {
    const [year, month, day] = value.split("-").map(Number);
    return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(year, month - 1, day)));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="source-portals-title">
          {t("source_portals.title")}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
          {t("source_portals.subtitle")}
        </p>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert" data-testid="source-portals-error">
          <span>{t("source_portals.load_error")}: {error}</span>
          <button type="button" className="shrink-0 underline" onClick={() => setRetry((value) => value + 1)}>
            {t("common.refresh")}
          </button>
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2" role="status" aria-live="polite" aria-busy="true" data-testid="source-portals-loading">
          {[...Array(4)].map((_, index) => <div key={index} className="h-48 rounded-xl bg-muted animate-pulse" />)}
        </div>
      ) : error ? null : portals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center" data-testid="source-portals-empty">
          <Compass className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
          <p className="font-medium text-muted-foreground">{t("source_portals.empty")}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="source-portals-grid">
          {portals.map((portal) => (
            <article key={portal.portal_key} className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-base font-semibold leading-snug">
                    {localized(portal.title_zh, portal.title_en)}
                  </h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {localized(portal.institution_zh, portal.institution_en)}
                  </p>
                </div>
                <a href={portal.url} target="_blank" rel="noreferrer" className="shrink-0 rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label={`${t("source_portals.open_source")} ${localized(portal.title_zh, portal.title_en)}`}>
                  <ExternalLink className="h-4 w-4" />
                </a>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {localized(portal.overview_zh, portal.overview_en)}
              </p>

              <section className="mt-5 border-t border-border pt-4" aria-label={t("source_portals.updates")}>
                <h3 className="text-sm font-medium">{t("source_portals.updates")}</h3>
                {portal.updates.length ? (
                  <ol className="mt-3 space-y-4">
                    {portal.updates.map((update) => (
                      <li key={update.acquired_on} className="grid grid-cols-[auto_1fr] items-start gap-3">
                        <time dateTime={update.acquired_on} className="whitespace-nowrap pt-0.5 text-xs text-muted-foreground">
                          {formatDate(update.acquired_on)}
                        </time>
                        <p className="text-sm leading-relaxed">
                          {localized(update.description_zh, update.description_en)}
                        </p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t("source_portals.no_updates")}
                  </p>
                )}
              </section>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
