import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings as SettingsIcon,
  Bot,
  Cpu,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
  Eye,
  EyeOff,
  Plus,
  Key,
  AlertCircle,
  Globe,
  Search,
  Tag,
  ChevronDown,
  ChevronUp,
  X,
  Shield,
  MessageSquare,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";

type SettingsTab = "ai" | "search" | "categories" | "tokens" | "system" | "prompts";

interface KnownProvider {
  display_name: string;
  api_key_hint: string;
  default_base_url: string;
  is_search_provider?: boolean;
}

interface ConfiguredProvider {
  name: string;
  configured: boolean;
  has_key: boolean;
  base_url?: string;
  models?: string[];
}

interface AiModelsCurrent {
  catalog: { provider: string; model: string; system_prompt?: string };
  embeddings: { provider: string; model: string };
  chatbot: {
    provider: string;
    model: string;
    prompts?: {
      base?: string;
      expert?: string;
      summary?: string;
      tutorial?: string;
      comparison?: string;
    };
    summarization_prompt?: string;
  };
  ocr: { provider: string; model: string };
}

interface AvailableModel {
  name: string;
  display_name?: string;
  types?: string[];
}

interface SearchEngine {
  id: string;
  name: string;
  configured: boolean;
}

interface BackendDefaults {
  max_pages?: number;
  max_depth?: number;
  delay_seconds?: number;
  file_exts?: string[];
  keywords?: string[];
  exclude_keywords?: string[];
  exclude_prefixes?: string[];
  schedule_interval?: string;
  user_agent?: string;
}

interface BackendSettings {
  defaults?: BackendDefaults;
  paths?: Record<string, string>;
  search?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
}

interface CategoriesConfig {
  categories: Record<string, string[]>;
  ai_filter_keywords: string[];
  ai_keywords: string[];
}

interface ApiToken {
  id: string;
  subject: string;
  group: string;
  created_at: string;
  last_used?: string;
}

const AI_FUNCTIONS = ["catalog", "embeddings", "chatbot", "ocr"] as const;
type AiFunction = (typeof AI_FUNCTIONS)[number];

const FUNCTION_LABELS: Record<AiFunction, { en: string; zh: string }> = {
  catalog: { en: "Cataloging", zh: "编目" },
  embeddings: { en: "Embeddings", zh: "向量嵌入" },
  chatbot: { en: "Chatbot", zh: "聊天机器人" },
  ocr: { en: "OCR / Markdown", zh: "OCR / Markdown" },
};

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Bot;
  label: string;
  testId: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors whitespace-nowrap",
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground hover:bg-muted"
      )}
      data-testid={testId}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );
}

function StatusBadge({ configured }: { configured: boolean }) {
  return configured ? (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
      <CheckCircle2 className="w-3 h-3" />
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
      <XCircle className="w-3 h-3" />
    </span>
  );
}

function Toast({ message, type, onClose }: { message: string; type: "success" | "error"; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000);
    return () => clearTimeout(timer);
  }, [onClose]);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className={cn(
        "fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium",
        type === "success" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-300" : "bg-destructive/10 border-destructive/30 text-destructive"
      )}
    >
      {type === "success" ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
      {message}
    </motion.div>
  );
}

const OCR_ENGINE_DEFS = [
  { name: "docling", provider: "local", displayName: "Docling", isLocal: true },
  { name: "marker", provider: "local", displayName: "Marker", isLocal: true },
  { name: "mistral", provider: "mistral", displayName: "Mistral OCR", isLocal: false },
  { name: "deepseekocr", provider: "siliconflow", displayName: "DeepSeek OCR", isLocal: false },
];

