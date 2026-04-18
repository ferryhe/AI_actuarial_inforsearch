import { Zap, History } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { TaskTableProps } from "./Tasks.types";
import { statusBadge, formatDate } from "./TaskCard";

export function TaskTable({ historyTasks, onViewLog }: TaskTableProps) {
  const { t } = useTranslation();

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
        const itemCount = task.type === "catalog"
          ? (task.catalog_ok ?? task.items_processed ?? 0)
          : (task.items_downloaded ?? task.items_processed ?? 0);
        const hasErrors = task.errors && task.errors.length > 0;
        return (
          <div key={i} className="border-t border-border hover:bg-muted/20 transition-colors"
            data-testid={`row-history-task-${i}`}>
            <div className="grid md:grid-cols-[1fr_90px_110px_120px_120px_80px] gap-1 md:gap-3 px-4 py-3 items-center">
              <div className="font-medium text-sm truncate max-w-full">{task.name || "-"}</div>
              <div className="text-xs text-muted-foreground hidden md:block">{task.type || "-"}</div>
              <div className="hidden md:block">{task.status ? statusBadge(task.status) : "-"}</div>
              <div className="text-xs text-muted-foreground hidden md:block">{task.started_at ? formatDate(task.started_at) : "-"}</div>
              <div className="text-xs text-muted-foreground hidden md:block">{task.completed_at ? formatDate(task.completed_at) : "-"}</div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground hidden md:block">{itemCount}</span>
                {task.id && (
                  <button onClick={() => onViewLog(task.id, task.name, task)}
                    className="text-[10px] px-2 py-1 rounded border border-border hover:bg-muted transition-colors flex items-center gap-1 shrink-0"
                    data-testid={`button-view-log-${i}`}>
                    <Zap className="w-3 h-3" />{t("tasks.log")}
                  </button>
                )}
              </div>
            </div>
            {/* Extra stats row for catalog tasks */}
            {task.type === "catalog" && (task.catalog_scanned != null || task.catalog_ok != null) && (
              <div className="px-4 pb-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                {task.catalog_scanned != null && <span>{t("tasks.stats.scanned")}: {task.catalog_scanned}</span>}
                {task.catalog_ok != null && <span className="text-emerald-600 dark:text-emerald-400">{t("tasks.stats.ok")}: {task.catalog_ok}</span>}
                {task.catalog_skipped != null && <span>{t("tasks.stats.skipped")}: {task.catalog_skipped}</span>}
                {task.catalog_errors != null && task.catalog_errors > 0 && <span className="text-red-500">{t("tasks.stats.errors")}: {task.catalog_errors}</span>}
              </div>
            )}
            {/* Items stats for non-catalog tasks */}
            {task.type !== "catalog" && ((task.items_downloaded ?? 0) > 0 || (task.items_skipped ?? 0) > 0) && (
              <div className="px-4 pb-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                {(task.items_downloaded ?? 0) > 0 && <span>{t("tasks.stats.downloaded")}: {task.items_downloaded}</span>}
                {(task.items_skipped ?? 0) > 0 && <span>{t("tasks.stats.skipped")}: {task.items_skipped}</span>}
              </div>
            )}
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
