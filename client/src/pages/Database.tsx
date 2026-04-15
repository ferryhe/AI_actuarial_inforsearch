import { useEffect, useState, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { useLocation, useSearch } from "wouter";
import {
  Search,
  FileIcon,
  Inbox,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Filter,
  X,
  Trash2,
  Download,
  Eye,
  Square,
  CheckSquare,
  FileSpreadsheet,
  Loader2,
} from "lucide-react";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";
import { buildFileDetailPath, buildFilePreviewPath } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";

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
  const [selectedUrls, setSelectedUrls] = useState<string[]>([]);
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkDeleteProgress, setBulkDeleteProgress] = useState<{ current: number; total: number } | null>(null);

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
    setSelectedUrls((current) => current.filter((url) => files.some((file) => file.url === url && !file.deleted_at)));
  }, [files]);


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

  function navigateToFile(file: FileItem) {
    databaseScrollCache.set(locationKey, window.scrollY);
    navigate(buildFileDetailPath(file.url, locationKey));
  }

  function navigateToPreview(file: FileItem) {
    databaseScrollCache.set(locationKey, window.scrollY);
    navigate(buildFilePreviewPath(file.url, locationKey));
  }

  function toggleSelected(url: string) {
    setSelectedUrls((current) => (current.includes(url) ? current.filter((item) => item !== url) : [...current, url]));
  }

  function toggleSelectAllVisible() {
    const visibleUrls = files.filter((file) => !file.deleted_at).map((file) => file.url);
    if (visibleUrls.length === 0) return;
    setSelectedUrls((current) => {
      const allSelected = visibleUrls.every((url) => current.includes(url));
      if (allSelected) {
        return current.filter((url) => !visibleUrls.includes(url));
      }
      return Array.from(new Set([...current, ...visibleUrls]));
    });
  }

  function downloadFile(file: FileItem) {
    const a = document.createElement("a");
    a.href = `/api/download?url=${encodeURIComponent(file.url)}`;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function exportCsv() {
    const a = document.createElement("a");
    a.href = "/api/export?format=csv";
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function refreshCurrentPage() {
    await fetchFiles({ forceNetwork: true });
  }

  async function confirmBulkDelete() {
    if (selectedUrls.length === 0) {
      setShowBulkDeleteModal(false);
      return;
    }
    setBulkDeleting(true);
    setBulkDeleteProgress({ current: 0, total: selectedUrls.length });
    try {
      for (let i = 0; i < selectedUrls.length; i += 1) {
        const url = selectedUrls[i];
        await apiPost("/api/files/delete", { url, confirm: "DELETE" });
        setBulkDeleteProgress({ current: i + 1, total: selectedUrls.length });
      }
      setSelectedUrls([]);
      setShowBulkDeleteModal(false);
      await refreshCurrentPage();
    } finally {
      setBulkDeleting(false);
      setBulkDeleteProgress(null);
    }
  }

  const activeFilterCount = [source, category, includeDeleted ? "y" : ""].filter(Boolean).length;
  const selectableVisibleUrls = files.filter((file) => !file.deleted_at).map((file) => file.url);
  const allVisibleSelected = selectableVisibleUrls.length > 0 && selectableVisibleUrls.every((url) => selectedUrls.includes(url));

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
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <button
            onClick={exportCsv}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-foreground hover:bg-muted transition-colors"
            data-testid="button-export-csv"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            {t("db.export_csv")}
          </button>
          <span className="shrink-0 rounded-full border border-primary/20 bg-primary/5 px-3 py-2 text-xs font-medium text-primary">
            {t("db.fastapi_file_actions")}
          </span>
        </div>
      </motion.div>

      {(files.length > 0 || selectedUrls.length > 0) && (
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={toggleSelectAllVisible}
            className="inline-flex items-center gap-2 text-sm font-medium text-foreground hover:text-primary transition-colors"
            data-testid="button-select-all-visible"
          >
            {allVisibleSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
            {t("db.select_all")}
          </button>
          <div className="flex items-center gap-2 sm:justify-end">
            <span className="text-sm text-muted-foreground" data-testid="text-selected-count">
              {selectedUrls.length} {t("db.selected_count")}
            </span>
            <button
              type="button"
              onClick={() => setShowBulkDeleteModal(true)}
              disabled={selectedUrls.length === 0 || bulkDeleting}
              className="inline-flex items-center gap-2 rounded-lg bg-destructive px-3 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              data-testid="button-bulk-delete"
            >
              {bulkDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              {t("db.bulk_delete")}
            </button>
          </div>
        </div>
      )}

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
          <div className="hidden lg:grid grid-cols-[36px_1fr_110px_120px_50px_70px_90px_140px] gap-3 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            <button
              type="button"
              onClick={toggleSelectAllVisible}
              className="flex items-center justify-center hover:text-foreground transition-colors"
              data-testid="checkbox-select-all-header"
            >
              {allVisibleSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4 opacity-70" />}
            </button>
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
            const hasMd = !!file.markdown_content || !!file.markdown_source;
            const isDeleted = !!file.deleted_at;
            const isSelected = selectedUrls.includes(file.url);

            return (
              <motion.div
                key={file.url}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className={cn(
                  "grid lg:grid-cols-[36px_1fr_110px_120px_50px_70px_90px_140px] gap-1 lg:gap-3 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer",
                  isDeleted && "opacity-50"
                )}
                onClick={() => navigateToFile(file)}
                data-testid={`file-row-${i}`}
              >
                <div className="hidden lg:flex items-center justify-center">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isDeleted) return;
                      toggleSelected(file.url);
                    }}
                    disabled={isDeleted}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
                    data-testid={`checkbox-select-${i}`}
                  >
                    {isSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                  </button>
                </div>

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

                <div className="hidden lg:flex items-center gap-1.5 justify-end">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigateToPreview(file);
                    }}
                    className="inline-flex items-center justify-center rounded-md border border-border p-2 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    data-testid={`button-preview-${i}`}
                    title={t("db.preview")}
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      downloadFile(file);
                    }}
                    className="inline-flex items-center justify-center rounded-md border border-border p-2 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    data-testid={`button-download-${i}`}
                    title={t("db.download")}
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex items-center gap-2 sm:hidden mt-1">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isDeleted) return;
                      toggleSelected(file.url);
                    }}
                    disabled={isDeleted}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
                    data-testid={`checkbox-select-mobile-${i}`}
                  >
                    {isSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                  </button>
                  <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", contentTypeBadgeColor(file.content_type))}>
                    {contentTypeLabel(file.content_type)}
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDate(file.last_seen)}</span>
                  <span className="text-xs text-muted-foreground">{formatSize(file.bytes)}</span>
                </div>
                <div className="flex items-center gap-2 sm:hidden mt-2 pl-6">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigateToPreview(file);
                    }}
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    data-testid={`button-preview-mobile-${i}`}
                  >
                    <Eye className="w-3.5 h-3.5" />
                    {t("db.preview")}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      downloadFile(file);
                    }}
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    data-testid={`button-download-mobile-${i}`}
                  >
                    <Download className="w-3.5 h-3.5" />
                    {t("db.download")}
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

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

      <ConfirmDeleteModal
        open={showBulkDeleteModal}
        onClose={() => {
          if (!bulkDeleting) {
            setShowBulkDeleteModal(false);
            setBulkDeleteProgress(null);
          }
        }}
        onConfirm={confirmBulkDelete}
        loading={bulkDeleting}
        message={bulkDeleteProgress
          ? t("db.bulk_delete_progress")
              .replace("{current}", String(bulkDeleteProgress.current))
              .replace("{total}", String(bulkDeleteProgress.total))
          : t("common.confirm_delete_msg")}
      />
    </div>
  );
}
