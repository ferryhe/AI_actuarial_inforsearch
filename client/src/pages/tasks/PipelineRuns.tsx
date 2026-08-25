import { useEffect, useState, useCallback } from "react";
import {
  RefreshCw, ChevronDown, ChevronUp, Loader2, AlertCircle,
  FileText, ListTree, Network,
} from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";
import { statusBadge, formatDate } from "./TaskCard";
import type { PipelineRun, PipelineRunDetail, PipelineStage, PipelineChildRun } from "./Tasks.types";

interface PipelineRunsProps {
  onViewLog: (taskId: string, taskName: string) => void;
}

function parseJsonField(raw: string | null): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function summarizeJson(raw: string | null): string | null {
  if (!raw) return null;
  const parsed = parseJsonField(raw);
  if (parsed === null) return raw;
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const entries = Object.entries(parsed as Record<string, unknown>);
    if (entries.length === 0) return "{}";
    const preview = entries
      .slice(0, 6)
      .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
      .join(", ");
    return entries.length > 6 ? `${preview}, …` : preview;
  }
  return JSON.stringify(parsed);
}

function StageDetail({ stage }: { stage: PipelineStage }) {
  const { t } = useTranslation();
  return (
    <div className="border-t border-border/60 px-4 py-3 space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {stage.started_at && (
          <span>{t("tasks.started")}: {formatDate(stage.started_at)}</span>
        )}
        {stage.finished_at && (
          <span>{t("tasks.pipeline.finished")}: {formatDate(stage.finished_at)}</span>
        )}
        {stage.retry_count > 0 && (
          <span>{t("tasks.pipeline.retries")}: {stage.retry_count}</span>
        )}
      </div>
      {stage.error && (
        <div className="rounded-md bg-red-500/10 text-red-600 dark:text-red-400 px-3 py-2 text-xs break-all"
          data-testid={`pipeline-stage-error-${stage.stage_name}`}>
          {t("tasks.pipeline.error")}: {stage.error}
        </div>
      )}
      {summarizeJson(stage.options_json) && (
        <div className="text-xs">
          <span className="font-semibold text-muted-foreground">{t("tasks.pipeline.options")}: </span>
          <code className="text-foreground/80 break-all">{summarizeJson(stage.options_json)}</code>
        </div>
      )}
      {summarizeJson(stage.checkpoint_json) && (
        <div className="text-xs">
          <span className="font-semibold text-muted-foreground">{t("tasks.pipeline.checkpoint")}: </span>
          <code className="text-foreground/80 break-all">{summarizeJson(stage.checkpoint_json)}</code>
        </div>
      )}
      {summarizeJson(stage.committed_artifacts_json) && (
        <div className="text-xs">
          <span className="font-semibold text-muted-foreground">{t("tasks.pipeline.artifacts")}: </span>
          <code className="text-foreground/80 break-all">{summarizeJson(stage.committed_artifacts_json)}</code>
        </div>
      )}
    </div>
  );
}

function ChildRunRow({ child }: { child: PipelineChildRun }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 text-xs text-muted-foreground">
      {statusBadge(child.status)}
      <code className="text-foreground/80 break-all">{child.child_run_id}</code>
      {child.partial ? <span className="text-amber-500">{t("tasks.pipeline.partial")}</span> : null}
      {child.error && <span className="text-red-500 break-all">{child.error}</span>}
    </div>
  );
}

