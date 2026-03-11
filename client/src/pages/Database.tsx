import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation, useSearch } from "wouter";
import {
  Search,
  Download,
  FileIcon,
  Inbox,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Filter,
  X,
  Eye,
  Trash2,
  Loader2,
  AlertCircle,
  FileDown,
} from "lucide-react";
import { buildFileDetailPath, buildFilePreviewPath } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";

interface FileItem {
  url: string;
  title: string;
  original_filename: string;
  source_site: string;
  content_type: string;
  last_seen: string;
  category: string | null;
  summary: string | null;
  markdown_content: string | null;
  markdown_source: string | null;
  bytes: number | null;
  deleted_at: string | null;
}

interface FilesResponse {
  files: FileItem[];
  total: number;
  limit: number;
  offset: number;
}

interface CategoryOption {
  name: string;
  count?: number | null;
}

const PAGE_SIZE = 20;

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.3, ease: "easeOut" as const },
  }),
};

function contentTypeLabel(ct: string): string {
  if (!ct) return "-";
  if (ct.includes("pdf")) return "PDF";
  if (ct.includes("word") || ct.includes("document")) return "DOCX";
  if (ct.includes("presentation") || ct.includes("powerpoint")) return "PPTX";
  if (ct.includes("spreadsheet") || ct.includes("excel")) return "XLSX";
  if (ct.includes("html")) return "HTML";
  return ct.split("/").pop()?.toUpperCase() || ct;
}

function contentTypeBadgeColor(ct: string): string {
  if (!ct) return "bg-gray-500/10 text-gray-600 dark:text-gray-400";
  if (ct.includes("pdf")) return "bg-red-500/10 text-red-600 dark:text-red-400";
  if (ct.includes("word") || ct.includes("document")) return "bg-blue-500/10 text-blue-600 dark:text-blue-400";
  if (ct.includes("presentation") || ct.includes("powerpoint")) return "bg-orange-500/10 text-orange-600 dark:text-orange-400";
  if (ct.includes("spreadsheet") || ct.includes("excel")) return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
  if (ct.includes("html")) return "bg-violet-500/10 text-violet-600 dark:text-violet-400";
  return "bg-gray-500/10 text-gray-600 dark:text-gray-400";
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return dateStr;
  }
}

function formatSize(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

type SortField = "title" | "source_site" | "content_type" | "last_seen" | "bytes";
type SortDir = "asc" | "desc";

interface DatabaseQueryState {
  offset: number;
  query: string;
  source: string;
  category: string;
  includeDeleted: boolean;
  orderBy: SortField;
  orderDir: SortDir;
}

interface CachedFilesEntry {
  data: FilesResponse;
  timestamp: number;
}

interface CachedMetaEntry {
  sources: string[];
  categories: CategoryOption[];
  timestamp: number;
}

const FILES_CACHE_TTL_MS = 2 * 60 * 1000;
const META_CACHE_TTL_MS = 5 * 60 * 1000;
const MAX_FILES_CACHE_ENTRIES = 100;
const MAX_SCROLL_CACHE_ENTRIES = 200;

function isFresh(timestamp: number, ttlMs: number): boolean {
  return Date.now() - timestamp < ttlMs;
}

class FilesCache {
  private map = new Map<string, CachedFilesEntry>();

  get(key: string): CachedFilesEntry | undefined {
    const entry = this.map.get(key);
    if (!entry) return undefined;
    if (!isFresh(entry.timestamp, FILES_CACHE_TTL_MS)) {
      this.map.delete(key);
      return undefined;
    }
    return entry;
  }

  set(key: string, value: CachedFilesEntry): void {
    this.pruneStale();
    this.map.set(key, value);
    this.enforceSizeLimit();
  }

  delete(key: string): void {
    this.map.delete(key);
  }

  clear(): void {
    this.map.clear();
  }

  private pruneStale(): void {
    const now = Date.now();
    for (const [k, entry] of this.map) {
      if (now - entry.timestamp >= FILES_CACHE_TTL_MS) {
        this.map.delete(k);
      }
    }
  }

  private enforceSizeLimit(): void {
    while (this.map.size > MAX_FILES_CACHE_ENTRIES) {
      const oldest = this.map.keys().next().value;
      if (oldest === undefined) break;
      this.map.delete(oldest);
    }
  }
}

class ScrollCache {
  private map = new Map<string, number>();

  get(key: string): number | undefined {
    return this.map.get(key);
  }

  set(key: string, value: number): void {
    this.map.set(key, value);
    this.enforceSizeLimit();
  }

  private enforceSizeLimit(): void {
    while (this.map.size > MAX_SCROLL_CACHE_ENTRIES) {
      const oldest = this.map.keys().next().value;
      if (oldest === undefined) break;
      this.map.delete(oldest);
    }
  }
}

const fileListCache = new FilesCache();
let databaseMetaCache: CachedMetaEntry | null = null;
const databaseScrollCache = new ScrollCache();

function buildFilesParams(state: DatabaseQueryState): URLSearchParams {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(state.offset),
    order_by: state.orderBy,
    order_dir: state.orderDir,
  });
  if (state.query) params.set("query", state.query);
  if (state.source) params.set("source", state.source);
  if (state.category) params.set("category", state.category);
  if (state.includeDeleted) params.set("include_deleted", "true");
  return params;
}

