import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation } from "wouter";
import {
  BookOpen,
  Plus,
  FileText,
  Layers,
  Tag,
  Inbox,
  X,
  Loader2,
  Settings2,
  Trash2,
  Eye,
  AlertTriangle,
  FolderOpen,
  Sparkles,
  RefreshCw,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";

interface KnowledgeBase {
  id: string;
  kb_id?: string;
  name: string;
  description?: string;
  document_count?: number;
  file_count?: number;
  chunk_count?: number;
  status?: string;
  availability?: string;
  categories?: string[];
  embedding_model?: string;
  index_embedding_model?: string;
  needs_reindex?: boolean;
  embedding_compatible?: boolean;
  current_embeddings?: {
    provider?: string;
    model?: string;
    dimension?: number;
  };
  kb_mode?: string;
}

interface ChunkProfile {
  profile_id?: string;
  name: string;
  chunk_size: number;
  chunk_overlap: number;
  splitter?: string;
  tokenizer?: string;
}

interface CurrentEmbedding {
  provider?: string;
  model?: string;
  dimension?: number;
}

interface SelectableFile {
  url: string;
  title?: string;
  original_filename?: string;
  source_site?: string;
  category?: string;
  markdown_updated_at?: string;
  chunk_set_id?: string;
  chunk_profile_id?: string;
  chunk_profile_name?: string;
  chunk_count?: number;
}

interface CategoryOption {
  name: string;
  count?: number | null;
}

const emptyKbForm = {
  name: "",
  kb_id: "",
  description: "",
  categories: [] as string[],
  file_urls: [] as string[],
  kb_mode: "manual",
  chunk_profile_id: "",
};

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.35, ease: "easeOut" as const },
  }),
};

function StatusBadge({ status }: { status?: string }) {
  const s = status?.toLowerCase() || "unknown";
  const colors =
    s === "active" || s === "ready"
      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
      : s === "building" || s === "indexing"
        ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
        : "bg-muted text-muted-foreground";

  return (
    <span
      className={cn("inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full", colors)}
      data-testid="status-badge"
    >
      {status || "unknown"}
    </span>
  );
}

function ModeBadge({ mode }: { mode?: string }) {
  if (!mode) return null;
  const isCategory = mode === "category";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full",
        isCategory
          ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
          : "bg-slate-500/10 text-slate-600 dark:text-slate-400"
      )}
    >
      {isCategory ? <FolderOpen className="w-2.5 h-2.5" /> : <Sparkles className="w-2.5 h-2.5" />}
      {mode}
    </span>
  );
}

function normalizeCategoryNames(items: unknown): string[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (item && typeof item === "object" && "name" in item) {
        return String((item as CategoryOption).name || "").trim();
      }
      return "";
    })
    .filter((item, index, all): item is string => Boolean(item) && all.indexOf(item) === index);
}

