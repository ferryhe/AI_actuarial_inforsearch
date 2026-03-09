import { useEffect, useState, useCallback, useRef } from "react";
import { useLocation, useSearch } from "wouter";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Download,
  Trash2,
  Eye,
  Pencil,
  Save,
  X,
  Loader2,
  AlertCircle,
  ExternalLink,
  FileText,
  Tag,
  BookOpen,
  Layers,
  ChevronDown,
  ChevronUp,
  Sparkles,
  RefreshCw,
  Check,
  Clock,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";
import { useTaskOptions } from "@/hooks/use-task-options";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";

interface FileData {
  url: string;
  title: string;
  original_filename: string;
  source_site: string;
  source_page_url?: string;
  content_type: string;
  bytes: number;
  local_path?: string;
  crawl_time?: string;
  last_seen?: string;
  category?: string;
  summary?: string;
  keywords?: string[];
  catalog_model?: string;
  catalog_updated_at?: string;
  deleted_at?: string;
  sha256?: string;
}

interface MarkdownData {
  markdown_content?: string;
  markdown_source?: string;
  markdown_updated_at?: string;
}

interface ChunkSet {
  chunk_set_id: string;
  profile_name?: string;
  profile_id?: string;
  chunk_count?: number;
  created_at?: string;
  updated_at?: string;
  kb_id?: string;
  kb_name?: string;
}

interface ChunkProfile {
  id?: string;
  profile_id?: string;
  name: string;
  chunk_size?: number;
  chunk_overlap?: number;
  splitter?: string;
}

interface KnowledgeBase {
  id: string;
  name: string;
}

interface CategoriesConfig {
  categories: Record<string, unknown>;
}

type TaskStatus = "idle" | "submitted" | "polling" | "completed" | "timeout";

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return dateStr; }
}

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

function useTaskPoller(onComplete: () => void, intervalMs = 2000, maxMs = 30000) {
  const [status, setStatus] = useState<TaskStatus>("idle");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const jobIdRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
    jobIdRef.current = null;
  }, []);

  const start = useCallback((jobId?: string) => {
    cleanup();
    jobIdRef.current = jobId || null;
    setStatus("polling");
    timerRef.current = setInterval(async () => {
      try {
        const res = await apiGet<{ tasks?: Array<{ id?: string; status?: string }> }>("/api/tasks/active");
        const tasks = res.tasks || [];
        const myTask = jobIdRef.current
          ? tasks.find((t) => t.id === jobIdRef.current)
          : null;
        if (jobIdRef.current && !myTask) {
          cleanup();
          setStatus("completed");
          onComplete();
          setTimeout(() => setStatus("idle"), 3000);
        } else if (!jobIdRef.current && tasks.length === 0) {
          cleanup();
          setStatus("completed");
          onComplete();
          setTimeout(() => setStatus("idle"), 3000);
        }
      } catch { /* keep polling */ }
    }, intervalMs);
    timeoutRef.current = setTimeout(() => {
      cleanup();
      setStatus("timeout");
      onComplete();
      setTimeout(() => setStatus("idle"), 5000);
    }, maxMs);
  }, [cleanup, onComplete, intervalMs, maxMs]);

  const reset = useCallback(() => { cleanup(); setStatus("idle"); }, [cleanup]);

  useEffect(() => cleanup, [cleanup]);

  return { status, start, reset };
}

function TaskStatusBadge({ status, t }: { status: TaskStatus; t: (k: string) => string }) {
  if (status === "idle") return null;
  const config = {
    submitted: { icon: <Loader2 className="w-3 h-3 animate-spin" />, text: t("fv.task_submitted"), cls: "text-blue-600 bg-blue-500/10" },
    polling: { icon: <Clock className="w-3 h-3 animate-pulse" />, text: t("fv.task_running"), cls: "text-amber-600 bg-amber-500/10" },
    completed: { icon: <CheckCircle2 className="w-3 h-3" />, text: t("fv.task_completed"), cls: "text-emerald-600 bg-emerald-500/10" },
    timeout: { icon: <Clock className="w-3 h-3" />, text: t("fv.task_timeout"), cls: "text-orange-600 bg-orange-500/10" },
  }[status];
  if (!config) return null;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full", config.cls)}>
      {config.icon}{config.text}
    </span>
  );
}