function buildDatabaseLocation(state: DatabaseQueryState): string {
  const page = Math.floor(state.offset / PAGE_SIZE) + 1;
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("order_by", state.orderBy);
  params.set("order_dir", state.orderDir);
  if (state.query) params.set("query", state.query);
  if (state.source) params.set("source", state.source);
  if (state.category) params.set("category", state.category);
  if (state.includeDeleted) params.set("include_deleted", "true");
  return `/database?${params.toString()}`;
}

function getCachedFiles(key: string): FilesResponse | null {
  const entry = fileListCache.get(key);
  return entry ? entry.data : null;
}

function setCachedFiles(key: string, data: FilesResponse): void {
  fileListCache.set(key, { data, timestamp: Date.now() });
}

function getCachedMeta(): CachedMetaEntry | null {
  if (!databaseMetaCache) return null;
  if (!isFresh(databaseMetaCache.timestamp, META_CACHE_TTL_MS)) {
    return null;
  }
  return databaseMetaCache;
}

function setCachedMeta(sources: string[], categories: CategoryOption[]): void {
  databaseMetaCache = {
    sources,
    categories,
    timestamp: Date.now(),
  };
}

function normalizeCategories(items: Array<string | CategoryOption> | undefined): CategoryOption[] {
  return (items || [])
    .map((item) => {
      if (typeof item === "string") {
        const name = item.trim();
        return name ? { name } : null;
      }
      if (item && typeof item.name === "string" && item.name.trim()) {
        return {
          name: item.name.trim(),
          count: typeof item.count === "number" ? item.count : null,
        };
      }
      return null;
    })
    .filter((item): item is CategoryOption => item !== null);
}

