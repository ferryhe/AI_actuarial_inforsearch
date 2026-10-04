import { Zap, History } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { TaskTableProps } from "./Tasks.types";
import { statusBadge } from "./TaskCard";
import { TaskMetrics as TaskResultSummary, getTaskItemCount } from "./TaskMetrics";
import { EnumDiagnostic, EnumDisplay, canInspectEnumRaw } from "@/lib/enum-display";
import { FormattedDateTime } from "@/components/FormattedDateTime";

export function TaskTable({ historyTasks, onViewLog }: TaskTableProps) {
  const { t, lang } = useTranslation();
  const { user } = useAuth();

  if (historyTasks.length === 0) {
    return (
      <div className="text-center py-8 rounded-xl border border-dashed border-border bg-card" data-testid="text-no-history">
        <History className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
        <p className="text-sm font-medium text-muted-foreground">{t("tasks.no_history")}</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="hidden md:grid grid-cols-[1fr_90px_110px_120px_120px_80px] gap-3 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
        <span>{t("tasks.col.name")}</span>
        <span>{t("tasks.col.type")}</span>
        <span>{t("tasks.col.status")}</span>
        <span>{t("tasks.col.started")}</span>
        <span>{t("tasks.col.completed")}</span>
        <span>{t("tasks.col.items")}</span>
      </div>
      {historyTasks.map((task, i) => {
        const itemCount = getTaskItemCount(task);
        const hasErrors = task.errors && task.errors.length > 0;
        return (
          <div key={i} className="border-t border-border hover:bg-muted/20 transition-colors"
            data-testid={`row-history-task-${i}`}>
            <div className="grid md:grid-cols-[1fr_90px_110px_120px_120px_80px] gap-1 md:gap-3 px-4 py-3 items-center">
              <div className="min-w-0">
                <div className="font-medium text-sm truncate max-w-full">{task.name || "-"}</div>
                <div className="text-[10px] font-mono text-muted-foreground truncate" data-testid={`text-history-task-id-${i}`}>ID: {task.id || "-"}</div>
              </div>
              <div className="text-xs text-muted-foreground hidden md:block"><EnumDisplay category="task_type" value={task.type} t={t} /><EnumDiagnostic category="task_type" value={task.type} t={t} canInspectRaw={canInspectEnumRaw(user?.role)} /></div>
              <div className="hidden md:block">{task.status ? statusBadge(task.status, t, canInspectEnumRaw(user?.role)) : "-"}</div>
              <div className="text-xs text-muted-foreground hidden md:block"><FormattedDateTime value={task.started_at} lang={lang} fallback="-" /></div>
              <div className="text-xs text-muted-foreground hidden md:block"><FormattedDateTime value={task.completed_at} lang={lang} fallback="-" /></div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground hidden md:block">{itemCount}</span>
                {task.id && (
                  <button onClick={() => onViewLog(task.id, task.name, task)} aria-label={t("a11y.view_task_log", { target: task.name || task.id })}
                    className="min-h-[48px] text-[10px] px-2 py-1 rounded border border-border hover:bg-muted transition-colors flex items-center gap-1 shrink-0"
                    data-testid={`button-view-log-${i}`}>
                    <Zap className="w-3 h-3" />{t("tasks.log")}
                  </button>
                )}
              </div>
            </div>
            <TaskResultSummary task={{ ...task, result: task.result }} t={t} className="px-4 pb-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground" />
            {/* Error summary */}
            {hasErrors && (
              <div className="px-4 pb-2 text-[11px] text-red-500 truncate">
                {task.errors![0]}{task.errors!.length > 1 ? ` (+${task.errors!.length - 1} ${t("tasks.errors.more")})` : ""}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
