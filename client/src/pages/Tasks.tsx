import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Square,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  Globe,
  FileUp,
  Search,
  BookOpen,
  FileText,
  Layers,
  Database,
  Link2,
  X,
  ScrollText,
  Inbox,
  ArrowLeft,
  AlertCircle,
  Info,
  Compass,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";

interface Task {
  id: string;
  name: string;
  type: string;
  status: string;
  progress: number;
  started_at: string;
  current_activity: string;
  items_processed: number;
  items_total: number;
}

interface SiteConfig {
  name: string;
  url?: string;
  max_pages?: number;
  max_depth?: number;
  keywords?: string[];
  exclude_keywords?: string[];
  exclude_prefixes?: string[];
  schedule_interval?: string;
  content_selector?: string;
}

interface KBItem {
  kb_id: string;
  name: string;
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.4, ease: "easeOut" as const },
  }),
};

function statusIcon(status: string) {
  switch (status) {
    case "running":
      return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
    case "success":
    case "completed":
      return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
    case "error":
    case "failed":
      return <XCircle className="w-4 h-4 text-red-500" />;
    case "stopped":
      return <Square className="w-4 h-4 text-amber-500" />;
    default:
      return <Clock className="w-4 h-4 text-muted-foreground" />;
  }
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    running: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
    success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    completed: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    error: "bg-red-500/10 text-red-600 dark:text-red-400",
    failed: "bg-red-500/10 text-red-600 dark:text-red-400",
    stopped: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full",
        colors[status] || "bg-muted text-muted-foreground"
      )}
      data-testid={`status-badge-${status}`}
    >
      {statusIcon(status)}
      {status}
    </span>
  );
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

