import { motion } from "framer-motion";
import { Square, CheckCircle2, XCircle, Loader2, Clock, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import type { HistoryTask, Task, TaskContractResult } from "./Tasks.types";

function statusIcon(status: string) {
  switch (status) {
    case "running":
      return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
    case "success":
    case "completed":
    case "succeeded":
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

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    running: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
    success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    completed: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    succeeded: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    pending: "bg-muted text-muted-foreground",
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
      data-testid={`status-badge-${status}`}
    >
      {statusIcon(status)}
      {status}
    </span>
  );
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

interface TaskCardProps {
  task: Task;
  index: number;
  onStop?: (id: string) => void;
  onViewLog?: (id: string | undefined, name: string | undefined, task?: HistoryTask) => void;
}

export function TaskResultSummary({ type, result }: { type?: string; result?: TaskContractResult }) {
  const { t } = useTranslation();
  if (!result) return null;
  if (type === "chunk_generation") {
    const chunkSets = result.chunk_sets || [];
    const chunks = chunkSets.reduce((total, row) => total + Number(row.chunk_count || 0), 0);
    return (
      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground" data-testid="task-chunk-result">
        <span>{t("tasks.stats.chunk_sets")}: {chunkSets.length}</span>
        <span>{t("tasks.stats.chunks")}: {chunks}</span>
      </div>
    );
  }
  if (type === "embedding_generation") {
    return (
      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground" data-testid="task-embedding-result">
        <span>{result.provider || "?"} / {result.model || "?"} / {result.dimension ?? "?"}</span>
        <span>{t("tasks.stats.generated")}: {result.generated ?? 0}</span>
        <span>{t("tasks.stats.reused")}: {result.reused ?? 0}</span>
        <span>{t("tasks.stats.invalid_regenerated")}: {result.invalid_regenerated ?? 0}</span>
        <span>{t("tasks.stats.failed")}: {result.failed ?? 0}</span>
      </div>
    );
  }
  return null;
}

export function TaskCard({ task, index, onStop, onViewLog }: TaskCardProps) {
  const { t } = useTranslation();
  return (
    <motion.div
      custom={index}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4, ease: "easeOut" }}
      className="rounded-xl border border-border bg-card p-5"
      data-testid={`card-active-task-${task.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            {statusBadge(task.status)}
            <span className="font-semibold text-sm truncate">{task.name}</span>
          </div>
          {task.current_activity && (
            <p className="text-xs text-muted-foreground mt-1 truncate" data-testid={`text-activity-${task.id}`}>{task.current_activity}</p>
          )}
          <p className="text-[11px] font-mono text-muted-foreground mt-1" data-testid={`text-task-id-${task.id}`}>ID: {task.id}</p>
        </div>
        <div className="flex items-center gap-1">
        {onViewLog && (
          <button onClick={() => onViewLog(task.id, task.name, task)}
            className="shrink-0 p-2 rounded-lg border border-border hover:bg-muted transition-colors"
            data-testid={`button-active-task-log-${task.id}`} title={t("tasks.log")}><Zap className="w-4 h-4" /></button>
        )}
        {onStop && (
          <button onClick={() => onStop(task.id)}
            className="shrink-0 p-2 rounded-lg bg-red-500/10 text-red-600 hover:bg-red-500/20 transition-colors"
            data-testid={`button-stop-task-${task.id}`} title={t("tasks.stop")}><Square className="w-4 h-4" /></button>
        )}
        </div>
      </div>
      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
          <span>{task.items_processed}/{task.items_total || "?"}</span>
          <span>{Math.round(task.progress)}%</span>
        </div>
        <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
          <motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }}
            animate={{ width: `${Math.min(task.progress, 100)}%` }} transition={{ duration: 0.5 }} />
        </div>
      </div>
      <div className="mt-2"><TaskResultSummary type={task.type} result={task.result} /></div>
      <p className="text-[11px] text-muted-foreground mt-2">{t("tasks.started")}: {formatDate(task.started_at)}</p>
    </motion.div>
  );
}

export { statusBadge, statusIcon, formatDate };
