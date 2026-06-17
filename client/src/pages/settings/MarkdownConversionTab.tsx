import { useEffect, useState } from "react";
import { FileText, Loader2, RefreshCw, Save, AlertTriangle } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";

interface MarkdownToolConfig {
  name?: string;
  display_name?: string;
  displayName?: string;
  provider?: string;
  enabled?: boolean;
  auto_enabled?: boolean;
  paid_or_api?: boolean;
  model?: string;
  tuning?: Record<string, unknown>;
}

interface MarkdownFormatConfig {
  extensions?: string[];
  candidate_chain?: string[];
}

interface MarkdownConversionConfig {
  version?: number;
  default_tool?: string;
  tools?: Record<string, MarkdownToolConfig>;
  formats?: Record<string, MarkdownFormatConfig>;
  limits?: Record<string, number>;
}

interface MarkdownConversionOptions {
  config?: MarkdownConversionConfig;
  default_tool?: string;
  tools?: Array<MarkdownToolConfig & { name: string }>;
  formats?: Record<string, MarkdownFormatConfig>;
  limits?: Record<string, number>;
  config_path_set?: boolean;
}

function parseList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function MarkdownConversionTab() {
  const { t } = useTranslation();
  const [config, setConfig] = useState<MarkdownConversionConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [limitDrafts, setLimitDrafts] = useState<Record<string, string>>({});

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<MarkdownConversionOptions>("/api/config/markdown-conversion");
      const nextConfig = res.config || {
        default_tool: res.default_tool,
        tools: Object.fromEntries((res.tools || []).map((tool) => [tool.name, tool])),
        formats: res.formats,
        limits: res.limits,
      };
      setConfig(nextConfig);
      setLimitDrafts(Object.fromEntries(Object.entries(nextConfig.limits || {}).map(([key, limit]) => [key, String(limit)])));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.markdown_load_error"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadConfig(); }, []);

  const updateTool = (name: string, patch: Partial<MarkdownToolConfig>) => {
    setConfig((prev) => prev ? {
      ...prev,
      tools: { ...(prev.tools || {}), [name]: { ...((prev.tools || {})[name] || {}), ...patch } },
    } : prev);
  };

  const updateFormat = (name: string, patch: Partial<MarkdownFormatConfig>) => {
    setConfig((prev) => prev ? {
      ...prev,
      formats: { ...(prev.formats || {}), [name]: { ...((prev.formats || {})[name] || {}), ...patch } },
    } : prev);
  };

  const updateLimit = (name: string, value: string) => {
    setLimitDrafts((prev) => ({ ...prev, [name]: value }));
    if (!value.trim()) return;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    setConfig((prev) => prev ? {
      ...prev,
      limits: { ...(prev.limits || {}), [name]: parsed },
    } : prev);
  };

  const resetLimitDraft = (name: string) => {
    const current = config?.limits?.[name];
    setLimitDrafts((prev) => ({ ...prev, [name]: current == null ? "" : String(current) }));
  };

  const saveConfig = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const res = await apiPost<MarkdownConversionOptions>("/api/config/markdown-conversion", config);
      setConfig(res.config || config);
      setMessage(t("settings.markdown_saved"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.markdown_save_error"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  if (!config) {
    return <div className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">{error || t("settings.markdown_load_error")}</div>;
  }

  const tools = config.tools || {};
  const formats = config.formats || {};
  const toolNames = Object.keys(tools);

  return (
    <div className="space-y-6" data-testid="markdown-conversion-tab">
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-semibold">{t("settings.markdown_conversion_title")}</h3>
            </div>
            <p className="text-xs text-muted-foreground mt-1">{t("settings.markdown_conversion_desc")}</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={loadConfig} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs hover:bg-muted" data-testid="button-refresh-markdown-config">
              <RefreshCw className="w-3.5 h-3.5" />{t("common.refresh")}
            </button>
            <button type="button" onClick={saveConfig} disabled={saving} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:opacity-50" data-testid="button-save-markdown-config">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}{t("common.save")}
            </button>
          </div>
        </div>
        {message && <div className="mt-4 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">{message}</div>}
        {error && <div className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}
      </div>

      <section className="rounded-xl border border-border bg-card p-5 space-y-3">
        <label className="block text-xs font-medium text-muted-foreground">{t("settings.markdown_default_tool")}</label>
        <select value={config.default_tool || ""} onChange={(e) => setConfig({ ...config, default_tool: e.target.value })} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" data-testid="select-markdown-default-tool">
          {toolNames.map((name) => <option key={name} value={name}>{tools[name]?.display_name || tools[name]?.displayName || name}</option>)}
        </select>
      </section>

      <section className="rounded-xl border border-border bg-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">{t("settings.markdown_tools")}</h3>
        <div className="divide-y divide-border rounded-lg border border-border overflow-hidden">
          {toolNames.map((name) => {
            const tool = tools[name] || {};
            return (
              <div key={name} className="grid md:grid-cols-[1fr_120px_120px_120px] gap-3 p-3 text-sm" data-testid={`markdown-tool-${name}`}>
                <div>
                  <div className="font-medium">{tool.display_name || tool.displayName || name}</div>
                  <div className="text-xs text-muted-foreground">{tool.provider || "local"}{tool.paid_or_api ? ` · ${t("settings.markdown_paid_or_api")}` : ""}</div>
                </div>
                <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={tool.enabled !== false} onChange={(e) => updateTool(name, { enabled: e.target.checked })} />{t("settings.enabled")}</label>
                <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={tool.auto_enabled !== false} onChange={(e) => updateTool(name, { auto_enabled: e.target.checked })} />{t("settings.markdown_auto_enabled")}</label>
                <input value={tool.model || ""} onChange={(e) => updateTool(name, { model: e.target.value })} placeholder="model" className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs" />
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border border-border bg-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">{t("settings.markdown_formats")}</h3>
        {Object.entries(formats).map(([name, fmt]) => (
          <div key={name} className="rounded-lg border border-border p-3 space-y-2" data-testid={`markdown-format-${name}`}>
            <div className="text-sm font-medium">{name}</div>
            <label className="block text-xs text-muted-foreground">extensions</label>
            <input value={(fmt.extensions || []).join(", ")} onChange={(e) => updateFormat(name, { extensions: parseList(e.target.value) })} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs" />
            <label className="block text-xs text-muted-foreground">candidate_chain</label>
            <input value={(fmt.candidate_chain || []).join(", ")} onChange={(e) => updateFormat(name, { candidate_chain: parseList(e.target.value) })} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs" />
          </div>
        ))}
      </section>

      <section className="rounded-xl border border-border bg-card p-5 space-y-3">
        <h3 className="text-sm font-semibold">{t("settings.markdown_limits")}</h3>
        {Object.entries(config.limits || {}).map(([name, value]) => (
          <label key={name} className="grid sm:grid-cols-[220px_1fr] gap-3 items-center text-sm">
            <span className="text-muted-foreground">{name}</span>
            <input type="number" value={limitDrafts[name] ?? String(value)} onChange={(e) => updateLimit(name, e.target.value)} onBlur={() => resetLimitDraft(name)} className="rounded-lg border border-border bg-background px-3 py-2 text-sm" />
          </label>
        ))}
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><AlertTriangle className="w-3.5 h-3.5" />{t("settings.markdown_paid_hint")}</p>
      </section>
    </div>
  );
}
