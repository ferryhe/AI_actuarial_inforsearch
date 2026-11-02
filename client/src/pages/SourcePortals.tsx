import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearch } from "wouter";
import { ArrowLeft, ArrowRight, Compass, ExternalLink, Search } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet, formatApiErrorDetail } from "@/lib/api";
import { DATABASE_PAGE_SIZE } from "@/lib/database-query";

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

function useSourcePortals() {
  const { t } = useTranslation();
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

  return { portals, loading, error, retryLoad: () => setRetry((value) => value + 1) };
}

function localized(lang: string, zh: string, en: string) {
  return lang === "zh" ? zh : en;
}

function formatDate(value: string, lang: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

function portalListHref(query: string, page: number) {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (page > 1) params.set("page", String(page));
  const suffix = params.toString();
  return suffix ? `/source-portals?${suffix}` : "/source-portals";
}

function portalDetailHref(portalKey: string, query: string, page: number) {
  const suffix = portalListHref(query, page).split("?")[1];
  return `/source-portals/${encodeURIComponent(portalKey)}${suffix ? `?${suffix}` : ""}`;
}

function parsePage(search: string) {
  const rawPage = Number(new URLSearchParams(search).get("page") || "1");
  return Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
}

function SourcePortalError({ error, onRetry }: { error: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between" role="alert" data-testid="source-portals-error">
      <span>{t("source_portals.load_error")}: {error}</span>
      <button type="button" className="min-h-[44px] shrink-0 self-start underline sm:self-auto" onClick={onRetry}>
        {t("common.refresh")}
      </button>
    </div>
  );
}

function SourcePortalsLoading() {
  return (
    <div className="space-y-3" role="status" aria-live="polite" aria-busy="true" data-testid="source-portals-loading">
      {[...Array(5)].map((_, index) => <div key={index} className="h-24 rounded-xl bg-muted animate-pulse" />)}
    </div>
  );
}

export default function SourcePortals() {
  const { lang, t } = useTranslation();
  const { portals, loading, error, retryLoad } = useSourcePortals();
  const search = useSearch();
  const [, navigate] = useLocation();
  const params = new URLSearchParams(search);
  const query = params.get("query") || "";
  const requestedPage = parsePage(search);

  const filteredPortals = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return portals;
    return portals.filter((portal) => [
      portal.title_zh,
      portal.title_en,
      portal.institution_zh,
      portal.institution_en,
      portal.overview_zh,
      portal.overview_en,
    ].some((value) => value.toLocaleLowerCase().includes(normalizedQuery)));
  }, [portals, query]);

  const pageCount = Math.max(1, Math.ceil(filteredPortals.length / DATABASE_PAGE_SIZE));
  const page = Math.min(requestedPage, pageCount);
  const pagePortals = filteredPortals.slice((page - 1) * DATABASE_PAGE_SIZE, page * DATABASE_PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="source-portals-title">
          {t("source_portals.title")}
        </h1>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {t("source_portals.subtitle")}
        </p>
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <label htmlFor="input-source-portal-search" className="mb-1 block text-xs font-medium text-muted-foreground">
          {t("source_portals.search_label")}
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <input
            id="input-source-portal-search"
            type="search"
            value={query}
            onChange={(event) => navigate(portalListHref(event.target.value, 1), { replace: true })}
            placeholder={t("source_portals.search_placeholder")}
            className="min-h-[44px] w-full rounded-lg border border-border bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            data-testid="input-source-portal-search"
          />
        </div>
      </div>

      {error && <SourcePortalError error={error} onRetry={retryLoad} />}

      {loading ? (
        <SourcePortalsLoading />
      ) : error ? null : portals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center" data-testid="source-portals-empty">
          <Compass className="mx-auto mb-3 h-12 w-12 text-muted-foreground/40" aria-hidden="true" />
          <p className="font-medium text-muted-foreground">{t("source_portals.empty")}</p>
        </div>
      ) : filteredPortals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center" data-testid="source-portals-no-results">
          <p className="font-medium text-muted-foreground">{t("source_portals.no_results")}</p>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-border bg-card" data-testid="source-portals-list" role="table" aria-label={t("source_portals.title")}>
            <div className="hidden border-b border-border bg-muted/40 sm:block" role="rowgroup">
              <div className="grid grid-cols-[minmax(0,1.1fr)_minmax(9rem,0.9fr)_minmax(12rem,2fr)_minmax(8.5rem,auto)] gap-4 px-5 py-3 text-xs font-medium text-muted-foreground" role="row">
                <span role="columnheader">{t("source_portals.column_title")}</span>
                <span role="columnheader">{t("source_portals.column_institution")}</span>
                <span role="columnheader">{t("source_portals.column_overview")}</span>
                <span role="columnheader" className="text-right">{t("source_portals.column_latest")}</span>
              </div>
            </div>
            <div role="rowgroup">
              {pagePortals.map((portal) => {
                const latestDate = portal.updates
                  .map((update) => update.acquired_on)
                  .sort((left, right) => right.localeCompare(left))[0];
                const title = localized(lang, portal.title_zh, portal.title_en);
                const institution = localized(lang, portal.institution_zh, portal.institution_en);
                return (
                  <article key={portal.portal_key} className="grid min-w-0 grid-cols-1 items-start gap-y-1.5 border-b border-border px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,1.1fr)_minmax(9rem,0.9fr)_minmax(12rem,2fr)_minmax(8.5rem,auto)] sm:gap-4 sm:px-5" data-testid="source-portal-row" role="row">
                    <div className="min-w-0" role="cell">
                      <h2 className="break-words text-sm font-semibold leading-snug">
                        <Link href={portalDetailHref(portal.portal_key, query, page)} className="rounded-sm text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                          {title}
                        </Link>
                      </h2>
                      <p className="mt-1 break-words text-xs text-muted-foreground sm:hidden">{institution}</p>
                    </div>
                    <div className="hidden min-w-0 break-words text-sm text-muted-foreground sm:block" role="cell">{institution}</div>
                    <p className="line-clamp-2 min-w-0 break-words text-sm leading-relaxed text-muted-foreground" role="cell">
                      {localized(lang, portal.overview_zh, portal.overview_en)}
                    </p>
                    <div className="min-w-0 break-words text-xs text-muted-foreground sm:text-right" role="cell">
                      {latestDate ? (
                        <>
                          <span className="sm:hidden">{t("source_portals.latest_update")}: </span>
                          <time dateTime={latestDate} className="whitespace-nowrap">{formatDate(latestDate, lang)}</time>
                        </>
                      ) : t("source_portals.no_updates_yet")}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>

          {pageCount > 1 && (
            <nav className="flex flex-col items-center justify-between gap-2 rounded-xl border border-border bg-card px-4 py-2 sm:flex-row" aria-label={t("source_portals.pagination")} data-testid="source-portals-pagination">
              <Link
                href={portalListHref(query, page - 1)}
                aria-disabled={page <= 1}
                tabIndex={page <= 1 ? -1 : undefined}
                className={`inline-flex min-h-[44px] items-center gap-2 rounded-lg px-3 text-sm font-medium ${page <= 1 ? "pointer-events-none text-muted-foreground/50" : "text-primary hover:bg-primary/5"}`}
                data-testid="source-portals-pagination-previous"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                {t("source_portals.previous_page")}
              </Link>
              <span className="text-sm text-muted-foreground" aria-live="polite" data-testid="source-portals-page-label">
                {t("source_portals.page_label", { page, total: pageCount })}
              </span>
              <Link
                href={portalListHref(query, page + 1)}
                aria-disabled={page >= pageCount}
                tabIndex={page >= pageCount ? -1 : undefined}
                className={`inline-flex min-h-[44px] items-center gap-2 rounded-lg px-3 text-sm font-medium ${page >= pageCount ? "pointer-events-none text-muted-foreground/50" : "text-primary hover:bg-primary/5"}`}
                data-testid="source-portals-pagination-next"
              >
                {t("source_portals.next_page")}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

export function SourcePortalDetail({ params }: { params?: { portalKey?: string } }) {
  const { lang, t } = useTranslation();
  const { portals, loading, error, retryLoad } = useSourcePortals();
  const search = useSearch();
  const portal = portals.find((item) => item.portal_key === params?.portalKey);
  const backHref = portalListHref(
    new URLSearchParams(search).get("query") || "",
    parsePage(search),
  );

  return (
    <div className="space-y-5">
      <Link href={backHref} className="inline-flex min-h-[44px] items-center gap-2 rounded-md text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" data-testid="source-portal-back">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {t("source_portals.back_to_list")}
      </Link>

      {error && <SourcePortalError error={error} onRetry={retryLoad} />}

      {loading ? (
        <SourcePortalsLoading />
      ) : error ? null : !portal ? (
        <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center sm:p-10" data-testid="source-portal-not-found">
          <Compass className="mx-auto mb-3 h-12 w-12 text-muted-foreground/40" aria-hidden="true" />
          <h1 className="text-lg font-semibold">{t("source_portals.not_found_title")}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{t("source_portals.not_found_description")}</p>
        </div>
      ) : (
        <article className="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-6" data-testid="source-portal-detail">
          <header className="min-w-0 border-b border-border pb-5">
            <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h1 className="break-words text-xl font-serif font-bold leading-snug sm:text-2xl" data-testid="source-portal-detail-title">
                  {localized(lang, portal.title_zh, portal.title_en)}
                </h1>
                <p className="mt-1 break-words text-sm text-muted-foreground">
                  {localized(lang, portal.institution_zh, portal.institution_en)}
                </p>
              </div>
              <a
                href={portal.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-[44px] max-w-full items-center gap-2 self-start break-all rounded-lg border border-border px-3 py-2 text-sm text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                aria-label={`${t("source_portals.open_source")} ${localized(lang, portal.title_zh, portal.title_en)}`}
                data-testid="source-portal-original-link"
              >
                <ExternalLink className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="break-all">{portal.url}</span>
              </a>
            </div>
            <p className="mt-4 break-words text-sm leading-relaxed text-muted-foreground">
              {localized(lang, portal.overview_zh, portal.overview_en)}
            </p>
          </header>

          <section className="pt-5" aria-label={t("source_portals.updates")}>
            <h2 className="text-base font-semibold">{t("source_portals.updates")}</h2>
            {portal.updates.length ? (
              <ol className="mt-4 space-y-5">
                {portal.updates.map((update) => (
                  <li key={update.acquired_on} className="grid min-w-0 grid-cols-1 items-start gap-1.5 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-4">
                    <time dateTime={update.acquired_on} className="whitespace-nowrap pt-0.5 text-xs text-muted-foreground">
                      {formatDate(update.acquired_on, lang)}
                    </time>
                    <p className="break-words text-sm leading-relaxed">
                      {localized(lang, update.description_zh, update.description_en)}
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground" data-testid="source-portal-no-updates">
                {t("source_portals.no_updates")}
              </p>
            )}
          </section>
        </article>
      )}
    </div>
  );
}