export function PipelineRuns({ onViewLog }: PipelineRunsProps) {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, PipelineRunDetail>>({});
  const [detailLoading, setDetailLoading] = useState<Record<string, boolean>>({});
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<{ runs?: PipelineRun[]; count?: number }>("/api/pipeline/runs?limit=50");
      setRuns(res.runs || []);
    } catch (e) {
      console.error("Failed to fetch pipeline runs:", e);
      setError(t("tasks.pipeline.load_error"));
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { void fetchRuns(); }, [fetchRuns]);

  const toggleExpand = async (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);
    setDetailErrors((prev) => ({ ...prev, [runId]: "" }));
    if (details[runId]) return;
    setDetailLoading((prev) => ({ ...prev, [runId]: true }));
    try {
      const detail = await apiGet<PipelineRunDetail>(`/api/pipeline/runs/${encodeURIComponent(runId)}`);
      setDetails((prev) => ({ ...prev, [runId]: detail }));
    } catch (e) {
      console.error("Failed to fetch pipeline run detail:", e);
      setDetailErrors((prev) => ({ ...prev, [runId]: t("tasks.pipeline.detail_error") }));
    } finally {
      setDetailLoading((prev) => ({ ...prev, [runId]: false }));
    }
  };

  return (
    <div data-testid="pipeline-runs">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Network className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">{t("tasks.pipeline.title")}</h2>
        </div>
        <button onClick={() => void fetchRuns()}
          className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          data-testid="button-refresh-pipeline-runs" title={t("tasks.refresh")}>
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs text-red-500 mb-3"
          data-testid="text-pipeline-runs-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{error}</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <p className="text-xs text-muted-foreground py-1" data-testid="text-no-pipeline-runs">
          {t("tasks.pipeline.no_runs")}
        </p>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const isExpanded = expandedRunId === run.run_id;
            const detail = details[run.run_id];
            const isLoading = detailLoading[run.run_id];
            return (
              <div key={run.run_id} className="rounded-xl border border-border bg-card overflow-hidden"
                data-testid={`pipeline-run-${run.run_id}`}>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void toggleExpand(run.run_id)}
                    className="flex-1 min-w-0 flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/40 transition-colors"
                    data-testid={`button-expand-run-${run.run_id}`}
                    aria-expanded={isExpanded}
                  >
                    {statusBadge(run.status)}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-foreground/80 truncate">{run.run_id}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground mt-0.5">
                        {run.correlation_id && (
                          <span>{t("tasks.pipeline.task_id")}: <code>{run.correlation_id}</code></span>
                        )}
                        {run.source_type && <span>{t("tasks.pipeline.source")}: {run.source_type}</span>}
                        {run.started_at && <span>{t("tasks.started")}: {formatDate(run.started_at)}</span>}
                        {run.finished_at && <span>{t("tasks.pipeline.finished")}: {formatDate(run.finished_at)}</span>}
                      </div>
                    </div>
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
                  </button>
                  {run.correlation_id && (
                    <button
                      type="button"
                      onClick={() => onViewLog(run.correlation_id, run.correlation_id)}
                      className="shrink-0 mr-2 p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      data-testid={`button-pipeline-log-${run.run_id}`}
                      title={t("tasks.pipeline.view_log")}
                    >
                      <FileText className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {isExpanded && (
                  <div className="border-t border-border/60" data-testid={`pipeline-run-detail-${run.run_id}`}>
                    {run.error && (
                      <div className="px-4 py-2 text-xs text-red-500 border-b border-border/60 break-all"
                        data-testid={`pipeline-run-error-${run.run_id}`}>
                        {t("tasks.pipeline.error")}: {run.error}
                      </div>
                    )}

                    <div className="px-4 py-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <ListTree className="w-3.5 h-3.5" />
                      {t("tasks.pipeline.stages")}
                    </div>

                    {isLoading ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : detailErrors[run.run_id] ? (
                      <p className="px-4 pb-3 text-xs text-red-500" data-testid="text-pipeline-detail-error">{detailErrors[run.run_id]}</p>
                    ) : detail && detail.stages.length === 0 ? (
                      <p className="px-4 pb-3 text-xs text-muted-foreground" data-testid="text-no-pipeline-stages">{t("tasks.pipeline.no_stages")}</p>
                    ) : detail ? (
                      <div data-testid={`pipeline-stages-${run.run_id}`}>
                        {detail.stages.map((stage) => (
                          <div key={`${stage.stage_name}-${stage.stage_order}`}
                            className="border-t border-border/60"
                            data-testid={`pipeline-stage-${stage.stage_name}`}>
                            <div className="flex items-center gap-3 px-4 py-2">
                              <span className="text-[11px] text-muted-foreground font-mono">{stage.stage_order}</span>
                              {statusBadge(stage.status)}
                              <span className="text-sm font-medium">{stage.stage_name}</span>
                            </div>
                            <StageDetail stage={stage} />
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {detail && detail.child_runs.length > 0 && (
                      <div className="border-t border-border/60">
                        <div className="px-4 py-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          <Network className="w-3.5 h-3.5" />
                          {t("tasks.pipeline.child_runs")}
                        </div>
                        <div data-testid={`pipeline-child-runs-${run.run_id}`}>
                          {detail.child_runs.map((child) => (
                            <ChildRunRow key={child.child_run_id} child={child} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default PipelineRuns;
