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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";

interface KnowledgeBase {
  id: string;
  kb_id?: string;
  name: string;
  description?: string;
  document_count?: number;
  file_count?: number;
  chunk_count?: number;
  status?: string;
  categories?: string[];
  embedding_model?: string;
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
  const [deleting, setDeleting] = useState(false);

  const [kbForm, setKbForm] = useState({
    name: "",
    description: "",
    categories: "",
    embedding_model: "",
    kb_mode: "manual",
  });

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
    ])
      .then(([kbResp, profileResp]) => {
        const kbRaw = kbResp?.data;
        const kbList: KnowledgeBase[] = Array.isArray(kbRaw) ? kbRaw : [];
        setKbs(kbList);

        const profRaw = profileResp?.data;
        const pList: ChunkProfile[] = Array.isArray(profRaw)
          ? profRaw
          : Array.isArray((profRaw as Record<string, unknown>)?.profiles)
            ? (profRaw as Record<string, unknown>).profiles as ChunkProfile[]
            : [];
        setProfiles(pList);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const generateKbId = (name: string) => {
    return name.trim().toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 60) || "kb";
  };

  const handleCreateKB = async () => {
    if (!kbForm.name.trim()) return;
    setCreating(true);
    try {
      const categories = kbForm.categories
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      await apiPost("/api/rag/knowledge-bases", {
        kb_id: generateKbId(kbForm.name),
        name: kbForm.name,
        description: kbForm.description,
        categories,
        embedding_model: kbForm.embedding_model || undefined,
        kb_mode: kbForm.kb_mode,
      });
      setKbForm({ name: "", description: "", categories: "", embedding_model: "", kb_mode: "manual" });
      setShowCreateKB(false);
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

  const handleCreateProfile = async () => {
    if (!profileForm.name.trim()) return;
    setCreating(true);
    try {
      await apiPost("/api/chunk/profiles", {
        name: profileForm.name,
        chunk_size: profileForm.chunk_size,
        overlap: profileForm.overlap,
        splitter: profileForm.splitter,
        tokenizer: profileForm.tokenizer,
      });
      setProfileForm({ name: "", chunk_size: 512, overlap: 50, splitter: "semantic", tokenizer: "cl100k_base" });
      setShowCreateProfile(false);
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
          onClick={() => setShowCreateKB(true)}
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
                onClick={() => setShowCreateKB(false)}
                className="p-1 rounded hover:bg-muted"
                data-testid="button-close-create-kb"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.name")}
                </label>
                <input
                  type="text"
                  value={kbForm.name}
                  onChange={(e) => setKbForm({ ...kbForm, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  placeholder={t("knowledge.name_placeholder")}
                  data-testid="input-kb-name"
                />
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
              <div className="sm:col-span-2">
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.description")}
                </label>
                <textarea
                  value={kbForm.description}
                  onChange={(e) => setKbForm({ ...kbForm, description: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                  rows={3}
                  placeholder={t("knowledge.desc_placeholder")}
                  data-testid="input-kb-description"
                />
                <p className="text-[10px] text-muted-foreground mt-1">{t("knowledge.desc_guidance")}</p>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.embedding_model")}
                </label>
                <input
                  type="text"
                  value={kbForm.embedding_model}
                  onChange={(e) => setKbForm({ ...kbForm, embedding_model: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  placeholder={t("knowledge.embedding_placeholder")}
                  data-testid="input-kb-embedding"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">
                  {t("knowledge.categories")}
                </label>
                <input
                  type="text"
                  value={kbForm.categories}
                  onChange={(e) => setKbForm({ ...kbForm, categories: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  placeholder={t("knowledge.categories_placeholder")}
                  data-testid="input-kb-categories"
                />
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button
                onClick={handleCreateKB}
                disabled={creating || !kbForm.name.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                data-testid="button-submit-kb"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                {t("knowledge.create")}
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
                      <StatusBadge status={kb.status} />
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

                <AnimatePresence>
                  {deleteConfirm === kbId && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="absolute inset-0 bg-card/95 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center p-6 z-10"
                    >
                      <AlertTriangle className="w-8 h-8 text-red-500 mb-2" />
                      <p className="text-sm font-medium mb-1">{t("knowledge.delete_confirm")}</p>
                      <p className="text-xs text-muted-foreground mb-4 text-center">{t("knowledge.delete_warn")}</p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setDeleteConfirm(null)}
                          className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors"
                          data-testid={`button-cancel-delete-${kbId}`}
                        >
                          {t("knowledge.cancel")}
                        </button>
                        <button
                          onClick={() => handleDeleteKB(kbId)}
                          disabled={deleting}
                          className="px-3 py-1.5 text-xs rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center gap-1"
                          data-testid={`button-confirm-delete-${kbId}`}
                        >
                          {deleting && <Loader2 className="w-3 h-3 animate-spin" />}
                          {t("knowledge.delete")}
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
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
            onClick={() => setShowCreateProfile(true)}
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
                  onClick={() => setShowCreateProfile(false)}
                  className="p-1 rounded hover:bg-muted"
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
              <div className="flex justify-end mt-4">
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
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="grid grid-cols-[1fr_80px_80px_90px_100px_40px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>{t("knowledge.profile_name")}</span>
              <span>{t("knowledge.chunk_size")}</span>
              <span>{t("knowledge.overlap")}</span>
              <span>{t("knowledge.splitter")}</span>
              <span>{t("knowledge.tokenizer")}</span>
              <span />
            </div>
            {profiles.map((profile, i) => (
              <div
                key={profile.profile_id || profile.name}
                className="grid grid-cols-[1fr_80px_80px_90px_100px_40px] gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors items-center"
                data-testid={`row-profile-${i}`}
              >
                <span className="text-sm font-medium">{profile.name}</span>
                <span className="text-sm text-muted-foreground">{profile.chunk_size}</span>
                <span className="text-sm text-muted-foreground">{profile.chunk_overlap}</span>
                <span className="text-xs text-muted-foreground">{profile.splitter || "-"}</span>
                <span className="text-xs text-muted-foreground font-mono">{profile.tokenizer || "-"}</span>
                <button
                  onClick={() => profile.profile_id && handleDeleteProfile(profile.profile_id)}
                  className="p-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition-colors"
                  data-testid={`button-delete-profile-${i}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