const taskTypes = [
  { type: "scheduled", apiType: "scheduled", icon: Globe, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  { type: "web_crawl", apiType: "quick_check", icon: Compass, color: "bg-orange-500/10 text-orange-600 dark:text-orange-400" },
  { type: "adhoc_url", apiType: "url", icon: Link2, color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400" },
  { type: "file_import", apiType: "file", icon: FileUp, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  { type: "web_search", apiType: "search", icon: Search, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { type: "catalog", apiType: "catalog", icon: BookOpen, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  { type: "markdown", apiType: "markdown_conversion", icon: FileText, color: "bg-pink-500/10 text-pink-600 dark:text-pink-400" },
  { type: "chunk", apiType: "chunk_generation", icon: Layers, color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  { type: "rag_index", apiType: "rag_indexing", icon: Database, color: "bg-teal-500/10 text-teal-600 dark:text-teal-400" },
];

function FormField({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground/70">{hint}</p>}
    </div>
  );
}

function InputField({ value, onChange, placeholder, type = "text", testId }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; testId?: string;
}) {
  return (
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId} />
  );
}

function SelectField({ value, onChange, options, testId }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; testId?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function CheckboxField({ checked, onChange, label, testId }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; testId?: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded" data-testid={testId} />
      {label}
    </label>
  );
}

function RunButton({ onClick, disabled, submitting, label }: {
  onClick: () => void; disabled: boolean; submitting: boolean; label: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
      data-testid="button-run-task">
      {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
      {label}
    </button>
  );
}

function StatsBanner({ items }: { items: { label: string; value: string | number | null | undefined }[] }) {
  const valid = items.filter((i) => i.value != null);
  if (valid.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="stats-banner">
      {valid.map((item) => (
        <div key={item.label}>
          <p className="text-[11px] text-muted-foreground">{item.label}</p>
          <p className="text-sm font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function SiteDetailCard({ site, expanded, onToggle }: { site: SiteConfig; expanded: boolean; onToggle: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border border-border bg-muted/30 overflow-hidden" data-testid={`card-site-${site.name}`}>
      <button onClick={onToggle}
        className="w-full flex items-center gap-3 px-3.5 py-2.5 text-left hover:bg-muted/50 transition-colors">
        <Globe className="w-4 h-4 text-primary shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium truncate block">{site.name}</span>
          {site.url && <span className="text-[11px] text-muted-foreground truncate block">{site.url}</span>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {site.schedule_interval && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">{site.schedule_interval}</span>
          )}
          {expanded ? <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />}
        </div>
      </button>
      {expanded && (
        <div className="px-3.5 pb-3 pt-1 border-t border-border space-y-2 text-xs">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            <div><span className="text-muted-foreground">{t("tasks.form.max_pages")}:</span> <span className="font-medium">{site.max_pages ?? "—"}</span></div>
            <div><span className="text-muted-foreground">{t("tasks.form.max_depth")}:</span> <span className="font-medium">{site.max_depth ?? "—"}</span></div>
          </div>
          {site.keywords && site.keywords.length > 0 && (
            <div>
              <span className="text-muted-foreground">{t("tasks.form.keywords")}:</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {site.keywords.map((kw) => (
                  <span key={kw} className="px-1.5 py-0.5 rounded bg-muted text-[10px]">{kw}</span>
                ))}
              </div>
            </div>
          )}
          {site.exclude_keywords && site.exclude_keywords.length > 0 && (
            <div>
              <span className="text-muted-foreground">{t("tasks.form.exclude_keywords")}:</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {site.exclude_keywords.map((kw) => (
                  <span key={kw} className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-600 dark:text-red-400 text-[10px]">{kw}</span>
                ))}
              </div>
            </div>
          )}
          {site.content_selector && (
            <div><span className="text-muted-foreground">{t("tasks.form.content_selector")}:</span> <code className="text-[10px] bg-muted px-1 rounded">{site.content_selector}</code></div>
          )}
          {site.url && (
            <a href={site.url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline mt-1">
              <ExternalLink className="w-3 h-3" />{t("tasks.form.visit_site")}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function ScheduledForm({ sites, onSubmit, submitting }: { sites: SiteConfig[]; onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [site, setSite] = useState("");
  const [maxPages, setMaxPages] = useState("");
  const [maxDepth, setMaxDepth] = useState("");
  const [showSites, setShowSites] = useState(false);
  const [expandedSite, setExpandedSite] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.scheduled_desc")}</p>
      <FormField label={t("tasks.form.target_site")}>
        <SelectField value={site} onChange={setSite} testId="select-site"
          options={[{ value: "", label: t("tasks.form.all_sites") + ` (${sites.length})` }, ...sites.map((s) => ({ value: s.name, label: s.name }))]} />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.max_pages")} hint={t("tasks.form.default_hint") + " 200"}>
          <InputField value={maxPages} onChange={setMaxPages} placeholder="200" type="number" testId="input-max-pages" />
        </FormField>
        <FormField label={t("tasks.form.max_depth")} hint={t("tasks.form.default_hint") + " 2"}>
          <InputField value={maxDepth} onChange={setMaxDepth} placeholder="2" type="number" testId="input-max-depth" />
        </FormField>
      </div>
      {sites.length > 0 && (
        <div className="border-t border-border pt-3 mt-1">
          <button onClick={() => setShowSites(!showSites)}
            className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-toggle-sites">
            <Settings2 className="w-3.5 h-3.5" />
            {t("tasks.form.configured_sites_detail")} ({sites.length})
            {showSites ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showSites && (
            <div className="mt-3 space-y-2 max-h-[300px] overflow-y-auto pr-1">
              {sites.map((s) => (
                <SiteDetailCard key={s.name} site={s}
                  expanded={expandedSite === s.name}
                  onToggle={() => setExpandedSite(expandedSite === s.name ? null : s.name)} />
              ))}
            </div>
          )}
        </div>
      )}
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting}
        onClick={() => onSubmit({ type: "scheduled", name: site ? `Scheduled: ${site}` : "Scheduled Collection",
          site: site || undefined, max_pages: maxPages ? parseInt(maxPages) : undefined, max_depth: maxDepth ? parseInt(maxDepth) : undefined })} />
    </div>
  );
}

function WebCrawlForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [maxPages, setMaxPages] = useState("10");
  const [maxDepth, setMaxDepth] = useState("1");
  const [keywords, setKeywords] = useState("");
  const [fileExts, setFileExts] = useState("");
  const [checkDb, setCheckDb] = useState(false);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.web_crawl_desc")}</p>
      <FormField label={t("tasks.form.crawl_url")}>
        <InputField value={url} onChange={setUrl} placeholder="https://example.org/reports/" testId="input-crawl-url" />
      </FormField>
      <FormField label={t("tasks.form.crawl_name")} hint={t("tasks.form.crawl_name_hint")}>
        <InputField value={name} onChange={setName} placeholder="Quick Check" testId="input-crawl-name" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.max_pages")} hint={t("tasks.form.default_hint") + " 10"}>
          <InputField value={maxPages} onChange={setMaxPages} placeholder="10" type="number" testId="input-crawl-max-pages" />
        </FormField>
        <FormField label={t("tasks.form.max_depth")} hint={t("tasks.form.default_hint") + " 1"}>
          <InputField value={maxDepth} onChange={setMaxDepth} placeholder="1" type="number" testId="input-crawl-max-depth" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.keywords")} hint={t("tasks.form.comma_separated")}>
        <InputField value={keywords} onChange={setKeywords} placeholder="artificial intelligence, actuarial" testId="input-crawl-keywords" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <InputField value={fileExts} onChange={setFileExts} placeholder=".pdf,.docx" testId="input-crawl-file-exts" />
      </FormField>
      <CheckboxField checked={checkDb} onChange={setCheckDb} label={t("tasks.form.check_database")} testId="checkbox-crawl-check-db" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !url.trim()}
        onClick={() => { if (!url.trim()) return;
          onSubmit({ type: "quick_check", name: name || "Quick Check", url: url.trim(),
            max_pages: parseInt(maxPages) || 10, max_depth: parseInt(maxDepth) || 1,
            keywords: keywords ? keywords.split(",").map((k) => k.trim()).filter(Boolean) : [],
            file_exts: fileExts ? fileExts.split(",").map((e) => e.trim()).filter(Boolean) : undefined,
            check_database: checkDb });
        }} />
    </div>
  );
}

function AdhocUrlForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [urls, setUrls] = useState("");
  const [fileExts, setFileExts] = useState(".pdf,.docx,.pptx");
  const [checkDb, setCheckDb] = useState(true);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.url_desc")}</p>
      <FormField label={t("tasks.form.urls")}>
        <textarea value={urls} onChange={(e) => setUrls(e.target.value)} placeholder={t("tasks.form.urls_placeholder")} rows={4}
          className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          data-testid="input-urls" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <InputField value={fileExts} onChange={setFileExts} placeholder=".pdf,.docx,.pptx" testId="input-file-exts" />
      </FormField>
      <CheckboxField checked={checkDb} onChange={setCheckDb} label={t("tasks.form.check_database")} testId="checkbox-check-db" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !urls.trim()}
        onClick={() => {
          const urlList = urls.split("\n").map((u) => u.trim()).filter(Boolean);
          if (!urlList.length) return;
          onSubmit({ type: "url", name: `URL Collection (${urlList.length})`, urls: urlList,
            file_exts: fileExts.split(",").map((e) => e.trim()).filter(Boolean), check_database: checkDb });
        }} />
    </div>
  );
}

function FileImportForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [dirPath, setDirPath] = useState("");
  const [extensions, setExtensions] = useState(".pdf,.docx,.pptx");
  const [recursive, setRecursive] = useState(true);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.file_desc")}</p>
      <FormField label={t("tasks.form.directory_path")}>
        <InputField value={dirPath} onChange={setDirPath} placeholder="/path/to/files" testId="input-dir-path" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <InputField value={extensions} onChange={setExtensions} placeholder=".pdf,.docx,.pptx" testId="input-extensions" />
      </FormField>
      <CheckboxField checked={recursive} onChange={setRecursive} label={t("tasks.form.recursive")} testId="checkbox-recursive" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !dirPath.trim()}
        onClick={() => { if (!dirPath.trim()) return;
          onSubmit({ type: "file", name: `File Import: ${dirPath}`, directory_path: dirPath,
            extensions: extensions.split(",").map((e) => e.trim()).filter(Boolean), recursive });
        }} />
    </div>
  );
}

function WebSearchForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [engine, setEngine] = useState("brave");
  const [count, setCount] = useState("20");
  const [site, setSite] = useState("");
  const [searchLang, setSearchLang] = useState("");
  const [searchCountry, setSearchCountry] = useState("");
  const [excludeKw, setExcludeKw] = useState("");
  const [fileExts, setFileExts] = useState("");
  const [useDefaults, setUseDefaults] = useState(true);

  const engines = [
    { value: "brave", label: "Brave Search" },
    { value: "google", label: "Google (SerpAPI)" },
    { value: "serper", label: "Google (Serper)" },
    { value: "tavily", label: "Tavily" },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.search_desc")}</p>
      <FormField label={t("tasks.form.search_query")}>
        <InputField value={query} onChange={setQuery} placeholder={t("tasks.form.search_query_placeholder")} testId="input-search-query" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.search_engine")}>
          <SelectField value={engine} onChange={setEngine} options={engines} testId="select-engine" />
        </FormField>
        <FormField label={t("tasks.form.max_results")}>
          <InputField value={count} onChange={setCount} placeholder="20" type="number" testId="input-count" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.site_filter")}>
        <InputField value={site} onChange={setSite} placeholder="example.com" testId="input-site-filter" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.search_lang")} hint="en, zh, fr...">
          <InputField value={searchLang} onChange={setSearchLang} placeholder="" testId="input-search-lang" />
        </FormField>
        <FormField label={t("tasks.form.search_country")} hint="US, CN, GB...">
          <InputField value={searchCountry} onChange={setSearchCountry} placeholder="" testId="input-search-country" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.exclude_keywords")} hint={t("tasks.form.comma_separated")}>
        <InputField value={excludeKw} onChange={setExcludeKw} placeholder="" testId="input-exclude-kw" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <InputField value={fileExts} onChange={setFileExts} placeholder=".pdf,.docx" testId="input-search-file-exts" />
      </FormField>
      <CheckboxField checked={useDefaults} onChange={setUseDefaults} label={t("tasks.form.use_search_defaults")} testId="checkbox-use-defaults" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !query.trim()}
        onClick={() => { if (!query.trim()) return;
          onSubmit({ type: "search", name: `Search: ${query}`, query, engine, count: parseInt(count) || 20,
            site: site || undefined, search_lang: searchLang || undefined, search_country: searchCountry || undefined,
            search_exclude_keywords: excludeKw ? excludeKw.split(",").map((k) => k.trim()).filter(Boolean) : undefined,
            file_exts: fileExts ? fileExts.split(",").map((e) => e.trim()).filter(Boolean) : undefined,
            use_search_defaults: useDefaults });
        }} />
    </div>
  );
}

function CatalogForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("100");
  const [startIndex, setStartIndex] = useState("1");
  const [provider, setProvider] = useState("");
  const [inputSource, setInputSource] = useState("markdown");
  const [retryErrors, setRetryErrors] = useState(false);
  const [skipExisting, setSkipExisting] = useState(true);
  const [overwriteExisting, setOverwriteExisting] = useState(false);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const loadStats = useCallback(async (cat?: string) => {
    setStatsLoading(true);
    try {
      const q = cat ? `?category=${encodeURIComponent(cat)}` : "";
      const res = await apiGet<{ data?: Record<string, unknown> } & Record<string, unknown>>(`/api/catalog/stats${q}`);
      setStats(res.data || res);
    } catch { setStats(null); }
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.catalog_desc")}</p>
      {statsLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("tasks.form.loading_stats")}</div>
      ) : stats && (
        <StatsBanner items={[
          { label: t("tasks.form.stat_local_files"), value: stats.total_local_files as number },
          { label: t("tasks.form.stat_cataloged"), value: stats.total_catalog_ok as number },
          { label: t("tasks.form.stat_candidates"), value: stats.candidate_total as number },
          { label: t("tasks.form.stat_first_candidate"), value: stats.first_candidate_index as number },
        ]} />
      )}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.scope")}>
          <SelectField value={scopeMode} onChange={(v) => { setScopeMode(v); if (v === "index") loadStats(); }} testId="select-scope"
            options={[{ value: "index", label: t("tasks.form.scope_all") }, { value: "category", label: t("tasks.form.scope_category") }]} />
        </FormField>
        <FormField label={t("tasks.form.scan_count")} hint={t("tasks.form.max_hint") + " 2000"}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="100" type="number" testId="input-scan-count" />
        </FormField>
      </div>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} onBlur={handleCategoryBlur} placeholder="SOA, IAA..."
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="input-category" />
        </FormField>
      )}
      <FormField label={t("tasks.form.start_index")} hint={t("tasks.form.start_index_hint")}>
        <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-start-index" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.provider")} hint={t("tasks.form.provider_hint")}>
          <InputField value={provider} onChange={setProvider} placeholder="openai" testId="input-provider" />
        </FormField>
        <FormField label={t("tasks.form.input_source")}>
          <SelectField value={inputSource} onChange={setInputSource} testId="select-input-source"
            options={[{ value: "markdown", label: "Markdown" }, { value: "source", label: "Source" }]} />
        </FormField>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={retryErrors} onChange={setRetryErrors} label={t("tasks.form.retry_errors")} testId="checkbox-retry-errors" />
        <CheckboxField checked={skipExisting} onChange={(v) => { setSkipExisting(v); if (v) setOverwriteExisting(false); }}
          label={t("tasks.form.skip_existing")} testId="checkbox-skip-existing" />
        <CheckboxField checked={overwriteExisting} onChange={(v) => { setOverwriteExisting(v); if (v) setSkipExisting(false); }}
          label={t("tasks.form.overwrite_existing")} testId="checkbox-overwrite-existing" />
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim())}
        onClick={() => onSubmit({ type: "catalog", name: "AI Catalog", scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined, scan_count: parseInt(scanCount) || 100,
          scan_start_index: parseInt(startIndex) || 1, provider: provider || undefined, input_source: inputSource,
          retry_errors: retryErrors, skip_existing: skipExisting, overwrite_existing: overwriteExisting })} />
    </div>
  );
}

function MarkdownForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [startIndex, setStartIndex] = useState("");
  const [tool, setTool] = useState("docling");
  const [skipExisting, setSkipExisting] = useState(true);
  const [overwriteExisting, setOverwriteExisting] = useState(false);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const tools = [
    { value: "docling", label: "Docling" },
    { value: "marker", label: "Marker" },
    { value: "mistral", label: "Mistral OCR" },
    { value: "auto", label: "Auto" },
  ];

  const loadStats = useCallback(async (cat?: string) => {
    setStatsLoading(true);
    try {
      const q = cat ? `?category=${encodeURIComponent(cat)}` : "";
      const res = await apiGet<{ data?: Record<string, unknown> } & Record<string, unknown>>(`/api/markdown_conversion/stats${q}`);
      setStats(res.data || res);
    } catch { setStats(null); }
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  useEffect(() => {
    if (stats && !startIndex) {
      const first = stats.first_without_markdown_index;
      if (first != null) setStartIndex(String(first));
    }
  }, [stats, startIndex]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.markdown_desc")}</p>
      {statsLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("tasks.form.loading_stats")}</div>
      ) : stats && (
        <StatsBanner items={[
          { label: t("tasks.form.stat_convertible"), value: stats.total_convertible as number },
          { label: t("tasks.form.stat_with_markdown"), value: stats.total_with_markdown as number },
          { label: t("tasks.form.stat_first_no_md"), value: stats.first_without_markdown_index as number },
        ]} />
      )}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.conversion_tool")}>
          <SelectField value={tool} onChange={setTool} options={tools} testId="select-tool" />
        </FormField>
        <FormField label={t("tasks.form.scan_count")} hint={t("tasks.form.max_hint") + " 2000"}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-md-scan-count" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.start_index")} hint={t("tasks.form.start_index_hint")}>
        <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-md-start-index" />
      </FormField>
      <FormField label={t("tasks.form.scope")}>
        <SelectField value={scopeMode} onChange={(v) => { setScopeMode(v); if (v === "index") loadStats(); }} testId="select-md-scope"
          options={[{ value: "index", label: t("tasks.form.scope_all") }, { value: "category", label: t("tasks.form.scope_category") }]} />
      </FormField>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} onBlur={handleCategoryBlur} placeholder="SOA, IAA..."
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="input-md-category" />
        </FormField>
      )}
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={skipExisting} onChange={(v) => { setSkipExisting(v); if (v) setOverwriteExisting(false); }}
          label={t("tasks.form.skip_existing")} testId="checkbox-md-skip" />
        <CheckboxField checked={overwriteExisting} onChange={(v) => { setOverwriteExisting(v); if (v) setSkipExisting(false); }}
          label={t("tasks.form.overwrite_existing")} testId="checkbox-md-overwrite" />
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim())}
        onClick={() => onSubmit({ type: "markdown_conversion", name: `Markdown (${tool})`, conversion_tool: tool,
          scope_mode: scopeMode, category: scopeMode === "category" ? category : undefined,
          scan_count: parseInt(scanCount) || 50, scan_start_index: startIndex ? parseInt(startIndex) : undefined,
          skip_existing: skipExisting, overwrite_existing: overwriteExisting })} />
    </div>
  );
}

function ChunkForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [startIndex, setStartIndex] = useState("");
  const [chunkSize, setChunkSize] = useState("800");
  const [chunkOverlap, setChunkOverlap] = useState("100");
  const [splitter, setSplitter] = useState("semantic");
  const [tokenizer, setTokenizer] = useState("cl100k_base");
  const [profileName, setProfileName] = useState("");
  const [overwriteSameProfile, setOverwriteSameProfile] = useState(false);
  const [kbId, setKbId] = useState("");
  const [kbs, setKbs] = useState<KBItem[]>([]);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const loadStats = useCallback(async (cat?: string) => {
    setStatsLoading(true);
    try {
      const q = cat ? `?category=${encodeURIComponent(cat)}` : "";
      const res = await apiGet<{ data?: Record<string, unknown> } & Record<string, unknown>>(`/api/chunk_generation/stats${q}`);
      setStats(res.data || res);
    } catch { setStats(null); }
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => {
    apiGet<{ knowledge_bases?: Array<Record<string, string>>; data?: { knowledge_bases?: Array<Record<string, string>> } }>("/api/rag/knowledge-bases")
      .then((res) => {
        const raw = res.data?.knowledge_bases || res.knowledge_bases || [];
        setKbs(raw.map((kb) => ({ kb_id: kb.kb_id || kb.id || "", name: kb.name || kb.kb_id || kb.id || "" })));
      }).catch(() => setKbs([]));
  }, []);

  useEffect(() => {
    if (stats && !startIndex) {
      const first = stats.first_without_chunks_index;
      if (first != null) setStartIndex(String(first));
    }
  }, [stats, startIndex]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.chunk_desc")}</p>
      {statsLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("tasks.form.loading_stats")}</div>
      ) : stats && (
        <StatsBanner items={[
          { label: t("tasks.form.stat_with_markdown"), value: stats.total_with_markdown as number },
          { label: t("tasks.form.stat_with_chunks"), value: stats.total_with_chunks as number },
          { label: t("tasks.form.stat_first_no_chunk"), value: stats.first_without_chunks_index as number },
        ]} />
      )}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.scan_count")} hint={t("tasks.form.max_hint") + " 2000"}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-chunk-scan-count" />
        </FormField>
        <FormField label={t("tasks.form.start_index")} hint={t("tasks.form.start_index_hint")}>
          <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-chunk-start-index" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.scope")}>
        <SelectField value={scopeMode} onChange={(v) => { setScopeMode(v); if (v === "index") loadStats(); }} testId="select-chunk-scope"
          options={[{ value: "index", label: t("tasks.form.scope_all") }, { value: "category", label: t("tasks.form.scope_category") }]} />
      </FormField>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} onBlur={handleCategoryBlur} placeholder="SOA, IAA..."
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="input-chunk-category" />
        </FormField>
      )}
      <div className="border-t border-border pt-3 mt-1">
        <p className="text-xs font-medium text-muted-foreground mb-3">{t("tasks.form.chunk_params")}</p>
        <div className="grid grid-cols-2 gap-3">
          <FormField label={t("tasks.form.chunk_size")} hint="64 – 8192">
            <InputField value={chunkSize} onChange={setChunkSize} placeholder="800" type="number" testId="input-chunk-size" />
          </FormField>
          <FormField label={t("tasks.form.chunk_overlap")} hint="0 – 2048">
            <InputField value={chunkOverlap} onChange={setChunkOverlap} placeholder="100" type="number" testId="input-chunk-overlap" />
          </FormField>
        </div>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <FormField label={t("tasks.form.splitter")}>
            <SelectField value={splitter} onChange={setSplitter} testId="select-splitter"
              options={[{ value: "semantic", label: "Semantic" }, { value: "recursive", label: "Recursive" }]} />
          </FormField>
          <FormField label={t("tasks.form.tokenizer")}>
            <SelectField value={tokenizer} onChange={setTokenizer} testId="select-tokenizer"
              options={[{ value: "cl100k_base", label: "cl100k_base" }, { value: "p50k_base", label: "p50k_base" }, { value: "o200k_base", label: "o200k_base" }]} />
          </FormField>
        </div>
        <div className="mt-3">
          <FormField label={t("tasks.form.chunk_profile")} hint={t("tasks.form.profile_hint")}>
            <InputField value={profileName} onChange={setProfileName} placeholder="task-profile" testId="input-chunk-profile" />
          </FormField>
        </div>
      </div>
      <div className="border-t border-border pt-3 mt-1">
        <p className="text-xs font-medium text-muted-foreground mb-3">{t("tasks.form.kb_binding")}</p>
        <FormField label={t("tasks.form.bind_to_kb")} hint={t("tasks.form.bind_hint")}>
          <SelectField value={kbId} onChange={setKbId} testId="select-chunk-kb"
            options={[{ value: "", label: t("tasks.form.no_binding") }, ...kbs.map((kb) => ({ value: kb.kb_id, label: kb.name }))]} />
        </FormField>
      </div>
      <CheckboxField checked={overwriteSameProfile} onChange={setOverwriteSameProfile}
        label={t("tasks.form.overwrite_same_profile")} testId="checkbox-overwrite-profile" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim())}
        onClick={() => onSubmit({ type: "chunk_generation", name: "Chunk Generation", scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined, scan_count: parseInt(scanCount) || 50,
          scan_start_index: startIndex ? parseInt(startIndex) : undefined,
          chunk_size: parseInt(chunkSize) || 800, chunk_overlap: parseInt(chunkOverlap) || 100,
          splitter, tokenizer, profile_name: profileName || undefined,
          overwrite_same_profile: overwriteSameProfile, kb_id: kbId || undefined })} />
    </div>
  );
}

function RagIndexForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [kbId, setKbId] = useState("");
  const [kbs, setKbs] = useState<KBItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [forceReindex, setForceReindex] = useState(false);
  const [incremental, setIncremental] = useState(true);

  useEffect(() => {
    apiGet<{ knowledge_bases?: Array<Record<string, string>>; data?: { knowledge_bases?: Array<Record<string, string>> } }>("/api/rag/knowledge-bases")
      .then((res) => {
        const raw = res.data?.knowledge_bases || res.knowledge_bases || [];
        setKbs(raw.map((kb) => ({ kb_id: kb.kb_id || kb.id || "", name: kb.name || kb.kb_id || kb.id || "" })));
      }).catch(() => setKbs([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.rag_desc")}</p>
      <FormField label={t("tasks.form.knowledge_base")}>
        {loading ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" />{t("tasks.form.loading_kbs")}</div>
        ) : kbs.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground"><AlertCircle className="w-4 h-4" />{t("tasks.form.no_kbs")}</div>
        ) : (
          <SelectField value={kbId} onChange={setKbId} testId="select-kb"
            options={[{ value: "", label: t("tasks.form.select_kb") }, ...kbs.map((kb) => ({ value: kb.kb_id, label: kb.name }))]} />
        )}
      </FormField>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={incremental} onChange={(v) => { setIncremental(v); if (v) setForceReindex(false); }}
          label={t("tasks.form.incremental")} testId="checkbox-incremental" />
        <CheckboxField checked={forceReindex} onChange={(v) => { setForceReindex(v); if (v) setIncremental(false); }}
          label={t("tasks.form.force_reindex")} testId="checkbox-force-reindex" />
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !kbId}
        onClick={() => { if (!kbId) return;
          onSubmit({ type: "rag_indexing", name: `RAG Index: ${kbId}`, kb_id: kbId, force_reindex: forceReindex, incremental });
        }} />
    </div>
  );
}

