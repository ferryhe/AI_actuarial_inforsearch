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
  Sparkles,
  Square,
  CheckSquare,
  FileSpreadsheet,
  Loader2,
} from "lucide-react";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";
import { buildFileDetailPath, buildFilePreviewPath } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { apiGet, apiPost } from "@/lib/api";
import { categoryDisplayName } from "@/lib/category-labels";
import {
  buildDatabaseLocation,
  buildFilesParams,
  DATABASE_PAGE_SIZE,
  parseDatabaseQueryState,
  type DatabaseQueryState,
  type SortDir,
  type SortField,
} from "@/lib/database-query";
import { formatWeeklyDateTime } from "@/lib/weekly-dashboard";
import { getCanonicalDisplayName, getChatValidName } from "./chat/displayName";

interface FileItem {
  url: string;
  title: string;
  original_filename: string;
  source_site: string;
  content_type: string;
  first_seen: string;
  last_seen: string;
  category: string | null;
  summary: string | null;
  has_markdown: boolean;
  markdown_source: string | null;
  bytes: number | null;
  deleted_at: string | null;
}

interface ExplainDocumentState {
  explainDocument: {
    file_url: string;
    filename: string;
    title: string;
    category: string;
    keywords: string[];
  };
}

interface FilesResponse {
  files: FileItem[];
  total: number;
  limit: number;
  offset: number;
}

interface CategoryOption {
  name: string;
  label?: string;
  labels?: { en?: string; zh?: string };
  count?: number | null;
}

const PAGE_SIZE = DATABASE_PAGE_SIZE;

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

