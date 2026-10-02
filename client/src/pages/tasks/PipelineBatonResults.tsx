import { CheckCircle2, ChevronDown, ChevronUp, Square, XCircle } from "lucide-react";
import type { ReactNode } from "react";

export type PipelineStepName = "scheduled" | "markdown_conversion" | "catalog" | "chunk_generation" | "rag_indexing";

interface PipelineStageTask {
  task_id: string;
  status: string;
  error_count: number;
  first_error_code: string;
  first_error_summary: string;
  failed_items: number;
  kb_id?: string;
  subtask?: "kb_index" | "ready_data_build";
  label?: string;
}

export interface PipelineView {
  config: { overrides: Partial<Record<PipelineStepName, Record<string, unknown>>> };
  state: { round_status: string; current_step?: string; last_check?: string };
  summary: {
    status: string;
    successful_stages: number;
    failed_stages: number;
    stopped_stages: number;
    latest_failure: { task_id: string | null; stage: PipelineStepName; error_count: number; first_error_code: string; summary: string } | null;
  };
  stages: Array<{
    step: PipelineStepName;
    status: string;
    tasks: PipelineStageTask[];
    failures: Array<{ task_id: string | null; first_error_code: string; first_error_summary: string }>;
  }>;
}

interface PipelineStep {
  step: PipelineStepName;
  label: string;
  testId: string;
}

interface PipelineBatonResultsProps {
  view: PipelineView | null;
  steps: PipelineStep[];
  expanded: Set<string> | null;
  showFailuresOnly: boolean;
  onShowFailuresOnly: (value: boolean) => void;
  onToggle: (step: PipelineStepName) => void;
  onViewLog: (taskId: string, taskName: string) => void;
  renderSettings: (step: PipelineStepName) => ReactNode;
  t: (key: string) => string;
}

export function PipelineBatonResults({
  view,
  steps,
  expanded,
  showFailuresOnly,
  onShowFailuresOnly,
  onToggle,
  onViewLog,
  renderSettings,
  t,
}: PipelineBatonResultsProps) {
  const latestFailure = view?.summary.latest_failure;
  const failedSteps = new Set(view?.stages.filter((stage) => stage.status === "failed").map((stage) => stage.step));
  return <>
    {view && <p className="text-xs text-muted-foreground" data-testid="pipeline-display-status">{t(`tasks.pipeline.${view.summary.status}`)}</p>}
    {view && <p className="text-xs text-muted-foreground">
      {t("tasks.pipeline.stages")}: {t("tasks.pipeline.successful")}: {view.summary.successful_stages} · {t("tasks.pipeline.failed")}: {view.summary.failed_stages} · {t("tasks.pipeline.stopped")}: {view.summary.stopped_stages}
    </p>}
    {latestFailure && (latestFailure.task_id ? <button type="button" onClick={() => onViewLog(latestFailure.task_id!, latestFailure.stage)} className="min-h-[48px] text-left text-xs text-destructive underline" data-testid="button-pipeline-latest-failure">
      {t("tasks.pipeline.latest_failure")}: {latestFailure.summary} · {t("tasks.pipeline.view_log")}
    </button> : <p className="text-xs text-destructive" data-testid="pipeline-latest-failure-summary">{t("tasks.pipeline.latest_failure")}: {latestFailure.summary}</p>)}
    <label className="flex min-h-[48px] items-center gap-2 text-xs">
      <input type="checkbox" checked={showFailuresOnly} onChange={(event) => onShowFailuresOnly(event.target.checked)} data-testid="pipeline-failed-only" />
      {t("tasks.pipeline.failed_only")}
    </label>
    <div className="space-y-2">
      {steps.filter((step) => !showFailuresOnly || view?.stages.find((item) => item.step === step.step)?.status === "failed").map((step, index) => {
        const stage = view?.stages.find((item) => item.step === step.step);
        const hasOverride = Boolean(view?.config.overrides[step.step]);
        const stageStatus = stage?.status || "idle";
        const isExpanded = (expanded || failedSteps).has(step.step);
        return <div key={step.step} className={`rounded-xl border bg-card ${stageStatus === "failed" ? "border-destructive/50" : "border-border"}`} data-testid={step.testId}>
          <button type="button" onClick={() => onToggle(step.step)} aria-expanded={isExpanded} className="flex min-h-[48px] w-full items-center gap-3 px-4 py-3 text-left" data-testid={`button-pipeline-stage-${step.step}`}>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-xs font-semibold">{index + 1}</span>
            <span className="flex-1 font-medium">{step.label}{step.step === "rag_indexing" ? ` — ${t("tasks.pipeline.all_indexable_kbs")}` : ""}</span>
            <span className={`flex items-center gap-1 text-xs ${stageStatus === "failed" ? "text-destructive" : "text-muted-foreground"}`}>
              {stageStatus === "failed" ? <XCircle className="h-4 w-4" /> : stageStatus === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : stageStatus === "stopped" ? <Square className="h-4 w-4 text-amber-500" /> : null}
              {t(`tasks.pipeline.${stageStatus}`)}
            </span>
            <span className="text-xs text-muted-foreground">{hasOverride ? t("tasks.pipeline.saved") : t("tasks.pipeline.default_settings")}</span>
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {stage && stage.tasks.length > 0 && <div className="flex flex-wrap gap-2 border-t border-border px-4 py-2">
            {stage.tasks.map((task) => <button key={task.task_id} type="button" onClick={() => onViewLog(task.task_id, `${task.label || step.label}${task.kb_id ? `: ${task.kb_id}` : ""}`)} className="min-h-[48px] text-xs text-primary underline" data-testid={`button-pipeline-task-log-${task.task_id}`}>
              {task.label || step.label} · {task.status} · {task.task_id}{task.kb_id ? ` · ${task.kb_id}` : ""} · {t("tasks.pipeline.view_log")}
              {(task.error_count > 0 || task.failed_items > 0) && <span> · {t("tasks.pipeline.errors")}: {task.error_count} · {t("tasks.pipeline.failed_items")}: {task.failed_items}{task.first_error_code ? ` · ${task.first_error_code}` : ""}{task.first_error_summary ? ` · ${task.first_error_summary}` : ""}</span>}
            </button>)}
          </div>}
          {stage?.failures.map((failure, failureIndex) => failure.task_id ? <button key={`${failure.first_error_code}-${failureIndex}`} type="button" onClick={() => onViewLog(failure.task_id!, step.label)} className="block min-h-[48px] border-t border-border px-4 py-2 text-left text-xs text-destructive underline" data-testid={`button-pipeline-failure-log-${failure.task_id}`}>
            {failure.first_error_summary} · {t("tasks.pipeline.view_log")}
          </button> : <p key={`${failure.first_error_code}-${failureIndex}`} className="border-t border-border px-4 py-2 text-xs text-destructive">{failure.first_error_summary}</p>)}
          {isExpanded && <div className="border-t border-border p-4">{renderSettings(step.step)}</div>}
        </div>;
      })}
    </div>
  </>;
}
