import { motion } from "framer-motion";
import { Square, CheckCircle2, XCircle, Loader2, Clock, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import type { HistoryTask, Task } from "./Tasks.types";
import { TaskMetrics } from "./TaskMetrics";
import { IconButton } from "@/components/a11y/IconButton";
import { EnumDiagnostic, EnumDisplay, canInspectEnumRaw } from "@/lib/enum-display";
import { FormattedDateTime } from "@/components/FormattedDateTime";

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

function statusBadge(status: string, t: (key: string) => string, canInspectRaw = false) {
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
    <div className="inline-flex flex-col"
    >
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full",
        colors[status] || "bg-muted text-muted-foreground"
      )}
      data-testid="status-badge"
    >
      {statusIcon(status)}
      <EnumDisplay category="status" value={status} t={t} />
    </span>
    <EnumDiagnostic category="status" value={status} t={t} canInspectRaw={canInspectRaw} />
    </div>
  );
}

interface TaskCardProps {
  task: Task;
  index: number;
  onStop?: (id: string, name?: string) => void;
  onViewLog?: (id: string | undefined, name: string | undefined, task?: HistoryTask) => void;
}

export function TaskCard({ task, index, onStop, onViewLog }: TaskCardProps) {
  const { t, lang } = useTranslation();
  const { user } = useAuth();
  const target = task.name?.trim() || task.id;
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
            {statusBadge(task.status, t, canInspectEnumRaw(user?.role))}
            <span className="font-semibold text-sm truncate">{task.name}</span>
          </div>
          {task.current_activity && (
            <p className="text-xs text-muted-foreground mt-1 truncate" data-testid={`text-activity-${task.id}`}>{task.current_activity}</p>
          )}
          <p className="text-[11px] font-mono text-muted-foreground mt-1" data-testid={`text-task-id-${task.id}`}>ID: {task.id}</p>
        </div>
        <div className="flex items-center gap-1">
        {onViewLog && (
          <IconButton onClick={() => onViewLog(task.id, target, task)} label={t("a11y.view_task_log", { target })}
            className="shrink-0 border border-border hover:bg-muted"
            data-testid={`button-active-task-log-${task.id}`}><Zap className="w-4 h-4" /></IconButton>
        )}
        {onStop && (
          <IconButton onClick={() => onStop(task.id, target)} label={t("a11y.stop_task", { target })}
            className="shrink-0 bg-red-500/10 text-red-600 hover:bg-red-500/20"
            data-testid={`button-stop-task-${task.id}`}><Square className="w-4 h-4" /></IconButton>
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
      <div className="mt-2"><TaskMetrics task={task} t={t} /></div>
      <p className="text-[11px] text-muted-foreground mt-2">{t("tasks.started")}: <FormattedDateTime value={task.started_at} lang={lang} fallback="-" /></p>
    </motion.div>
  );
}

export { statusBadge };