export default function DatabasePage() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const searchStr = useSearch();
  const { user } = useAuth();
  const canExport = user?.role === "admin" || user?.role === "operator";

  // Parse initial state from URL on first render
  const initialParams = new URLSearchParams(searchStr);
  const VALID_SORT_FIELDS: SortField[] = ["title", "source_site", "content_type", "last_seen", "bytes"];
  const rawOrderBy = initialParams.get("order_by") || "";
  const rawOrderDir = initialParams.get("order_dir") || "";
  const initialOffset = (() => {
    const page = Math.max(1, parseInt(initialParams.get("page") || "1", 10));
    return (page - 1) * PAGE_SIZE;
  })();
  const initialQuery = initialParams.get("query") || "";
  const initialSource = initialParams.get("source") || "";
  const initialCategory = initialParams.get("category") || "";
  const initialIncludeDeleted = initialParams.get("include_deleted") === "true";
  const initialOrderBy =
    VALID_SORT_FIELDS.includes(rawOrderBy as SortField) ? (rawOrderBy as SortField) : "last_seen";
  const initialOrderDir: SortDir = rawOrderDir === "asc" ? "asc" : "desc";
  const initialRequestKey = buildFilesParams({
    offset: initialOffset,
    query: initialQuery,
    source: initialSource,
    category: initialCategory,
    includeDeleted: initialIncludeDeleted,
    orderBy: initialOrderBy,
    orderDir: initialOrderDir,
  }).toString();
  const initialCachedFiles = getCachedFiles(initialRequestKey);
  const initialCachedMeta = getCachedMeta();

  const [files, setFiles] = useState<FileItem[]>(initialCachedFiles?.files || []);
  const [total, setTotal] = useState(initialCachedFiles?.total ?? 0);
  const [loading, setLoading] = useState(!initialCachedFiles);
  const [offset, setOffset] = useState(initialOffset);

  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [source, setSource] = useState(initialSource);
  const [category, setCategory] = useState(initialCategory);
  const [includeDeleted, setIncludeDeleted] = useState(initialIncludeDeleted);
  const [orderBy, setOrderBy] = useState<SortField>(initialOrderBy);
  const [orderDir, setOrderDir] = useState<SortDir>(initialOrderDir);

  // Track whether state was initialized from URL (avoid double-reset of offset)
  const initializedRef = useRef(false);
  const fetchSeqRef = useRef(0);
  const scrollRestoreAttemptedRef = useRef(false);

  const [sources, setSources] = useState<string[]>(initialCachedMeta?.sources || []);
  const [categories, setCategories] = useState<CategoryOption[]>(initialCachedMeta?.categories || []);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [showBulkDelete, setShowBulkDelete] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkProgress, setBulkProgress] = useState({ current: 0, total: 0 });
  const [bulkError, setBulkError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    // Only reset offset to 0 when filters change, not on initial render
    if (!initializedRef.current) {
      initializedRef.current = true;
      return;
    }
    setOffset(0);
  }, [debouncedQuery, source, category, includeDeleted, orderBy, orderDir]);

  const requestState: DatabaseQueryState = {
    offset,
    query: debouncedQuery,
    source,
    category,
    includeDeleted,
    orderBy,
    orderDir,
  };
  const requestKey = buildFilesParams(requestState).toString();
  const locationKey = buildDatabaseLocation(requestState);

  // Persist current state to URL so back-navigation restores filters/page
  useEffect(() => {
    window.history.replaceState(null, "", locationKey);
  }, [locationKey]);

  useEffect(() => {
    const cachedMeta = getCachedMeta();
    if (cachedMeta) {
      setSources(cachedMeta.sources);
      setCategories(cachedMeta.categories);
      return;
    }

    let cancelled = false;
    Promise.allSettled([
      apiGet<{ sources: string[] }>("/api/sources"),
      apiGet<{ categories: Array<string | CategoryOption> }>("/api/categories?mode=used"),
    ])
      .then(([sourcesResult, categoriesResult]) => {
        if (cancelled) return;
        const nextSources =
          sourcesResult.status === "fulfilled" ? sourcesResult.value.sources || [] : [];
        const nextCategories =
          categoriesResult.status === "fulfilled"
            ? normalizeCategories(categoriesResult.value.categories)
            : [];
        setSources(nextSources);
        setCategories(nextCategories);
        setCachedMeta(nextSources, nextCategories);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  const fetchFiles = useCallback(
    async ({ targetOffset = offset, forceNetwork = false }: { targetOffset?: number; forceNetwork?: boolean } = {}) => {
      const targetState: DatabaseQueryState = {
        offset: targetOffset,
        query: debouncedQuery,
        source,
        category,
        includeDeleted,
        orderBy,
        orderDir,
      };
      const targetKey = buildFilesParams(targetState).toString();
      const cached = forceNetwork ? null : getCachedFiles(targetKey);
      const isCurrentRequest = targetOffset === offset;

      if (isCurrentRequest) {
        if (cached) {
          setFiles(cached.files || []);
          setTotal(cached.total ?? 0);
          setLoading(false);
        } else {
          setLoading(true);
        }
      } else if (cached) {
        return cached;
      }

      const requestId = isCurrentRequest ? ++fetchSeqRef.current : fetchSeqRef.current;

      try {
        const data = await apiGet<FilesResponse>(`/api/files?${targetKey}`);
        setCachedFiles(targetKey, data);

        if (isCurrentRequest && requestId === fetchSeqRef.current) {
          setFiles(data.files || []);
          setTotal(data.total ?? 0);
        }

        return data;
      } catch {
        if (isCurrentRequest && requestId === fetchSeqRef.current && !cached) {
          setFiles([]);
          setTotal(0);
        }
        return null;
      } finally {
        if (isCurrentRequest && requestId === fetchSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [offset, debouncedQuery, source, category, includeDeleted, orderBy, orderDir]
  );

  useEffect(() => {
    void fetchFiles();
  }, [fetchFiles, requestKey]);

  useEffect(() => {
    if (loading || total <= 0) return;
    const prevOffset = offset - PAGE_SIZE;
    const nextOffset = offset + PAGE_SIZE;
    if (prevOffset >= 0) {
      void fetchFiles({ targetOffset: prevOffset });
    }
    if (nextOffset < total) {
      void fetchFiles({ targetOffset: nextOffset });
    }
  }, [fetchFiles, loading, offset, total]);

  useEffect(() => {
    return () => {
      databaseScrollCache.set(locationKey, window.scrollY);
    };
  }, [locationKey]);

  useEffect(() => {
    if (loading || scrollRestoreAttemptedRef.current) return;
    scrollRestoreAttemptedRef.current = true;
    const savedY = databaseScrollCache.get(locationKey);
    if (savedY == null) return;
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: savedY, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [loading, locationKey]);

  useEffect(() => {
    setSelectedUrls(new Set());
  }, [requestKey]);

  const toggleSelect = (url: string) => {
    setSelectedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedUrls.size === files.length) {
      setSelectedUrls(new Set());
    } else {
      setSelectedUrls(new Set(files.map((f) => f.url)));
    }
  };

  const handleBulkDelete = async () => {
    const urls = Array.from(selectedUrls);
    setBulkDeleting(true);
    setBulkProgress({ current: 0, total: urls.length });
    setBulkError(null);
    try {
      for (let i = 0; i < urls.length; i++) {
        setBulkProgress({ current: i + 1, total: urls.length });
        const res = await apiPost<{ success?: boolean; error?: string }>("/api/files/delete", { url: urls[i], confirm: "DELETE" });
        if (res.error) {
          if (res.error.toLowerCase().includes("disabled") || res.error.toLowerCase().includes("not enabled")) {
            setBulkError(t("db.deletion_disabled"));
            break;
          }
        }
      }
    } catch (err: unknown) {
      const msg = String((err as { message?: string })?.message || "");
      if (msg.includes("403") || msg.toLowerCase().includes("disabled") || msg.toLowerCase().includes("forbidden")) {
        setBulkError(t("db.deletion_disabled"));
      } else {
        setBulkError(msg);
      }
    } finally {
      setBulkDeleting(false);
      setShowBulkDelete(false);
      setSelectedUrls(new Set());
      fileListCache.clear();
      void fetchFiles({ forceNetwork: true });
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  function handleSort(field: SortField) {
    if (orderBy === field) {
      setOrderDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setOrderBy(field);
      setOrderDir("desc");
    }
  }

  function SortIcon({ field }: { field: SortField }) {
    if (orderBy !== field) return <ArrowUpDown className="w-3 h-3 opacity-40" />;
    return orderDir === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />;
  }

  function handleDownload(file: FileItem) {
    window.open(`/api/download?url=${encodeURIComponent(file.url)}`, "_blank");
  }

  function handleExport(format: "csv" | "json" = "csv") {
    window.open(`/api/export?format=${format}`, "_blank");
  }

  function navigateToFile(file: FileItem) {
    databaseScrollCache.set(locationKey, window.scrollY);
    navigate(buildFileDetailPath(file.url, locationKey));
  }

  function navigateToPreview(file: FileItem) {
    databaseScrollCache.set(locationKey, window.scrollY);
    navigate(buildFilePreviewPath(file.url, locationKey));
  }

  const activeFilterCount = [source, category, includeDeleted ? "y" : ""].filter(Boolean).length;

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">
            {t("db.title")}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">{t("db.subtitle")}</p>
        </div>
        {canExport && (
          <button
            onClick={() => handleExport("csv")}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-card text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
            title={t("db.export_csv")}
            data-testid="button-export-csv"
          >
            <FileDown className="w-4 h-4" />
            <span className="hidden sm:inline">{t("db.export_csv")}</span>
          </button>
        )}
      </motion.div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("db.search_placeholder")}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 transition-shadow"
            data-testid="input-search"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-muted"
              data-testid="button-clear-search"
            >
              <X className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          )}
        </div>

        <button
          onClick={() => setFiltersOpen(!filtersOpen)}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors",
            filtersOpen || activeFilterCount > 0
              ? "border-primary/40 bg-primary/5 text-primary"
              : "border-border bg-card text-muted-foreground hover:text-foreground"
          )}
          data-testid="button-toggle-filters"
        >
          <Filter className="w-4 h-4" />
          {t("db.filters")}
          {activeFilterCount > 0 && (
            <span className="ml-1 w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {filtersOpen && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="flex flex-col sm:flex-row gap-3 flex-wrap"
        >
          <div className="flex-1 min-w-[160px]">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("db.source")}</label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="select-source"
            >
              <option value="">{t("db.all_sources")}</option>
              {sources.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("db.category")}</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="select-category"
            >
              <option value="">{t("db.all_categories")}</option>
              <option value="__uncategorized__">{t("db.uncategorized")}</option>
              {categories.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.count != null ? `${c.name} (${c.count})` : c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("db.sort_by")}</label>
            <select
              value={`${orderBy}:${orderDir}`}
              onChange={(e) => {
                const [f, d] = e.target.value.split(":") as [SortField, SortDir];
                setOrderBy(f);
                setOrderDir(d);
              }}
              className="w-full px-3 py-2 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="select-sort"
            >
              <option value="last_seen:desc">{t("db.sort_date_newest")}</option>
              <option value="last_seen:asc">{t("db.sort_date_oldest")}</option>
              <option value="title:asc">{t("db.sort_title_az")}</option>
              <option value="source_site:asc">{t("db.sort_source_az")}</option>
              <option value="bytes:desc">{t("db.sort_size_largest")}</option>
            </select>
          </div>
          <div className="flex items-end gap-3">
            <label className="flex items-center gap-2 cursor-pointer px-3 py-2 rounded-lg border border-border bg-card text-sm" data-testid="checkbox-include-deleted">
              <input
                type="checkbox"
                checked={includeDeleted}
                onChange={(e) => setIncludeDeleted(e.target.checked)}
                className="rounded border-border"
              />
              <Trash2 className="w-3.5 h-3.5 text-muted-foreground" />
              {t("db.include_deleted")}
            </label>
            {activeFilterCount > 0 && (
              <button
                onClick={() => { setSource(""); setCategory(""); setIncludeDeleted(false); }}
                className="px-3 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                data-testid="button-clear-filters"
              >
                {t("db.clear_filters")}
              </button>
            )}
          </div>
        </motion.div>
      )}

      <div className="text-xs text-muted-foreground">
        {t("db.showing")} {total > 0 ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, total)} {t("db.of")} {total} {t("db.files")}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : files.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16 rounded-xl border border-dashed border-border bg-card"
          data-testid="empty-state"
        >
          <Inbox className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
          <p className="font-medium text-muted-foreground">{t("db.no_files")}</p>
          <p className="text-xs text-muted-foreground/70 mt-1">{t("db.no_files_desc")}</p>
        </motion.div>
      ) : (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="hidden lg:grid grid-cols-[28px_36px_1fr_110px_120px_50px_70px_90px_68px] gap-3 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            <span className="flex items-center">
              <input type="checkbox" checked={selectedUrls.size === files.length && files.length > 0}
                onChange={toggleSelectAll} className="rounded border-border cursor-pointer"
                data-testid="checkbox-select-all" title={t("db.select_all")} />
            </span>
            <span>#</span>
            <button onClick={() => handleSort("title")} className="flex items-center gap-1 hover:text-foreground transition-colors text-left" data-testid="sort-title">
              {t("table.title")} <SortIcon field="title" />
            </button>
            <button onClick={() => handleSort("source_site")} className="flex items-center gap-1 hover:text-foreground transition-colors text-left" data-testid="sort-source_site">
              {t("table.source")} <SortIcon field="source_site" />
            </button>
            <span>{t("table.category")}</span>
            <span>{t("table.md")}</span>
            <button onClick={() => handleSort("bytes")} className="flex items-center gap-1 hover:text-foreground transition-colors text-left" data-testid="sort-bytes">
              {t("table.size")} <SortIcon field="bytes" />
            </button>
            <button onClick={() => handleSort("last_seen")} className="flex items-center gap-1 hover:text-foreground transition-colors text-left" data-testid="sort-last_seen">
              {t("table.date")} <SortIcon field="last_seen" />
            </button>
            <span>{t("table.actions")}</span>
          </div>

          {files.map((file, i) => {
            const rowNum = offset + i + 1;
            const hasMd = !!file.markdown_content || !!file.markdown_source;
            const isDeleted = !!file.deleted_at;

            return (
              <motion.div
                key={file.url}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className={cn(
                  "grid lg:grid-cols-[28px_36px_1fr_110px_120px_50px_70px_90px_68px] gap-1 lg:gap-3 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer",
                  isDeleted && "opacity-50",
                  selectedUrls.has(file.url) && "bg-primary/5"
                )}
                onClick={() => navigateToFile(file)}
                data-testid={`file-row-${i}`}
              >
                <span className="hidden lg:flex items-center" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={selectedUrls.has(file.url)}
                    onChange={() => toggleSelect(file.url)} className="rounded border-border cursor-pointer"
                    data-testid={`checkbox-select-${i}`} />
                </span>
                <span className="hidden lg:flex items-center text-xs text-muted-foreground/60 tabular-nums" data-testid={`text-rownum-${i}`}>
                  {rowNum}
                </span>

                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileIcon className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                    <span className="text-sm font-medium truncate" data-testid={`text-title-${i}`}>
                      {file.title || file.original_filename || "Untitled"}
                    </span>
                    {file.content_type && (
                      <span className={cn("hidden sm:inline-block lg:hidden text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0", contentTypeBadgeColor(file.content_type))}>
                        {contentTypeLabel(file.content_type)}
                      </span>
                    )}
                    {isDeleted && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-500/10 text-red-600 dark:text-red-400 shrink-0">
                        {t("db.deleted_label")}
                      </span>
                    )}
                  </div>
                  {file.original_filename && file.original_filename !== file.title && (
                    <p className="text-xs text-muted-foreground/50 mt-0.5 truncate pl-6" data-testid={`text-filename-${i}`}>
                      {file.original_filename}
                    </p>
                  )}
                  {file.summary && (
                    <p className="text-xs text-muted-foreground/70 mt-0.5 truncate pl-6" data-testid={`text-summary-${i}`}>
                      {file.summary.length > 120 ? file.summary.slice(0, 120) + "…" : file.summary}
                    </p>
                  )}
                </div>

                <span className="text-xs text-muted-foreground truncate hidden lg:flex items-center" data-testid={`text-source-${i}`}>
                  {file.source_site || "-"}
                </span>

                <span className="text-xs text-muted-foreground truncate hidden lg:flex items-center" data-testid={`text-category-${i}`}>
                  {file.category || "-"}
                </span>

                <span className="hidden lg:flex items-center" data-testid={`text-md-${i}`}>
                  {hasMd ? (
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">Y</span>
                  ) : (
                    <span className="text-xs text-muted-foreground/40">-</span>
                  )}
                </span>

                <span className="text-xs text-muted-foreground tabular-nums hidden lg:flex items-center" data-testid={`text-size-${i}`}>
                  {formatSize(file.bytes)}
                </span>

                <span className="text-xs text-muted-foreground hidden lg:flex items-center" data-testid={`text-date-${i}`}>
                  {formatDate(file.last_seen)}
                </span>

                <div className="hidden lg:flex items-center gap-0.5">
                  <button
                    onClick={(e) => { e.stopPropagation(); navigateToPreview(file); }}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title={t("db.preview")}
                    data-testid={`button-preview-${i}`}
                  >
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title={t("db.download")}
                    data-testid={`button-download-${i}`}
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="flex items-center gap-2 sm:hidden mt-1">
                  <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", contentTypeBadgeColor(file.content_type))}>
                    {contentTypeLabel(file.content_type)}
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDate(file.last_seen)}</span>
                  <span className="text-xs text-muted-foreground">{formatSize(file.bytes)}</span>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      <AnimatePresence>
        {selectedUrls.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-5 py-3 rounded-xl bg-card border border-border shadow-xl"
            data-testid="bar-bulk-actions"
          >
            <span className="text-sm font-medium" data-testid="text-selected-count">
              {selectedUrls.size} {t("db.selected_count")}
            </span>
            <button
              onClick={() => setShowBulkDelete(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-colors"
              data-testid="button-bulk-delete"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {t("db.bulk_delete")}
            </button>
            <button
              onClick={() => setSelectedUrls(new Set())}
              className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground"
              data-testid="button-clear-selection"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {bulkError && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="flex items-center gap-2 px-4 py-3 rounded-xl border border-amber-500/30 bg-amber-500/5 text-sm text-amber-700 dark:text-amber-300"
          data-testid="text-bulk-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{bulkError}</span>
          <button onClick={() => setBulkError(null)} className="p-1 rounded hover:bg-muted"><X className="w-3.5 h-3.5" /></button>
        </motion.div>
      )}

      <ConfirmDeleteModal
        open={showBulkDelete}
        onClose={() => setShowBulkDelete(false)}
        onConfirm={handleBulkDelete}
        title={`${t("db.bulk_delete")} (${selectedUrls.size})`}
        message={bulkDeleting
          ? t("db.bulk_delete_progress").replace("{current}", String(bulkProgress.current)).replace("{total}", String(bulkProgress.total))
          : t("common.confirm_delete_msg")}
        loading={bulkDeleting}
      />

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0}
            className="flex items-center gap-1 px-3 py-2 rounded-lg border border-border bg-card text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted transition-colors"
            data-testid="button-prev-page"
          >
            <ChevronLeft className="w-4 h-4" />
            {t("db.prev")}
          </button>

          <span className="text-sm text-muted-foreground" data-testid="text-page-info">
            {t("db.page")} {currentPage} / {totalPages}
          </span>

          <button
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={offset + PAGE_SIZE >= total}
            className="flex items-center gap-1 px-3 py-2 rounded-lg border border-border bg-card text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted transition-colors"
            data-testid="button-next-page"
          >
            {t("db.next")}
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
