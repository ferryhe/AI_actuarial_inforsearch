import { useEffect, useState } from "react";
import { motion } from "framer-motion";
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
    </div>
  );
}
