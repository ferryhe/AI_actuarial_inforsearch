import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings as SettingsIcon,
  Globe,
  FolderOpen,
  Search,
  Bot,
  Cpu,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Clock,
  ScrollText,
  Square,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface BackendSettings {
  defaults?: {
    max_pages?: number;
    max_depth?: number;
    delay?: number;
    file_extensions?: string[];
    keywords?: string[];
  };
  paths?: Record<string, string>;
  search?: Record<string, unknown>;
  ai?: Record<string, unknown>;
  [key: string]: unknown;
}

interface LlmProvider {
  name: string;
  configured: boolean;
  models?: string[];
  [key: string]: unknown;
}

interface AiModel {
  id?: string;
  name: string;
  provider?: string;
  [key: string]: unknown;
}

interface SearchEngine {
  name: string;
  configured: boolean;
  [key: string]: unknown;
}

interface HistoryTask {
  id: string;
  name: string;
  type: string;
  status: string;
  started_at: string;
  items_processed: number;
}

function historyStatusIcon(status: string) {
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

function historyStatusBadge(status: string) {
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
      data-testid={`status-badge-history-${status}`}
    >
      {historyStatusIcon(status)}
      {status}
    </span>
  );
}

function historyFormatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: "easeOut" as const },
  }),
};

function SectionHeader({ icon: Icon, title, color }: { icon: typeof SettingsIcon; title: string; color: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", color)}>
        <Icon className="w-4.5 h-4.5" strokeWidth={1.8} />
      </div>
      <h2 className="text-lg font-semibold font-serif">{title}</h2>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground shrink-0">{label}</span>
      <span className="text-sm font-medium text-right break-all">{value ?? "-"}</span>
    </div>
  );
}

