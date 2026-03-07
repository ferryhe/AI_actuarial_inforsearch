import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";

interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  document_count?: number;
  chunk_count?: number;
  status?: string;
  categories?: string[];
  embedding_model?: string;
}

interface ChunkProfile {
  id?: string;
  name: string;
  chunk_size: number;
  overlap: number;
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: "easeOut" as const },
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

export default function Knowledge() {
  const { t } = useTranslation();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [profiles, setProfiles] = useState<ChunkProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateKB, setShowCreateKB] = useState(false);
  const [showCreateProfile, setShowCreateProfile] = useState(false);
  const [creating, setCreating] = useState(false);

  const [kbForm, setKbForm] = useState({
    name: "",
    description: "",
    categories: "",
    embedding_model: "",
  });

  const [profileForm, setProfileForm] = useState({
    name: "",
    chunk_size: 512,
    overlap: 50,
  });

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      apiGet<{ knowledge_bases?: KnowledgeBase[] } | KnowledgeBase[]>("/api/rag/knowledge-bases").catch(() => []),
      apiGet<{ profiles?: ChunkProfile[] } | ChunkProfile[]>("/api/chunk/profiles").catch(() => []),
    ])
      .then(([kbData, profileData]) => {
        const kbList = Array.isArray(kbData) ? kbData : (kbData as any)?.knowledge_bases || [];
        setKbs(kbList);
        const pList = Array.isArray(profileData) ? profileData : (profileData as any)?.profiles || [];
        setProfiles(pList);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreateKB = async () => {
    if (!kbForm.name.trim()) return;
    setCreating(true);
    try {
      const categories = kbForm.categories
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      await apiPost("/api/rag/knowledge-bases", {
        name: kbForm.name,
        description: kbForm.description,
        categories,
        embedding_model: kbForm.embedding_model || undefined,
      });
      setKbForm({ name: "", description: "", categories: "", embedding_model: "" });
      setShowCreateKB(false);
      loadData();
    } catch (err) {
      console.error("Failed to create KB:", err);
    } finally {
      setCreating(false);
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
      });
      setProfileForm({ name: "", chunk_size: 512, overlap: 50 });
      setShowCreateProfile(false);
      loadData();
    } catch (err) {
      console.error("Failed to create profile:", err);
    } finally {
      setCreating(false);
    }
  };

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

      {showCreateKB && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-border bg-card p-6"
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
            </div>
            <div className="sm:col-span-2">
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

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-48 rounded-xl bg-muted animate-pulse" />
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
          {kbs.map((kb, i) => (
            <motion.div
              key={kb.id || kb.name}
              custom={i}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              className="rounded-xl border border-border bg-card p-5 hover:border-primary/30 hover:shadow-md transition-all"
              data-testid={`card-kb-${kb.id || i}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400 flex items-center justify-center shrink-0">
                  <BookOpen className="w-5 h-5" strokeWidth={1.8} />
                </div>
                <StatusBadge status={kb.status} />
              </div>
              <h3 className="font-semibold text-sm mb-1" data-testid={`text-kb-name-${kb.id || i}`}>
                {kb.name}
              </h3>
              {kb.description && (
                <p className="text-xs text-muted-foreground leading-relaxed mb-3 line-clamp-2">
                  {kb.description}
                </p>
              )}
              <div className="flex items-center gap-4 text-xs text-muted-foreground mt-auto pt-3 border-t border-border">
                <span className="flex items-center gap-1" data-testid={`text-kb-docs-${kb.id || i}`}>
                  <FileText className="w-3.5 h-3.5" />
                  {kb.document_count ?? 0} {t("knowledge.documents")}
                </span>
                <span className="flex items-center gap-1" data-testid={`text-kb-chunks-${kb.id || i}`}>
                  <Layers className="w-3.5 h-3.5" />
                  {kb.chunk_count ?? 0} {t("knowledge.chunks")}
                </span>
              </div>
              {kb.categories && kb.categories.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {kb.categories.map((cat) => (
                    <span
                      key={cat}
                      className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary"
                    >
                      <Tag className="w-2.5 h-2.5" />
                      {cat}
                    </span>
                  ))}
                </div>
              )}
            </motion.div>
          ))}
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

        {showCreateProfile && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-border bg-card p-6 mb-4"
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
            <div className="grid sm:grid-cols-3 gap-4">
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

        {profiles.length === 0 ? (
          <div className="text-center py-8 rounded-xl border border-dashed border-border bg-card">
            <p className="text-sm text-muted-foreground" data-testid="text-no-profiles">
              {t("knowledge.no_profiles")}
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="grid grid-cols-[1fr_100px_100px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>{t("knowledge.profile_name")}</span>
              <span>{t("knowledge.chunk_size")}</span>
              <span>{t("knowledge.overlap")}</span>
            </div>
            {profiles.map((profile, i) => (
              <div
                key={profile.id || profile.name}
                className="grid grid-cols-[1fr_100px_100px] gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors"
                data-testid={`row-profile-${i}`}
              >
                <span className="text-sm font-medium">{profile.name}</span>
                <span className="text-sm text-muted-foreground">{profile.chunk_size}</span>
                <span className="text-sm text-muted-foreground">{profile.overlap}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
