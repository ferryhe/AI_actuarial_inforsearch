import { CheckCircle2, ChevronDown, ChevronUp, Square, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { EnumDiagnostic, EnumDisplay } from "@/lib/enum-display";

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

const readyDataFailurePrefixes = ["build_failure", "publish_failure", "stale_snapshot", "invalid_selector"];
const hasReadyDataFailurePrefix = (summary: string) => readyDataFailurePrefixes.some((prefix) => summary.startsWith(prefix));

function safeFailureSummary(code: string, summary: string, t: (key: string) => string): string {
  if (hasReadyDataFailurePrefix(summary)) return t("tasks.pipeline.ready_data_failure_summary");
  if (!code || !summary.includes(code)) return summary;
  const kbId = summary.match(/^Knowledge base (.+?) failed:/)?.[1];
  const key = code === "index_launch_failed" && kbId
    ? "tasks.pipeline.index_launch_failed_summary"
    : kbId ? "tasks.pipeline.kb_failure_summary" : "tasks.pipeline.failure_summary";
  return t(key).replace("{kbId}", kbId || "");
}

function FailureDiagnostic({ code, summary, t, canInspectRaw }: {
  code: string;
  summary: string;
  t: (key: string) => string;
  canInspectRaw: boolean;
}) {
  if (!canInspectRaw || (!code && !hasReadyDataFailurePrefix(summary))) return null;
  return <details className="text-[10px] text-muted-foreground" onClick={(event) => event.stopPropagation()}>
    <summary>{t("enum.diagnostic_details")}</summary>{code && <code>{code}</code>}<p>{summary}</p>
  </details>;
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
  canInspectRaw?: boolean;
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
  canInspectRaw = false,
}: PipelineBatonResultsProps) {
  const latestFailure = view?.summary.latest_failure;
  const failedSteps = new Set(view?.stages.filter((stage) => stage.status === "failed").map((stage) => stage.step));
  return <>
    {view && <div className="text-xs text-muted-foreground" data-testid="pipeline-display-status">
      <EnumDisplay category="status" value={view.summary.status} t={t} />
      <EnumDiagnostic category="status" value={view.summary.status} t={t} canInspectRaw={canInspectRaw} />
    </div>}
    {view && <p className="text-xs text-muted-foreground">
      {t("tasks.pipeline.stages")}: {t("tasks.pipeline.successful")}: {view.summary.successful_stages} · {t("tasks.pipeline.failed")}: {view.summary.failed_stages} · {t("tasks.pipeline.stopped")}: {view.summary.stopped_stages}
    </p>}
    {latestFailure && <div data-testid="pipeline-latest-failure">
      {latestFailure.task_id ? <button type="button" onClick={() => onViewLog(latestFailure.task_id!, latestFailure.stage)} className="min-h-[48px] text-left text-xs text-destructive underline" data-testid="button-pipeline-latest-failure">
        {t("tasks.pipeline.latest_failure")}: {safeFailureSummary(latestFailure.first_error_code, latestFailure.summary, t)} · {t("tasks.pipeline.view_log")}
      </button> : <p className="text-xs text-destructive" data-testid="pipeline-latest-failure-summary">{t("tasks.pipeline.latest_failure")}: {safeFailureSummary(latestFailure.first_error_code, latestFailure.summary, t)}</p>}
      <FailureDiagnostic code={latestFailure.first_error_code} summary={latestFailure.summary} t={t} canInspectRaw={canInspectRaw} />
    </div>}
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
            <span className={`flex items-center gap-1 text-xs ${stageStatus === "failed" ? "text-destructive" : "text-muted-foreground"}`} data-testid={`pipeline-stage-status-${step.step}`}>
              {stageStatus === "failed" ? <XCircle className="h-4 w-4" /> : stageStatus === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : stageStatus === "stopped" ? <Square className="h-4 w-4 text-amber-500" /> : null}
              <EnumDisplay category="status" value={stageStatus} t={t} />
            </span>
            <span className="text-xs text-muted-foreground">{hasOverride ? t("tasks.pipeline.saved") : t("tasks.pipeline.default_settings")}</span>
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          <EnumDiagnostic category="status" value={stageStatus} t={t} canInspectRaw={canInspectRaw} />
          {stage && stage.tasks.length > 0 && <div className="flex flex-wrap gap-2 border-t border-border px-4 py-2">
            {stage.tasks.map((task) => <div key={task.task_id}>
              <button type="button" onClick={() => onViewLog(task.task_id, `${task.label || step.label}${task.kb_id ? `: ${task.kb_id}` : ""}`)} className="min-h-[48px] text-xs text-primary underline" data-testid={`button-pipeline-task-log-${task.task_id}`}>
                {task.label || step.label} · <EnumDisplay category="status" value={task.status} t={t} /> · {task.task_id}{task.kb_id ? ` · ${task.kb_id}` : ""} · {t("tasks.pipeline.view_log")}
                {(task.error_count > 0 || task.failed_items > 0) && <span> · {t("tasks.pipeline.errors")}: {task.error_count} · {t("tasks.pipeline.failed_items")}: {task.failed_items}{task.first_error_code ? <> · <EnumDisplay category="error_code" value={task.first_error_code} t={t} /></> : ""}{task.first_error_summary ? ` · ${safeFailureSummary(task.first_error_code, task.first_error_summary, t)}` : ""}</span>}
              </button>
              <EnumDiagnostic category="status" value={task.status} t={t} canInspectRaw={canInspectRaw} />
              <FailureDiagnostic code={task.first_error_code} summary={task.first_error_summary} t={t} canInspectRaw={canInspectRaw} />
            </div>)}
          </div>}
          {stage?.failures.map((failure, failureIndex) => <div key={`${failure.first_error_code}-${failureIndex}`} className="border-t border-border px-4 py-2 text-xs text-destructive" data-testid={`pipeline-failure-${step.step}-${failureIndex}`}>
            {failure.task_id ? <button type="button" onClick={() => onViewLog(failure.task_id!, step.label)} className="min-h-[48px] text-left underline" data-testid={`button-pipeline-failure-log-${failure.task_id}`}>
              {safeFailureSummary(failure.first_error_code, failure.first_error_summary, t)} · {t("tasks.pipeline.view_log")}
            </button> : <span>{safeFailureSummary(failure.first_error_code, failure.first_error_summary, t)}</span>}
            <FailureDiagnostic code={failure.first_error_code} summary={failure.first_error_summary} t={t} canInspectRaw={canInspectRaw} />
          </div>)}
          {isExpanded && <div className="border-t border-border p-4">{renderSettings(step.step)}</div>}
        </div>;
      })}
    </div>
  </>;
}
