import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface FileItem {
  url: string;
  title: string;
  original_filename: string;
  source_site: string;
  content_type: string;
  last_seen: string;
}

interface FilesResponse {
  files: FileItem[];
  total: number;
  limit: number;
  offset: number;
}

interface Category {
  name: string;
  count: number;
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

type SortField = "title" | "source_site" | "content_type" | "last_seen";
type SortDir = "asc" | "desc";

export default function DatabasePage() {
  const { t } = useTranslation();

  const [files, setFiles] = useState<FileItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");
  const [orderBy, setOrderBy] = useState<SortField>("last_seen");
  const [orderDir, setOrderDir] = useState<SortDir>("desc");

  const [sources, setSources] = useState<string[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedQuery, source, category, orderBy, orderDir]);

  useEffect(() => {
    apiGet<{ sources: string[] }>("/api/sources")
      .then((d) => setSources(d.sources || []))
      .catch(() => {});
    apiGet<{ categories: Category[] }>("/api/categories")
      .then((d) => setCategories(d.categories || []))
      .catch(() => {});
  }, []);

  const fetchFiles = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      order_by: orderBy,
      order_dir: orderDir,
    });
    if (debouncedQuery) params.set("query", debouncedQuery);
    if (source) params.set("source", source);
    if (category) params.set("category", category);

    apiGet<FilesResponse>(`/api/files?${params}`)
      .then((data) => {
        setFiles(data.files || []);
        setTotal(data.total ?? 0);
      })
      .catch(() => {
        setFiles([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [offset, debouncedQuery, source, category, orderBy, orderDir]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

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

  const activeFilterCount = [source, category].filter(Boolean).length;

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">
          {t("db.title")}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("db.subtitle")}</p>
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
          className="flex flex-col sm:flex-row gap-3"
        >
          <div className="flex-1">
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
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("db.category")}</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="select-category"
            >
              <option value="">{t("db.all_categories")}</option>
              {categories.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.count})
                </option>
              ))}
            </select>
          </div>
          {activeFilterCount > 0 && (
            <div className="flex items-end">
              <button
                onClick={() => { setSource(""); setCategory(""); }}
                className="px-3 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                data-testid="button-clear-filters"
              >
                {t("db.clear_filters")}
              </button>
            </div>
          )}
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
          <div className="hidden sm:grid grid-cols-[1fr_140px_80px_100px_44px] gap-4 px-4 py-2.5 bg-muted/50">
            {([
              { field: "title" as SortField, label: t("table.title") },
              { field: "source_site" as SortField, label: t("table.source") },
              { field: "content_type" as SortField, label: t("table.type") },
              { field: "last_seen" as SortField, label: t("table.date") },
            ]).map(({ field, label }) => (
              <button
                key={field}
                onClick={() => handleSort(field)}
                className="flex items-center gap-1 text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors text-left"
                data-testid={`sort-${field}`}
              >
                {label}
                <SortIcon field={field} />
              </button>
            ))}
            <span />
          </div>

          {files.map((file, i) => (
            <motion.div
              key={file.url}
              custom={i}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              className="grid sm:grid-cols-[1fr_140px_80px_100px_44px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors"
              data-testid={`file-row-${i}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <FileIcon className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                <span className="text-sm font-medium truncate" data-testid={`text-title-${i}`}>
                  {file.title || file.original_filename || "Untitled"}
                </span>
              </div>
              <span className="text-sm text-muted-foreground truncate hidden sm:block" data-testid={`text-source-${i}`}>
                {file.source_site || "-"}
              </span>
              <span className="hidden sm:block">
                {file.content_type && (
                  <span className={cn("inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full", contentTypeBadgeColor(file.content_type))}>
                    {contentTypeLabel(file.content_type)}
                  </span>
                )}
              </span>
              <span className="text-xs text-muted-foreground hidden sm:flex items-center" data-testid={`text-date-${i}`}>
                {formatDate(file.last_seen)}
              </span>
              <div className="hidden sm:flex items-center justify-center">
                <button
                  onClick={() => handleDownload(file)}
                  className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                  title={t("db.download")}
                  data-testid={`button-download-${i}`}
                >
                  <Download className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          ))}
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
    </div>
  );
}