export default function Tasks() {
  const { t } = useTranslation();
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [historyTasks, setHistoryTasks] = useState<Task[]>([]);
  const [sites, setSites] = useState<SiteConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [logModal, setLogModal] = useState<{ taskId: string; log: string } | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [activeForm, setActiveForm] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const [activeRes, historyRes] = await Promise.all([
        apiGet<{ tasks: Task[] }>("/api/tasks/active"),
        apiGet<{ tasks: Task[] }>("/api/tasks/history?limit=20"),
      ]);
      setActiveTasks(activeRes.tasks || []);
      setHistoryTasks(historyRes.tasks || []);
    } catch (e) { console.error("Failed to fetch tasks:", e); }
  }, []);

  const fetchSites = useCallback(async () => {
    try {
      const res = await apiGet<{ sites: SiteConfig[] }>("/api/config/sites");
      setSites(res.sites || []);
    } catch { setSites([]); }
  }, []);

  useEffect(() => {
    Promise.all([fetchTasks(), fetchSites()]).finally(() => setLoading(false));
    intervalRef.current = setInterval(fetchTasks, 5000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchTasks, fetchSites]);

  const stopTask = async (taskId: string) => {
    try { await apiPost(`/api/tasks/stop/${taskId}`); await fetchTasks(); }
    catch (e) { console.error("Failed to stop task:", e); }
  };

  const viewLog = async (taskId: string) => {
    setLogLoading(true);
    setLogModal({ taskId, log: "" });
    try {
      const res = await apiGet<{ log: string }>(`/api/tasks/log/${taskId}`);
      setLogModal({ taskId, log: res.log || t("tasks.form.no_log") });
    } catch { setLogModal({ taskId, log: t("tasks.form.log_error") }); }
    finally { setLogLoading(false); }
  };

  const handleSubmitTask = async (data: Record<string, unknown>) => {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      const res = await apiPost<{ success?: boolean; job_id?: string; error?: string }>("/api/collections/run", data);
      if (res.error) { setSubmitError(res.error); return; }
      setSubmitSuccess(res.job_id ? `${t("tasks.form.started")} (${res.job_id})` : t("tasks.form.started"));
      await fetchTasks();
      setTimeout(() => { setActiveForm(null); setSubmitSuccess(null); }, 2000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t("tasks.form.start_error");
      setSubmitError(msg);
    } finally { setSubmitting(false); }
  };

  const activeTaskType = taskTypes.find((tt) => tt.type === activeForm);

  function renderForm() {
    switch (activeForm) {
      case "scheduled": return <ScheduledForm sites={sites} onSubmit={handleSubmitTask} submitting={submitting} />;
      case "web_crawl": return <WebCrawlForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "adhoc_url": return <AdhocUrlForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "file_import": return <FileImportForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "web_search": return <WebSearchForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "catalog": return <CatalogForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "markdown": return <MarkdownForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "chunk": return <ChunkForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "rag_index": return <RagIndexForm onSubmit={handleSubmitTask} submitting={submitting} />;
      default: return null;
    }
  }

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">{t("tasks.title")}</h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">{t("tasks.subtitle")}</p>
      </motion.div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">{t("tasks.active")}</h2>
          <button onClick={fetchTasks} className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-refresh-tasks" title={t("tasks.refresh")}><RefreshCw className="w-4 h-4" /></button>
        </div>

        {loading ? (
          <div className="space-y-3">{[...Array(2)].map((_, i) => <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />)}</div>
        ) : activeTasks.length === 0 ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="text-center py-10 rounded-xl border border-dashed border-border bg-card" data-testid="text-no-active-tasks">
            <CheckCircle2 className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("tasks.no_active")}</p>
          </motion.div>
        ) : (
          <div className="space-y-3">
            {activeTasks.map((task, i) => (
              <motion.div key={task.id} custom={i} variants={fadeUp} initial="hidden" animate="visible"
                className="rounded-xl border border-border bg-card p-5" data-testid={`card-active-task-${task.id}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {statusBadge(task.status)}
                      <span className="font-semibold text-sm truncate">{task.name}</span>
                    </div>
                    {task.current_activity && (
                      <p className="text-xs text-muted-foreground mt-1 truncate" data-testid={`text-activity-${task.id}`}>{task.current_activity}</p>
                    )}
                  </div>
                  <button onClick={() => stopTask(task.id)}
                    className="shrink-0 p-2 rounded-lg bg-red-500/10 text-red-600 hover:bg-red-500/20 transition-colors"
                    data-testid={`button-stop-task-${task.id}`} title={t("tasks.stop")}><Square className="w-4 h-4" /></button>
                </div>
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>{task.items_processed}/{task.items_total || "?"}</span>
                    <span>{Math.round(task.progress)}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                    <motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }}
                      animate={{ width: `${Math.min(task.progress, 100)}%` }} transition={{ duration: 0.5 }} />
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">{t("tasks.started")}: {formatDate(task.started_at)}</p>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.new_task")}</h2>
        <AnimatePresence mode="wait">
          {activeForm ? (
            <motion.div key="form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }} className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
                <button onClick={() => { setActiveForm(null); setSubmitError(null); setSubmitSuccess(null); }}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors" data-testid="button-back-tasks">
                  <ArrowLeft className="w-4 h-4" /></button>
                {activeTaskType && (
                  <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", activeTaskType.color)}>
                    <activeTaskType.icon className="w-5 h-5" strokeWidth={1.8} /></div>
                )}
                <h3 className="font-semibold text-sm">{t(`tasks.type.${activeForm}`)}</h3>
              </div>
              <div className="p-5 space-y-0">
                {submitError && (
                  <div className="mb-4 px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs flex items-center gap-2" data-testid="text-submit-error">
                    <AlertCircle className="w-4 h-4 shrink-0" /><span className="flex-1">{submitError}</span>
                    <button onClick={() => setSubmitError(null)} className="shrink-0"><X className="w-3.5 h-3.5" /></button>
                  </div>
                )}
                {submitSuccess && (
                  <div className="mb-4 px-3 py-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2" data-testid="text-submit-success">
                    <CheckCircle2 className="w-4 h-4 shrink-0" /><span>{submitSuccess}</span></div>
                )}
                {renderForm()}
              </div>
            </motion.div>
          ) : (
            <motion.div key="grid" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {taskTypes.map(({ type, icon: Icon, color }, i) => (
                <motion.button key={type} custom={i} variants={fadeUp} initial="hidden" animate="visible"
                  onClick={() => { setActiveForm(type); setSubmitError(null); setSubmitSuccess(null); }}
                  className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border bg-card hover:border-primary/30 hover:shadow-md transition-all duration-300"
                  data-testid={`button-start-${type}`}>
                  <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", color)}>
                    <Icon className="w-5 h-5" strokeWidth={1.8} /></div>
                  <span className="text-xs font-medium text-center">{t(`tasks.type.${type}`)}</span>
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
        {!activeForm && sites.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="text-xs text-muted-foreground self-center">{t("tasks.configured_sites")}:</span>
            {sites.map((site) => (
              <span key={site.name} className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
                data-testid={`text-site-${site.name}`}>{site.name}</span>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.history")}</h2>
        {loading ? (
          <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />)}</div>
        ) : historyTasks.length === 0 ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="text-center py-10 rounded-xl border border-dashed border-border bg-card" data-testid="text-no-history">
            <Inbox className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("tasks.no_history")}</p>
          </motion.div>
        ) : (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="hidden sm:grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>{t("tasks.col.name")}</span><span>{t("tasks.col.type")}</span><span>{t("tasks.col.status")}</span>
              <span>{t("tasks.col.started")}</span><span>{t("tasks.col.items")}</span>
            </div>
            {historyTasks.map((task, i) => (
              <motion.div key={task.id} custom={i} variants={fadeUp} initial="hidden" animate="visible"
                className="grid sm:grid-cols-[1fr_100px_100px_120px_60px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
                onClick={() => viewLog(task.id)} data-testid={`row-history-task-${task.id}`}>
                <div className="flex items-center gap-2 min-w-0">
                  <ScrollText className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                  <span className="text-sm font-medium truncate">{task.name}</span>
                </div>
                <span className="text-xs text-muted-foreground hidden sm:flex items-center">{task.type}</span>
                <span className="hidden sm:flex items-center">{statusBadge(task.status)}</span>
                <span className="text-xs text-muted-foreground hidden sm:flex items-center">{formatDate(task.started_at)}</span>
                <span className="text-xs text-muted-foreground hidden sm:flex items-center">{task.items_processed}</span>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {logModal && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
            onClick={() => setLogModal(null)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="bg-card rounded-xl border border-border shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
              onClick={(e) => e.stopPropagation()} data-testid="modal-task-log">
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h3 className="font-semibold text-sm">{t("tasks.log_title")} — {logModal.taskId}</h3>
                <button onClick={() => setLogModal(null)} className="p-1.5 rounded-lg hover:bg-muted transition-colors" data-testid="button-close-log">
                  <X className="w-4 h-4" /></button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">
                {logLoading ? (
                  <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
                ) : (
                  <pre className="text-xs font-mono whitespace-pre-wrap text-muted-foreground leading-relaxed" data-testid="text-task-log">{logModal.log}</pre>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
