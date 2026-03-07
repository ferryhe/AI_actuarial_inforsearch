import { useEffect, useState, useCallback } from "react";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";

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
  id: string;
  name: string;
  chunk_size?: number;
  chunk_overlap?: number;
  splitter?: string;
}

interface KnowledgeBase {
  id: string;
  name: string;
}

interface AiModelsConfig {
  current: {
    catalog: { provider: string; model: string };
    ocr: { provider: string; model: string };
  };
}

interface CategoriesConfig {
  categories: Record<string, unknown>;
}

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

export default function FileDetail() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const searchString = useSearch();
  const fileUrl = new URLSearchParams(searchString).get("url") || "";

  const [file, setFile] = useState<FileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
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

  const [convertEngine, setConvertEngine] = useState("docling");
  const [convertOverwrite, setConvertOverwrite] = useState(true);
  const [converting, setConverting] = useState(false);

  const [chunkSets, setChunkSets] = useState<ChunkSet[]>([]);
  const [chunkSetsLoading, setChunkSetsLoading] = useState(false);

  const [showCatalogModal, setShowCatalogModal] = useState(false);
  const [catalogSource, setCatalogSource] = useState("markdown");
  const [catalogOverwrite, setCatalogOverwrite] = useState(false);
  const [catalogSubmitting, setCatalogSubmitting] = useState(false);
  const [aiConfig, setAiConfig] = useState<AiModelsConfig | null>(null);

  const [showChunkModal, setShowChunkModal] = useState(false);
  const [chunkProfiles, setChunkProfiles] = useState<ChunkProfile[]>([]);
  const [chunkProfileId, setChunkProfileId] = useState("");
  const [chunkKbId, setChunkKbId] = useState("");
  const [chunkOverwrite, setChunkOverwrite] = useState(false);
  const [chunkSubmitting, setChunkSubmitting] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);

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

  useEffect(() => { fetchFile(); }, [fetchFile]);

  useEffect(() => {
    if (!fileUrl) return;
    setMdLoading(true);
    apiGet<{ markdown?: MarkdownData }>(`/api/files/${encodeURIComponent(fileUrl)}/markdown`)
      .then((res) => {
        setMarkdown(res.markdown || null);
        if (res.markdown?.markdown_content) setMdEditContent(res.markdown.markdown_content);
      })
      .catch(() => setMarkdown(null))
      .finally(() => setMdLoading(false));
  }, [fileUrl]);

  useEffect(() => {
    if (!fileUrl) return;
    setChunkSetsLoading(true);
    apiGet<{ data?: { chunk_sets?: ChunkSet[] }; chunk_sets?: ChunkSet[] }>(`/api/files/${encodeURIComponent(fileUrl)}/chunk-sets`)
      .then((res) => {
        const sets = res.data?.chunk_sets || res.chunk_sets || [];
        setChunkSets(sets);
      })
      .catch(() => setChunkSets([]))
      .finally(() => setChunkSetsLoading(false));
  }, [fileUrl]);

  useEffect(() => {
    apiGet<CategoriesConfig>("/api/config/categories")
      .then((res) => {
        const cats = res.categories || {};
        setAllCategories(Object.keys(cats));
      })
      .catch(() => {});
    apiGet<AiModelsConfig>("/api/config/ai-models")
      .then((res) => setAiConfig(res))
      .catch(() => {});
  }, []);

  function startEdit() {
    if (!file) return;
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
      const res = await apiPost<{ file?: FileData }>("/api/files/update", {
        url: file.url,
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
    } catch { /* ignore */ } finally { setMdSaving(false); }
  }

  async function triggerConversion() {
    if (!file) return;
    setConverting(true);
    try {
      await apiPost("/api/collections/run", {
        type: "markdown",
        name: `MD Convert: ${file.title || file.original_filename}`,
        file_urls: [file.url],
        engine: convertEngine,
        overwrite_existing: convertOverwrite,
      });
      setTimeout(() => {
        apiGet<{ markdown?: MarkdownData }>(`/api/files/${encodeURIComponent(fileUrl)}/markdown`)
          .then((res) => {
            setMarkdown(res.markdown || null);
            if (res.markdown?.markdown_content) setMdEditContent(res.markdown.markdown_content);
          })
          .catch(() => {});
      }, 3000);
    } catch { /* ignore */ } finally { setConverting(false); }
  }

  async function submitCatalog() {
    if (!file) return;
    setCatalogSubmitting(true);
    try {
      await apiPost("/api/collections/run", {
        type: "catalog",
        name: `Catalog: ${file.title || file.original_filename}`,
        file_urls: [file.url],
        input_source: catalogSource,
        overwrite_existing: catalogOverwrite,
      });
      setShowCatalogModal(false);
      setTimeout(() => fetchFile(), 5000);
    } catch { /* ignore */ } finally { setCatalogSubmitting(false); }
  }

  async function openChunkModal() {
    setShowChunkModal(true);
    try {
      const [profiles, kbs] = await Promise.all([
        apiGet<{ data?: { profiles?: ChunkProfile[] }; profiles?: ChunkProfile[] }>("/api/chunk/profiles"),
        apiGet<{ data?: { knowledge_bases?: KnowledgeBase[] }; knowledge_bases?: KnowledgeBase[] }>("/api/rag/knowledge-bases"),
      ]);
      const p = profiles.data?.profiles || profiles.profiles || [];
      const k = kbs.data?.knowledge_bases || kbs.knowledge_bases || [];
      setChunkProfiles(p);
      setKnowledgeBases(k);
      if (p.length > 0 && !chunkProfileId) setChunkProfileId(p[0].id);
    } catch { /* ignore */ }
  }

  async function submitChunk() {
    if (!file || !chunkProfileId) return;
    setChunkSubmitting(true);
    try {
      await apiPost(`/api/files/${encodeURIComponent(file.url)}/chunk-sets/generate`, {
        profile_id: chunkProfileId,
        overwrite_same_profile: chunkOverwrite,
        kb_id: chunkKbId || undefined,
      });
      setShowChunkModal(false);
      setTimeout(() => {
        apiGet<{ data?: { chunk_sets?: ChunkSet[] }; chunk_sets?: ChunkSet[] }>(`/api/files/${encodeURIComponent(fileUrl)}/chunk-sets`)
          .then((res) => setChunkSets(res.data?.chunk_sets || res.chunk_sets || []))
          .catch(() => {});
      }, 3000);
    } catch { /* ignore */ } finally { setChunkSubmitting(false); }
  }

  async function handleDelete() {
    if (!file) return;
    setDeleting(true);
    try {
      await apiPost("/api/files/delete", { url: file.url });
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
        <button onClick={() => navigate("/database")} className="text-sm text-primary hover:underline" data-testid="link-back-database">
          {t("fv.back")}
        </button>
      </div>
    );
  }

  const selectedCategories = (editing ? editCategory : file.category || "").split(";").map((c) => c.trim()).filter(Boolean);
  const keywords = editing ? editKeywords.split(",").map((k) => k.trim()).filter(Boolean) : file.keywords || [];
  const hasMarkdown = !!(markdown?.markdown_content);

  return (
    <div className="space-y-6 max-w-4xl">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3">
        <button onClick={() => navigate("/database")} className="p-2 rounded-lg hover:bg-muted transition-colors" data-testid="button-back">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl sm:text-2xl font-serif font-bold tracking-tight truncate" data-testid="text-file-title">
            {file.title || file.original_filename || "Untitled"}
          </h1>
          <div className="flex items-center gap-2 mt-0.5">
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

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="flex flex-wrap gap-2">
        {!editing ? (
          <button onClick={startEdit} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors" data-testid="button-edit">
            <Pencil className="w-3.5 h-3.5" />{t("fv.edit")}
          </button>
        ) : (
          <>
            <button onClick={saveEdit} disabled={saving} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50" data-testid="button-save">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}{t("fv.save")}
            </button>
            <button onClick={() => setEditing(false)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors" data-testid="button-cancel">
              <X className="w-3.5 h-3.5" />{t("fv.cancel")}
            </button>
          </>
        )}
        <button onClick={() => setShowCatalogModal(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors" data-testid="button-catalog">
          <Sparkles className="w-3.5 h-3.5" />{t("fv.catalog")}
        </button>
        <button onClick={handleDownload} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors" data-testid="button-download">
          <Download className="w-3.5 h-3.5" />{t("fv.download")}
        </button>
        <button onClick={() => navigate(`/file-preview?file_url=${encodeURIComponent(file.url)}`)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted transition-colors" data-testid="button-preview">
          <Eye className="w-3.5 h-3.5" />{t("fv.preview")}
        </button>
        {!deleteConfirm ? (
          <button onClick={() => setDeleteConfirm(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-destructive/30 text-destructive text-sm hover:bg-destructive/10 transition-colors" data-testid="button-delete">
            <Trash2 className="w-3.5 h-3.5" />{t("fv.delete")}
          </button>
        ) : (
          <div className="flex items-center gap-1">
            <button onClick={handleDelete} disabled={deleting} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-destructive text-destructive-foreground text-sm hover:bg-destructive/90 transition-colors disabled:opacity-50" data-testid="button-confirm-delete">
              {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}{t("fv.confirm_delete")}
            </button>
            <button onClick={() => setDeleteConfirm(false)} className="px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors" data-testid="button-cancel-delete">
              {t("fv.cancel")}
            </button>
          </div>
        )}
      </motion.div>

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

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
          <Tag className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold">{t("fv.catalog_info")}</h3>
        </div>
        <div className="p-4 space-y-4">
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

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("fv.chunk_status")}</h3>
          </div>
          <button onClick={openChunkModal} className="text-xs px-2.5 py-1 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors" data-testid="button-modify-chunk">
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

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("fv.md_content")}</h3>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setMdTab("view")}
              className={cn("text-xs px-2.5 py-1 rounded-lg transition-colors", mdTab === "view" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground")}
              data-testid="button-md-view">{t("fv.view")}</button>
            <button onClick={() => { setMdTab("edit"); if (markdown?.markdown_content) setMdEditContent(markdown.markdown_content); }}
              className={cn("text-xs px-2.5 py-1 rounded-lg transition-colors", mdTab === "edit" ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground")}
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
              <textarea value={mdEditContent} onChange={(e) => setMdEditContent(e.target.value)} rows={16}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-xs font-mono resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder={t("fv.md_edit_ph")} data-testid="input-markdown" />
              <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
                <div className="flex items-center gap-2">
                  <label className="text-xs text-muted-foreground">{t("fv.convert_engine")}</label>
                  <select value={convertEngine} onChange={(e) => setConvertEngine(e.target.value)}
                    className="text-xs px-2 py-1 rounded-lg border border-border bg-background" data-testid="select-convert-engine">
                    <option value="docling">Docling</option>
                    <option value="marker">Marker</option>
                    <option value="mistral">Mistral OCR</option>
                    <option value="deepseekocr">DeepSeek OCR</option>
                  </select>
                </div>
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                  <input type="checkbox" checked={convertOverwrite} onChange={(e) => setConvertOverwrite(e.target.checked)} className="rounded" />
                  {t("fv.overwrite_md")}
                </label>
                <button onClick={triggerConversion} disabled={converting}
                  className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50 flex items-center gap-1.5"
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
                <button onClick={() => setMdTab("view")} className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
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

      {showCatalogModal && (
        <Modal onClose={() => setShowCatalogModal(false)}>
          <h3 className="text-base font-semibold flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-primary" />{t("fv.catalog_modal_title")}
          </h3>
          <p className="text-xs text-muted-foreground mb-4">{t("fv.catalog_hint")}</p>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.catalog_from")}</label>
              <select value={catalogSource} onChange={(e) => setCatalogSource(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-catalog-source">
                <option value="markdown">{t("fv.catalog_from_md")}</option>
                <option value="source">{t("fv.catalog_from_src")}</option>
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">{t("fv.catalog_from_hint")}</p>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={catalogOverwrite} onChange={(e) => setCatalogOverwrite(e.target.checked)} className="rounded" />
              {t("fv.overwrite_recompute")}
            </label>
            {aiConfig && (
              <p className="text-xs text-muted-foreground">
                {t("fv.ai_provider")}: {aiConfig.current.catalog.provider} / {aiConfig.current.catalog.model}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <button onClick={() => setShowCatalogModal(false)} className="text-sm px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors">
                {t("fv.cancel")}
              </button>
              <button onClick={submitCatalog} disabled={catalogSubmitting}
                className="text-sm px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                data-testid="button-submit-catalog">
                {catalogSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                {t("fv.submit_catalog")}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {showChunkModal && (
        <Modal onClose={() => setShowChunkModal(false)}>
          <h3 className="text-base font-semibold flex items-center gap-2 mb-3">
            <Layers className="w-4 h-4 text-primary" />{t("fv.chunk_modal_title")}
          </h3>
          <p className="text-xs text-muted-foreground mb-4">{t("fv.chunk_hint")}</p>
          <div className="space-y-4">
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
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">{t("fv.bind_kb")}</label>
              <select value={chunkKbId} onChange={(e) => setChunkKbId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-chunk-kb">
                <option value="">{t("fv.no_bind")}</option>
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>{kb.name}</option>
                ))}
              </select>
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
              <button onClick={submitChunk} disabled={chunkSubmitting || !chunkProfileId}
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
