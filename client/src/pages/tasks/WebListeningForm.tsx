import { useState } from "react";
import { Loader2, Wand2, CheckCircle2, AlertTriangle, Save } from "lucide-react";
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

function JsonPreview({ value }: { value: unknown }) {
  if (!value) return null;
  return (
    <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-muted/60 p-3 text-xs whitespace-pre-wrap">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function WebListeningForm({ onMaterialized }: WebListeningFormProps) {
  const { t } = useTranslation();
  const { permissions } = useAuth();
  const canWriteSites = permissions.includes("sites.write");
  const canWriteSchedule = permissions.includes("schedule.write");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [goal, setGoal] = useState("");
  const [name, setName] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<WebListeningValidationResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const draftRule = async () => {
    if (!canWriteSites || !websiteUrl.trim() || !goal.trim()) return;
    setBusy("draft");
    setError(null);
    setMessage(null);
    try {
      const res = await apiPost<WebListeningValidationResponse>("/api/web-listening/rules/draft", {
        website_url: websiteUrl.trim(),
        goal: goal.trim(),
        name: name.trim() || undefined,
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
      window.dispatchEvent(new CustomEvent("scheduled-tasks:changed"));
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
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={draftRule} disabled={busy !== null || !canWriteSites || !websiteUrl.trim() || !goal.trim()} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50" data-testid="button-web-listening-draft">
          {busy === "draft" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}{t("tasks.web_listening.draft")}
        </button>
        <button type="button" onClick={validateRule} disabled={busy !== null || !canWriteSites || !yamlText.trim()} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50" data-testid="button-web-listening-validate">
          {busy === "validate" ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}{t("tasks.web_listening.validate")}
        </button>
        <button type="button" onClick={materializeRule} disabled={busy !== null || !canWriteSites || !canWriteSchedule || !yamlText.trim()} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" data-testid="button-web-listening-materialize">
          {busy === "materialize" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{t("tasks.web_listening.materialize")}
        </button>
      </div>
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