function formatDate(dateStr: string, lang: string): string {
  if (!dateStr) return "-";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

function formatSize(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
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
    .map<CategoryOption | null>((item) => {
      if (typeof item === "string") {
        const name = item.trim();
        return name ? { name } : null;
      }
      if (item && typeof item.name === "string" && item.name.trim()) {
        return {
          name: item.name.trim(),
          label: typeof item.label === "string" ? item.label : undefined,
          labels: item.labels,
          count: typeof item.count === "number" ? item.count : null,
        };
      }
      return null;
    })
    .filter((item): item is CategoryOption => item !== null);
}

export default function DatabasePage() {
  const { t, lang } = useTranslation();
  const { permissions, isLoading: authLoading } = useAuth();
  const canDeleteFiles = permissions.includes("files.delete");
  const canDownloadFiles = permissions.includes("files.download");
  const canExportFiles = permissions.includes("export.read");
  const [, navigate] = useLocation();
  const searchStr = useSearch();

  const initialStateRef = useRef<DatabaseQueryState | null>(null);
  if (initialStateRef.current === null) {
    initialStateRef.current = parseDatabaseQueryState(searchStr);
  }
  const initialState = initialStateRef.current;
  const initialRequestKey = buildFilesParams(initialState).toString();
  const initialCachedFiles = getCachedFiles(initialRequestKey);
  const initialCachedMeta = getCachedMeta();

  const [files, setFiles] = useState<FileItem[]>(initialCachedFiles?.files || []);
  const [total, setTotal] = useState(initialCachedFiles?.total ?? 0);
  const [loading, setLoading] = useState(!initialCachedFiles);
  const [offset, setOffset] = useState(initialState.offset);

  const [query, setQuery] = useState(initialState.query);
  const [debouncedQuery, setDebouncedQuery] = useState(initialState.query);
  const [source, setSource] = useState(initialState.source);
  const [category, setCategory] = useState(initialState.category);
  const [includeDeleted, setIncludeDeleted] = useState(initialState.includeDeleted);
  const [orderBy, setOrderBy] = useState<SortField>(initialState.orderBy);
  const [orderDir, setOrderDir] = useState<SortDir>(initialState.orderDir);

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
  const [pageJumpInput, setPageJumpInput] = useState("1");

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
    includeDeleted: !authLoading && canDeleteFiles && includeDeleted,
    orderBy,
    orderDir,
    snapshotId: initialState.snapshotId,
    firstSeenFrom: initialState.firstSeenFrom,
    firstSeenBefore: initialState.firstSeenBefore,
  };
  const requestKey = buildFilesParams(requestState).toString();
  const locationKey = buildDatabaseLocation(requestState);

  // Persist current state to URL so back-navigation restores filters/page
  useEffect(() => {
    if (authLoading) return;
    window.history.replaceState(null, "", locationKey);
  }, [authLoading, locationKey]);

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
        includeDeleted: !authLoading && canDeleteFiles && includeDeleted,
        orderBy,
        orderDir,
        snapshotId: initialState.snapshotId,
        firstSeenFrom: initialState.firstSeenFrom,
        firstSeenBefore: initialState.firstSeenBefore,
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
    [offset, debouncedQuery, source, category, authLoading, canDeleteFiles, includeDeleted, orderBy, orderDir]
  );

  useEffect(() => {
    if (authLoading) return;
    void fetchFiles();
  }, [authLoading, fetchFiles, requestKey]);

  useEffect(() => {
    if (authLoading || loading || total <= 0) return;
    const prevOffset = offset - PAGE_SIZE;
    const nextOffset = offset + PAGE_SIZE;
    if (prevOffset >= 0) {
      void fetchFiles({ targetOffset: prevOffset });
    }
    if (nextOffset < total) {
      void fetchFiles({ targetOffset: nextOffset });
    }
  }, [authLoading, fetchFiles, loading, offset, total]);

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

  useEffect(() => {
    setPageJumpInput(String(currentPage));
  }, [currentPage]);

  function handlePageJump() {
    const normalizedPage = pageJumpInput.trim();
    if (!/^\d+$/.test(normalizedPage)) {
      setPageJumpInput(String(currentPage));
      return;
    }
    const parsedPage = Number(normalizedPage);
    if (!Number.isSafeInteger(parsedPage)) {
      setPageJumpInput(String(currentPage));
      return;
    }
    const targetPage = Math.min(totalPages, Math.max(1, parsedPage));
    setPageJumpInput(String(targetPage));
    setOffset((targetPage - 1) * PAGE_SIZE);
  }

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

  function explainFile(file: FileItem) {
    const displayName = getCanonicalDisplayName(file, t("dashboard.untitled_material"));
    const filename = getChatValidName(file.original_filename) || displayName;
    databaseScrollCache.set(locationKey, window.scrollY);
    navigate("/chat", {
      state: {
        explainDocument: {
          file_url: file.url,
          filename,
          title: displayName,
          category: file.category || "",
          keywords: [],
        },
      },
    });
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

  const activeFilterCount = [source, category, canDeleteFiles && includeDeleted ? "y" : ""].filter(Boolean).length;
  const selectableVisibleUrls = canDeleteFiles ? files.filter((file) => !file.deleted_at).map((file) => file.url) : [];
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
          {canExportFiles && (
            <button
              onClick={exportCsv}
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-medium text-foreground hover:bg-muted transition-colors"
              data-testid="button-export-csv"
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              {t("db.export_csv")}
            </button>
          )}
        </div>
      </motion.div>

      {initialState.snapshotId && initialState.firstSeenFrom && initialState.firstSeenBefore && (
        <div
          className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm break-words [overflow-wrap:anywhere]"
          data-testid="weekly-period-context"
        >
          {t("db.weekly_period_context")
            .replace("{snapshot}", initialState.snapshotId)
            .replace("{start}", formatWeeklyDateTime(initialState.firstSeenFrom, lang))
            .replace("{end}", formatWeeklyDateTime(initialState.firstSeenBefore, lang))}
        </div>
      )}

      {canDeleteFiles && (files.length > 0 || selectedUrls.length > 0) && (
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
                  {c.count != null ? `${categoryDisplayName(c, lang)} (${c.count})` : categoryDisplayName(c, lang)}
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
              <option value="first_seen:desc">{t("db.sort_first_seen_newest")}</option>
              <option value="first_seen:asc">{t("db.sort_first_seen_oldest")}</option>
              <option value="title:asc">{t("db.sort_title_az")}</option>
              <option value="source_site:asc">{t("db.sort_source_az")}</option>
              <option value="bytes:desc">{t("db.sort_size_largest")}</option>
            </select>
          </div>
          <div className="flex items-end gap-3">
            {canDeleteFiles && (
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
            )}
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
          <div className={cn("hidden lg:grid gap-3 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider", canDeleteFiles ? "grid-cols-[36px_1fr_110px_120px_50px_70px_90px_176px]" : "grid-cols-[1fr_110px_120px_50px_70px_90px_136px]")}>
            {canDeleteFiles && (
              <button
                type="button"
                onClick={toggleSelectAllVisible}
                className="flex items-center justify-center hover:text-foreground transition-colors"
                data-testid="checkbox-select-all-header"
              >
                {allVisibleSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4 opacity-70" />}
              </button>
            )}
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
            <button onClick={() => handleSort(orderBy === "first_seen" ? "first_seen" : "last_seen")} className="flex items-center gap-1 hover:text-foreground transition-colors text-left" data-testid="sort-date">
              {orderBy === "first_seen" ? t("db.first_seen") : t("table.date")} <SortIcon field={orderBy === "first_seen" ? "first_seen" : "last_seen"} />
            </button>
            <span>{t("table.actions")}</span>
          </div>

          {files.map((file, i) => {
            const hasMd = file.has_markdown;
            const isDeleted = !!file.deleted_at;
            const isSelected = selectedUrls.includes(file.url);
            const displayName = getCanonicalDisplayName(file, t("dashboard.untitled_material"));
            const originalName = getChatValidName(file.original_filename);
            const displayDate = orderBy === "first_seen" ? file.first_seen : file.last_seen;

            return (
              <motion.div
                key={file.url}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className={cn(
                  "grid gap-1 lg:gap-3 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer",
                  canDeleteFiles ? "lg:grid-cols-[36px_1fr_110px_120px_50px_70px_90px_176px]" : "lg:grid-cols-[1fr_110px_120px_50px_70px_90px_136px]",
                  isDeleted && "opacity-50"
                )}
                onClick={() => navigateToFile(file)}
                data-testid={`file-row-${i}`}
              >
                {canDeleteFiles && (
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
                )}

                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileIcon className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                    <span className="text-sm font-medium truncate" title={displayName} data-testid={`text-title-${i}`}>
                      {displayName}
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
                  {originalName && originalName !== displayName && (
                    <p className="text-xs text-muted-foreground/50 mt-0.5 truncate pl-6" data-testid={`text-filename-${i}`}>
                      {originalName}
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
                  {categoryDisplayName(file.category, lang)}
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
                  {formatDate(displayDate, lang)}
                </span>

                <div className="hidden lg:flex items-center gap-1.5 justify-end">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!hasMd || isDeleted) return;
                      explainFile(file);
                    }}
                    disabled={!hasMd || isDeleted}
                    className="inline-flex items-center justify-center rounded-md border border-border p-2 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
                    data-testid={`button-ai-explain-${i}`}
                    title={hasMd ? t("db.explain_with_ai") : t("db.explain_unavailable")}
                  >
                    <Sparkles className="w-4 h-4" />
                  </button>
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
                  {canDownloadFiles && (
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
                  )}
                </div>

                <div className="flex items-center gap-2 sm:hidden mt-1">
                  {canDeleteFiles && (
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
                  )}
                  <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", contentTypeBadgeColor(file.content_type))}>
                    {contentTypeLabel(file.content_type)}
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDate(displayDate, lang)}</span>
                  <span className="text-xs text-muted-foreground">{formatSize(file.bytes)}</span>
                </div>
                <div className="flex items-center gap-2 sm:hidden mt-2 pl-6">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!hasMd || isDeleted) return;
                      explainFile(file);
                    }}
                    disabled={!hasMd || isDeleted}
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
                    data-testid={`button-ai-explain-mobile-${i}`}
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    {t("db.explain_with_ai")}
                  </button>
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
                  {canDownloadFiles && (
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
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
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

          <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
            <label htmlFor="database-page-jump" className="whitespace-nowrap">
              {t("db.go_to_page")}
            </label>
            <input
              id="database-page-jump"
              type="number"
              min={1}
              max={totalPages}
              inputMode="numeric"
              value={pageJumpInput}
              onChange={(e) => setPageJumpInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handlePageJump()}
              className="h-9 w-20 rounded-lg border border-border bg-background px-2 text-center text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              data-testid="input-page-jump"
            />
            <button
              type="button"
              onClick={handlePageJump}
              className="h-9 rounded-lg border border-border bg-card px-3 text-sm font-medium text-foreground hover:bg-muted transition-colors"
              data-testid="button-page-jump"
            >
              {t("db.jump")}
            </button>
          </div>

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
        onConfirm={() => {
          void confirmBulkDelete();
        }}
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
