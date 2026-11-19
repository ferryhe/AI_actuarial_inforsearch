import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearch } from "wouter";
import { ArrowLeft, ArrowRight, Compass, ExternalLink, Search } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet, formatApiErrorDetail } from "@/lib/api";
import { DATABASE_PAGE_SIZE } from "@/lib/database-query";
import { buildFileDetailPath } from "@/lib/navigation";

interface PortalUpdate {
  acquired_on: string;
  description_zh: string;
  description_en: string;
}

interface PortalIntakeUpdate {
  acquired_on: string;
  new_count: number;
  backfill_count: number;
  other_count: number;
  files: {
    url: string;
    title: string;
    first_seen?: string;
    timing: "new" | "backfill" | "other";
    published_on: string | null;
    available?: boolean;
  }[];
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
  entry_links?: { url: string; title_zh: string; title_en: string }[];
  updates: PortalUpdate[];
  intake_updates?: PortalIntakeUpdate[];
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
    apiGet<{ portals?: SourcePortal[]; other_intake_updates?: PortalIntakeUpdate[] }>("/api/source-portals")
      .then((result) => {
        if (cancelled) return;
        const cards = result.portals || [];
        if (result.other_intake_updates?.length) {
          setPortals([...cards, {
            portal_key: "other-intake",
            url: "",
            title_zh: "其他来源",
            title_en: "Other Sources",
            institution_zh: "资料库",
            institution_en: "Library",
            overview_zh: "来自其他渠道或来源待确认的入库记录。",
            overview_en: "Intake from other channels and sources awaiting attribution.",
            updates: [],
            intake_updates: result.other_intake_updates,
          }]);
        } else {
          setPortals(cards);
        }
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

function observationDescription(update: PortalUpdate, lang: string) {
  if (lang === "zh") {
    return update.description_zh
      .replace(/^新发现(\d+)份AI资料(?=：)/, "发现 $1 条 AI 资料线索")
      .replace(/^未发现新的AI资料。/, "未发现新的 AI 资料线索。");
  }
  return update.description_en
    .replace(/^Found (\d+) new AI material(s?)(?=:)/, "Found $1 AI resource lead$2")
    .replace(/^No new AI materials were found\./, "No new AI resource leads were found.");
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

function intakeCounts(update: PortalIntakeUpdate, t: ReturnType<typeof useTranslation>["t"]) {
  return [
    t("source_portals.new_count", { count: update.new_count }),
    t("weekly.backfill_count", { count: update.backfill_count }),
    t("weekly.other_intake_count", { count: update.other_count }),
  ].join(" · ");
}

function PortalTimeline({ portal, returnPath }: { portal: SourcePortal; returnPath: string }) {
  const { lang, t } = useTranslation();
  const observations = new Map(portal.updates.map((update) => [update.acquired_on, update]));
  const intakeByDay = new Map((portal.intake_updates || []).map((update) => [update.acquired_on, update]));
  const days = [...new Set([...observations.keys(), ...intakeByDay.keys()])].sort().reverse();

  if (!days.length) {
    return (
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground" data-testid="source-portal-no-updates">
        {t("source_portals.no_updates")}
      </p>
    );
  }

  return (
    <>
      <p className="mt-2 text-xs text-muted-foreground">{t("source_portals.activity_dates")}</p>
      <ol className="mt-4 divide-y divide-border" data-testid="source-portal-activity">
        {days.map((day) => {
          const observation = observations.get(day);
          const intake = intakeByDay.get(day);
          const count = intake?.files.length ?? 0;
          return (
            <li key={day} className="min-w-0 py-3" data-testid="source-portal-activity-day">
              <time dateTime={day} className="text-sm font-semibold">{formatDate(day, lang)}</time>
              {observation ? (
                <p className="mt-1 break-words text-sm leading-relaxed">
                  <span className="mr-2 font-medium">{t("source_portals.observation_label")}</span>{" "}
                  <span>{observationDescription(observation, lang)}</span>
                </p>
              ) : null}
              <p className="mt-1 text-xs text-muted-foreground">
                {t("source_portals.intake_total", { count })}
                {intake ? " · " + intakeCounts(intake, t) : null}
              </p>
              {intake && count > 0 ? (
                <details className="mt-1" data-testid="source-portal-intake-details">
                  <summary className="min-h-[44px] cursor-pointer rounded-sm py-3 text-sm font-medium text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                    {t("source_portals.intake_details", { count })}
                  </summary>
                  <ul className="space-y-2 pb-1">
                    {intake.files.map((file) => (
                      <li key={file.url + " " + (file.first_seen ?? "")} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                        {file.available === false ? (
                          <span className="min-w-0 [overflow-wrap:anywhere]">{file.title}</span>
                        ) : (
                          <Link href={buildFileDetailPath(file.url, returnPath)} className="min-w-0 text-primary [overflow-wrap:anywhere] hover:underline">
                            {file.title}
                          </Link>
                        )}
                        <span className="text-xs text-muted-foreground">
                          {t("source_portals.intake_" + file.timing)}{file.published_on ? " · " + file.published_on : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </li>
          );
        })}
      </ol>
    </>
  );
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
                const latestIntake = portal.intake_updates?.[0];
                const latestDate = [...portal.updates, ...(latestIntake ? [latestIntake] : [])]
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
                          {latestIntake ? (
                            <p className="mt-1 leading-relaxed" data-testid="source-portal-intake-counts">
                              {latestIntake.acquired_on !== latestDate ? (
                                <time className="block" dateTime={latestIntake.acquired_on}>
                                  {formatDate(latestIntake.acquired_on, lang)}
                                </time>
                              ) : null}
                              {intakeCounts(latestIntake, t)}
                            </p>
                          ) : null}
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
  const returnPath = useLocation()[0] + (search ? `?${search}` : "");
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
              {portal.entry_links?.length ? (
                <div className="flex min-w-0 flex-col gap-2">
                  {portal.entry_links.map((entry) => (
                    <a key={entry.url} href={entry.url} target="_blank" rel="noreferrer"
                      className="inline-flex min-h-[44px] max-w-full items-center gap-2 self-start rounded-lg border border-border px-3 py-2 text-sm text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      data-testid="source-portal-entry-link">
                      <ExternalLink className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="break-words">{localized(lang, entry.title_zh, entry.title_en)}</span>
                    </a>
                  ))}
                </div>
              ) : portal.url ? (
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
              ) : null}
            </div>
            <p className="mt-4 break-words text-sm leading-relaxed text-muted-foreground">
              {localized(lang, portal.overview_zh, portal.overview_en)}
            </p>
          </header>

          <section className="pt-5" aria-label={t("source_portals.updates")}>
            <h2 className="text-base font-semibold">{t("source_portals.updates")}</h2>
            <PortalTimeline key={portal.portal_key} portal={portal} returnPath={returnPath} />
          </section>
        </article>
      )}
    </div>
  );
}