function ProviderCard({ provider }: { provider: LlmProvider }) {
  return (
    <div
      className="rounded-xl border border-border bg-card p-4 flex items-start gap-3"
      data-testid={`provider-card-${provider.name}`}
    >
      <div className={cn(
        "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
        provider.configured
          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : "bg-muted text-muted-foreground"
      )}>
        <Bot className="w-4.5 h-4.5" strokeWidth={1.8} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm">{provider.name}</span>
          {provider.configured ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" data-testid={`status-configured-${provider.name}`}>
              <CheckCircle2 className="w-3 h-3" />
              Configured
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground" data-testid={`status-not-configured-${provider.name}`}>
              <XCircle className="w-3 h-3" />
              Not configured
            </span>
          )}
        </div>
        {provider.models && provider.models.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {provider.models.map((m) => (
              <span key={m} className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                {m}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TaskHistorySection() {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [logModal, setLogModal] = useState<{ taskId: string; log: string } | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const hasFetched = useState(false);

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await apiGet<{ tasks: HistoryTask[] }>("/api/tasks/history?limit=50");
      setHistoryTasks(res.tasks || []);
    } catch {
      setHistoryTasks([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !hasFetched[0]) {
      hasFetched[1](true);
      fetchHistory();
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

  return (
    <motion.div
      custom={5}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      className="rounded-xl border border-border bg-card overflow-hidden"
      data-testid="section-task-history"
    >
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-muted/30 transition-colors"
        data-testid="button-toggle-task-history"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <Clock className="w-4.5 h-4.5" strokeWidth={1.8} />
          </div>
          <div className="text-left">
            <h2 className="text-lg font-semibold font-serif">{t("settings.task_history")}</h2>
            <p className="text-xs text-muted-foreground">{t("settings.task_history_desc")}</p>
          </div>
        </div>
        {expanded ? <ChevronUp className="w-5 h-5 text-muted-foreground" /> : <ChevronDown className="w-5 h-5 text-muted-foreground" />}
      </button>

      {expanded && (
        <div className="border-t border-border">
          {historyLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : historyTasks.length === 0 ? (
            <div className="text-center py-10" data-testid="text-no-history">
              <Clock className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
              <p className="font-medium text-muted-foreground">{t("tasks.no_history")}</p>
            </div>
          ) : (
            <div>
              <div className="hidden sm:grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                <span>{t("tasks.col.name")}</span>
                <span>{t("tasks.col.type")}</span>
                <span>{t("tasks.col.status")}</span>
                <span>{t("tasks.col.started")}</span>
                <span>{t("tasks.col.items")}</span>
              </div>
              {historyTasks.map((task) => (
                <div
                  key={task.id}
                  className="grid sm:grid-cols-[1fr_100px_100px_120px_60px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
                  onClick={() => viewLog(task.id)}
                  data-testid={`row-history-task-${task.id}`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <ScrollText className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                    <span className="text-sm font-medium truncate">{task.name}</span>
                  </div>
                  <span className="text-xs text-muted-foreground hidden sm:flex items-center">{task.type}</span>
                  <span className="hidden sm:flex items-center">{historyStatusBadge(task.status)}</span>
                  <span className="text-xs text-muted-foreground hidden sm:flex items-center">{historyFormatDate(task.started_at)}</span>
                  <span className="text-xs text-muted-foreground hidden sm:flex items-center">{task.items_processed}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

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
                <h3 className="font-semibold text-sm">{t("tasks.log_title")} — {logModal.taskId}</h3>
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
                  <pre
                    className="text-xs font-mono whitespace-pre-wrap text-muted-foreground leading-relaxed"
                    data-testid="text-task-log"
                  >
                    {logModal.log}
                  </pre>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function SettingsPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<BackendSettings | null>(null);
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [models, setModels] = useState<AiModel[]>([]);
  const [searchEngines, setSearchEngines] = useState<SearchEngine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = () => {
    setLoading(true);
    setError(null);
    Promise.allSettled([
      apiGet<BackendSettings>("/api/config/backend-settings"),
      apiGet<{ providers: LlmProvider[] }>("/api/config/llm-providers"),
      apiGet<{ models: AiModel[] }>("/api/config/ai-models"),
      apiGet<{ engines: SearchEngine[] }>("/api/config/search-engines"),
    ])
      .then(([settingsRes, providersRes, modelsRes, enginesRes]) => {
        if (settingsRes.status === "fulfilled") setSettings(settingsRes.value);
        if (providersRes.status === "fulfilled") setProviders(providersRes.value.providers || []);
        if (modelsRes.status === "fulfilled") setModels(modelsRes.value.models || []);
        if (enginesRes.status === "fulfilled") setSearchEngines(enginesRes.value.engines || []);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24" data-testid="settings-loading">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  const defaults = settings?.defaults || {};
  const paths = settings?.paths || {};
  const searchSettings = settings?.search || {};

  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="text-settings-title">
            {t("settings.title")}
          </h1>
          <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
            {t("settings.subtitle")}
          </p>
        </div>
        <button
          onClick={fetchData}
          className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          data-testid="button-refresh-settings"
          title={t("settings.refresh")}
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </motion.div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" data-testid="text-settings-error">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <motion.div
          custom={0}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="rounded-xl border border-border bg-card p-5"
          data-testid="section-crawler-defaults"
        >
          <SectionHeader icon={Globe} title={t("settings.crawler_defaults")} color="bg-blue-500/10 text-blue-600 dark:text-blue-400" />
          <div className="divide-y divide-border">
            <SettingRow label={t("settings.max_pages")} value={defaults.max_pages} />
            <SettingRow label={t("settings.max_depth")} value={defaults.max_depth} />
            <SettingRow label={t("settings.delay")} value={defaults.delay != null ? `${defaults.delay}s` : "-"} />
            <SettingRow
              label={t("settings.file_extensions")}
              value={
                defaults.file_extensions?.length ? (
                  <div className="flex flex-wrap gap-1 justify-end">
                    {defaults.file_extensions.map((ext) => (
                      <span key={ext} className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                        {ext}
                      </span>
                    ))}
                  </div>
                ) : "-"
              }
            />
            <SettingRow
              label={t("settings.keywords")}
              value={
                defaults.keywords?.length ? (
                  <div className="flex flex-wrap gap-1 justify-end">
                    {defaults.keywords.map((kw) => (
                      <span key={kw} className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-600 dark:text-violet-400 font-medium">
                        {kw}
                      </span>
                    ))}
                  </div>
                ) : "-"
              }
            />
          </div>
        </motion.div>

        <motion.div
          custom={1}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="rounded-xl border border-border bg-card p-5"
          data-testid="section-paths"
        >
          <SectionHeader icon={FolderOpen} title={t("settings.paths")} color="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" />
          <div className="divide-y divide-border">
            {Object.entries(paths).length > 0 ? (
              Object.entries(paths).map(([key, val]) => (
                <SettingRow key={key} label={key} value={String(val)} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground py-2">{t("settings.no_data")}</p>
            )}
          </div>
        </motion.div>

        <motion.div
          custom={2}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="rounded-xl border border-border bg-card p-5"
          data-testid="section-search"
        >
          <SectionHeader icon={Search} title={t("settings.search_settings")} color="bg-amber-500/10 text-amber-600 dark:text-amber-400" />
          <div className="divide-y divide-border">
            {Object.entries(searchSettings).length > 0 ? (
              Object.entries(searchSettings).map(([key, val]) => (
                <SettingRow key={key} label={key} value={String(val)} />
              ))
            ) : (
              <p className="text-sm text-muted-foreground py-2">{t("settings.no_data")}</p>
            )}
          </div>
          {searchEngines.length > 0 && (
            <div className="mt-4 pt-4 border-t border-border">
              <h3 className="text-sm font-semibold mb-3">{t("settings.search_engines")}</h3>
              <div className="grid gap-2">
                {searchEngines.map((engine) => (
                  <div
                    key={engine.name}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-muted/50"
                    data-testid={`search-engine-${engine.name}`}
                  >
                    <span className="text-sm font-medium">{engine.name}</span>
                    {engine.configured ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="w-3 h-3" />
                        {t("settings.configured")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                        <XCircle className="w-3 h-3" />
                        {t("settings.not_configured")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>

        <motion.div
          custom={3}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="rounded-xl border border-border bg-card p-5"
          data-testid="section-ai-models"
        >
          <SectionHeader icon={Cpu} title={t("settings.ai_models")} color="bg-violet-500/10 text-violet-600 dark:text-violet-400" />
          {models.length > 0 ? (
            <div className="space-y-2">
              {models.map((model, i) => (
                <div
                  key={model.id || model.name || i}
                  className="flex items-center justify-between py-2 px-3 rounded-lg bg-muted/50"
                  data-testid={`ai-model-${model.name}`}
                >
                  <span className="text-sm font-medium">{model.name}</span>
                  {model.provider && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                      {model.provider}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-2">{t("settings.no_data")}</p>
          )}
        </motion.div>
      </div>

      <motion.div
        custom={4}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        data-testid="section-llm-providers"
      >
        <SectionHeader icon={Bot} title={t("settings.llm_providers")} color="bg-primary/10 text-primary" />
        {providers.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {providers.map((provider) => (
              <ProviderCard key={provider.name} provider={provider} />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
            <Bot className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">{t("settings.no_providers")}</p>
          </div>
        )}
      </motion.div>

      <TaskHistorySection />
    </div>
  );
}