export default function Knowledge() {
  const { t } = useTranslation();
  const [, navigate] = useLocation();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [profiles, setProfiles] = useState<ChunkProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateKB, setShowCreateKB] = useState(false);
  const [showCreateProfile, setShowCreateProfile] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleteProfileConfirm, setDeleteProfileConfirm] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [indexingKb, setIndexingKb] = useState<string | null>(null);
  const [currentEmbedding, setCurrentEmbedding] = useState<CurrentEmbedding | null>(null);
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [selectableFiles, setSelectableFiles] = useState<SelectableFile[]>([]);
  const [fileSearch, setFileSearch] = useState("");
  const [selectableFilesLoading, setSelectableFilesLoading] = useState(false);
  const [categoryStats, setCategoryStats] = useState<Record<string, number> | null>(null);
  const [categoryStatsLoading, setCategoryStatsLoading] = useState(false);

  const [kbForm, setKbForm] = useState(emptyKbForm);

  const [profileForm, setProfileForm] = useState({
    name: "",
    chunk_size: 512,
    overlap: 50,
    splitter: "semantic",
    tokenizer: "cl100k_base",
  });

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      apiGet<Record<string, unknown>>("/api/rag/knowledge-bases").catch(() => null),
      apiGet<Record<string, unknown>>("/api/chunk/profiles").catch(() => null),
      apiGet<Record<string, unknown>>("/api/rag/categories/mapping").catch(() => null),
      apiGet<Record<string, unknown>>("/api/categories?mode=used").catch(() => null),
    ])
      .then(([kbResp, profileResp, ragCategoriesResp, usedCategoriesResp]) => {
        const kbPayload = kbResp as {
          knowledge_bases?: KnowledgeBase[];
          current_embeddings?: CurrentEmbedding;
          data?: { knowledge_bases?: KnowledgeBase[]; current_embeddings?: CurrentEmbedding };
        } | null;
        const kbList: KnowledgeBase[] = kbPayload?.knowledge_bases || kbPayload?.data?.knowledge_bases || [];
        setKbs(kbList);
        setCurrentEmbedding(kbPayload?.current_embeddings || kbPayload?.data?.current_embeddings || null);

        const profilePayload = profileResp as { profiles?: ChunkProfile[]; data?: ChunkProfile[] | { profiles?: ChunkProfile[] } } | null;
        const legacyProfiles = profilePayload?.data;
        const pList: ChunkProfile[] = Array.isArray(profilePayload?.profiles)
          ? profilePayload.profiles
          : Array.isArray(legacyProfiles)
            ? legacyProfiles
            : Array.isArray((legacyProfiles as Record<string, unknown> | undefined)?.profiles)
              ? ((legacyProfiles as Record<string, unknown>).profiles as ChunkProfile[])
              : [];
        setProfiles(pList);

        const ragCategories = normalizeCategoryNames((ragCategoriesResp as { categories?: unknown[] } | null)?.categories);
        const usedCategories = normalizeCategoryNames((usedCategoriesResp as { categories?: unknown[] } | null)?.categories);
        setCategoryOptions(Array.from(new Set([...ragCategories, ...usedCategories])).sort((a, b) => a.localeCompare(b)));
      })
      .finally(() => setLoading(false));
  }, []);

  const loadSelectableFiles = useCallback((query = "") => {
    if (!kbForm.chunk_profile_id) {
      setSelectableFiles([]);
      setSelectableFilesLoading(false);
      return;
    }
    setSelectableFilesLoading(true);
    const params = new URLSearchParams({ limit: "50" });
    params.set("profile_id", kbForm.chunk_profile_id);
    const normalizedQuery = query.trim();
    if (normalizedQuery) params.set("query", normalizedQuery);
    apiGet<{ files?: SelectableFile[]; data?: { files?: SelectableFile[] } }>(`/api/rag/files/selectable?${params.toString()}`)
      .then((res) => setSelectableFiles(res.files || res.data?.files || []))
      .catch(() => setSelectableFiles([]))
      .finally(() => setSelectableFilesLoading(false));
  }, [kbForm.chunk_profile_id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!showCreateKB || kbForm.chunk_profile_id) return;
    const defaultProfileId = profiles.find((profile) => profile.profile_id)?.profile_id || "";
    if (defaultProfileId) {
      setKbForm((current) => current.chunk_profile_id ? current : { ...current, chunk_profile_id: defaultProfileId });
    }
  }, [kbForm.chunk_profile_id, profiles, showCreateKB]);

  useEffect(() => {
    if (!showCreateKB || kbForm.kb_mode !== "manual") return;
    const timer = window.setTimeout(() => loadSelectableFiles(fileSearch), 250);
    return () => window.clearTimeout(timer);
  }, [fileSearch, kbForm.chunk_profile_id, kbForm.kb_mode, loadSelectableFiles, showCreateKB]);

  useEffect(() => {
    if (!showCreateKB || kbForm.kb_mode !== "category" || kbForm.categories.length === 0 || !kbForm.chunk_profile_id) {
      setCategoryStats(null);
      setCategoryStatsLoading(false);
      return;
    }
    setCategoryStatsLoading(true);
    apiPost<{ totals?: Record<string, number> }>("/api/rag/categories/stats", {
      categories: kbForm.categories,
      profile_id: kbForm.chunk_profile_id,
    })
      .then((res) => setCategoryStats(res.totals || null))
      .catch(() => setCategoryStats(null))
      .finally(() => setCategoryStatsLoading(false));
  }, [kbForm.categories, kbForm.chunk_profile_id, kbForm.kb_mode, showCreateKB]);

  const generateKbId = (name: string) => {
    return name.trim().toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 60) || "kb";
  };

  const handleCreateKB = async (createAndIndex = false) => {
    if (!kbForm.name.trim()) return;
    if (!kbForm.chunk_profile_id) return;
    if (kbForm.kb_mode === "category" && kbForm.categories.length === 0) return;
    if (kbForm.kb_mode === "manual" && kbForm.file_urls.length === 0) return;
    const finalKbId = kbForm.kb_id.trim() || generateKbId(kbForm.name);
    setCreating(true);
    try {
      await apiPost("/api/rag/knowledge-bases", {
        kb_id: finalKbId,
        name: kbForm.name,
        description: kbForm.description,
        categories: kbForm.categories,
        file_urls: kbForm.kb_mode === "manual" ? kbForm.file_urls : [],
        kb_mode: kbForm.kb_mode,
        chunk_profile_id: kbForm.chunk_profile_id,
      });
      if (createAndIndex) {
        await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(finalKbId)}/index`, {
          incremental: true,
        });
      }
      const defaultProfileId = profiles.find((profile) => profile.profile_id)?.profile_id || "";
      setKbForm({ ...emptyKbForm, chunk_profile_id: defaultProfileId });
      setFileSearch("");
      closeCreateKB();
      loadData();
    } catch (err) {
      console.error("Failed to create KB:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKB = async (kbId: string) => {
    setDeleting(true);
    try {
      await apiDelete(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}`);
      setDeleteConfirm(null);
      loadData();
    } catch (err) {
      console.error("Failed to delete KB:", err);
    } finally {
      setDeleting(false);
    }
  };

  const handleReembedKB = async (kbId: string) => {
    setIndexingKb(kbId);
    try {
      await apiPost(`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/index`, {
        force_reindex: true,
      });
      loadData();
    } catch (err) {
      console.error("Failed to re-embed KB:", err);
    } finally {
      setIndexingKb(null);
    }
  };

  const toggleKbCategory = (category: string) => {
    setKbForm((current) => ({
      ...current,
      categories: current.categories.includes(category)
        ? current.categories.filter((item) => item !== category)
        : [...current.categories, category],
    }));
  };

  const toggleKbFile = (fileUrl: string) => {
    setKbForm((current) => ({
      ...current,
      file_urls: current.file_urls.includes(fileUrl)
        ? current.file_urls.filter((item) => item !== fileUrl)
        : [...current.file_urls, fileUrl],
    }));
  };

  const handleCreateProfile = async () => {
    if (!profileForm.name.trim()) return;
    setCreating(true);
    try {
      await apiPost("/api/chunk/profiles", {
        name: profileForm.name,
        chunk_size: profileForm.chunk_size,
        chunk_overlap: profileForm.overlap,
        splitter: profileForm.splitter,
        tokenizer: profileForm.tokenizer,
      });
      setProfileForm({ name: "", chunk_size: 512, overlap: 50, splitter: "semantic", tokenizer: "cl100k_base" });
      closeCreateProfile();
      loadData();
    } catch (err) {
      console.error("Failed to create profile:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteProfile = async (profileId: string) => {
    try {
      await apiDelete(`/api/chunk/profiles/${encodeURIComponent(profileId)}`);
      loadData();
    } catch (err) {
      console.error("Failed to delete profile:", err);
    }
  };

  const [showCleanup, setShowCleanup] = useState(false);
  const [cleanupDays, setCleanupDays] = useState(30);
  const [cleanupDryRun, setCleanupDryRun] = useState(true);
  const [cleanupRunning, setCleanupRunning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<Record<string, unknown> | null>(null);

  const openCreateKB = () => {
    setShowCreateProfile(false);
    setShowCreateKB(true);
  };

  const closeCreateKB = () => {
    setShowCreateKB(false);
  };

  const openCreateProfile = () => {
    setShowCreateKB(false);
    setShowCreateProfile(true);
  };

  const closeCreateProfile = () => {
    setShowCreateProfile(false);
  };

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("open") === "create") {
      setShowCreateProfile(false);
      setShowCreateKB(true);
    }
  }, []);

  const handleCleanup = async () => {
    setCleanupRunning(true);
    setCleanupResult(null);
    try {
      const res = await apiPost<Record<string, unknown>>("/api/chunk-sets/cleanup", {
        older_than_days: cleanupDays,
        dry_run: cleanupDryRun,
        limit: 5000,
      });
      setCleanupResult((res as Record<string, unknown>)?.data as Record<string, unknown> || res);
      if (!cleanupDryRun) loadData();
    } catch (err) {
      console.error("Cleanup failed:", err);
    } finally {
      setCleanupRunning(false);
    }
  };

  const getKbId = (kb: KnowledgeBase) => kb.kb_id || kb.id;

  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">
            {t("knowledge.title")}
          </h1>
          <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
            {t("knowledge.subtitle")}
          </p>
        </div>
        <button
          onClick={openCreateKB}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          data-testid="button-create-kb"
        >
          <Plus className="w-4 h-4" />
          {t("knowledge.create")}
        </button>
      </motion.div>

      <AnimatePresence>
        {showCreateKB && (
          <motion.div
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            className="rounded-xl border border-border bg-card p-6 overflow-hidden"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-sm">{t("knowledge.create_title")}</h3>
              <button
                type="button"
                aria-label="Close create knowledge base panel"
                onClick={closeCreateKB}
                className="p-2 rounded hover:bg-muted"
                data-testid="button-close-create-kb"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.name")} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={kbForm.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setKbForm((f) => ({
                      ...f,
                      name,
                      kb_id: f.kb_id === "" || f.kb_id === generateKbId(f.name) ? "" : f.kb_id,
                    }));
                  }}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  placeholder={t("knowledge.name_placeholder")}
                  data-testid="input-kb-name"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.kb_id_label")}
                </label>
                <input
                  type="text"
                  value={kbForm.kb_id || (kbForm.name ? generateKbId(kbForm.name) : "")}
                  onChange={(e) => setKbForm({ ...kbForm, kb_id: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30"
                  placeholder={t("knowledge.kb_id_placeholder")}
                  data-testid="input-kb-id"
                />
                <p className="text-[10px] text-muted-foreground mt-1">{t("knowledge.kb_id_hint")}</p>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.mode")}
                </label>
                <select
                  value={kbForm.kb_mode}
                  onChange={(e) => setKbForm({ ...kbForm, kb_mode: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  data-testid="select-kb-mode"
                >
                  <option value="manual">{t("knowledge.mode_manual")}</option>
                  <option value="category">{t("knowledge.mode_category")}</option>
                </select>
                <p className="text-[10px] text-muted-foreground mt-1">{t("knowledge.mode_hint")}</p>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.chunk_profile")} <span className="text-red-500">*</span>
                </label>
                <select
                  value={kbForm.chunk_profile_id}
                  onChange={(e) => {
                    setKbForm({ ...kbForm, chunk_profile_id: e.target.value, file_urls: [] });
                    setSelectableFiles([]);
                  }}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  data-testid="select-kb-chunk-profile"
                  disabled={profiles.length === 0}
                >
                  {profiles.length === 0 ? (
                    <option value="">{t("knowledge.no_profiles")}</option>
                  ) : (
                    profiles.map((profile) => (
                      <option key={profile.profile_id || profile.name} value={profile.profile_id || ""}>
                        {profile.name} ({profile.chunk_size}/{profile.chunk_overlap})
                      </option>
                    ))
                  )}
                </select>
                <p className="text-[10px] text-muted-foreground mt-1">{t("knowledge.chunk_profile_hint")}</p>
              </div>
              <div className="sm:col-span-2">
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.description")}
                </label>
                <textarea
                  value={kbForm.description}
                  onChange={(e) => setKbForm({ ...kbForm, description: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                  rows={2}
                  placeholder={t("knowledge.desc_placeholder")}
                  data-testid="input-kb-description"
                />
                <p className="text-[11px] text-muted-foreground/70 mt-1">{t("knowledge.desc_guidance")}</p>
              </div>
              {kbForm.kb_mode === "category" && (
                <div className="sm:col-span-2 rounded-lg border border-border bg-muted/20 p-3" data-testid="kb-category-picker">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <label className="text-xs font-medium text-muted-foreground">
                      {t("knowledge.categories")} <span className="text-amber-600">({t("knowledge.required")})</span>
                    </label>
                    <span className="text-[11px] text-muted-foreground">
                      {kbForm.categories.length} {t("db.selected_count")}
                    </span>
                  </div>
                  {(categoryStatsLoading || categoryStats) && (
                    <div className="mb-3 rounded-lg border border-border bg-background px-3 py-2 text-[11px] text-muted-foreground" data-testid="kb-category-stats">
                      {categoryStatsLoading ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {t("tasks.form.loading_stats")}
                        </span>
                      ) : categoryStats ? (
                        <span>
                          {t("knowledge.category_stats")}:
                          {" "}{categoryStats.total_files || 0} {t("kb.stat_files")},
                          {" "}{categoryStats.markdown_files || 0} Markdown,
                          {" "}{categoryStats.ready_chunk_files || 0} {t("knowledge.chunks")}
                        </span>
                      ) : null}
                    </div>
                  )}
                  {categoryOptions.length === 0 ? (
                    <p className="text-xs text-muted-foreground py-2">{t("knowledge.no_categories_available")}</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {categoryOptions.map((category) => {
                        const selected = kbForm.categories.includes(category);
                        return (
                          <button
                            key={category}
                            type="button"
                            onClick={() => toggleKbCategory(category)}
                            className={cn(
                              "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                              selected
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-border bg-background text-muted-foreground hover:text-foreground hover:bg-muted"
                            )}
                            data-testid={`button-toggle-kb-category-${category}`}
                          >
                            {category}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
              {kbForm.kb_mode === "manual" && (
                <div className="sm:col-span-2 rounded-lg border border-border bg-muted/20 p-3" data-testid="kb-document-picker">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
                    <label className="text-xs font-medium text-muted-foreground">{t("knowledge.select_documents")}</label>
                    <span className="text-[11px] text-muted-foreground">
                      {kbForm.file_urls.length} {t("db.selected_count")}
                    </span>
                  </div>
                  <div className="relative mb-3">
                    <input
                      type="text"
                      value={fileSearch}
                      onChange={(e) => setFileSearch(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                      placeholder={t("knowledge.document_search_placeholder")}
                      data-testid="input-kb-document-search"
                    />
                    {selectableFilesLoading && (
                      <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />
                    )}
                  </div>
                  {!kbForm.chunk_profile_id ? (
                    <p className="text-xs text-muted-foreground py-2">{t("knowledge.select_chunk_profile_first")}</p>
                  ) : selectableFiles.length === 0 && !selectableFilesLoading ? (
                    <p className="text-xs text-muted-foreground py-2">{t("knowledge.no_selectable_chunk_files")}</p>
                  ) : (
                    <div className="max-h-56 overflow-y-auto rounded-lg border border-border bg-background divide-y divide-border">
                      {selectableFiles.map((file) => {
                        const selected = kbForm.file_urls.includes(file.url);
                        const title = file.title || file.original_filename || file.url;
                        return (
                          <button
                            key={file.url}
                            type="button"
                            onClick={() => toggleKbFile(file.url)}
                            className={cn(
                              "flex w-full items-start gap-3 px-3 py-2 text-left transition-colors",
                              selected ? "bg-primary/10" : "hover:bg-muted/70"
                            )}
                            data-testid={`button-toggle-kb-file-${file.url}`}
                          >
                            <span
                              className={cn(
                                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                                selected ? "border-primary bg-primary text-primary-foreground" : "border-border"
                              )}
                            >
                              {selected ? <Check className="h-3 w-3" /> : null}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium text-foreground">{title}</span>
                              <span className="mt-0.5 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                                {file.category && <span>{file.category}</span>}
                                {file.source_site && <span>{file.source_site}</span>}
                                {typeof file.chunk_count === "number" && <span>{file.chunk_count} {t("knowledge.chunks")}</span>}
                              </span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="flex justify-end mt-4 gap-2">
              <button
                type="button"
                onClick={closeCreateKB}
                className="px-4 py-2 rounded-lg border border-border bg-background text-sm font-medium hover:bg-muted transition-colors"
                data-testid="button-cancel-kb"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={() => handleCreateKB(false)}
                disabled={
                  creating
                  || !kbForm.name.trim()
                  || !kbForm.chunk_profile_id
                  || (kbForm.kb_mode === "category" && kbForm.categories.length === 0)
                  || (kbForm.kb_mode === "manual" && kbForm.file_urls.length === 0)
                }
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                data-testid="button-submit-kb"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                {t("knowledge.create")}
              </button>
              <button
                onClick={() => handleCreateKB(true)}
                disabled={
                  creating
                  || !kbForm.name.trim()
                  || !kbForm.chunk_profile_id
                  || (kbForm.kb_mode === "category" && kbForm.categories.length === 0)
                  || (kbForm.kb_mode === "manual" && kbForm.file_urls.length === 0)
                }
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 transition-colors disabled:opacity-50"
                data-testid="button-submit-kb-index"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                {t("knowledge.create_and_index")}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-52 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : kbs.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16 rounded-xl border border-dashed border-border bg-card"
        >
          <Inbox className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
          <p className="font-medium text-muted-foreground" data-testid="text-no-kbs">
            {t("knowledge.no_kbs")}
          </p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            {t("knowledge.no_kbs_desc")}
          </p>
        </motion.div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {kbs.map((kb, i) => {
            const kbId = getKbId(kb);
            const needsReembed = kb.needs_reindex || kb.embedding_compatible === false;
            const status = kb.availability || kb.status;
            const cardEmbeddingLabel = kb.current_embeddings?.model || currentEmbedding?.model || kb.embedding_model || "";
            return (
              <motion.div
                key={kbId}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className="rounded-xl border border-border bg-card hover:border-primary/30 hover:shadow-md transition-all group relative"
                data-testid={`card-kb-${kbId}`}
              >
                <div className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-10 h-10 rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400 flex items-center justify-center shrink-0">
                      <BookOpen className="w-5 h-5" strokeWidth={1.8} />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <ModeBadge mode={kb.kb_mode} />
                      <StatusBadge status={status} />
                    </div>
                  </div>
                  <h3 className="font-semibold text-sm mb-1" data-testid={`text-kb-name-${kbId}`}>
                    {kb.name}
                  </h3>
                  {kb.description ? (
                    <p className="text-xs text-muted-foreground leading-relaxed mb-3 line-clamp-2">
                      {kb.description}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground/50 italic mb-3">
                      {t("knowledge.no_description")}
                    </p>
                  )}
                  {kb.embedding_model && (
                    <p className="text-[10px] text-muted-foreground/70 mb-2 font-mono truncate">
                      {kb.embedding_model}
                    </p>
                  )}
                  {needsReembed && (
                    <div
                      className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3"
                      data-testid={`banner-reembed-kb-${kbId}`}
                    >
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium text-amber-800 dark:text-amber-300">
                            {t("knowledge.needs_reembed")}
                          </p>
                          <p className="text-[10px] text-amber-700/80 dark:text-amber-300/80 mt-0.5 font-mono truncate">
                            {cardEmbeddingLabel}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleReembedKB(kbId)}
                        disabled={indexingKb === kbId}
                        className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-amber-600 text-white text-xs font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors"
                        data-testid={`button-reembed-kb-${kbId}`}
                      >
                        <RefreshCw className={cn("w-3.5 h-3.5", indexingKb === kbId && "animate-spin")} />
                        {t("knowledge.reembed")}
                      </button>
                    </div>
                  )}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground pt-3 border-t border-border">
                    <span className="flex items-center gap-1" data-testid={`text-kb-docs-${kbId}`}>
                      <FileText className="w-3.5 h-3.5" />
                      {kb.file_count ?? kb.document_count ?? 0} {t("knowledge.documents")}
                    </span>
                    <span className="flex items-center gap-1" data-testid={`text-kb-chunks-${kbId}`}>
                      <Layers className="w-3.5 h-3.5" />
                      {kb.chunk_count ?? 0} {t("knowledge.chunks")}
                    </span>
                  </div>
                  {kb.categories && kb.categories.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {kb.categories.slice(0, 4).map((cat) => (
                        <span
                          key={cat}
                          className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary"
                        >
                          <Tag className="w-2.5 h-2.5" />
                          {cat}
                        </span>
                      ))}
                      {kb.categories.length > 4 && (
                        <span className="text-[10px] text-muted-foreground">
                          +{kb.categories.length - 4}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="flex border-t border-border">
                  <button
                    onClick={() => navigate(`/knowledge/${encodeURIComponent(kbId)}`)}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium text-primary hover:bg-primary/5 transition-colors rounded-bl-xl"
                    data-testid={`button-view-kb-${kbId}`}
                  >
                    <Eye className="w-3.5 h-3.5" />
                    {t("knowledge.view_detail")}
                  </button>
                  <div className="w-px bg-border" />
                  <button
                    onClick={() => setDeleteConfirm(kbId)}
                    className="flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium text-red-500 hover:bg-red-500/5 transition-colors rounded-br-xl"
                    data-testid={`button-delete-kb-${kbId}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <ConfirmDeleteModal
                  open={deleteConfirm === kbId}
                  onClose={() => setDeleteConfirm(null)}
                  onConfirm={() => handleDeleteKB(kbId)}
                  title={t("knowledge.delete_confirm")}
                  message={t("knowledge.delete_warn")}
                  loading={deleting}
                />
              </motion.div>
            );
          })}
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Settings2 className="w-5 h-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold">{t("knowledge.chunk_profiles")}</h2>
          </div>
          <button
            onClick={openCreateProfile}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm font-medium hover:bg-muted transition-colors"
            data-testid="button-create-profile"
          >
            <Plus className="w-4 h-4" />
            {t("knowledge.create_profile")}
          </button>
        </div>

        <AnimatePresence>
          {showCreateProfile && (
            <motion.div
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              className="rounded-xl border border-border bg-card p-6 mb-4 overflow-hidden"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-sm">{t("knowledge.create_profile_title")}</h3>
                <button
                  type="button"
                  aria-label="Close create chunk profile panel"
                  onClick={closeCreateProfile}
                  className="p-2 rounded hover:bg-muted"
                  data-testid="button-close-create-profile"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    {t("knowledge.profile_name")}
                  </label>
                  <input
                    type="text"
                    value={profileForm.name}
                    onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    placeholder={t("knowledge.profile_name_placeholder")}
                    data-testid="input-profile-name"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    {t("knowledge.chunk_size")}
                  </label>
                  <input
                    type="number"
                    value={profileForm.chunk_size}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, chunk_size: parseInt(e.target.value) || 512 })
                    }
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    min={64}
                    max={8192}
                    data-testid="input-chunk-size"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    {t("knowledge.overlap")}
                  </label>
                  <input
                    type="number"
                    value={profileForm.overlap}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, overlap: parseInt(e.target.value) || 50 })
                    }
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    min={0}
                    max={1024}
                    data-testid="input-overlap"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    {t("knowledge.splitter")}
                  </label>
                  <select
                    value={profileForm.splitter}
                    onChange={(e) => setProfileForm({ ...profileForm, splitter: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    data-testid="select-profile-splitter"
                  >
                    <option value="semantic">{t("knowledge.splitter_semantic")}</option>
                    <option value="recursive">{t("knowledge.splitter_recursive")}</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    {t("knowledge.tokenizer")}
                  </label>
                  <select
                    value={profileForm.tokenizer}
                    onChange={(e) => setProfileForm({ ...profileForm, tokenizer: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    data-testid="select-profile-tokenizer"
                  >
                    <option value="cl100k_base">cl100k_base</option>
                    <option value="p50k_base">p50k_base</option>
                    <option value="o200k_base">o200k_base</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end mt-4 gap-2">
                <button
                  type="button"
                  onClick={closeCreateProfile}
                  className="px-4 py-2 rounded-lg border border-border bg-background text-sm font-medium hover:bg-muted transition-colors"
                  data-testid="button-cancel-profile"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleCreateProfile}
                  disabled={creating || !profileForm.name.trim()}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                  data-testid="button-submit-profile"
                >
                  {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                  {t("knowledge.create_profile")}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {profiles.length === 0 ? (
          <div className="text-center py-8 rounded-xl border border-dashed border-border bg-card">
            <p className="text-sm text-muted-foreground" data-testid="text-no-profiles">
              {t("knowledge.no_profiles")}
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-card overflow-x-auto">
            <table className="w-full min-w-[540px] text-sm">
              <thead>
                <tr className="bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  <th className="text-left px-4 py-2.5 whitespace-nowrap">{t("knowledge.profile_name")}</th>
                  <th className="text-right px-4 py-2.5 whitespace-nowrap">{t("knowledge.chunk_size")}</th>
                  <th className="text-right px-4 py-2.5 whitespace-nowrap">{t("knowledge.overlap")}</th>
                  <th className="text-left px-4 py-2.5 whitespace-nowrap">{t("knowledge.splitter")}</th>
                  <th className="text-left px-4 py-2.5 whitespace-nowrap">{t("knowledge.tokenizer")}</th>
                  <th className="w-10 px-2 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {profiles.map((profile, i) => (
                  <tr
                    key={profile.profile_id || profile.name}
                    className="border-t border-border hover:bg-muted/30 transition-colors"
                    data-testid={`row-profile-${i}`}
                  >
                    <td className="px-4 py-3 font-medium whitespace-nowrap">{profile.name}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground tabular-nums">{profile.chunk_size}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground tabular-nums">{profile.chunk_overlap}</td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{profile.splitter || "-"}</td>
                    <td className="px-4 py-3 text-muted-foreground font-mono whitespace-nowrap">{profile.tokenizer || "-"}</td>
                    <td className="px-2 py-3 text-center">
                      <button
                        onClick={() => profile.profile_id && setDeleteProfileConfirm(profile.profile_id)}
                        className="p-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-colors"
                        data-testid={`button-delete-profile-${i}`}
                        title={t("knowledge.delete_profile")}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <ConfirmDeleteModal
          open={!!deleteProfileConfirm}
          onClose={() => setDeleteProfileConfirm(null)}
          onConfirm={() => {
            if (deleteProfileConfirm) {
              handleDeleteProfile(deleteProfileConfirm);
              setDeleteProfileConfirm(null);
            }
          }}
          title={t("knowledge.delete_profile")}
          message={t("knowledge.confirm_delete_profile")}
        />

        <div className="flex items-center gap-3 mt-4">
          <button
            onClick={() => { setShowCleanup(!showCleanup); setCleanupResult(null); }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-muted/50 transition-colors"
            data-testid="button-toggle-cleanup"
          >
            <Trash2 className="w-3.5 h-3.5" />
            {t("knowledge.cleanup_orphan")}
          </button>
        </div>

        <AnimatePresence>
          {showCleanup && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="rounded-xl border border-border bg-card p-5 overflow-hidden"
            >
              <h4 className="text-sm font-semibold mb-3">{t("knowledge.cleanup_title")}</h4>
              <p className="text-xs text-muted-foreground mb-4">{t("knowledge.cleanup_desc")}</p>
              <div className="flex flex-wrap items-end gap-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1 block">
                    {t("knowledge.cleanup_days")}
                  </label>
                  <input
                    type="number"
                    value={cleanupDays}
                    onChange={(e) => setCleanupDays(parseInt(e.target.value) || 30)}
                    className="w-24 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    min={1}
                    max={365}
                    data-testid="input-cleanup-days"
                  />
                </div>
                <label className="flex items-center gap-2 text-sm cursor-pointer py-2">
                  <input
                    type="checkbox"
                    checked={cleanupDryRun}
                    onChange={(e) => setCleanupDryRun(e.target.checked)}
                    className="rounded border-border"
                    data-testid="checkbox-cleanup-dryrun"
                  />
                  <span className="text-xs text-muted-foreground">{t("knowledge.cleanup_dryrun")}</span>
                </label>
                <button
                  onClick={handleCleanup}
                  disabled={cleanupRunning}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50",
                    cleanupDryRun
                      ? "bg-primary text-primary-foreground hover:bg-primary/90"
                      : "bg-red-600 text-white hover:bg-red-700"
                  )}
                  data-testid="button-run-cleanup"
                >
                  {cleanupRunning && <Loader2 className="w-4 h-4 animate-spin" />}
                  {cleanupDryRun ? t("knowledge.cleanup_preview") : t("knowledge.cleanup_run")}
                </button>
              </div>
              {cleanupResult && (
                <div className="mt-4 p-3 rounded-lg bg-muted/50 text-xs font-mono whitespace-pre-wrap" data-testid="text-cleanup-result">
                  {JSON.stringify(cleanupResult, null, 2)}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
