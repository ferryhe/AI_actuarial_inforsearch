import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { useRoute, useLocation } from "wouter";
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Layers,
  Loader2,
  Save,
  Trash2,
  Plus,
  RefreshCw,
  Link2,
  Unlink,
  Tag,
  AlertCircle,
  CheckCircle2,
  Clock,
  Zap,
  FolderOpen,
  X,
  Search,
  LinkIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost, apiPut, apiDelete, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface KBMeta {
  kb_id: string;
  name: string;
  description?: string;
  kb_mode?: string;
  chunk_profile_id?: string;
  chunk_profile_name?: string;
  embedding_provider?: string;
  embedding_model?: string;
  embedding_dimension?: number;
  index_embedding_provider?: string;
  index_embedding_model?: string;
  index_embedding_dimension?: number;
  needs_reindex?: boolean;
  embedding_compatible?: boolean;
  current_embeddings?: {
    provider?: string;
    model?: string;
    dimension?: number;
  };
  chunk_size?: number;
  chunk_overlap?: number;
  status?: string;
  file_count?: number;
  chunk_count?: number;
  index_type?: string;
  created_at?: string;
  manifest_profile?: string;
  agentic_ready_manifest?: AgenticReadyManifest;
}

interface AgenticReadyManifest {
  kb_id: string;
  profile: string;
  status: "missing" | "ready" | "building" | "failed" | "stale";
  usable: boolean;
  output_dir?: string;
  built_at?: string;
  doc_count?: number;
  section_count?: number;
  error_message?: string;
  stale_reason?: string;
  fallback_mode?: string;
}

interface KBStats {
  file_count?: number;
  chunk_count?: number;
  pending_count?: number;
  indexed_count?: number;
  total_files?: number;
  total_chunks?: number;
  pending_files?: number;
  indexed_files?: number;
}

interface KBFile {
  file_url: string;
  title?: string;
  category?: string;
  chunk_set_id?: string;
  binding_mode?: string;
  chunk_count?: number;
  profile_name?: string;
  chunk_profile?: string;
  status?: string;
}

interface KBCategory {
  name: string;
  file_count?: number;
}

interface UnmappedCategory {
  name: string;
  file_count?: number;
}

interface SelectableFile {
  file_url: string;
  url?: string;
  title?: string;
  category?: string;
  source_site?: string;
  chunk_set_id?: string;
  chunk_count?: number;
  chunk_profile_id?: string;
  chunk_profile_name?: string;
}

function StatusDot({ status }: { status?: string }) {
  const s = (status || "").toLowerCase();
  const color =
    s === "active" || s === "ready" || s === "indexed"
      ? "bg-emerald-500"
      : s === "building" || s === "indexing" || s === "pending"
        ? "bg-amber-500 animate-pulse"
        : "bg-muted-foreground/40";
  return <span className={cn("w-2 h-2 rounded-full inline-block shrink-0", color)} />;
}

function getManifestStatusClass(status?: AgenticReadyManifest["status"]) {
  switch (status) {
    case "ready":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "building":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "failed":
      return "bg-red-500/10 text-red-700 dark:text-red-300";
    case "stale":
      return "bg-orange-500/10 text-orange-700 dark:text-orange-300";
    case "missing":
    default:
      return "bg-muted text-muted-foreground";
  }
}

function getManifestFallbackMessage(manifest?: AgenticReadyManifest | null) {
  const status = manifest?.status || "missing";
  const fallback = manifest?.fallback_mode || "standard RAG";
  if (status === "ready" && manifest?.usable) return "";
  if (status === "building") return "Agentic manifest is building.";
  if (status === "failed") {
    return `Build failed${manifest?.error_message ? `: ${manifest.error_message}` : ""}. Falling back to ${fallback}.`;
  }
  if (status === "stale") {
    return `Manifest stale${manifest?.stale_reason ? `: ${manifest.stale_reason}` : ""}. Falling back to ${fallback}.`;
  }
  return `Agentic manifest missing. Falling back to ${fallback}.`;
}

function getManifestActionLabel(manifest?: AgenticReadyManifest | null) {
  const status = manifest?.status || "missing";
  if (status === "ready" || status === "stale" || status === "failed") return "Rebuild manifest";
  if (status === "building") return "Building";
  return "Build manifest";
}

