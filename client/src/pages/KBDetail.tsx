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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";

interface KBMeta {
  kb_id: string;
  name: string;
  description?: string;
  kb_mode?: string;
  embedding_model?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  status?: string;
  file_count?: number;
  chunk_count?: number;
  index_type?: string;
  created_at?: string;
}

interface KBStats {
  file_count?: number;
  chunk_count?: number;
  pending_count?: number;
  indexed_count?: number;
}

interface KBFile {
  file_url: string;
  title?: string;
  category?: string;
  chunk_set_id?: string;
  binding_mode?: string;
  chunk_count?: number;
  profile_name?: string;
  status?: string;
}

interface KBCategory {
  name: string;
  file_count?: number;
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

export default function KBDetail() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const [match, params] = useRoute("/knowledge/:kbId");
  const kbId = params?.kbId ? decodeURIComponent(params.kbId) : "";

  const [meta, setMeta] = useState<KBMeta | null>(null);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [files, setFiles] = useState<KBFile[]>([]);
  const [categories, setCategories] = useState<KBCategory[]>([]);
  const [unmappedCategories, setUnmappedCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [indexing, setIndexing] = useState(false);

  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [hasEdits, setHasEdits] = useState(false);

  const [showAddCategory, setShowAddCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");

  const [fileSearch, setFileSearch] = useState("");

  const loadMeta = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<KBMeta | { data: KBMeta }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`);
      const m = (res as { data: KBMeta }).data || (res as KBMeta);
      setMeta(m);
      setEditName(m.name || "");
      setEditDesc(m.description || "");
    } catch {
      setMeta(null);
    }
  }, [kbId]);

  const loadStats = useCallback(async () => {
    if (!kbId) return;
    try {
      const res = await apiGet<KBStats | { data: KBStats }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/stats`);
      setStats((res as { data: KBStats }).data || (res as KBStats));
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
      const res = await apiGet<{ categories?: KBCategory[]; data?: { categories?: KBCategory[] } }>(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/categories`);
      setCategories(res.data?.categories || res.categories || []);
    } catch {
      setCategories([]);
    }
    try {
      const res2 = await apiGet<{ categories?: string[]; data?: { categories?: string[] } }>("/api/rag/categories/unmapped");
      setUnmappedCategories(res2.data?.categories || res2.categories || []);
    } catch {
      setUnmappedCategories([]);
    }
  }, [kbId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadMeta(), loadStats(), loadFiles(), loadCategories()]);
    setLoading(false);
  }, [loadMeta, loadStats, loadFiles, loadCategories]);

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
    try {
      await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/categories`, {
        categories: [cat.trim()],
        action: "add",
      });
      setNewCategory("");
      setShowAddCategory(false);
      await loadCategories();
    } catch (err) {
      console.error("Failed to add category:", err);
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
    try {
      const endpoint = force
        ? `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index/build`
        : `/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index`;
      await apiPost(endpoint, force ? {} : { incremental: true });
      await loadStats();
    } catch (err) {
      console.error("Failed to build index:", err);
    } finally {
      setIndexing(false);
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

  const pendingCount = stats?.pending_count ?? 0;

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
            </div>
            {hasEdits && (
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
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.4 }}
        className="grid grid-cols-2 sm:grid-cols-4 gap-3"
      >
        {[
          { label: t("kb.stat_files"), value: stats?.file_count ?? meta.file_count ?? 0, icon: FileText, color: "text-blue-500" },
          { label: t("kb.stat_chunks"), value: stats?.chunk_count ?? meta.chunk_count ?? 0, icon: Layers, color: "text-violet-500" },
          { label: t("kb.stat_indexed"), value: stats?.indexed_count ?? 0, icon: CheckCircle2, color: "text-emerald-500" },
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
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50"
          data-testid="button-index-rebuild"
        >
          <RefreshCw className={cn("w-4 h-4", indexing && "animate-spin")} />
          {t("kb.rebuild_index")}
        </button>
      </motion.div>

      {(meta.kb_mode === "category" || categories.length > 0) && (
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
            <button
              onClick={() => setShowAddCategory(!showAddCategory)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-muted transition-colors"
              data-testid="button-add-category"
            >
              <Plus className="w-3.5 h-3.5" />
              {t("kb.add_category")}
            </button>
          </div>

          {showAddCategory && (
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
                  <button
                    onClick={() => handleRemoveCategory(cat.name)}
                    className="ml-0.5 opacity-0 group-hover:opacity-100 hover:text-red-500 transition-all"
                    data-testid={`button-remove-category-${cat.name}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
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
          <input
            value={fileSearch}
            onChange={(e) => setFileSearch(e.target.value)}
            placeholder={t("kb.search_files")}
            className="w-48 px-3 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
            data-testid="input-search-kb-files"
          />
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
                      {file.profile_name && (
                        <span className="font-mono">{file.profile_name}</span>
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
                  <button
                    onClick={() => handleRemoveFile(file.file_url)}
                    className="p-1.5 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-colors shrink-0"
                    title={t("kb.remove_file")}
                    data-testid={`button-remove-file-${i}`}
                  >
                    <Unlink className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </motion.div>
    </div>
  );
}