export default function FileDetail() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const searchString = useSearch();
  const fileUrl = new URLSearchParams(searchString).get("url") || "";

  function goBack() {
    // If navigated from within the app with an explicit "from" param, use it.
    const fromParam = new URLSearchParams(searchString).get("from");
    if (fromParam && fromParam.startsWith("/")) {
      navigate(fromParam);
      return;
    }
    // Fallback: browser history back if referrer is same origin.
    try {
      const ref = document.referrer;
      if (ref && new URL(ref).origin === window.location.origin) {
        window.history.back();
        return;
      }
    } catch {
      // URL parse failed — fall through to default
    }
    navigate("/database");
  }

  const [file, setFile] = useState<FileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editSummary, setEditSummary] = useState("");
  const [editKeywords, setEditKeywords] = useState("");
  const [saving, setSaving] = useState(false);

  const [allCategories, setAllCategories] = useState<string[]>([]);
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);

  const [markdown, setMarkdown] = useState<MarkdownData | null>(null);
  const [mdLoading, setMdLoading] = useState(false);
  const [mdTab, setMdTab] = useState<"view" | "edit">("view");
  const [mdEditContent, setMdEditContent] = useState("");
  const [mdSaving, setMdSaving] = useState(false);
  const [mdExpanded, setMdExpanded] = useState(false);
  const [mdDirty, setMdDirty] = useState(false);

  const [convertEngine, setConvertEngine] = useState("");
  const [convertOverwrite, setConvertOverwrite] = useState(true);
  const [converting, setConverting] = useState(false);

  const [chunkSets, setChunkSets] = useState<ChunkSet[]>([]);
  const [chunkSetsLoading, setChunkSetsLoading] = useState(false);

  const [showCatalogModal, setShowCatalogModal] = useState(false);
  const [catalogSource, setCatalogSource] = useState("markdown");
  const [catalogOverwrite, setCatalogOverwrite] = useState(false);
  const [catalogUpdateTitle, setCatalogUpdateTitle] = useState(false);
  const [catalogOutputLanguage, setCatalogOutputLanguage] = useState("auto");
  const [catalogSubmitting, setCatalogSubmitting] = useState(false);

  const taskOptions = useTaskOptions();

  const [showChunkModal, setShowChunkModal] = useState(false);
  const [chunkProfiles, setChunkProfiles] = useState<ChunkProfile[]>([]);
  const [chunkProfileId, setChunkProfileId] = useState("");
  const [chunkKbId, setChunkKbId] = useState("");
  const [chunkOverwrite, setChunkOverwrite] = useState(false);
  const [chunkSubmitting, setChunkSubmitting] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);

  const [inlineChunkSize, setInlineChunkSize] = useState(800);
  const [inlineChunkOverlap, setInlineChunkOverlap] = useState(100);
  const [inlineSplitter, setInlineSplitter] = useState("recursive");
  const [inlineTokenizer, setInlineTokenizer] = useState("cl100k_base");

  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fetchFile = useCallback(async () => {
    if (!fileUrl) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<{ file: FileData }>(`/api/files/detail?url=${encodeURIComponent(fileUrl)}`);
      setFile(res.file);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load file");
    } finally { setLoading(false); }
  }, [fileUrl]);

  const refreshMarkdown = useCallback(async () => {
    if (!fileUrl) return;
    try {
      const res = await apiGet<{ markdown?: MarkdownData }>(`/api/files/${encodeURIComponent(fileUrl)}/markdown`);
      setMarkdown(res.markdown || null);
      if (res.markdown?.markdown_content) setMdEditContent(res.markdown.markdown_content);
    } catch { setMarkdown(null); }
  }, [fileUrl]);

  const refreshChunks = useCallback(async () => {
    if (!fileUrl) return;
    try {
      const res = await apiGet<{ data?: { chunk_sets?: ChunkSet[] }; chunk_sets?: ChunkSet[] }>(`/api/files/${encodeURIComponent(fileUrl)}/chunk-sets`);
      setChunkSets(res.data?.chunk_sets || res.chunk_sets || []);
    } catch { setChunkSets([]); }
  }, [fileUrl]);

  const conversionPoller = useTaskPoller(refreshMarkdown);
  const catalogPoller = useTaskPoller(fetchFile);

  const anyTaskRunning = converting || catalogSubmitting || chunkSubmitting ||
    conversionPoller.status === "polling" ||
    catalogPoller.status === "polling";
  const mdEditMode = mdTab === "edit";

  useEffect(() => {
    if (!convertEngine && taskOptions.conversionToolsInfo.length > 0) {
      setConvertEngine(taskOptions.conversionToolsInfo[0].name);
    } else if (convertEngine && taskOptions.conversionToolsInfo.length > 0) {
      const valid = taskOptions.conversionToolsInfo.some((t) => t.name === convertEngine);
      if (!valid) setConvertEngine(taskOptions.conversionToolsInfo[0].name);
    }
  }, [taskOptions.conversionToolsInfo, convertEngine]);

  useEffect(() => { fetchFile(); }, [fetchFile]);

  useEffect(() => {
    if (!fileUrl) return;
    setMdLoading(true);
    refreshMarkdown().finally(() => setMdLoading(false));
  }, [fileUrl, refreshMarkdown]);

  useEffect(() => {
    if (!fileUrl) return;
    setChunkSetsLoading(true);
    refreshChunks().finally(() => setChunkSetsLoading(false));
  }, [fileUrl, refreshChunks]);

  useEffect(() => {
    apiGet<CategoriesConfig>("/api/config/categories")
      .then((res) => {
        const cats = res.categories || {};
        setAllCategories(Object.keys(cats));
      })
      .catch(() => {});
  }, []);

  function startEdit() {
    if (!file) return;
    setEditTitle(file.title || "");
    setEditCategory(file.category || "");
    setEditSummary(file.summary || "");
    setEditKeywords((file.keywords || []).join(", "));
    setEditing(true);
  }

  async function saveEdit() {
    if (!file) return;
    setSaving(true);
    try {
      const kws = editKeywords.split(",").map((k) => k.trim()).filter(Boolean);
      const titleChanged = editTitle.trim() !== (file.title || "").trim();
      const res = await apiPost<{ file?: FileData }>("/api/files/update", {
        url: file.url,
        title: titleChanged ? editTitle.trim() : undefined,
        category: editCategory || undefined,
        summary: editSummary || undefined,
        keywords: kws.length > 0 ? kws : undefined,
      });
      if (res.file) setFile(res.file);
      setEditing(false);
    } catch { /* ignore */ } finally { setSaving(false); }
  }

  function toggleCategory(cat: string) {
    const current = editCategory.split(";").map((c) => c.trim()).filter(Boolean);
    const idx = current.indexOf(cat);
    if (idx >= 0) current.splice(idx, 1);
    else current.push(cat);
    setEditCategory(current.join("; "));
  }

  async function saveMarkdown() {
    if (!fileUrl) return;
    setMdSaving(true);
    try {
      const res = await apiPost<{ markdown?: MarkdownData }>(`/api/files/${encodeURIComponent(fileUrl)}/markdown`, {
        markdown_content: mdEditContent,
        markdown_source: "manual",
      });
      if (res.markdown) setMarkdown(res.markdown);
      setMdTab("view");
      setMdDirty(false);
    } catch { /* ignore */ } finally { setMdSaving(false); }
  }

  async function triggerConversion() {
    if (!file) return;
    if (mdDirty) {
      const ok = window.confirm(t("fv.confirm_discard_md"));
      if (!ok) return;
    }
    setConverting(true);
    try {
      const res = await apiPost<{ job_id?: string }>("/api/collections/run", {
        type: "markdown_conversion",
        name: `MD Convert: ${file.title || file.original_filename}`,
        file_urls: [file.url],
        engine: convertEngine,
        overwrite_existing: convertOverwrite,
      });
      setMdTab("view");
      setMdDirty(false);
      conversionPoller.start(res.job_id);
    } catch { /* ignore */ } finally { setConverting(false); }
  }

  async function submitCatalog() {
    if (!file) return;
    setCatalogSubmitting(true);
    try {
      const res = await apiPost<{ job_id?: string }>("/api/collections/run", {
        type: "catalog",
        name: `Catalog: ${file.title || file.original_filename}`,
        file_urls: [file.url],
        input_source: catalogSource,
        overwrite_existing: catalogOverwrite,
        update_title: catalogUpdateTitle,
        output_language: catalogOutputLanguage,
      });
      setShowCatalogModal(false);
      catalogPoller.start(res.job_id);
    } catch { /* ignore */ } finally { setCatalogSubmitting(false); }
  }

  const [kbLoadError, setKbLoadError] = useState(false);

  async function openChunkModal() {
    setShowChunkModal(true);
    try {
      const profilesRes = await apiGet<Record<string, unknown>>("/api/chunk/profiles");
      const pd = profilesRes.data as Record<string, unknown> | undefined;
      const p: ChunkProfile[] = Array.isArray(pd) ? pd : Array.isArray(pd?.profiles) ? pd.profiles as ChunkProfile[] : [];
      setChunkProfiles(p);
      if (p.length > 0 && !chunkProfileId) setChunkProfileId(p[0].profile_id || p[0].id);
    } catch { /* ignore */ }
    try {
      const kbsRes = await apiGet<Record<string, unknown>>("/api/rag/knowledge-bases");
      const kd = kbsRes.data;
      const k: KnowledgeBase[] = Array.isArray(kd) ? kd : [];
      setKnowledgeBases(k);
      setKbLoadError(false);
    } catch {
      setKnowledgeBases([]);
      setKbLoadError(true);
    }
  }

  const hasProfiles = chunkProfiles.length > 0;

  async function submitChunk() {
    if (!file) return;
    if (hasProfiles && !chunkProfileId) return;
    setChunkSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        overwrite_same_profile: chunkOverwrite,
        kb_id: chunkKbId || undefined,
      };
      if (hasProfiles && chunkProfileId) {
        body.profile_id = chunkProfileId;
      } else {
        body.chunk_size = inlineChunkSize;
        body.chunk_overlap = inlineChunkOverlap;
        body.splitter = inlineSplitter;
        body.tokenizer = inlineTokenizer;
      }
      await apiPost(`/api/files/${encodeURIComponent(file.url)}/chunk-sets/generate`, body);
      setShowChunkModal(false);
      await refreshChunks();
    } catch { /* ignore */ } finally { setChunkSubmitting(false); }
  }

  async function handleDelete() {
    if (!file) return;
    setDeleting(true);
    try {
      await apiPost("/api/files/delete", { url: file.url, confirm: "DELETE" });
      navigate("/database");
    } catch { setDeleting(false); }
  }

  function handleDownload() {
    if (!file) return;
    const a = document.createElement("a");
    a.href = `/api/download?url=${encodeURIComponent(file.url)}`;
    a.target = "_blank";
    a.click();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !file) {
    return (
      <div className="space-y-4 py-16 text-center">
        <AlertCircle className="w-12 h-12 mx-auto text-destructive/60" />
        <p className="text-muted-foreground">{error || "File not found"}</p>
        <button onClick={() => goBack()} className="text-sm text-primary hover:underline" data-testid="link-back-database">
          {t("fv.back")}
        </button>
      </div>
    );
  }

  const selectedCategories = (editing ? editCategory : file.category || "").split(";").map((c) => c.trim()).filter(Boolean);
  const keywords = editing ? editKeywords.split(",").map((k) => k.trim()).filter(Boolean) : file.keywords || [];
  const hasMarkdown = !!(markdown?.markdown_content);

  const disabledBtn = "opacity-40 pointer-events-none cursor-not-allowed";

  const canEdit = !anyTaskRunning && !mdEditMode;
  const canCatalog = !anyTaskRunning && !editing && !mdEditMode;
  const canDownload = true;
  const canPreview = true;
  const canDelete = !anyTaskRunning;
  const canModifyChunk = !anyTaskRunning && !editing && !mdEditMode;
  const canSwitchMdEdit = !editing && !anyTaskRunning;
  const canConvert = !editing && !anyTaskRunning;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Section 1: Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3">
        <button onClick={() => goBack()} className="p-2 rounded-lg hover:bg-muted transition-colors" data-testid="button-back">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl sm:text-2xl font-serif font-bold tracking-tight truncate" data-testid="text-file-title">
            {file.title || file.original_filename || "Untitled"}
          </h1>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", contentTypeBadgeColor(file.content_type))}>
              {contentTypeLabel(file.content_type)}
            </span>
            <span className="text-xs text-muted-foreground">{formatBytes(file.bytes)}</span>
            {file.deleted_at && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-destructive/10 text-destructive">
                {t("fv.deleted")}
              </span>
            )}
          </div>
        </div>
      </motion.div>

      {/* Section 1b: Toolbar */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="flex flex-wrap items-center gap-2">
        {!editing ? (
          <button onClick={startEdit} disabled={!canEdit}
            className={cn("flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors", !canEdit && disabledBtn)}
            data-testid="button-edit">
            <Pencil className="w-3.5 h-3.5" />{t("fv.edit")}
          </button>
        ) : (
          <>
            <button onClick={saveEdit} disabled={saving} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50" data-testid="button-save">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}{t("fv.save")}
            </button>
            <button onClick={() => { setEditing(false); setShowCategoryPicker(false); }} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors" data-testid="button-cancel">
              <X className="w-3.5 h-3.5" />{t("fv.cancel")}
            </button>
          </>
        )}
        <button onClick={() => setShowCatalogModal(true)} disabled={!canCatalog}
          className={cn("flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors", !canCatalog && disabledBtn)}
          data-testid="button-catalog">
          <Sparkles className="w-3.5 h-3.5" />{t("fv.catalog")}
        </button>
        <button onClick={handleDownload} disabled={!canDownload}
          className={cn("flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors", !canDownload && disabledBtn)}
          data-testid="button-download">
          <Download className="w-3.5 h-3.5" />{t("fv.download")}
        </button>
        <button onClick={() => navigate(`/file-preview?file_url=${encodeURIComponent(file.url)}`)} disabled={!canPreview}
          className={cn("flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors", !canPreview && disabledBtn)}
          data-testid="button-preview">
          <Eye className="w-3.5 h-3.5" />{t("fv.preview")}
        </button>
        <button onClick={() => setDeleteConfirm(true)} disabled={!canDelete}
          className={cn("flex items-center gap-1.5 px-3 py-2 rounded-lg border border-destructive/30 text-destructive text-sm hover:bg-destructive/10 transition-colors", !canDelete && disabledBtn)}
          data-testid="button-delete">
          <Trash2 className="w-3.5 h-3.5" />{t("fv.delete")}
        </button>
        <ConfirmDeleteModal
          open={!!deleteConfirm}
          onClose={() => setDeleteConfirm(false)}
          onConfirm={handleDelete}
          title={t("fv.confirm_delete")}
          loading={deleting}
        />
        <div className="flex items-center gap-1.5 ml-auto">
          <TaskStatusBadge status={conversionPoller.status} t={t} />
          <TaskStatusBadge status={catalogPoller.status} t={t} />
        </div>
      </motion.div>

      {/* Section 2: Metadata Card */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold">{t("fv.metadata")}</h3>
        </div>
        <div className="p-4">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-border">
              <MetaRow label={t("fv.source_site")} testId="text-source">
                {file.source_site || "-"}
              </MetaRow>
              <MetaRow label={t("fv.orig_url")} testId="text-url">
                {file.source_site === "Local Import" || file.source_site === "File Import" ? (
                  <span className="text-muted-foreground text-xs break-all">{file.url}</span>
                ) : (
                  <a href={file.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-xs break-all inline-flex items-center gap-1" data-testid="link-original-url">
                    {file.url}<ExternalLink className="w-3 h-3 shrink-0" />
                  </a>
                )}
              </MetaRow>
              {file.source_page_url && (
                <MetaRow label={t("fv.source_page")} testId="text-source-page">
                  <a href={file.source_page_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-xs break-all inline-flex items-center gap-1">
                    {file.source_page_url}<ExternalLink className="w-3 h-3 shrink-0" />
                  </a>
                </MetaRow>
              )}
              <MetaRow label={t("fv.content_type")} testId="text-content-type">{file.content_type || "-"}</MetaRow>
              <MetaRow label={t("fv.file_size")} testId="text-file-size">{formatBytes(file.bytes)}</MetaRow>
              {file.local_path && <MetaRow label={t("fv.local_path")} testId="text-local-path"><span className="text-xs break-all font-mono">{file.local_path}</span></MetaRow>}
              <MetaRow label={t("fv.collected_date")} testId="text-collected">{formatDate(file.crawl_time || file.last_seen)}</MetaRow>
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* Section 3: Catalog Information */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
          <Tag className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold">{t("fv.catalog_info")}</h3>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{t("fv.title")}</label>
            {editing ? (
              <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder={t("fv.title_ph")} data-testid="input-title" />
            ) : (
              <p className="text-sm font-medium" data-testid="text-title">
                {file.title || <span className="text-muted-foreground italic">{file.original_filename}</span>}
              </p>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{t("fv.category")}</label>
            {editing ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {selectedCategories.map((c) => (
                    <span key={c} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-primary/10 text-primary">
                      {c}
                      <button onClick={() => toggleCategory(c)} className="hover:text-destructive"><X className="w-3 h-3" /></button>
                    </span>
                  ))}
                  {selectedCategories.length === 0 && <span className="text-xs text-muted-foreground">{t("fv.uncategorized")}</span>}
                </div>
                <button onClick={() => setShowCategoryPicker(!showCategoryPicker)}
                  className="text-xs text-primary hover:underline" data-testid="button-toggle-categories">
                  {t("fv.choose_cat")}
                </button>
                {showCategoryPicker && allCategories.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 p-2 rounded-lg border border-border bg-muted/30">
                    {allCategories.map((c) => (
                      <button key={c} onClick={() => toggleCategory(c)}
                        className={cn("text-xs px-2 py-1 rounded-full border transition-colors",
                          selectedCategories.includes(c) ? "border-primary bg-primary/10 text-primary" : "border-border hover:border-primary/50"
                        )} data-testid={`button-cat-${c}`}>{c}</button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {selectedCategories.length > 0
                  ? selectedCategories.map((c) => (
                    <span key={c} className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary">{c}</span>
                  ))
                  : <span className="text-xs text-muted-foreground">{t("fv.uncategorized")}</span>
                }
              </div>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{t("fv.summary")}</label>
            {editing ? (
              <textarea value={editSummary} onChange={(e) => setEditSummary(e.target.value)} rows={4}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder={t("fv.no_summary")} data-testid="input-summary" />
            ) : (
              <p className="text-sm whitespace-pre-wrap" data-testid="text-summary">
                {file.summary || <span className="text-muted-foreground italic">{t("fv.no_summary")}</span>}
              </p>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{t("fv.keywords")}</label>
            {editing ? (
              <input value={editKeywords} onChange={(e) => setEditKeywords(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder={t("fv.kw_ph")} data-testid="input-keywords" />
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {keywords.length > 0
                  ? keywords.map((k, i) => (
                    <span key={i} className="text-xs px-2 py-1 rounded-full bg-muted text-foreground">{k}</span>
                  ))
                  : <span className="text-xs text-muted-foreground italic">{t("fv.no_keywords")}</span>
                }
              </div>
            )}
          </div>

          {file.catalog_model && (
            <p className="text-[11px] text-muted-foreground">
              {t("fv.ai_provider")}: {file.catalog_model} {file.catalog_updated_at ? `(${formatDate(file.catalog_updated_at)})` : ""}
            </p>
          )}
        </div>
      </motion.div>

      {/* Section 4: Markdown Content */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("fv.md_content")}</h3>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => { setMdTab("view"); setMdDirty(false); }}
              className={cn("text-xs px-2.5 py-1 rounded-lg transition-colors", mdTab === "view" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground")}
              data-testid="button-md-view">{t("fv.view")}</button>
            <button onClick={() => { setMdTab("edit"); if (markdown?.markdown_content) setMdEditContent(markdown.markdown_content); setMdDirty(false); }}
              disabled={!canSwitchMdEdit}
              className={cn("text-xs px-2.5 py-1 rounded-lg transition-colors",
                mdTab === "edit" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground",
                !canSwitchMdEdit && disabledBtn
              )}
              data-testid="button-md-edit">{t("fv.md_edit")}</button>
            {hasMarkdown && (
              <button onClick={() => setMdExpanded(!mdExpanded)}
                className="text-xs px-2 py-1 rounded-lg hover:bg-muted text-muted-foreground transition-colors" data-testid="button-md-expand">
                {mdExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            )}
          </div>
        </div>
        <div className="p-4">
          {mdLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("fv.loading")}</div>
          ) : mdTab === "view" ? (
            hasMarkdown ? (
              <div className={cn("prose prose-sm dark:prose-invert max-w-none overflow-y-auto transition-all", mdExpanded ? "max-h-none" : "max-h-[60vh]")}
                data-testid="text-markdown-content">
                <pre className="whitespace-pre-wrap text-sm font-sans">{markdown?.markdown_content}</pre>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground italic">{t("fv.no_md")}</p>
            )
          ) : (
            <div className="space-y-3">
              <textarea value={mdEditContent} onChange={(e) => { setMdEditContent(e.target.value); setMdDirty(true); }} rows={16}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-xs font-mono resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder={t("fv.md_edit_ph")} data-testid="input-markdown" />
              <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground">{t("fv.convert_engine")}</label>
                  <select value={convertEngine} onChange={(e) => setConvertEngine(e.target.value)}
                    disabled={!canConvert}
                    className={cn("text-xs px-2 py-1 rounded-lg border border-border bg-background", !canConvert && disabledBtn)}
                    data-testid="select-convert-engine">
                    {taskOptions.conversionToolsInfo.map((tool) => (
                      <option key={tool.name} value={tool.name}>{tool.displayName}</option>
                    ))}
                  </select>
                </div>
                <label className={cn("flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer", !canConvert && disabledBtn)}>
                  <input type="checkbox" checked={convertOverwrite} onChange={(e) => setConvertOverwrite(e.target.checked)} className="rounded" disabled={!canConvert} />
                  {t("fv.overwrite_md")}
                </label>
                <button onClick={triggerConversion} disabled={converting || !canConvert}
                  className={cn("text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50 flex items-center gap-1.5", !canConvert && disabledBtn)}
                  data-testid="button-convert">
                  {converting ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                  {t("fv.convert_btn")}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={saveMarkdown} disabled={mdSaving}
                  className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  data-testid="button-save-md">
                  {mdSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  {t("fv.save_md")}
                </button>
                <button onClick={() => { setMdTab("view"); setMdDirty(false); }} className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
                  data-testid="button-cancel-md">{t("fv.cancel")}</button>
                {markdown?.markdown_updated_at && (
                  <span className="text-[11px] text-muted-foreground ml-auto">
                    {t("fv.last_updated")}: {formatDate(markdown.markdown_updated_at)}
                    {markdown.markdown_source && ` (${markdown.markdown_source})`}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </motion.div>

      {/* Section 5: RAG Chunks */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("fv.chunk_status")}</h3>
          </div>
          <button onClick={openChunkModal} disabled={!canModifyChunk}
            className={cn("text-xs px-2.5 py-1 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors", !canModifyChunk && disabledBtn)}
            data-testid="button-modify-chunk">
            {t("fv.modify_chunk")}
          </button>
        </div>
        <div className="p-4">
          {chunkSetsLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("fv.loading")}</div>
          ) : chunkSets.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">{t("fv.no_chunks")}</p>
          ) : (
            <div className="space-y-2">
              {chunkSets.map((cs) => (
                <div key={cs.chunk_set_id} className="flex items-center justify-between text-xs p-2 rounded-lg bg-muted/30 border border-border">
                  <div className="space-y-0.5">
                    <span className="font-medium">{cs.profile_name || cs.profile_id || "default"}</span>
                    {cs.kb_name && <span className="ml-2 text-muted-foreground">KB: {cs.kb_name}</span>}
                  </div>
                  <div className="flex items-center gap-3 text-muted-foreground">
                    <span>{cs.chunk_count ?? "?"} chunks</span>
                    <span>{formatDate(cs.updated_at || cs.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>

      {/* Modal: AI Catalog */}
      {showCatalogModal && (
        <Modal onClose={() => setShowCatalogModal(false)}>
          <h3 className="text-base font-semibold flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-primary" />{t("fv.catalog_modal_title")}
          </h3>
          <p className="text-xs text-muted-foreground mb-4">{t("fv.catalog_hint")}</p>
          <div className="space-y-4">
            {taskOptions.catalogProviders.length === 0 && (
              <div className="px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/5 text-xs text-amber-700 dark:text-amber-300">
                {t("fv.no_catalog_provider")}{" "}
                <a href="/settings" className="underline hover:no-underline">{t("fv.go_to_settings")}</a>
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.catalog_from")}</label>
              <select value={catalogSource} onChange={(e) => setCatalogSource(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-catalog-source">
                <option value="markdown">{t("fv.catalog_from_md")}</option>
                <option value="source">{t("fv.catalog_from_src")}</option>
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">{t("fv.catalog_from_hint")}</p>
            </div>
            {taskOptions.catalogProviders.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border text-xs text-muted-foreground">
                <span className="font-medium">{t("fv.ai_provider")}:</span>
                <span>{taskOptions.catalogProviders.join(", ")}</span>
                <span className="ml-auto text-[10px]">({t("fv.configured_in_settings")})</span>
              </div>
            )}
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={catalogOverwrite} onChange={(e) => setCatalogOverwrite(e.target.checked)} className="rounded" />
              {t("fv.overwrite_recompute")}
            </label>
            {taskOptions.catalogProviders.length > 0 && (
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={catalogUpdateTitle} onChange={(e) => setCatalogUpdateTitle(e.target.checked)} className="rounded" data-testid="checkbox-update-title" />
                <span>
                  {t("fv.update_title_with_ai")}
                  <span className="ml-1 text-[11px] text-muted-foreground">{t("fv.update_title_hint")}</span>
                </span>
              </label>
            )}
            {taskOptions.catalogProviders.length > 0 && (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("tasks.form.output_language")}</label>
                <select
                  value={catalogOutputLanguage}
                  onChange={(e) => setCatalogOutputLanguage(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background"
                  data-testid="select-output-language">
                  <option value="auto">{t("tasks.form.lang_auto")}</option>
                  <option value="en">{t("tasks.form.lang_en")}</option>
                  <option value="zh">{t("tasks.form.lang_zh")}</option>
                </select>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <button onClick={() => setShowCatalogModal(false)} className="text-sm px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors">
                {t("fv.cancel")}
              </button>
              <button onClick={submitCatalog} disabled={catalogSubmitting || taskOptions.catalogProviders.length === 0}
                className="text-sm px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                data-testid="button-submit-catalog">
                {catalogSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                {t("fv.submit_catalog")}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Modal: Chunk Generation */}
      {showChunkModal && (
        <Modal onClose={() => setShowChunkModal(false)}>
          <h3 className="text-base font-semibold flex items-center gap-2 mb-3">
            <Layers className="w-4 h-4 text-primary" />{t("fv.chunk_modal_title")}
          </h3>
          <p className="text-xs text-muted-foreground mb-4">{t("fv.chunk_hint")}</p>
          <div className="space-y-4">
            {hasProfiles ? (
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.chunk_profile")}</label>
                <select value={chunkProfileId} onChange={(e) => setChunkProfileId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-chunk-profile">
                  {chunkProfiles.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} ({p.chunk_size || "?"})</option>
                  ))}
                </select>
                <p className="text-[11px] text-muted-foreground mt-1">{t("fv.chunk_profile_hint")}</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/5 text-xs text-amber-700 dark:text-amber-400">
                  {t("fv.no_profiles_hint")}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.inline_chunk_size")}</label>
                    <input type="number" value={inlineChunkSize} onChange={(e) => setInlineChunkSize(Number(e.target.value))}
                      min={64} max={8192}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-inline-chunk-size" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.inline_chunk_overlap")}</label>
                    <input type="number" value={inlineChunkOverlap} onChange={(e) => setInlineChunkOverlap(Number(e.target.value))}
                      min={0} max={2048}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-inline-chunk-overlap" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.inline_splitter")}</label>
                    <select value={inlineSplitter} onChange={(e) => setInlineSplitter(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-inline-splitter">
                      <option value="recursive">{t("knowledge.splitter_recursive")}</option>
                      <option value="semantic">{t("knowledge.splitter_semantic")}</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.inline_tokenizer")}</label>
                    <select value={inlineTokenizer} onChange={(e) => setInlineTokenizer(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-inline-tokenizer">
                      <option value="cl100k_base">cl100k_base</option>
                      <option value="p50k_base">p50k_base</option>
                      <option value="r50k_base">r50k_base</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.bind_kb")}</label>
              {kbLoadError ? (
                <div className="px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/5 text-xs text-amber-700 dark:text-amber-400">
                  {t("fv.kb_load_error")}
                </div>
              ) : (
                <select value={chunkKbId} onChange={(e) => setChunkKbId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-chunk-kb">
                  <option value="">{t("fv.no_bind")}</option>
                  {knowledgeBases.map((kb) => (
                    <option key={kb.id} value={kb.id}>{kb.name}</option>
                  ))}
                </select>
              )}
              <p className="text-[11px] text-muted-foreground mt-1">{t("fv.bind_kb_hint")}</p>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={chunkOverwrite} onChange={(e) => setChunkOverwrite(e.target.checked)} className="rounded" />
              {t("fv.overwrite_recompute")}
            </label>
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <button onClick={() => setShowChunkModal(false)} className="text-sm px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors">
                {t("fv.cancel")}
              </button>
              <button onClick={submitChunk} disabled={chunkSubmitting || (hasProfiles && !chunkProfileId)}
                className="text-sm px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                data-testid="button-submit-chunk">
                {chunkSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                {t("fv.submit_chunk")}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function MetaRow({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <tr>
      <td className="py-2 pr-4 text-xs font-medium text-muted-foreground whitespace-nowrap align-top w-[140px]">{label}</td>
      <td className="py-2 text-sm" data-testid={testId}>{children}</td>
    </tr>
  );
}

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}>
        {children}
      </motion.div>
    </div>
  );
}