export default function KBDetail() {
  const { t } = useTranslation();
  const { permissions } = useAuth();
  const canManageKnowledge = permissions.includes("config.write");
  const canRunKnowledgeTasks = permissions.includes("tasks.run");
  const [, navigate] = useLocation();
  const [match, params] = useRoute("/knowledge/:kbId");
  const kbId = params?.kbId ? decodeURIComponent(params.kbId) : "";

  const [meta, setMeta] = useState<KBMeta | null>(null);
  const canBindFiles = canManageKnowledge && Boolean(meta?.chunk_profile_id);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [files, setFiles] = useState<KBFile[]>([]);
  const [categories, setCategories] = useState<KBCategory[]>([]);
  const [unmappedCategories, setUnmappedCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [agenticManifest, setAgenticManifest] = useState<AgenticReadyManifest | null>(null);
  const [manifestBuilding, setManifestBuilding] = useState(false);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [hasEdits, setHasEdits] = useState(false);

  const [showAddCategory, setShowAddCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");

  const [fileSearch, setFileSearch] = useState("");

  const [showPendingFiles, setShowPendingFiles] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<KBFile[]>([]);
  const [loadingPending, setLoadingPending] = useState(false);

  const [showBindDialog, setShowBindDialog] = useState(false);
  const [bindSearch, setBindSearch] = useState("");
  const [bindableFiles, setBindableFiles] = useState<SelectableFile[]>([]);
  const [bindLoading, setBindLoading] = useState(false);
  const [selectedBindFiles, setSelectedBindFiles] = useState<string[]>([]);
  const [bindSubmitting, setBindSubmitting] = useState(false);

  const loadMeta = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<{ knowledge_base?: (KBMeta & { stats?: KBStats; categories?: string[] }) }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`);
      const m = res.knowledge_base;
      if (!m) {
        setMeta(null);
        setAgenticManifest(null);
        return;
      }
      setMeta(m);
      setAgenticManifest(m.agentic_ready_manifest || null);
      if (m.stats) {
        setStats(m.stats);
      }
      setEditName(m.name || "");
      setEditDesc(m.description || "");
    } catch {
      setMeta(null);
      setAgenticManifest(null);
    }
  }, [kbId]);

  const loadAgenticManifest = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<{ manifest?: AgenticReadyManifest }>(
        `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/agentic-ready-manifest`
      );
      setAgenticManifest(res.manifest || null);
    } catch {
      setAgenticManifest(null);
    }
  }, [kbId]);

  const loadStats = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<KBStats>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/stats`);
      setStats(res);
    } catch {
      setStats(null);
    }
  }, [kbId]);

  const loadFiles = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<{ files?: KBFile[]; data?: { files?: KBFile[] } }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files`);
      setFiles(res.data?.files || res.files || []);
    } catch {
      setFiles([]);
    }
  }, [kbId]);

  const loadCategories = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<{ categories?: Array<string | KBCategory> }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/categories`);
      const normalized = (res.categories || []).map((item) =>
        typeof item === "string" ? { name: item } : { name: item.name, file_count: item.file_count }
      );
      setCategories(normalized);
    } catch {
      setCategories([]);
    }
    try {
      const res2 = await apiGet<{ unmapped_categories?: UnmappedCategory[] }>("/api/rag/categories/unmapped");
      setUnmappedCategories((res2.unmapped_categories || []).map((item) => item.name).filter(Boolean));
    } catch {
      setUnmappedCategories([]);
    }
  }, [kbId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadMeta(), loadStats(), loadFiles(), loadCategories(), loadAgenticManifest()]);
    setLoading(false);
  }, [loadMeta, loadStats, loadFiles, loadCategories, loadAgenticManifest]);

  useEffect(() => {
    if (match) loadAll();
  }, [match, loadAll]);

  const handleSave = async () => {
    if (!kbId) return;
    setSaving(true);
    try {
      await apiPut(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`, {
        name: editName,
        description: editDesc,
      });
      setHasEdits(false);
      await loadMeta();
    } catch (err) {
      console.error("Failed to save KB:", err);
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveFile = async (fileUrl: string) => {
    try {
      await apiDelete(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files/${encodeURIComponent(fileUrl)}`);
      await Promise.all([loadFiles(), loadStats()]);
    } catch (err) {
      console.error("Failed to remove file:", err);
    }
  };

  const handleAddCategory = async (cat: string) => {
    if (!cat.trim()) return;
    setActionNotice(null);
    setActionError(null);
    try {
      const res = await apiPost<{ category_sync?: { added_count?: number } }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/categories`, {
        categories: [cat.trim()],
        action: "add",
      });
      const addedCount = res.category_sync?.added_count ?? 0;
      setActionNotice(
        addedCount > 0
          ? t("kb.category_sync_notice").replace("{count}", String(addedCount))
          : t("kb.category_added_notice")
      );
      setNewCategory("");
      setShowAddCategory(false);
      await Promise.all([loadMeta(), loadStats(), loadFiles(), loadCategories()]);
    } catch (err) {
      console.error("Failed to add category:", err);
      const detail = formatApiErrorDetail(err);
      setActionError(detail || t("kb.category_add_error"));
    }
  };

  const handleRemoveCategory = async (cat: string) => {
    try {
      await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/categories`, {
        categories: [cat],
        action: "remove",
      });
      await loadCategories();
    } catch (err) {
      console.error("Failed to remove category:", err);
    }
  };

  const handleBuildIndex = async (force: boolean) => {
    setIndexing(true);
    setActionNotice(null);
    setActionError(null);
    try {
      const endpoint = `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index`;
      const res = await apiPost<{
        category_sync?: { added_count?: number };
        all_sync?: { added_count?: number };
      }>(endpoint, force ? { force_reindex: true } : { incremental: true });
      const addedCount = res.category_sync?.added_count ?? res.all_sync?.added_count ?? 0;
      setActionNotice(
        addedCount > 0
          ? t("kb.index_sync_notice").replace("{count}", String(addedCount))
          : t("kb.index_started_notice")
      );
      await Promise.all([loadMeta(), loadStats(), loadFiles()]);
    } catch (err) {
      console.error("Failed to build index:", err);
      const detail = formatApiErrorDetail(err);
      setActionError(detail || t("kb.index_error"));
    } finally {
      setIndexing(false);
    }
  };

  const handleBuildAgenticManifest = async () => {
    if (!kbId) return;
    setManifestBuilding(true);
    setActionNotice(null);
    setActionError(null);
    try {
      const res = await apiPost<{ manifest?: AgenticReadyManifest; validation?: { valid?: boolean; errors?: string[] } }>(
        `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/agentic-ready-manifest/build`,
        {}
      );
      const nextManifest = res.manifest || null;
      setAgenticManifest(nextManifest);
      if (nextManifest) {
        setMeta((current) =>
          current
            ? {
                ...current,
                manifest_profile: nextManifest.profile || current.manifest_profile,
                agentic_ready_manifest: nextManifest,
              }
            : current
        );
      }
      const status = nextManifest?.status || "missing";
      if (status === "ready" && res.validation?.valid !== false) {
        setActionNotice("Agentic manifest build completed.");
      } else {
        const detail = res.validation?.errors?.join("; ") || nextManifest?.error_message || nextManifest?.stale_reason || status;
        setActionError(`Agentic manifest build did not produce ready data: ${detail}`);
      }
    } catch (err) {
      console.error("Failed to build agentic manifest:", err);
      const detail = formatApiErrorDetail(err);
      setActionError(detail || "Failed to build agentic manifest.");
    } finally {
      setManifestBuilding(false);
    }
  };

  const handleSearchBindable = async (query?: string) => {
    setBindLoading(true);
    try {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      params.set("kb_id", kbId);
      params.set("limit", "500");
      if (meta && meta.chunk_profile_id) params.set("profile_id", meta.chunk_profile_id);
      const url = `/api/rag/files/selectable?${params.toString()}`;
      const res = await apiGet<{ files?: Array<SelectableFile & { url?: string }> }>(url);
      setBindableFiles(
        (res.files || []).map((file) => ({
          file_url: file.file_url || file.url || "",
          title: file.title,
          category: file.category,
          source_site: file.source_site,
          chunk_set_id: file.chunk_set_id,
          chunk_count: file.chunk_count,
          chunk_profile_id: file.chunk_profile_id,
          chunk_profile_name: file.chunk_profile_name,
        })).filter((file) => file.file_url)
      );
    } catch {
      setBindableFiles([]);
    } finally {
      setBindLoading(false);
    }
  };

  const handleOpenBindDialog = () => {
    if (!canBindFiles) return;
    setShowBindDialog(true);
    setBindSearch("");
    setSelectedBindFiles([]);
    setActionNotice(null);
    setActionError(null);
    handleSearchBindable();
  };

  const handleToggleBindFile = (fileUrl: string) => {
    setSelectedBindFiles((prev) =>
      prev.includes(fileUrl) ? prev.filter((u) => u !== fileUrl) : [...prev, fileUrl]
    );
  };

  const handleSelectAllBindFiles = () => {
    const visibleFileUrls = bindableFiles.map((file) => file.file_url).filter(Boolean);
    if (visibleFileUrls.length === 0) return;
    setSelectedBindFiles((prev) => {
      const allVisibleSelected = bindableFiles.every((file) => prev.includes(file.file_url));
      return allVisibleSelected
        ? prev.filter((fileUrl) => !visibleFileUrls.includes(fileUrl))
        : Array.from(new Set([...prev, ...visibleFileUrls]));
    });
  };

  const handleSubmitBindings = async () => {
    if (selectedBindFiles.length === 0) return;
    setBindSubmitting(true);
    setActionNotice(null);
    setActionError(null);
    try {
      if (meta?.kb_mode === "manual") {
        await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files`, {
          file_urls: selectedBindFiles,
          chunk_profile_id: meta.chunk_profile_id,
        });
        setActionNotice(t("kb.files_added_notice").replace("{count}", String(selectedBindFiles.length)));
      } else {
        await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/bindings`, {
          bindings: selectedBindFiles.map((fileUrl) => {
            const file = bindableFiles.find((item) => item.file_url === fileUrl);
            if (!file?.chunk_set_id) return null;
            return {
              file_url: file.file_url,
              chunk_set_id: file.chunk_set_id,
              binding_mode: "follow_latest",
            };
          }).filter(Boolean),
        });
        setActionNotice(t("kb.files_bound_notice").replace("{count}", String(selectedBindFiles.length)));
      }
      setShowBindDialog(false);
      setSelectedBindFiles([]);
      await Promise.all([loadFiles(), loadStats()]);
    } catch (err) {
      console.error("Failed to add files to KB:", err);
      const detail = formatApiErrorDetail(err);
      setActionError(detail || t("kb.add_files_error"));
    } finally {
      setBindSubmitting(false);
    }
  };

  const loadPendingFiles = async () => {
    setLoadingPending(true);
    try {
      const res = await apiGet<{ pending_files?: KBFile[] }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files/pending`);
      setPendingFiles(res.pending_files || []);
      setShowPendingFiles(true);
    } catch (err) {
      console.error("Failed to load pending files:", err);
      setPendingFiles([]);
      setShowPendingFiles(true);
    } finally {
      setLoadingPending(false);
    }
  };

  if (!match) return null;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="text-center py-20">
        <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
        <p className="font-medium text-muted-foreground">{t("kb.not_found")}</p>
        <button
          onClick={() => navigate("/knowledge")}
          className="mt-4 text-sm text-primary hover:underline"
          data-testid="button-back-not-found"
        >
          {t("kb.back_to_list")}
        </button>
      </div>
    );
  }

  const filteredFiles = files.filter((f) => {
    if (!fileSearch) return true;
    const q = fileSearch.toLowerCase();
    return (
      f.file_url.toLowerCase().includes(q) ||
      (f.title || "").toLowerCase().includes(q) ||
      (f.category || "").toLowerCase().includes(q)
    );
  });

  const pendingCount = stats?.pending_count ?? stats?.pending_files ?? 0;
  const needsEmbeddingRebuild = meta.needs_reindex || meta.embedding_compatible === false;
  const isManualMode = meta.kb_mode === "manual";
  const isCategoryMode = meta.kb_mode === "category";
  const manifest = agenticManifest || meta.agentic_ready_manifest || null;
  const manifestStatus = manifest?.status || "missing";
  const manifestProfile = manifest ? manifest.profile || meta.manifest_profile || "default" : meta.manifest_profile || "default";
  const manifestDocCount = manifest ? manifest.doc_count ?? 0 : 0;
  const manifestSectionCount = manifest ? manifest.section_count ?? 0 : 0;
  const manifestOutputDir = manifest ? manifest.output_dir || "-" : "-";
  const manifestMessage = getManifestFallbackMessage(manifest);
  const manifestBusy = manifestBuilding || manifestStatus === "building";
  const currentEmbeddingLabel = [
    meta.current_embeddings?.provider,
    meta.current_embeddings?.model,
  ].filter(Boolean).join(" / ") || meta.embedding_model || "";
  const indexEmbeddingLabel = [
    meta.index_embedding_provider || meta.embedding_provider,
    meta.index_embedding_model || meta.embedding_model,
  ].filter(Boolean).join(" / ");

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <button
          onClick={() => navigate("/knowledge")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
          data-testid="button-back-to-kbs"
        >
          <ArrowLeft className="w-4 h-4" />
          {t("kb.back_to_list")}
        </button>

        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400 flex items-center justify-center shrink-0">
              <BookOpen className="w-6 h-6" strokeWidth={1.8} />
            </div>
            <div className="flex-1 min-w-0">
              {canManageKnowledge && (
                <>
                  <input
                    value={editName}
                    onChange={(e) => {
                      setEditName(e.target.value);
                      setHasEdits(true);
                    }}
                    className="text-xl font-serif font-bold tracking-tight bg-transparent border-none outline-none w-full focus:ring-0 p-0"
                    data-testid="input-kb-edit-name"
                  />
                  <textarea
                    value={editDesc}
                    onChange={(e) => {
                      setEditDesc(e.target.value);
                      setHasEdits(true);
                    }}
                    placeholder={t("kb.desc_placeholder")}
                    className="mt-2 w-full text-sm text-muted-foreground bg-transparent border-none outline-none resize-none focus:ring-0 p-0 leading-relaxed"
                    rows={2}
                    data-testid="input-kb-edit-desc"
                  />
                  <p className="text-[10px] text-muted-foreground/60 mt-1">{t("kb.desc_guidance")}</p>
                </>
              )}
              {!canManageKnowledge && (
                <>
                  <h1 className="text-xl font-serif font-bold tracking-tight" data-testid="text-kb-name-readonly">{meta.name}</h1>
                  {meta.description && (
                    <p className="mt-2 text-sm text-muted-foreground leading-relaxed" data-testid="text-kb-desc-readonly">{meta.description}</p>
                  )}
                </>
              )}
            </div>
            {canManageKnowledge && hasEdits && (
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 shrink-0"
                data-testid="button-save-kb"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t("kb.save")}
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-4 pt-4 border-t border-border text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <StatusDot status={meta.status} />
              {meta.status || "unknown"}
            </span>
            {meta.kb_mode && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted">
                {meta.kb_mode === "category" ? <FolderOpen className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
                {meta.kb_mode}
              </span>
            )}
            {meta.embedding_model && (
              <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-muted">
                {meta.embedding_model}
              </span>
            )}
            {meta.created_at && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {new Date(meta.created_at).toLocaleDateString()}
              </span>
            )}
          </div>

          <div
            className="mt-4 rounded-lg border border-border bg-muted/20 p-4"
            data-testid="panel-agentic-manifest"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full",
                      getManifestStatusClass(manifestStatus)
                    )}
                    data-testid="badge-agentic-manifest-detail"
                  >
                    Agentic {manifestStatus}
                  </span>
                  <span className="text-[11px] text-muted-foreground font-mono">
                    Profile: {manifestProfile}
                  </span>
                </div>
                {manifestMessage && (
                  <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
                    {manifestMessage}
                  </p>
                )}
              </div>
              {canRunKnowledgeTasks && (
                <button
                  type="button"
                  onClick={handleBuildAgenticManifest}
                  disabled={manifestBusy}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors"
                  data-testid="button-build-agentic-manifest-detail"
                >
                  {manifestBuilding ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <RefreshCw className={cn("w-4 h-4", manifestStatus === "building" && "animate-spin")} />
                  )}
                  {manifestBuilding ? "Building" : getManifestActionLabel(manifest)}
                </button>
              )}
            </div>
            <div className="mt-3 grid gap-2 text-[11px] text-muted-foreground sm:grid-cols-2 lg:grid-cols-4">
              <span className="font-mono truncate">Profile {manifestProfile}</span>
              <span className="tabular-nums">{manifestDocCount} docs</span>
              <span className="tabular-nums">{manifestSectionCount} sections</span>
              <span className="font-mono break-all">Output {manifestOutputDir}</span>
            </div>
            {manifest?.built_at && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Built {new Date(manifest.built_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      </motion.div>

      {actionError && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive" data-testid="alert-kb-detail-action-error">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}
      {actionNotice && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300" data-testid="alert-kb-detail-action-notice">
          <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{actionNotice}</span>
        </div>
      )}

      {canRunKnowledgeTasks && needsEmbeddingRebuild && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12, duration: 0.35 }}
          className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"
          data-testid="banner-embedding-mismatch"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3 min-w-0">
              <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                  {t("kb.embedding_mismatch_title")}
                </p>
                <p className="text-xs text-amber-800/80 dark:text-amber-200/80 mt-1">
                  {t("kb.embedding_mismatch_desc")}
                </p>
                <p className="text-[10px] text-amber-800/70 dark:text-amber-200/70 mt-1 font-mono truncate">
                  {indexEmbeddingLabel} -&gt; {currentEmbeddingLabel}
                </p>
              </div>
            </div>
            <button
              onClick={() => handleBuildIndex(true)}
              disabled={indexing}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors"
              data-testid="button-reembed-current-embedding"
            >
              <RefreshCw className={cn("w-4 h-4", indexing && "animate-spin")} />
              {t("kb.reembed_current")}
            </button>
          </div>
        </motion.div>
      )}

      {canRunKnowledgeTasks && isCategoryMode && pendingCount > 0 && !needsEmbeddingRebuild && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.14, duration: 0.35 }}
          className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4"
          data-testid="banner-category-index-required"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <Clock className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                  {t("kb.category_index_required_title")}
                </p>
                <p className="text-xs text-amber-800/80 dark:text-amber-200/80 mt-1">
                  {t("kb.category_index_required_desc").replace("{count}", String(pendingCount))}
                </p>
              </div>
            </div>
            <button
              onClick={() => handleBuildIndex(false)}
              disabled={indexing}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors"
              data-testid="button-category-index-now"
            >
              <Zap className={cn("w-4 h-4", indexing && "animate-pulse")} />
              {t("kb.index_now")}
            </button>
          </div>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.4 }}
        className="grid grid-cols-2 sm:grid-cols-4 gap-3"
      >
        {[
          { label: t("kb.stat_files"), value: stats?.file_count ?? stats?.total_files ?? meta.file_count ?? 0, icon: FileText, color: "text-blue-500" },
          { label: t("kb.stat_chunks"), value: stats?.chunk_count ?? stats?.total_chunks ?? meta.chunk_count ?? 0, icon: Layers, color: "text-violet-500" },
          { label: t("kb.stat_indexed"), value: stats?.indexed_count ?? stats?.indexed_files ?? 0, icon: CheckCircle2, color: "text-emerald-500" },
          { label: t("kb.stat_pending"), value: pendingCount, icon: Clock, color: pendingCount > 0 ? "text-amber-500" : "text-muted-foreground" },
        ].map((s, i) => (
          <div key={i} className="rounded-xl border border-border bg-card p-4" data-testid={`stat-card-${i}`}>
            <div className="flex items-center gap-2 mb-2">
              <s.icon className={cn("w-4 h-4", s.color)} />
              <span className="text-xs text-muted-foreground">{s.label}</span>
            </div>
            <p className="text-2xl font-bold tabular-nums">{s.value}</p>
          </div>
        ))}
      </motion.div>

      {canRunKnowledgeTasks && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4 }}
          className="flex items-center gap-2"
        >
        <button
          onClick={() => handleBuildIndex(false)}
          disabled={indexing || pendingCount === 0}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          data-testid="button-index-incremental"
        >
          {indexing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          {t("kb.index_now")} {pendingCount > 0 && `(${pendingCount})`}
        </button>
        <button
          onClick={() => handleBuildIndex(true)}
          disabled={indexing}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors disabled:opacity-50",
            needsEmbeddingRebuild
              ? "border-amber-500/40 text-amber-800 dark:text-amber-300 hover:bg-amber-500/10"
              : "border-border hover:bg-muted"
          )}
          data-testid="button-index-rebuild"
        >
          <RefreshCw className={cn("w-4 h-4", indexing && "animate-spin")} />
          {needsEmbeddingRebuild ? t("kb.reembed_current") : t("kb.rebuild_index")}
        </button>
        {pendingCount > 0 && (
          <button
            onClick={loadPendingFiles}
            disabled={loadingPending}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50"
            data-testid="button-view-pending"
          >
            {loadingPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Clock className="w-4 h-4" />}
            {t("kb.view_pending")} ({pendingCount})
          </button>
        )}
        </motion.div>
      )}

      {canRunKnowledgeTasks && showPendingFiles && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="rounded-xl border border-amber-500/30 bg-card overflow-hidden"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-amber-500/5">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-500" />
              <span className="text-sm font-semibold">{t("kb.pending_files")}</span>
              <span className="text-xs text-muted-foreground">({pendingFiles.length})</span>
            </div>
            <button
              onClick={() => setShowPendingFiles(false)}
              className="p-1.5 rounded hover:bg-muted"
              data-testid="button-close-pending"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          {pendingFiles.length === 0 ? (
            <div className="text-center py-8">
              <CheckCircle2 className="w-6 h-6 mx-auto text-emerald-500 mb-2" />
              <p className="text-sm text-muted-foreground">{t("kb.no_pending_files")}</p>
            </div>
          ) : (
            <div className="divide-y divide-border max-h-[30vh] overflow-y-auto">
              {pendingFiles.map((file, i) => {
                const fileName = file.file_url.split("/").pop() || file.file_url;
                return (
                  <div
                    key={file.file_url}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors"
                    data-testid={`row-pending-file-${i}`}
                  >
                    <FileText className="w-4 h-4 text-amber-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate" title={file.file_url}>
                        {file.title || fileName}
                      </p>
                      <div className="flex items-center gap-3 mt-0.5 text-[10px] text-muted-foreground">
                        {file.category && (
                          <span className="flex items-center gap-0.5">
                            <Tag className="w-2.5 h-2.5" />
                            {file.category}
                          </span>
                        )}
                        {file.status && (
                          <span className="flex items-center gap-1">
                            <StatusDot status={file.status} />
                            {file.status}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </motion.div>
      )}

      {(isCategoryMode || categories.length > 0) && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="rounded-xl border border-border bg-card overflow-hidden"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
            <div className="flex items-center gap-2">
              <Tag className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-semibold">{t("kb.categories")}</span>
              <span className="text-xs text-muted-foreground">({categories.length})</span>
            </div>
            {canManageKnowledge && (
              <button
                onClick={() => setShowAddCategory(!showAddCategory)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-muted transition-colors"
                data-testid="button-add-category"
              >
                <Plus className="w-3.5 h-3.5" />
                {t("kb.add_category")}
              </button>
            )}
          </div>

          {canManageKnowledge && showAddCategory && (
            <div className="px-4 py-3 border-b border-border bg-muted/10 flex items-center gap-2">
              <input
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                placeholder={t("kb.category_placeholder")}
                list="unmapped-categories"
                className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                data-testid="input-new-category"
              />
              <datalist id="unmapped-categories">
                {unmappedCategories.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
              <button
                onClick={() => handleAddCategory(newCategory)}
                disabled={!newCategory.trim()}
                className="px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
                data-testid="button-submit-category"
              >
                {t("kb.add")}
              </button>
              <button
                onClick={() => { setShowAddCategory(false); setNewCategory(""); }}
                className="p-1.5 rounded hover:bg-muted"
                data-testid="button-close-add-category"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          <div className="px-4 py-3 flex flex-wrap gap-2">
            {categories.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("kb.no_categories")}</p>
            ) : (
              categories.map((cat) => (
                <span
                  key={cat.name}
                  className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-primary/10 text-primary group"
                >
                  <Tag className="w-3 h-3" />
                  {cat.name}
                  {cat.file_count != null && (
                    <span className="text-[10px] text-primary/60">({cat.file_count})</span>
                  )}
                  {canManageKnowledge && (
                    <button
                      onClick={() => handleRemoveCategory(cat.name)}
                      className="ml-0.5 opacity-0 group-hover:opacity-100 hover:text-red-500 transition-all"
                      data-testid={`button-remove-category-${cat.name}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </span>
              ))
            )}
          </div>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.4 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm font-semibold">{t("kb.files")}</span>
            <span className="text-xs text-muted-foreground">({files.length})</span>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={fileSearch}
              onChange={(e) => setFileSearch(e.target.value)}
              placeholder={t("kb.search_files")}
              className="w-48 px-3 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="input-search-kb-files"
            />
            {canManageKnowledge && (
              <button
                onClick={handleOpenBindDialog}
                disabled={!canBindFiles}
                title={!canBindFiles ? t("knowledge.select_chunk_profile_first") : undefined}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                data-testid="button-bind-files"
              >
                <LinkIcon className="w-3.5 h-3.5" />
                {isManualMode ? t("kb.add_files") : t("kb.bind_file")}
              </button>
            )}
          </div>
        </div>

        {filteredFiles.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="w-8 h-8 mx-auto text-muted-foreground/30 mb-2" />
            <p className="text-sm text-muted-foreground">
              {files.length === 0 ? t("kb.no_files") : t("kb.no_files_match")}
            </p>
            {files.length === 0 && (
              <p className="text-xs text-muted-foreground/60 mt-1">{t("kb.no_files_hint")}</p>
            )}
          </div>
        ) : (
          <div className="divide-y divide-border max-h-[50vh] overflow-y-auto">
            {filteredFiles.map((file, i) => {
              const fileName = file.file_url.split("/").pop() || file.file_url;
              return (
                <div
                  key={file.file_url}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-muted/20 transition-colors"
                  data-testid={`row-kb-file-${i}`}
                >
                  <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" title={file.file_url}>
                      {file.title || fileName}
                    </p>
                    <div className="flex items-center gap-3 mt-0.5 text-[10px] text-muted-foreground">
                      {file.category && (
                        <span className="flex items-center gap-0.5">
                          <Tag className="w-2.5 h-2.5" />
                          {file.category}
                        </span>
                      )}
                      {(file.profile_name || file.chunk_profile) && (
                        <span className="font-mono">{file.profile_name || file.chunk_profile}</span>
                      )}
                      {file.chunk_count != null && (
                        <span>{file.chunk_count} chunks</span>
                      )}
                      {file.binding_mode && (
                        <span className={cn(
                          "flex items-center gap-0.5 px-1.5 py-0.5 rounded-full",
                          file.binding_mode === "follow_latest"
                            ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                            : "bg-slate-500/10 text-slate-600 dark:text-slate-400"
                        )}>
                          <Link2 className="w-2.5 h-2.5" />
                          {file.binding_mode === "follow_latest" ? t("kb.follow_latest") : t("kb.pinned")}
                        </span>
                      )}
                    </div>
                  </div>
                  {canManageKnowledge && (
                    <button
                      onClick={() => handleRemoveFile(file.file_url)}
                      className="p-1.5 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-colors shrink-0"
                      title={t("kb.remove_file")}
                      data-testid={`button-remove-file-${i}`}
                    >
                      <Unlink className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </motion.div>

      {canManageKnowledge && showBindDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" data-testid="dialog-bind-files">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-lg rounded-xl border border-border bg-card shadow-xl overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2">
                <LinkIcon className="w-5 h-5 text-primary" />
                <h3 className="text-base font-semibold">{isManualMode ? t("kb.add_files_title") : t("kb.bind_file_title")}</h3>
              </div>
              <button
                onClick={() => setShowBindDialog(false)}
                className="p-1.5 rounded hover:bg-muted transition-colors"
                data-testid="button-close-bind-dialog"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-5 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    value={bindSearch}
                    onChange={(e) => setBindSearch(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSearchBindable(bindSearch);
                    }}
                    placeholder={t("kb.bind_search_placeholder")}
                    className="w-full pl-8 pr-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                    data-testid="input-bind-search"
                  />
                </div>
                <button
                  onClick={() => handleSearchBindable(bindSearch)}
                  disabled={bindLoading}
                  className="px-3 py-2 text-sm rounded-lg bg-muted hover:bg-muted/80 transition-colors disabled:opacity-50"
                  data-testid="button-bind-search"
                >
                  {bindLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                </button>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <button
                  type="button"
                  onClick={handleSelectAllBindFiles}
                  disabled={bindableFiles.length === 0}
                  className="rounded-md border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
                  data-testid="button-select-all-bind-files"
                >
                  {bindableFiles.length > 0 && bindableFiles.every((file) => selectedBindFiles.includes(file.file_url))
                    ? t("knowledge.clear_loaded")
                    : t("knowledge.select_all")}
                </button>
                <span className="text-[11px] text-muted-foreground">
                  {selectedBindFiles.length} {t("db.selected_count")}
                </span>
              </div>
            </div>

            <div className="max-h-[40vh] overflow-y-auto divide-y divide-border">
              {bindLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : bindableFiles.length === 0 ? (
                <div className="text-center py-10">
                  <FileText className="w-8 h-8 mx-auto text-muted-foreground/30 mb-2" />
                  <p className="text-sm text-muted-foreground">{t("kb.no_selectable_files")}</p>
                </div>
              ) : (
                bindableFiles.map((file) => {
                  const selected = selectedBindFiles.includes(file.file_url);
                  const fileName = file.file_url.split("/").pop() || file.file_url;
                  return (
                    <div
                      key={file.file_url}
                      onClick={() => handleToggleBindFile(file.file_url)}
                      className={cn(
                        "flex items-center gap-3 px-5 py-3 cursor-pointer transition-colors",
                        selected ? "bg-primary/5" : "hover:bg-muted/20"
                      )}
                      data-testid={`row-bind-file-${file.file_url}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => handleToggleBindFile(file.file_url)}
                        className="accent-primary shrink-0"
                        data-testid={`checkbox-bind-file-${file.file_url}`}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{file.title || fileName}</p>
                        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
                          {file.category && (
                            <span className="flex items-center gap-0.5">
                              <Tag className="w-2.5 h-2.5" />
                              {file.category}
                            </span>
                          )}
                          {file.source_site && <span>{file.source_site}</span>}
                          {file.chunk_profile_name && <span className="font-mono">{file.chunk_profile_name}</span>}
                          {file.chunk_count != null && <span>{file.chunk_count} chunks</span>}
                        </div>
                      </div>
                      {selected && <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />}
                    </div>
                  );
                })
              )}
            </div>

            <div className="flex items-center justify-between px-5 py-4 border-t border-border bg-muted/20">
              <span className="text-xs text-muted-foreground">
                {selectedBindFiles.length > 0
                  ? `${selectedBindFiles.length} ${t("kb.files_selected")}`
                  : t("kb.select_files_hint")}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowBindDialog(false)}
                  className="px-3 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
                  data-testid="button-cancel-bind"
                >
                  {t("knowledge.cancel")}
                </button>
                <button
                  onClick={handleSubmitBindings}
                  disabled={selectedBindFiles.length === 0 || bindSubmitting}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  data-testid="button-submit-bind"
                >
                  {bindSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <LinkIcon className="w-4 h-4" />}
                  {isManualMode ? t("kb.add_files_submit") : t("kb.bind_submit")}
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
