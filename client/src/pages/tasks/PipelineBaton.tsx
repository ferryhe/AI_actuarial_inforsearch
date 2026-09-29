import { useCallback, useEffect, useState } from "react";
import { Loader2, Play, RefreshCw } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { CheckboxField, FormField, InputField } from "@/components/FormFields";
import { useAuth } from "@/context/AuthContext";
import { apiGet, apiPost } from "@/lib/api";
import { CatalogForm } from "./CatalogForm";
import { ChunkForm } from "./ChunkForm";
import { MarkdownForm } from "./MarkdownForm";
import { RagIndexForm } from "./RagIndexForm";
import { PipelineBatonResults, type PipelineStepName, type PipelineView } from "./PipelineBatonResults";

type StepName = PipelineStepName;

interface ScheduledTask {
  name: string;
  type: string;
  interval: string;
  timezone?: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

const steps: Array<{ step: StepName; label: string; testId: string }> = [
  { step: "scheduled", label: "Scheduled Collection", testId: "pipeline-step-scheduled" },
  { step: "markdown_conversion", label: "Markdown", testId: "pipeline-step-markdown_conversion" },
  { step: "catalog", label: "Catalog", testId: "pipeline-step-catalog" },
  { step: "chunk_generation", label: "Chunk & Embedding", testId: "pipeline-step-chunk_generation" },
  { step: "rag_indexing", label: "KB Index & Ready Data", testId: "pipeline-step-rag_indexing" },
];

const batonOwnedFields: Partial<Record<StepName, string[]>> = {
  rag_indexing: ["incremental", "force_reindex", "kb_id"],
};

export function PipelineBaton({ onViewLog }: { onViewLog: (taskId: string, taskName: string) => void }) {
  const { t } = useTranslation();
  const { permissions } = useAuth();
  const canRun = permissions.includes("tasks.run");
  const canConfigure = permissions.includes("schedule.write");
  const [expanded, setExpanded] = useState<Set<string> | null>(null);
  const [showFailuresOnly, setShowFailuresOnly] = useState(false);
  const [view, setView] = useState<PipelineView | null>(null);
  const [scheduledTask, setScheduledTask] = useState<ScheduledTask | null>(null);
  const [scheduledInterval, setScheduledInterval] = useState("");
  const [scheduledEnabled, setScheduledEnabled] = useState(true);
  const [scheduledSite, setScheduledSite] = useState("");
  const [scheduledMaxPages, setScheduledMaxPages] = useState("");
  const [scheduledMaxDepth, setScheduledMaxDepth] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [nextView, scheduled] = await Promise.all([
        apiGet<PipelineView>("/api/pipeline/status"),
        apiGet<{ tasks: ScheduledTask[] }>("/api/scheduled-tasks"),
      ]);
      setView(nextView);
      const source = (scheduled.tasks || []).find((task) => task.name === "Scheduled Collection" && task.type === "scheduled") || null;
      setScheduledTask(source);
      setScheduledInterval(source?.interval || "");
      setScheduledEnabled(source?.enabled ?? true);
      setScheduledSite(String(source?.params.site || ""));
      setScheduledMaxPages(source?.params.max_pages == null ? "" : String(source.params.max_pages));
      setScheduledMaxDepth(source?.params.max_depth == null ? "" : String(source.params.max_depth));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("tasks.pipeline.load_error"));
    }
  }, [t]);

  useEffect(() => { void refresh(); }, [refresh]);

  const toggle = (step: StepName) => {
    setExpanded((current) => {
      const next = new Set(current || view?.stages.filter((stage) => stage.status === "failed").map((stage) => stage.step));
      if (next.has(step)) next.delete(step);
      else next.add(step);
      return next;
    });
  };

  const saveOverride = async (step: Exclude<StepName, "scheduled">, task: Record<string, unknown>) => {
    if (!view) return;
    setBusy(step);
    try {
      const forbiddenFields = new Set(["type", "name", "file_urls", ...(batonOwnedFields[step] || [])]);
      const payload = Object.fromEntries(
        Object.entries(task).filter(([key, value]) => !forbiddenFields.has(key) && value !== undefined)
      );
      const overrides = { ...view.config.overrides };
      if (Object.keys(payload).length > 0) overrides[step] = payload;
      else delete overrides[step];
      setView(await apiPost<PipelineView>("/api/pipeline/config", { overrides }));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("tasks.sched.save_fail"));
    } finally {
      setBusy(null);
    }
  };

  const saveScheduled = async () => {
    if (!scheduledTask) return;
    setBusy("scheduled");
    try {
      const params = { ...scheduledTask.params };
      for (const [key, value] of [["site", scheduledSite], ["max_pages", scheduledMaxPages], ["max_depth", scheduledMaxDepth]]) {
        if (!value.trim()) {
          delete params[key];
        } else if (key === "site") {
          params[key] = value.trim();
        } else {
          const numericValue = Number(value);
          if (!Number.isFinite(numericValue)) throw new Error(`${key} must be a finite number`);
          params[key] = numericValue;
        }
      }
      const nextInterval = scheduledInterval.trim();
      const scheduleChanged = nextInterval !== scheduledTask.interval;
      await apiPost("/api/scheduled-tasks/update", {
        original_name: scheduledTask.name,
        name: scheduledTask.name,
        type: scheduledTask.type,
        ...(scheduleChanged ? {
          interval: nextInterval,
          ...(!nextInterval.startsWith("every ") && scheduledTask.timezone
            ? { timezone: scheduledTask.timezone }
            : {}),
        } : {}),
        enabled: scheduledEnabled,
        params,
      });
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("tasks.sched.save_fail"));
    } finally {
      setBusy(null);
    }
  };

  const start = async () => {
    setBusy("start");
    try {
      setView(await apiPost<PipelineView>("/api/pipeline/start"));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("tasks.form.start_error"));
    } finally {
      setBusy(null);
    }
  };

  const hasExistingResults = Boolean(view?.stages.some((stage) => stage.tasks.length > 0));

  const settingsFor = (step: StepName) => {
    if (!view) return null;
    const initialTask = view.config.overrides[step] || {};
    if (step === "scheduled") {
      return scheduledTask ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FormField label={t("tasks.sched.schedule_interval")} hint={t("tasks.sched.interval_hint")}>
              <InputField value={scheduledInterval} onChange={setScheduledInterval} placeholder="daily at 02:00" testId="input-pipeline-scheduled-interval" />
            </FormField>
            <FormField label={t("tasks.sched.enabled")}>
              <CheckboxField checked={scheduledEnabled} onChange={setScheduledEnabled} label={t("tasks.sched.enabled")} testId="checkbox-pipeline-scheduled-enabled" />
            </FormField>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <InputField value={scheduledSite} onChange={setScheduledSite} placeholder={t("tasks.sched.param.site")} testId="input-pipeline-scheduled-site" />
            <InputField value={scheduledMaxPages} onChange={setScheduledMaxPages} placeholder={t("tasks.sched.param.max_pages")} type="number" testId="input-pipeline-scheduled-max-pages" />
            <InputField value={scheduledMaxDepth} onChange={setScheduledMaxDepth} placeholder={t("tasks.sched.param.max_depth")} type="number" testId="input-pipeline-scheduled-max-depth" />
          </div>
          <button type="button" onClick={() => void saveScheduled()} disabled={!canConfigure || busy === step}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">
            {t("common.save")}
          </button>
        </div>
      ) : <p className="text-sm text-muted-foreground">Scheduled Collection not found</p>;
    }
    if (step === "markdown_conversion") return <MarkdownForm key={JSON.stringify(initialTask)} settingsMode initialTask={initialTask} onSubmit={(task) => void saveOverride(step, task)} submitting={busy === step} />;
    if (step === "catalog") return <CatalogForm key={JSON.stringify(initialTask)} settingsMode initialTask={initialTask} onSubmit={(task) => void saveOverride(step, task)} submitting={busy === step} />;
    if (step === "chunk_generation") return <ChunkForm key={JSON.stringify(initialTask)} settingsMode initialTask={initialTask} onSubmit={(task) => void saveOverride(step, task)} submitting={busy === step} />;
    return <RagIndexForm key={JSON.stringify(initialTask)} settingsMode initialTask={initialTask} onSubmit={(task) => void saveOverride(step, task)} submitting={busy === step} />;
  };

  return (
    <div className="space-y-4" data-testid="pipeline-baton">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("tasks.pipeline.title")}</h2>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void refresh()} className="rounded-lg border border-border p-2" aria-label={t("tasks.refresh")}><RefreshCw className="h-4 w-4" /></button>
          <button type="button" onClick={() => void start()} disabled={!canRun || busy === "start" || view?.state.round_status === "running"}
            className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50" data-testid="button-start-pipeline-baton">
            {busy === "start" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{t(hasExistingResults ? "tasks.pipeline.rerun" : "tasks.pipeline.start")}
          </button>
        </div>
      </div>
      {error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>}
      <PipelineBatonResults view={view} steps={steps} expanded={expanded} showFailuresOnly={showFailuresOnly} onShowFailuresOnly={setShowFailuresOnly} onToggle={toggle} onViewLog={onViewLog} renderSettings={settingsFor} t={t} />
    </div>
  );
}
