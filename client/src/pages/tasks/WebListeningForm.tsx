import { useState } from "react";
import { Loader2, Wand2, CheckCircle2, AlertTriangle, Save, Compass } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { apiPost } from "@/lib/api";

interface WebListeningFormProps {
  onMaterialized?: () => void | Promise<void>;
}

interface WebListeningValidationResponse {
  success?: boolean;
  valid?: boolean;
  yaml?: string;
  errors?: string[];
  warnings?: string[];
  materialized_config?: {
    site?: Record<string, unknown>;
    scheduled_task?: Record<string, unknown>;
  };
}

interface WebListeningMaterializeResponse extends WebListeningValidationResponse {
  backup?: string;
  updated?: { site?: boolean; scheduled_task?: boolean };
}

interface WebListeningExplorationResponse {
  success?: boolean;
  suggestions?: {
    tools?: string[];
    content_types?: string[];
    allow_url_patterns?: string[];
    queries?: string[];
    content_selector?: string | null;
  };
  observations?: Record<string, unknown>;
  warnings?: string[];
}

function JsonPreview({ value }: { value: unknown }) {
  if (!value) return null;
  return (
    <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-muted/60 p-3 text-xs whitespace-pre-wrap">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function parseList(value: string): string[] {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
}

export function WebListeningForm({ onMaterialized }: WebListeningFormProps) {
  const { t } = useTranslation();
  const { permissions } = useAuth();
  const canWriteSites = permissions.includes("sites.write");
  const canWriteSchedule = permissions.includes("schedule.write");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [goal, setGoal] = useState("");
  const [name, setName] = useState("");
  const [tools, setTools] = useState<string[]>(["crawler", "search"]);
  const [contentTypes, setContentTypes] = useState<string[]>(["file", "webpage"]);
  const [allowPatterns, setAllowPatterns] = useState("");
  const [queries, setQueries] = useState("");
  const [contentSelector, setContentSelector] = useState("main");
  const [scheduleInterval, setScheduleInterval] = useState("weekly");
  const [yamlText, setYamlText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<WebListeningValidationResponse | null>(null);
  const [exploration, setExploration] = useState<WebListeningExplorationResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleSelection = (value: string, current: string[], setCurrent: (values: string[]) => void) => {
    setCurrent(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  };
  const strategyReady = tools.length > 0 && contentTypes.length > 0;
  const exploreSite = async () => {
    if (!canWriteSites || !websiteUrl.trim() || !goal.trim()) return;
    setBusy("explore");
    setError(null);
    setMessage(null);
    try {
      const res = await apiPost<WebListeningExplorationResponse>("/api/web-listening/rules/explore", {
        website_url: websiteUrl.trim(),
        goal: goal.trim(),
      });
      const suggestions = res.suggestions || {};
      if (suggestions.tools?.length) setTools(suggestions.tools);
      if (suggestions.content_types?.length) setContentTypes(suggestions.content_types);
      setAllowPatterns((suggestions.allow_url_patterns || []).join("\n"));
      setQueries((suggestions.queries || []).join("\n"));
      setContentSelector(suggestions.content_selector || "");
      setExploration(res);
      setMessage(t("tasks.web_listening.explored"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("tasks.web_listening.explore_error"));
    } finally {
      setBusy(null);
    }
  };
  const draftRule = async () => {
    if (!canWriteSites || !websiteUrl.trim() || !goal.trim()) return;
    setBusy("draft");
    setError(null);
    setMessage(null);
    try {
      const scopedPatterns = parseList(allowPatterns);
      const scopedQueries = parseList(queries);
      const res = await apiPost<WebListeningValidationResponse>("/api/web-listening/rules/draft", {
        website_url: websiteUrl.trim(),
        goal: goal.trim(),
        name: name.trim() || undefined,
        tools,
        content_types: contentTypes,
        allow_url_patterns: scopedPatterns.length ? scopedPatterns : undefined,
        queries: scopedQueries.length ? scopedQueries : undefined,
        content_selector: contentSelector.trim() || undefined,
        schedule_interval: scheduleInterval.trim() || "weekly",
      });
      setYamlText(res.yaml || "");
      setResult(res);
      setMessage(t("tasks.web_listening.drafted"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("tasks.web_listening.draft_error"));
    } finally {
      setBusy(null);
    }
  };

  const validateRule = async () => {
    if (!canWriteSites || !yamlText.trim()) return;
    setBusy("validate");
    setError(null);
    setMessage(null);
    try {
      const res = await apiPost<WebListeningValidationResponse>("/api/web-listening/rules/validate", { rule_yaml: yamlText });
      setResult(res);
      setMessage(res.valid === false ? t("tasks.web_listening.invalid") : t("tasks.web_listening.valid"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("tasks.web_listening.validate_error"));
    } finally {
      setBusy(null);
    }
  };

  const materializeRule = async () => {
    if (!canWriteSites || !canWriteSchedule || !yamlText.trim()) return;
    setBusy("materialize");
    setError(null);
    setMessage(null);
    try {
      const res = await apiPost<WebListeningMaterializeResponse>("/api/web-listening/rules/materialize", { rule_yaml: yamlText });
      setResult(res);
      await apiPost("/api/schedule/reinit", {}).catch(() => null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("scheduled-tasks:changed"));
      }
      await onMaterialized?.();
      setMessage(t("tasks.web_listening.materialized"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("tasks.web_listening.materialize_error"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5" data-testid="form-web-listening">
      <p className="text-sm text-muted-foreground">{t("tasks.form.web_listening_desc")}</p>
      {!canWriteSites && (
        <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {t("tasks.web_listening.site_write_required")}
        </div>
      )}
      <div className="grid md:grid-cols-2 gap-4">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.website_url")}</span>
          <input value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} placeholder="https://www.soa.org/resources/research-reports/" className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" data-testid="input-web-listening-url" />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.name")}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="SOA Research Monitor" className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" data-testid="input-web-listening-name" />
        </label>
      </div>
      <label className="space-y-1.5 block">
        <span className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.goal")}</span>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" data-testid="textarea-web-listening-goal" />
      </label>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div>
          <h3 className="text-sm font-semibold">{t("tasks.web_listening.strategy")}</h3>
          <p className="text-xs text-muted-foreground mt-1">{t("tasks.web_listening.strategy_hint")}</p>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <fieldset className="space-y-2">
            <legend className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.tools")}</legend>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={tools.includes("crawler")} onChange={() => toggleSelection("crawler", tools, setTools)} data-testid="checkbox-web-listening-tool-crawler" />
              {t("tasks.web_listening.tool_crawler")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={tools.includes("search")} onChange={() => toggleSelection("search", tools, setTools)} data-testid="checkbox-web-listening-tool-search" />
              {t("tasks.web_listening.tool_search")}
            </label>
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.content_types")}</legend>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={contentTypes.includes("file")} onChange={() => toggleSelection("file", contentTypes, setContentTypes)} data-testid="checkbox-web-listening-content-file" />
              {t("tasks.web_listening.content_file")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={contentTypes.includes("webpage")} onChange={() => toggleSelection("webpage", contentTypes, setContentTypes)} data-testid="checkbox-web-listening-content-webpage" />
              {t("tasks.web_listening.content_webpage")}
            </label>
          </fieldset>
        </div>
        {!strategyReady && <p className="text-xs text-destructive">{t("tasks.web_listening.strategy_required")}</p>}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.allow_patterns")}</span>
          <textarea value={allowPatterns} onChange={(e) => setAllowPatterns(e.target.value)} rows={3} placeholder="/research/&#10;/globalassets/" className="w-full rounded-lg border border-border bg-card px-3 py-2 font-mono text-xs" data-testid="input-web-listening-allow-patterns" />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.queries")}</span>
          <textarea value={queries} onChange={(e) => setQueries(e.target.value)} rows={3} placeholder="site:example.com actuarial AI filetype:pdf" className="w-full rounded-lg border border-border bg-card px-3 py-2 text-xs" data-testid="input-web-listening-queries" />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("tasks.form.content_selector")}</span>
          <input value={contentSelector} onChange={(e) => setContentSelector(e.target.value)} placeholder="main" className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" data-testid="input-web-listening-selector" />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("tasks.sched.schedule_interval")}</span>
          <input value={scheduleInterval} onChange={(e) => setScheduleInterval(e.target.value)} placeholder="weekly" className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" data-testid="input-web-listening-schedule" />
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={exploreSite} disabled={busy !== null || !canWriteSites || !websiteUrl.trim() || !goal.trim()} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" data-testid="button-web-listening-explore">
          {busy === "explore" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Compass className="w-4 h-4" />}{t("tasks.web_listening.explore")}
        </button>
        <button type="button" onClick={draftRule} disabled={busy !== null || !canWriteSites || !websiteUrl.trim() || !goal.trim() || !strategyReady} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50" data-testid="button-web-listening-draft">
          {busy === "draft" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}{t("tasks.web_listening.draft")}
        </button>
        <button type="button" onClick={validateRule} disabled={busy !== null || !canWriteSites || !yamlText.trim()} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50" data-testid="button-web-listening-validate">
          {busy === "validate" ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}{t("tasks.web_listening.validate")}
        </button>
        <button type="button" onClick={materializeRule} disabled={busy !== null || !canWriteSites || !canWriteSchedule || !yamlText.trim()} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" data-testid="button-web-listening-materialize">
          {busy === "materialize" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{t("tasks.web_listening.materialize")}
        </button>
      </div>
      {exploration && (
        <div className="rounded-lg border border-border bg-card p-3" data-testid="panel-web-listening-exploration">
          <h4 className="text-sm font-semibold">{t("tasks.web_listening.exploration")}</h4>
          <JsonPreview value={exploration.observations} />
          {!!exploration.warnings?.length && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{exploration.warnings.join("; ")}</p>
          )}
        </div>
      )}
      {!canWriteSchedule && (
        <p className="text-xs text-muted-foreground">{t("tasks.web_listening.schedule_write_required")}</p>
      )}
      <label className="space-y-1.5 block">
        <span className="text-xs font-medium text-muted-foreground">{t("tasks.web_listening.yaml")}</span>
        <textarea value={yamlText} onChange={(e) => setYamlText(e.target.value)} rows={12} className="w-full rounded-lg border border-border bg-card px-3 py-2 font-mono text-xs" data-testid="textarea-web-listening-yaml" />
      </label>
      {message && <div className="rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">{message}</div>}
      {error && <div className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</div>}
      {!!result?.errors?.length && (
        <div className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive" data-testid="text-web-listening-errors">
          <AlertTriangle className="inline w-3.5 h-3.5 mr-1" />{result.errors.join("; ")}
        </div>
      )}
      {!!result?.warnings?.length && (
        <div className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300" data-testid="text-web-listening-warnings">
          {result.warnings.join("; ")}
        </div>
      )}
      {result?.materialized_config && (
        <div className="grid md:grid-cols-2 gap-4">
          <div><h4 className="text-sm font-semibold">{t("tasks.web_listening.preview_site")}</h4><JsonPreview value={result.materialized_config.site} /></div>
          <div><h4 className="text-sm font-semibold">{t("tasks.web_listening.preview_task")}</h4><JsonPreview value={result.materialized_config.scheduled_task} /></div>
        </div>
      )}
    </div>
  );
}