function OcrEnginesRow({
  available,
  configuredNames,
  known,
  currentModels,
  modelEdits,
  updateModelEdit,
  lang,
  t,
}: {
  available: Record<string, AvailableModel[]>;
  configuredNames: Set<string>;
  known: Record<string, KnownProvider>;
  currentModels: AiModelsCurrent | null;
  modelEdits: Record<string, { provider: string; model: string }>;
  updateModelEdit: (fn: AiFunction, field: "provider" | "model", value: string) => void;
  lang: string;
  t: (key: string) => string;
}) {
  const fnLabel = lang === "zh" ? FUNCTION_LABELS.ocr.zh : FUNCTION_LABELS.ocr.en;
  const cur = modelEdits["ocr"] || currentModels?.ocr || { provider: "", model: "" };

  const engines = OCR_ENGINE_DEFS.map((eng) => {
    const isAvailable = eng.isLocal || configuredNames.has(eng.provider);
    const providerLabel = eng.isLocal
      ? t("settings.ocr_local")
      : (known[eng.provider]?.display_name || eng.provider);
    return { ...eng, isAvailable, providerLabel };
  });

  const availableApiProviders = Object.keys(available).filter((p) => {
    if (!configuredNames.has(p)) return false;
    return (available[p] || []).some((m) => (m.types || []).includes("ocr"));
  });

  const filteredModels = (available[cur.provider] || []).filter((m) => (m.types || []).includes("ocr"));

  return (
    <div className="px-5 py-4" data-testid="model-row-ocr">
      <label className="text-xs font-semibold text-muted-foreground mb-3 block">{fnLabel}</label>
      <div className="space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {engines.map((eng) => (
            <div
              key={eng.name}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-lg border text-xs",
                eng.isAvailable
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-border bg-muted/30 opacity-60"
              )}
              data-testid={`ocr-engine-${eng.name}`}
            >
              {eng.isAvailable ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
              ) : (
                <XCircle className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
              )}
              <div className="min-w-0">
                <span className="font-medium block truncate">{eng.displayName}</span>
                <span className="text-[10px] text-muted-foreground block truncate">
                  {eng.isLocal ? t("settings.ocr_no_key") : eng.providerLabel}
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">{t("settings.ocr_engines_hint")}</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] text-muted-foreground mb-1 block">{t("settings.ocr_default_provider")}</label>
            <select
              value={cur.provider}
              onChange={(e) => updateModelEdit("ocr", "provider", e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
              data-testid="select-provider-ocr"
            >
              <option value="">—</option>
              {availableApiProviders.map((p) => (
                <option key={p} value={p}>{known[p]?.display_name || p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground mb-1 block">{t("settings.model")}</label>
            <select
              value={cur.model}
              onChange={(e) => updateModelEdit("ocr", "model", e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
              data-testid="select-model-ocr"
            >
              <option value="">—</option>
              {filteredModels.map((m) => (
                <option key={m.name} value={m.name}>{m.display_name || m.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}

function AiConfigTab({ lang }: { lang: string }) {
  const { t } = useTranslation();
  const [known, setKnown] = useState<Record<string, KnownProvider>>({});
  const [configured, setConfigured] = useState<ConfiguredProvider[]>([]);
  const [currentModels, setCurrentModels] = useState<AiModelsCurrent | null>(null);
  const [available, setAvailable] = useState<Record<string, AvailableModel[]>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [baseUrlInput, setBaseUrlInput] = useState("");
  const [showKey, setShowKey] = useState(false);

  const [modelEdits, setModelEdits] = useState<Record<string, { provider: string; model: string }>>({});
  const [savingModels, setSavingModels] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [provRes, modelsRes] = await Promise.all([
        apiGet<{ known: Record<string, KnownProvider>; providers: ConfiguredProvider[] }>("/api/config/llm-providers"),
        apiGet<{ current: AiModelsCurrent; available: Record<string, AvailableModel[]> }>("/api/config/ai-models"),
      ]);
      setKnown(provRes.known || {});
      setConfigured(provRes.providers || []);
      setCurrentModels(modelsRes.current || null);
      setAvailable(modelsRes.available || {});
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const llmProviders = Object.entries(known).filter(([, info]) => !info.is_search_provider);
  const configuredNames = new Set(configured.filter((p) => p.configured || p.has_key).map((p) => p.name));

  async function saveProvider(providerName: string) {
    if (!apiKeyInput.trim()) return;
    setSaving(providerName);
    try {
      await apiPost("/api/config/llm-providers", {
        provider: providerName,
        api_key: apiKeyInput.trim(),
        base_url: baseUrlInput.trim() || undefined,
      });
      setToast({ message: t("settings.provider_saved"), type: "success" });
      setEditingProvider(null);
      setApiKeyInput("");
      setBaseUrlInput("");
      await fetchData();
    } catch {
      setToast({ message: t("settings.provider_save_error"), type: "error" });
    } finally {
      setSaving(null);
    }
  }

  async function deleteProvider(providerName: string) {
    if (!window.confirm(t("settings.confirm_delete_provider"))) return;
    setSaving(providerName);
    try {
      await apiDelete(`/api/config/llm-providers/${providerName}`);
      setToast({ message: t("settings.provider_deleted"), type: "success" });
      await fetchData();
    } catch {
      setToast({ message: t("settings.provider_delete_error"), type: "error" });
    } finally {
      setSaving(null);
    }
  }

  function startEditProvider(providerName: string) {
    setEditingProvider(providerName);
    setApiKeyInput("");
    setBaseUrlInput(known[providerName]?.default_base_url || "");
    setShowKey(false);
  }

  async function saveModelConfig() {
    if (Object.keys(modelEdits).length === 0) return;
    setSavingModels(true);
    try {
      await apiPost("/api/config/ai-models", modelEdits);
      setToast({ message: t("settings.models_saved"), type: "success" });
      setModelEdits({});
      await fetchData();
    } catch {
      setToast({ message: t("settings.models_save_error"), type: "error" });
    } finally {
      setSavingModels(false);
    }
  }

  function updateModelEdit(fn: AiFunction, field: "provider" | "model", value: string) {
    setModelEdits((prev) => {
      const current = prev[fn] || {
        provider: currentModels?.[fn]?.provider || "",
        model: currentModels?.[fn]?.model || "",
      };
      return { ...prev, [fn]: { ...current, [field]: value } };
    });
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <AnimatePresence>{toast && <Toast {...toast} onClose={() => setToast(null)} />}</AnimatePresence>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center gap-2">
          <Key className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold">{t("settings.llm_providers")}</h3>
          <span className="text-xs text-muted-foreground ml-auto">{configuredNames.size} {t("settings.configured").toLowerCase()}</span>
        </div>
        <div className="divide-y divide-border">
          {llmProviders.length === 0 ? (
            <div className="text-center py-10" data-testid="text-no-providers">
              <Bot className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
              <p className="text-sm text-muted-foreground">{t("settings.no_providers")}</p>
            </div>
          ) : llmProviders.map(([name, info]) => {
            const isConfigured = configuredNames.has(name);
            const isEditing = editingProvider === name;
            return (
              <div key={name} className="px-5 py-4" data-testid={`provider-row-${name}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusBadge configured={isConfigured} />
                    <div>
                      <span className="text-sm font-semibold">{info.display_name}</span>
                      <span className="text-xs text-muted-foreground ml-2">({name})</span>
                      {!isConfigured && (
                        <span className="ml-2 inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400" data-testid={`badge-not-configured-${name}`}>
                          {t("settings.not_configured")}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isConfigured && !isEditing && (
                      <button
                        onClick={() => deleteProvider(name)}
                        disabled={saving === name}
                        className="text-xs px-2 py-1 rounded-lg text-destructive hover:bg-destructive/10 transition-colors"
                        data-testid={`button-delete-provider-${name}`}
                      >
                        {saving === name ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                      </button>
                    )}
                    {!isEditing && (
                      <button
                        onClick={() => startEditProvider(name)}
                        className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
                        data-testid={`button-edit-provider-${name}`}
                      >
                        {isConfigured ? t("settings.update_key") : t("settings.add_key")}
                      </button>
                    )}
                  </div>
                </div>
                {isEditing && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-3 space-y-3">
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">{t("settings.api_key_label")}</label>
                      <div className="relative">
                        <input
                          type={showKey ? "text" : "password"}
                          value={apiKeyInput}
                          onChange={(e) => setApiKeyInput(e.target.value)}
                          placeholder={info.api_key_hint || "sk-..."}
                          className="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                          data-testid={`input-api-key-${name}`}
                        />
                        <button
                          onClick={() => setShowKey(!showKey)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                        >
                          {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>
                    {info.default_base_url && (
                      <div>
                        <label className="text-xs text-muted-foreground mb-1 block">{t("settings.base_url_label")} ({t("settings.optional")})</label>
                        <input
                          type="text"
                          value={baseUrlInput}
                          onChange={(e) => setBaseUrlInput(e.target.value)}
                          placeholder={info.default_base_url}
                          className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                          data-testid={`input-base-url-${name}`}
                        />
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => saveProvider(name)}
                        disabled={!apiKeyInput.trim() || saving === name}
                        className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                        data-testid={`button-save-provider-${name}`}
                      >
                        {saving === name ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                        {t("settings.save")}
                      </button>
                      <button
                        onClick={() => { setEditingProvider(null); setApiKeyInput(""); }}
                        className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
                      >
                        {t("settings.cancel")}
                      </button>
                    </div>
                  </motion.div>
                )}
              </div>
            );
          })}
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("settings.model_selection")}</h3>
          </div>
          {Object.keys(modelEdits).length > 0 && (
            <button
              onClick={saveModelConfig}
              disabled={savingModels}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid="button-save-models"
            >
              {savingModels ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {t("settings.save_model_config")}
            </button>
          )}
        </div>
        <div className="divide-y divide-border">
          {AI_FUNCTIONS.filter((fn) => fn !== "ocr").map((fn) => {
            const cur = modelEdits[fn] || currentModels?.[fn] || { provider: "", model: "" };
            const typeKey = fn === "chatbot" ? "chat" : fn;
            const filteredProviders = Object.keys(available).filter((p) => {
              if (!configuredNames.has(p)) return false;
              const models = available[p] || [];
              return models.some((m) => (m.types || []).includes(typeKey));
            });
            const filteredModels = (available[cur.provider] || []).filter((m) => (m.types || []).includes(typeKey));
            const fnLabel = lang === "zh" ? FUNCTION_LABELS[fn].zh : FUNCTION_LABELS[fn].en;
            return (
              <div key={fn} className="px-5 py-4" data-testid={`model-row-${fn}`}>
                <label className="text-xs font-semibold text-muted-foreground mb-2 block">{fnLabel}</label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] text-muted-foreground mb-1 block">{t("settings.provider")}</label>
                    <select
                      value={cur.provider}
                      onChange={(e) => updateModelEdit(fn, "provider", e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
                      data-testid={`select-provider-${fn}`}
                    >
                      <option value="">—</option>
                      {filteredProviders.map((p) => (
                        <option key={p} value={p}>{known[p]?.display_name || p}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[11px] text-muted-foreground mb-1 block">{t("settings.model")}</label>
                    <select
                      value={cur.model}
                      onChange={(e) => updateModelEdit(fn, "model", e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
                      data-testid={`select-model-${fn}`}
                    >
                      <option value="">—</option>
                      {filteredModels.map((m) => (
                        <option key={m.name} value={m.name}>{m.display_name || m.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            );
          })}
          <OcrEnginesRow
            available={available}
            configuredNames={configuredNames}
            known={known}
            currentModels={currentModels}
            modelEdits={modelEdits}
            updateModelEdit={updateModelEdit}
            lang={lang}
            t={t}
          />
        </div>
      </motion.div>
    </div>
  );
}

// ─── Reusable inline prompt editor card ──────────────────────────────────────
function PromptEditorCard({
  title,
  hint,
  defaultText,
  value,
  testIdPrefix,
  onSave,
}: {
  title: string;
  hint: string;
  defaultText: string;
  value: string;
  testIdPrefix: string;
  onSave: (v: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (editing === null) return;
    setSaving(true);
    try {
      await onSave(editing);
      setEditing(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
        {editing !== null && (
          <div className="flex items-center gap-2">
            <button onClick={() => setEditing(null)}
              className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors">
              {t("settings.cancel")}
            </button>
            <button onClick={handleSave} disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid={`${testIdPrefix}-save`}>
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {t("settings.save")}
            </button>
          </div>
        )}
      </div>
      <div className="px-5 py-4 space-y-2">
        <p className="text-xs text-muted-foreground">{hint}</p>
        {editing !== null ? (
          <textarea
            aria-label={title}
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
            rows={8}
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
            placeholder={defaultText}
            data-testid={`${testIdPrefix}-input`}
          />
        ) : (
          <div className="flex items-start gap-3">
            <pre className="flex-1 text-xs text-muted-foreground whitespace-pre-wrap break-words bg-muted/30 rounded-lg px-3 py-2 min-h-[3.5rem]">
              {value || defaultText}
            </pre>
            <button onClick={() => setEditing(value)}
              className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors shrink-0"
              data-testid={`${testIdPrefix}-edit`}>
              <Pencil className="w-3 h-3 inline mr-1" />{t("settings.edit")}
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── PromptsTab ───────────────────────────────────────────────────────────────
// The four chatbot mode keys (must match backend valid_prompt_keys in app.py)
const CHATBOT_MODE_KEYS = ["expert", "summary", "tutorial", "comparison"] as const;
type ChatbotModeKey = (typeof CHATBOT_MODE_KEYS)[number];

function PromptsTab() {
  const { t } = useTranslation();
  const [currentModels, setCurrentModels] = useState<AiModelsCurrent | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ current: AiModelsCurrent }>("/api/config/ai-models");
      setCurrentModels(res.current || null);
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  async function savePrompt(payload: Record<string, unknown>) {
    await apiPost("/api/config/ai-models", payload);
    setToast({ message: t("settings.catalog_prompt_saved"), type: "success" });
    await fetchData();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <AnimatePresence>{toast && <Toast {...toast} onClose={() => setToast(null)} />}</AnimatePresence>

      {/* Catalog system prompt */}
      <PromptEditorCard
        title={t("settings.catalog_prompt_title")}
        hint={t("settings.catalog_prompt_hint")}
        defaultText={t("settings.catalog_prompt_default")}
        value={currentModels?.catalog?.system_prompt || ""}
        testIdPrefix="catalog-prompt"
        onSave={async (v) => {
          await savePrompt({ catalog: { system_prompt: v } });
        }}
      />

      {/* Chatbot base instructions */}
      <PromptEditorCard
        title={t("settings.chatbot_base_prompt_title")}
        hint={t("settings.chatbot_base_prompt_hint")}
        defaultText={t("settings.chatbot_prompt_default")}
        value={currentModels?.chatbot?.prompts?.base || ""}
        testIdPrefix="chatbot-base-prompt"
        onSave={async (v) => {
          await savePrompt({ chatbot: { prompts: { base: v } } });
        }}
      />

      {/* Chatbot mode prompts */}
      {CHATBOT_MODE_KEYS.map((mode) => (
        <PromptEditorCard
          key={mode}
          title={t(`settings.chatbot_mode_prompt_${mode}`)}
          hint={t("settings.chatbot_mode_prompt_hint")}
          defaultText={t("settings.chatbot_prompt_default")}
          value={currentModels?.chatbot?.prompts?.[mode] || ""}
          testIdPrefix={`chatbot-${mode}-prompt`}
          onSave={async (v) => {
            await savePrompt({ chatbot: { prompts: { [mode]: v } } });
          }}
        />
      ))}

      {/* Document summarization prompt */}
      <PromptEditorCard
        title={t("settings.summarization_prompt_title")}
        hint={t("settings.summarization_prompt_hint")}
        defaultText={t("settings.chatbot_prompt_default")}
        value={currentModels?.chatbot?.summarization_prompt || ""}
        testIdPrefix="summarization-prompt"
        onSave={async (v) => {
          await savePrompt({ chatbot: { summarization_prompt: v } });
        }}
      />
    </div>
  );
}

function SearchCrawlerTab() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<BackendSettings | null>(null);
  const [searchEngines, setSearchEngines] = useState<SearchEngine[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const [editDefaults, setEditDefaults] = useState<BackendDefaults>({});
  const [dirty, setDirty] = useState(false);

  const [known, setKnown] = useState<Record<string, KnownProvider>>({});
  const [searchKeyEdit, setSearchKeyEdit] = useState<{ engine: string; key: string } | null>(null);
  const [searchKeySaving, setSearchKeySaving] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [settingsRes, enginesRes, provRes] = await Promise.all([
        apiGet<BackendSettings>("/api/config/backend-settings"),
        apiGet<{ engines: SearchEngine[] }>("/api/config/search-engines"),
        apiGet<{ known: Record<string, KnownProvider> }>("/api/config/llm-providers"),
      ]);
      setSettings(settingsRes);
      setEditDefaults(settingsRes.defaults || {});
      setSearchEngines(enginesRes.engines || []);
      setKnown(provRes.known || {});
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  function updateDefault<K extends keyof BackendDefaults>(key: K, value: BackendDefaults[K]) {
    setEditDefaults((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  }

  async function saveDefaults() {
    setSaving(true);
    try {
      await apiPost("/api/config/backend-settings", { defaults: editDefaults });
      setToast({ message: t("settings.defaults_saved"), type: "success" });
      setDirty(false);
      await fetchData();
    } catch {
      setToast({ message: t("settings.defaults_save_error"), type: "error" });
    } finally {
      setSaving(false);
    }
  }

  const SEARCH_PROVIDER_MAP: Record<string, string> = {
    brave: "brave_search",
    google: "serpapi",
    serper: "serper",
    tavily: "tavily",
  };

  async function saveSearchKey() {
    if (!searchKeyEdit?.key.trim() || !searchKeyEdit.engine) return;
    setSearchKeySaving(true);
    try {
      const providerName = SEARCH_PROVIDER_MAP[searchKeyEdit.engine] || searchKeyEdit.engine;
      await apiPost("/api/config/llm-providers", {
        provider: providerName,
        api_key: searchKeyEdit.key.trim(),
      });
      setToast({ message: t("settings.provider_saved"), type: "success" });
      setSearchKeyEdit(null);
      await fetchData();
    } catch {
      setToast({ message: t("settings.provider_save_error"), type: "error" });
    } finally {
      setSearchKeySaving(false);
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-8">
      <AnimatePresence>{toast && <Toast {...toast} onClose={() => setToast(null)} />}</AnimatePresence>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("settings.search_engines")}</h3>
          </div>
        </div>
        <div className="divide-y divide-border">
          {searchEngines.length === 0 ? (
            <div className="text-center py-10" data-testid="text-no-search-engines">
              <Search className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
              <p className="text-sm text-muted-foreground">{t("settings.no_data")}</p>
            </div>
          ) : searchEngines.map((engine) => (
            <div key={engine.id} className="px-5 py-4" data-testid={`search-engine-row-${engine.id}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <StatusBadge configured={engine.configured} />
                  <span className="text-sm font-semibold">{engine.name}</span>
                  {!engine.configured && (
                    <span className="inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400" data-testid={`badge-not-configured-search-${engine.id}`}>
                      {t("settings.not_configured")}
                    </span>
                  )}
                </div>
                {searchKeyEdit?.engine !== engine.id && (
                  <button
                    onClick={() => setSearchKeyEdit({ engine: engine.id, key: "" })}
                    className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
                    data-testid={`button-edit-search-${engine.id}`}
                  >
                    {engine.configured ? t("settings.update_key") : t("settings.add_key")}
                  </button>
                )}
              </div>
              {searchKeyEdit?.engine === engine.id && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-3 flex items-center gap-2">
                  <input
                    type="password"
                    value={searchKeyEdit.key}
                    onChange={(e) => setSearchKeyEdit({ ...searchKeyEdit, key: e.target.value })}
                    placeholder={known[SEARCH_PROVIDER_MAP[engine.id]]?.api_key_hint || "API Key"}
                    className="flex-1 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    data-testid={`input-search-key-${engine.id}`}
                  />
                  <button
                    onClick={saveSearchKey}
                    disabled={!searchKeyEdit.key.trim() || searchKeySaving}
                    className="text-xs px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                    data-testid={`button-save-search-${engine.id}`}
                  >
                    {searchKeySaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  </button>
                  <button
                    onClick={() => setSearchKeyEdit(null)}
                    className="text-xs px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
                  >
                    {t("settings.cancel")}
                  </button>
                </motion.div>
              )}
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("settings.crawler_defaults")}</h3>
          </div>
          {dirty && (
            <button
              onClick={saveDefaults}
              disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid="button-save-defaults"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {t("settings.save")}
            </button>
          )}
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t("settings.max_pages")}</label>
              <input type="number" value={editDefaults.max_pages ?? ""} onChange={(e) => updateDefault("max_pages", Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-max-pages" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t("settings.max_depth")}</label>
              <input type="number" value={editDefaults.max_depth ?? ""} onChange={(e) => updateDefault("max_depth", Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-max-depth" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">{t("settings.delay")}</label>
              <input type="number" step="0.1" value={editDefaults.delay_seconds ?? ""} onChange={(e) => updateDefault("delay_seconds", Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-delay" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">{t("settings.file_extensions")}</label>
            <input type="text" value={(editDefaults.file_exts || []).join(", ")}
              onChange={(e) => updateDefault("file_exts", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-extensions"
              placeholder=".pdf, .doc, .docx" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">{t("settings.crawler_keywords_label")}</label>
            <input type="text" value={(editDefaults.keywords || []).join(", ")}
              onChange={(e) => updateDefault("keywords", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="input-keywords"
              placeholder="artificial intelligence, machine learning, ..." />
            <p className="text-[11px] text-muted-foreground mt-1">{t("settings.crawler_keywords_desc")}</p>
          </div>
          {settings?.paths && Object.keys(settings.paths).length > 0 && (
            <div className="pt-3 border-t border-border">
              <label className="text-xs font-semibold text-muted-foreground mb-2 block">{t("settings.paths")}</label>
              <div className="space-y-1.5">
                {Object.entries(settings.paths).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-3 text-xs">
                    <span className="text-muted-foreground w-28 shrink-0">{k}</span>
                    <span className="font-mono text-foreground break-all">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}

function CategoriesTab() {
  const { t } = useTranslation();
  const [categories, setCategories] = useState<Record<string, string[]>>({});
  const [aiFilterKw, setAiFilterKw] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [newCatName, setNewCatName] = useState("");
  const [expandedCat, setExpandedCat] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<CategoriesConfig>("/api/config/categories");
      setCategories(res.categories || {});
      setAiFilterKw(res.ai_filter_keywords || []);
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  function addCategory() {
    const name = newCatName.trim();
    if (!name || categories[name]) return;
    setCategories((prev) => ({ ...prev, [name]: [] }));
    setNewCatName("");
    setDirty(true);
  }

  function deleteCategory(name: string) {
    if (!window.confirm(t("settings.confirm_delete_cat"))) return;
    setCategories((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    setDirty(true);
  }

  function updateCatKeywords(name: string, kwStr: string) {
    setCategories((prev) => ({
      ...prev,
      [name]: kwStr.split(",").map((s) => s.trim()).filter(Boolean),
    }));
    setDirty(true);
  }

  async function saveAll() {
    setSaving(true);
    try {
      await apiPost("/api/config/categories", {
        categories,
        ai_filter_keywords: aiFilterKw,
      });
      setToast({ message: t("settings.categories_saved"), type: "success" });
      setDirty(false);
    } catch {
      setToast({ message: t("settings.categories_save_error"), type: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  const catEntries = Object.entries(categories);

  return (
    <div className="space-y-8">
      <AnimatePresence>{toast && <Toast {...toast} onClose={() => setToast(null)} />}</AnimatePresence>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Tag className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("settings.categories_title")}</h3>
            <span className="text-xs text-muted-foreground">({catEntries.length})</span>
          </div>
          {dirty && (
            <button onClick={saveAll} disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid="button-save-categories">
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {t("settings.save")}
            </button>
          )}
        </div>
        <div className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <input type="text" value={newCatName} onChange={(e) => setNewCatName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addCategory()}
              placeholder={t("settings.new_category_ph")}
              className="flex-1 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="input-new-category" />
            <button onClick={addCategory} disabled={!newCatName.trim()}
              className="px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5 text-xs"
              data-testid="button-add-category">
              <Plus className="w-3 h-3" />{t("settings.add")}
            </button>
          </div>

          <div className="divide-y divide-border">
            {catEntries.length === 0 && (
              <div className="text-center py-8" data-testid="text-no-categories">
                <Tag className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
                <p className="text-sm text-muted-foreground">{t("settings.no_data")}</p>
              </div>
            )}
            {catEntries.map(([name, kws]) => {
              const isExpanded = expandedCat === name;
              return (
                <div key={name} className="py-3" data-testid={`cat-row-${name}`}>
                  <div className="flex items-center justify-between">
                    <button onClick={() => setExpandedCat(isExpanded ? null : name)} className="flex items-center gap-2 text-sm font-medium hover:text-primary transition-colors">
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      {name}
                      <span className="text-xs text-muted-foreground font-normal">({kws.length} {t("settings.keywords").toLowerCase()})</span>
                    </button>
                    <button onClick={() => deleteCategory(name)} className="text-xs p-1 rounded hover:bg-destructive/10 text-destructive transition-colors" data-testid={`button-delete-cat-${name}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  {isExpanded && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-2">
                      <textarea
                        value={kws.join(", ")}
                        onChange={(e) => updateCatKeywords(name, e.target.value)}
                        rows={3}
                        className="w-full px-3 py-2 rounded-lg border border-border bg-background text-xs font-mono resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
                        placeholder={t("settings.cat_keywords_ph")}
                        data-testid={`input-cat-keywords-${name}`}
                      />
                    </motion.div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center gap-2">
          <Tag className="w-4 h-4 text-amber-500" />
          <h3 className="text-sm font-semibold">{t("settings.ai_filter_kw")}</h3>
        </div>
        <div className="p-5">
          <textarea
            value={aiFilterKw.join(", ")}
            onChange={(e) => { setAiFilterKw(e.target.value.split(",").map((s) => s.trim()).filter(Boolean)); setDirty(true); }}
            rows={3}
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-xs font-mono resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
            placeholder={t("settings.ai_filter_kw_ph")}
            data-testid="input-ai-filter-keywords"
          />
          <p className="text-[11px] text-muted-foreground mt-1.5">{t("settings.ai_filter_kw_desc")}</p>
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1" data-testid="text-ai-filter-kw-hint">{t("settings.ai_filter_kw_hint")}</p>
        </div>
      </motion.div>
    </div>
  );
}

function SystemTab() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<BackendSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [fileDeletionEnabled, setFileDeletionEnabled] = useState(false);
  const [dirty, setDirty] = useState(false);
  const hasInit = useRef(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<BackendSettings>("/api/config/backend-settings");
      setSettings(res);
      if (!hasInit.current) {
        const rt = res.runtime as Record<string, boolean> | undefined;
        setFileDeletionEnabled(!!rt?.file_deletion_enabled);
        hasInit.current = true;
      }
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const runtime = settings?.runtime as Record<string, boolean> | undefined;

  const readOnlyFlags: Array<{ key: string; label: string }> = [
    { key: "require_auth", label: t("settings.flag_require_auth") },
    { key: "enable_global_logs_api", label: t("settings.flag_global_logs") },
    { key: "enable_rate_limiting", label: t("settings.flag_rate_limiting") },
    { key: "enable_csrf", label: t("settings.flag_csrf") },
    { key: "enable_security_headers", label: t("settings.flag_security_headers") },
  ];

  async function saveSystemSettings() {
    setSaving(true);
    try {
      await apiPost("/api/config/backend-settings", { system: { file_deletion_enabled: fileDeletionEnabled } });
      setToast({ message: t("settings.system_saved"), type: "success" });
      setDirty(false);
      hasInit.current = false;
      await fetchData();
    } catch {
      setToast({ message: t("settings.system_save_error"), type: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-8">
      <AnimatePresence>{toast && <Toast {...toast} onClose={() => setToast(null)} />}</AnimatePresence>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("settings.system_runtime")}</h3>
          </div>
          {dirty && (
            <button onClick={saveSystemSettings} disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid="button-save-system">
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {t("settings.save")}
            </button>
          )}
        </div>
        <div className="p-5 space-y-4">
          <p className="text-xs text-muted-foreground">{t("settings.system_runtime_desc")}</p>
          <div className="divide-y divide-border">
            {/* File deletion — YAML-configurable toggle */}
            <div className="py-3 flex items-center justify-between" data-testid="system-flag-file_deletion_enabled">
              <div>
                <span className="text-sm font-medium">{t("settings.flag_file_deletion")}</span>
                <span className="ml-2 text-[10px] text-muted-foreground bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                  {t("settings.flag_yaml_hint")}
                </span>
              </div>
              <button
                onClick={() => { setFileDeletionEnabled((v) => !v); setDirty(true); }}
                className={cn(
                  "relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  fileDeletionEnabled ? "bg-emerald-500" : "bg-muted border border-border"
                )}
                data-testid="toggle-file-deletion"
                aria-label={t("settings.flag_file_deletion")}
              >
                <span className={cn(
                  "inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform shadow-sm",
                  fileDeletionEnabled ? "translate-x-4" : "translate-x-1"
                )} />
              </button>
            </div>
            {/* Read-only env-var flags */}
            {readOnlyFlags.map(({ key, label }) => {
              const val = !!runtime?.[key];
              return (
                <div key={key} className="py-3 flex items-center justify-between" data-testid={`system-flag-${key}`}>
                  <div>
                    <span className="text-sm font-medium">{label}</span>
                    <span className="ml-2 text-[10px] text-muted-foreground">{t("settings.flag_env_hint")}</span>
                  </div>
                  <span className={cn(
                    "text-[11px] font-semibold px-2 py-0.5 rounded-full",
                    val
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "bg-muted text-muted-foreground"
                  )}>
                    {val ? t("settings.flag_enabled") : t("settings.flag_disabled")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function ApiTokensTab() {
  const { t } = useTranslation();
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [newSubject, setNewSubject] = useState("");
  const [newGroup, setNewGroup] = useState("reader");
  const [creating, setCreating] = useState(false);
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  const fetchTokens = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ tokens: ApiToken[] }>("/api/auth/tokens");
      setTokens(res.tokens || []);
    } catch {
      setTokens([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTokens(); }, [fetchTokens]);

  async function createToken() {
    if (!newSubject.trim()) return;
    setCreating(true);
    try {
      const res = await apiPost<{ token?: string; success?: boolean }>("/api/auth/tokens", {
        subject: newSubject.trim(),
        group: newGroup,
      });
      if (res.token) {
        setCreatedToken(res.token);
        setToast({ message: t("settings.token_created"), type: "success" });
        await fetchTokens();
      }
    } catch {
      setToast({ message: t("settings.token_create_error"), type: "error" });
    } finally {
      setCreating(false);
    }
  }

  async function revokeToken(tokenId: string) {
    if (!window.confirm(t("settings.confirm_revoke_token"))) return;
    try {
      await apiPost(`/api/auth/tokens/${tokenId}/revoke`, {});
      setToast({ message: t("settings.token_revoked"), type: "success" });
      await fetchTokens();
    } catch {
      setToast({ message: t("settings.token_revoke_error"), type: "error" });
    }
  }

  function formatDate(dateStr?: string): string {
    if (!dateStr) return "-";
    try {
      return new Date(dateStr).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch { return dateStr; }
  }

  if (loading) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-6">
      <AnimatePresence>{toast && <Toast {...toast} onClose={() => setToast(null)} />}</AnimatePresence>

      {createdToken && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1.5 min-w-0 flex-1">
              <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">{t("settings.token_created_notice")}</p>
              <code className="block text-xs font-mono bg-background px-3 py-2 rounded-lg border border-border break-all" data-testid="text-created-token">
                {createdToken}
              </code>
              <p className="text-[11px] text-muted-foreground">{t("settings.token_copy_warning")}</p>
            </div>
            <button onClick={() => setCreatedToken(null)} className="p-1 hover:bg-muted rounded"><X className="w-4 h-4" /></button>
          </div>
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold">{t("settings.api_tokens")}</h3>
          </div>
          <button onClick={() => setShowCreate(!showCreate)}
            className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5"
            data-testid="button-create-token">
            <Plus className="w-3 h-3" />{t("settings.create_token")}
          </button>
        </div>

        {showCreate && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            className="px-5 py-4 border-b border-border bg-muted/10">
            <div className="grid grid-cols-[1fr_120px_auto] gap-3 items-end">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">{t("settings.token_subject")}</label>
                <input type="text" value={newSubject} onChange={(e) => setNewSubject(e.target.value)}
                  placeholder={t("settings.token_subject_ph")}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  data-testid="input-token-subject" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">{t("settings.token_group")}</label>
                <select value={newGroup} onChange={(e) => setNewGroup(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="select-token-group">
                  <option value="reader">Reader</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button onClick={createToken} disabled={!newSubject.trim() || creating}
                className="px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 text-xs flex items-center gap-1.5"
                data-testid="button-submit-token">
                {creating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                {t("settings.create")}
              </button>
            </div>
          </motion.div>
        )}

        <div className="divide-y divide-border">
          {tokens.length === 0 ? (
            <div className="text-center py-10">
              <Key className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
              <p className="text-sm text-muted-foreground">{t("settings.no_tokens")}</p>
            </div>
          ) : (
            tokens.map((token) => (
              <div key={token.id} className="px-5 py-3 flex items-center justify-between" data-testid={`token-row-${token.id}`}>
                <div className="space-y-0.5 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{token.subject}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-semibold">{token.group}</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {t("settings.created")}: {formatDate(token.created_at)}
                    {token.last_used && <> · {t("settings.last_used")}: {formatDate(token.last_used)}</>}
                  </div>
                </div>
                <button onClick={() => revokeToken(token.id)}
                  className="text-xs px-2.5 py-1.5 rounded-lg text-destructive hover:bg-destructive/10 transition-colors flex items-center gap-1"
                  data-testid={`button-revoke-token-${token.id}`}>
                  <Trash2 className="w-3 h-3" />{t("settings.revoke")}
                </button>
              </div>
            ))
          )}
        </div>
      </motion.div>
    </div>
  );
}

export default function SettingsPage() {
  const { t, lang } = useTranslation();
  const [activeTab, setActiveTab] = useState<SettingsTab>("ai");

  const handleRefresh = () => {
    setActiveTab((prev) => {
      const cur = prev;
      setTimeout(() => setActiveTab(cur), 0);
      return cur;
    });
    window.location.reload();
  };

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="text-settings-title">
              {t("settings.title")}
            </h1>
            <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
              {t("settings.subtitle")}
            </p>
          </div>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border hover:bg-muted text-sm text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-refresh-settings"
            title={t("settings.refresh")}
          >
            <RefreshCw className="w-4 h-4" />
            <span className="hidden sm:inline">{t("settings.refresh")}</span>
          </button>
        </div>
      </motion.div>

      <div className="flex items-center gap-1 overflow-x-auto pb-1 border-b border-border" data-testid="settings-tabs">
        <TabButton active={activeTab === "ai"} onClick={() => setActiveTab("ai")} icon={Bot} label={t("settings.tab_ai")} testId="tab-ai" />
        <TabButton active={activeTab === "prompts"} onClick={() => setActiveTab("prompts")} icon={MessageSquare} label={t("settings.tab_prompts")} testId="tab-prompts" />
        <TabButton active={activeTab === "search"} onClick={() => setActiveTab("search")} icon={Search} label={t("settings.tab_search")} testId="tab-search" />
        <TabButton active={activeTab === "categories"} onClick={() => setActiveTab("categories")} icon={Tag} label={t("settings.tab_categories")} testId="tab-categories" />
        <TabButton active={activeTab === "tokens"} onClick={() => setActiveTab("tokens")} icon={Key} label={t("settings.tab_tokens")} testId="tab-tokens" />
        <TabButton active={activeTab === "system"} onClick={() => setActiveTab("system")} icon={Shield} label={t("settings.tab_system")} testId="tab-system" />
      </div>

      <div>
        {activeTab === "ai" && <AiConfigTab lang={lang} />}
        {activeTab === "prompts" && <PromptsTab />}
        {activeTab === "search" && <SearchCrawlerTab />}
        {activeTab === "categories" && <CategoriesTab />}
        {activeTab === "tokens" && <ApiTokensTab />}
        {activeTab === "system" && <SystemTab />}
      </div>
    </div>
  );
}
