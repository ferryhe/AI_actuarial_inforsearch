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
  ChevronDown,
  AlertCircle,
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
  { type: "adhoc_url", apiType: "url", icon: Link2, color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400" },
  { type: "file_import", apiType: "file", icon: FileUp, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  { type: "web_search", apiType: "search", icon: Search, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { type: "catalog", apiType: "catalog", icon: BookOpen, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  { type: "markdown", apiType: "markdown_conversion", icon: FileText, color: "bg-pink-500/10 text-pink-600 dark:text-pink-400" },
  { type: "chunk", apiType: "chunk_generation", icon: Layers, color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  { type: "rag_index", apiType: "rag_indexing", icon: Database, color: "bg-teal-500/10 text-teal-600 dark:text-teal-400" },
];

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

function InputField({
  value,
  onChange,
  placeholder,
  type = "text",
  testId,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  testId?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId}
    />
  );
}

function ScheduledForm({ sites, onSubmit, submitting }: { sites: SiteConfig[]; onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [site, setSite] = useState("");
  const [maxPages, setMaxPages] = useState("");
  const [maxDepth, setMaxDepth] = useState("");

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.scheduled_desc")}</p>
      <FormField label={t("tasks.form.target_site")}>
        <select
          value={site}
          onChange={(e) => setSite(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          data-testid="select-site"
        >
          <option value="">{t("tasks.form.all_sites")}</option>
          {sites.map((s) => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
        </select>
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.max_pages")}>
          <InputField value={maxPages} onChange={setMaxPages} placeholder="200" type="number" testId="input-max-pages" />
        </FormField>
        <FormField label={t("tasks.form.max_depth")}>
          <InputField value={maxDepth} onChange={setMaxDepth} placeholder="2" type="number" testId="input-max-depth" />
        </FormField>
      </div>
      <button
        onClick={() => onSubmit({
          type: "scheduled",
          name: site ? `Scheduled: ${site}` : "Scheduled Collection",
          site: site || undefined,
          max_pages: maxPages ? parseInt(maxPages) : undefined,
          max_depth: maxDepth ? parseInt(maxDepth) : undefined,
        })}
        disabled={submitting}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-scheduled"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function AdhocUrlForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [urls, setUrls] = useState("");

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.url_desc")}</p>
      <FormField label={t("tasks.form.urls")}>
        <textarea
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          placeholder={t("tasks.form.urls_placeholder")}
          rows={4}
          className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          data-testid="input-urls"
        />
      </FormField>
      <button
        onClick={() => {
          const urlList = urls.split("\n").map(u => u.trim()).filter(Boolean);
          if (urlList.length === 0) return;
          onSubmit({ type: "url", name: `URL Collection (${urlList.length})`, urls: urlList });
        }}
        disabled={submitting || !urls.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-url"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function FileImportForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
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
      <FormField label={t("tasks.form.file_extensions")}>
        <InputField value={extensions} onChange={setExtensions} placeholder=".pdf,.docx,.pptx" testId="input-extensions" />
      </FormField>
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)} className="rounded" data-testid="checkbox-recursive" />
        {t("tasks.form.recursive")}
      </label>
      <button
        onClick={() => {
          if (!dirPath.trim()) return;
          onSubmit({
            type: "file",
            name: `File Import: ${dirPath}`,
            directory_path: dirPath,
            extensions: extensions.split(",").map(e => e.trim()).filter(Boolean),
            recursive,
          });
        }}
        disabled={submitting || !dirPath.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-file"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function WebSearchForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [engine, setEngine] = useState("brave");
  const [count, setCount] = useState("20");
  const [site, setSite] = useState("");

  const engines = [
    { id: "brave", name: "Brave Search" },
    { id: "google", name: "Google (SerpAPI)" },
    { id: "serper", name: "Google (Serper)" },
    { id: "tavily", name: "Tavily" },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.search_desc")}</p>
      <FormField label={t("tasks.form.search_query")}>
        <InputField value={query} onChange={setQuery} placeholder={t("tasks.form.search_query_placeholder")} testId="input-search-query" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.search_engine")}>
          <select
            value={engine}
            onChange={(e) => setEngine(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="select-engine"
          >
            {engines.map((e) => (
              <option key={e.id} value={e.id}>{e.name}</option>
            ))}
          </select>
        </FormField>
        <FormField label={t("tasks.form.max_results")}>
          <InputField value={count} onChange={setCount} placeholder="20" type="number" testId="input-count" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.site_filter")}>
        <InputField value={site} onChange={setSite} placeholder="example.com" testId="input-site-filter" />
      </FormField>
      <button
        onClick={() => {
          if (!query.trim()) return;
          onSubmit({
            type: "search",
            name: `Search: ${query}`,
            query,
            engine,
            count: parseInt(count) || 20,
            site: site || undefined,
          });
        }}
        disabled={submitting || !query.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-search"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function CatalogForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("100");
  const [provider, setProvider] = useState("");
  const [inputSource, setInputSource] = useState("markdown");
  const [retryErrors, setRetryErrors] = useState(false);
  const [skipExisting, setSkipExisting] = useState(true);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.catalog_desc")}</p>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.scope")}>
          <select
            value={scopeMode}
            onChange={(e) => setScopeMode(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="select-scope"
          >
            <option value="index">{t("tasks.form.scope_all")}</option>
            <option value="category">{t("tasks.form.scope_category")}</option>
          </select>
        </FormField>
        <FormField label={t("tasks.form.scan_count")}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="100" type="number" testId="input-scan-count" />
        </FormField>
      </div>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <InputField value={category} onChange={setCategory} placeholder="SOA, IAA..." testId="input-category" />
        </FormField>
      )}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.provider")}>
          <InputField value={provider} onChange={setProvider} placeholder="openai" testId="input-provider" />
        </FormField>
        <FormField label={t("tasks.form.input_source")}>
          <select
            value={inputSource}
            onChange={(e) => setInputSource(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="select-input-source"
          >
            <option value="markdown">Markdown</option>
            <option value="source">Source</option>
          </select>
        </FormField>
      </div>
      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={retryErrors} onChange={(e) => setRetryErrors(e.target.checked)} className="rounded" data-testid="checkbox-retry-errors" />
          {t("tasks.form.retry_errors")}
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={skipExisting} onChange={(e) => setSkipExisting(e.target.checked)} className="rounded" data-testid="checkbox-skip-existing" />
          {t("tasks.form.skip_existing")}
        </label>
      </div>
      <button
        onClick={() => onSubmit({
          type: "catalog",
          name: "AI Catalog",
          scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined,
          scan_count: parseInt(scanCount) || 100,
          provider: provider || undefined,
          input_source: inputSource,
          retry_errors: retryErrors,
          skip_existing: skipExisting,
        })}
        disabled={submitting || (scopeMode === "category" && !category.trim())}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-catalog"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function MarkdownForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [tool, setTool] = useState("docling");

  const tools = [
    { id: "docling", name: "Docling" },
    { id: "marker", name: "Marker" },
    { id: "mistral", name: "Mistral OCR" },
    { id: "auto", name: "Auto" },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.markdown_desc")}</p>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.conversion_tool")}>
          <select
            value={tool}
            onChange={(e) => setTool(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="select-tool"
          >
            {tools.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </FormField>
        <FormField label={t("tasks.form.scan_count")}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-md-scan-count" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.scope")}>
        <select
          value={scopeMode}
          onChange={(e) => setScopeMode(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          data-testid="select-md-scope"
        >
          <option value="index">{t("tasks.form.scope_all")}</option>
          <option value="category">{t("tasks.form.scope_category")}</option>
        </select>
      </FormField>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <InputField value={category} onChange={setCategory} placeholder="SOA, IAA..." testId="input-md-category" />
        </FormField>
      )}
      <button
        onClick={() => onSubmit({
          type: "markdown_conversion",
          name: `Markdown (${tool})`,
          conversion_tool: tool,
          scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined,
          scan_count: parseInt(scanCount) || 50,
        })}
        disabled={submitting || (scopeMode === "category" && !category.trim())}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-markdown"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function ChunkForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [profileName, setProfileName] = useState("");

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.chunk_desc")}</p>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.scan_count")}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-chunk-scan-count" />
        </FormField>
        <FormField label={t("tasks.form.chunk_profile")}>
          <InputField value={profileName} onChange={setProfileName} placeholder={t("tasks.form.default_profile")} testId="input-chunk-profile" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.scope")}>
        <select
          value={scopeMode}
          onChange={(e) => setScopeMode(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          data-testid="select-chunk-scope"
        >
          <option value="index">{t("tasks.form.scope_all")}</option>
          <option value="category">{t("tasks.form.scope_category")}</option>
        </select>
      </FormField>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <InputField value={category} onChange={setCategory} placeholder="SOA, IAA..." testId="input-chunk-category" />
        </FormField>
      )}
      <button
        onClick={() => onSubmit({
          type: "chunk_generation",
          name: "Chunk Generation",
          scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined,
          scan_count: parseInt(scanCount) || 50,
          profile_name: profileName || undefined,
        })}
        disabled={submitting || (scopeMode === "category" && !category.trim())}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-chunk"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
    </div>
  );
}

function RagIndexForm({ onSubmit, submitting }: { onSubmit: (data: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [kbId, setKbId] = useState("");
  const [kbs, setKbs] = useState<KBItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<{ knowledge_bases?: Array<Record<string, string>>; data?: { knowledge_bases?: Array<Record<string, string>> } }>("/api/rag/knowledge-bases")
      .then((res) => {
        const raw = res.data?.knowledge_bases || res.knowledge_bases || [];
        setKbs(raw.map((kb) => ({ kb_id: kb.kb_id || kb.id || "", name: kb.name || kb.kb_id || kb.id || "" })));
      })
      .catch(() => setKbs([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.rag_desc")}</p>
      <FormField label={t("tasks.form.knowledge_base")}>
        {loading ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            {t("tasks.form.loading_kbs")}
          </div>
        ) : kbs.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <AlertCircle className="w-4 h-4" />
            {t("tasks.form.no_kbs")}
          </div>
        ) : (
          <select
            value={kbId}
            onChange={(e) => setKbId(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="select-kb"
          >
            <option value="">{t("tasks.form.select_kb")}</option>
            {kbs.map((kb) => (
              <option key={kb.kb_id} value={kb.kb_id}>{kb.name}</option>
            ))}
          </select>
        )}
      </FormField>
      <button
        onClick={() => {
          if (!kbId) return;
          onSubmit({ type: "rag_indexing", name: `RAG Index: ${kbId}`, kb_id: kbId });
        }}
        disabled={submitting || !kbId}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        data-testid="button-run-rag"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {t("tasks.form.run")}
      </button>
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
    } catch (e) {
      console.error("Failed to fetch tasks:", e);
    }
  }, []);

  const fetchSites = useCallback(async () => {
    try {
      const res = await apiGet<{ sites: SiteConfig[] }>("/api/config/sites");
      setSites(res.sites || []);
    } catch {
      setSites([]);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchTasks(), fetchSites()]).finally(() => setLoading(false));
    intervalRef.current = setInterval(fetchTasks, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchTasks, fetchSites]);

  const stopTask = async (taskId: string) => {
    try {
      await apiPost(`/api/tasks/stop/${taskId}`);
      await fetchTasks();
    } catch (e) {
      console.error("Failed to stop task:", e);
    }
  };

  const viewLog = async (taskId: string) => {
    setLogLoading(true);
    setLogModal({ taskId, log: "" });
    try {
      const res = await apiGet<{ log: string }>(`/api/tasks/log/${taskId}`);
      setLogModal({ taskId, log: res.log || t("tasks.form.no_log") });
    } catch {
      setLogModal({ taskId, log: t("tasks.form.log_error") });
    } finally {
      setLogLoading(false);
    }
  };

  const handleSubmitTask = async (data: Record<string, unknown>) => {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      const res = await apiPost<{ success?: boolean; job_id?: string; error?: string }>("/api/collections/run", data);
      if (res.error) {
        setSubmitError(res.error);
        return;
      }
      setSubmitSuccess(res.job_id ? `${t("tasks.form.started")} (${res.job_id})` : t("tasks.form.started"));
      await fetchTasks();
      setTimeout(() => {
        setActiveForm(null);
        setSubmitSuccess(null);
      }, 2000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t("tasks.form.start_error");
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const activeTaskType = taskTypes.find((tt) => tt.type === activeForm);

  function renderForm() {
    switch (activeForm) {
      case "scheduled":
        return <ScheduledForm sites={sites} onSubmit={handleSubmitTask} submitting={submitting} />;
      case "adhoc_url":
        return <AdhocUrlForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "file_import":
        return <FileImportForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "web_search":
        return <WebSearchForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "catalog":
        return <CatalogForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "markdown":
        return <MarkdownForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "chunk":
        return <ChunkForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "rag_index":
        return <RagIndexForm onSubmit={handleSubmitTask} submitting={submitting} />;
      default:
        return null;
    }
  }

  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">
          {t("tasks.title")}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
          {t("tasks.subtitle")}
        </p>
      </motion.div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">{t("tasks.active")}</h2>
          <button
            onClick={fetchTasks}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-refresh-tasks"
            title={t("tasks.refresh")}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[...Array(2)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
            ))}
          </div>
        ) : activeTasks.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-10 rounded-xl border border-dashed border-border bg-card"
            data-testid="text-no-active-tasks"
          >
            <CheckCircle2 className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("tasks.no_active")}</p>
          </motion.div>
        ) : (
          <div className="space-y-3">
            {activeTasks.map((task, i) => (
              <motion.div
                key={task.id}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className="rounded-xl border border-border bg-card p-5"
                data-testid={`card-active-task-${task.id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {statusBadge(task.status)}
                      <span className="font-semibold text-sm truncate">{task.name}</span>
                    </div>
                    {task.current_activity && (
                      <p className="text-xs text-muted-foreground mt-1 truncate" data-testid={`text-activity-${task.id}`}>
                        {task.current_activity}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => stopTask(task.id)}
                    className="shrink-0 p-2 rounded-lg bg-red-500/10 text-red-600 hover:bg-red-500/20 transition-colors"
                    data-testid={`button-stop-task-${task.id}`}
                    title={t("tasks.stop")}
                  >
                    <Square className="w-4 h-4" />
                  </button>
                </div>
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>{task.items_processed}/{task.items_total || "?"}</span>
                    <span>{Math.round(task.progress)}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                    <motion.div
                      className="h-full rounded-full bg-primary"
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(task.progress, 100)}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">
                  {t("tasks.started")}: {formatDate(task.started_at)}
                </p>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.new_task")}</h2>

        <AnimatePresence mode="wait">
          {activeForm ? (
            <motion.div
              key="form"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="rounded-xl border border-border bg-card overflow-hidden"
            >
              <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
                <button
                  onClick={() => { setActiveForm(null); setSubmitError(null); setSubmitSuccess(null); }}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                  data-testid="button-back-tasks"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                {activeTaskType && (
                  <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", activeTaskType.color)}>
                    <activeTaskType.icon className="w-5 h-5" strokeWidth={1.8} />
                  </div>
                )}
                <div>
                  <h3 className="font-semibold text-sm">{t(`tasks.type.${activeForm}`)}</h3>
                </div>
              </div>
              <div className="p-5">
                {submitError && (
                  <div className="mb-4 px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs flex items-center gap-2" data-testid="text-submit-error">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{submitError}</span>
                    <button onClick={() => setSubmitError(null)} className="ml-auto shrink-0"><X className="w-3.5 h-3.5" /></button>
                  </div>
                )}
                {submitSuccess && (
                  <div className="mb-4 px-3 py-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2" data-testid="text-submit-success">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>{submitSuccess}</span>
                  </div>
                )}
                {renderForm()}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="grid grid-cols-2 sm:grid-cols-4 gap-3"
            >
              {taskTypes.map(({ type, icon: Icon, color }, i) => (
                <motion.button
                  key={type}
                  custom={i}
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  onClick={() => { setActiveForm(type); setSubmitError(null); setSubmitSuccess(null); }}
                  className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border bg-card hover:border-primary/30 hover:shadow-md transition-all duration-300"
                  data-testid={`button-start-${type}`}
                >
                  <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", color)}>
                    <Icon className="w-5 h-5" strokeWidth={1.8} />
                  </div>
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
              <span
                key={site.name}
                className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
                data-testid={`text-site-${site.name}`}
              >
                {site.name}
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.history")}</h2>
        {loading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : historyTasks.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-10 rounded-xl border border-dashed border-border bg-card"
            data-testid="text-no-history"
          >
            <Inbox className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("tasks.no_history")}</p>
          </motion.div>
        ) : (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="hidden sm:grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>{t("tasks.col.name")}</span>
              <span>{t("tasks.col.type")}</span>
              <span>{t("tasks.col.status")}</span>
              <span>{t("tasks.col.started")}</span>
              <span>{t("tasks.col.items")}</span>
            </div>
            {historyTasks.map((task, i) => (
              <motion.div
                key={task.id}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className="grid sm:grid-cols-[1fr_100px_100px_120px_60px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
                onClick={() => viewLog(task.id)}
                data-testid={`row-history-task-${task.id}`}
              >
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
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
            onClick={() => setLogModal(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-card rounded-xl border border-border shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
              data-testid="modal-task-log"
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h3 className="font-semibold text-sm">
                  {t("tasks.log_title")} — {logModal.taskId}
                </h3>
                <button
                  onClick={() => setLogModal(null)}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                  data-testid="button-close-log"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">
                {logLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <pre className="text-xs font-mono whitespace-pre-wrap text-muted-foreground leading-relaxed" data-testid="text-task-log">
                    {logModal.log}
                  </pre>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
