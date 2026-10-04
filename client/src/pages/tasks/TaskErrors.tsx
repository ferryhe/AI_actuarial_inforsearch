import type { HistoryTask } from "./Tasks.types";
import { EnumDiagnostic, EnumDisplay } from "@/lib/enum-display";

const NATIVE_TASK_ID = /^task_[0-9]+_[0-9a-f]{16}$/;

export function trustedTaskIdFromSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  const taskId = params.get("task_id") || "";
  return params.size === 1 && NATIVE_TASK_ID.test(taskId) ? taskId : null;
}

function trustedContextUrl(value: string | undefined): string | null {
  if (!value?.startsWith("/tasks?")) return null;
  const taskId = trustedTaskIdFromSearch(value.slice(value.indexOf("?")));
  return taskId && value === `/tasks?task_id=${taskId}` ? value : null;
}

interface TaskErrorDetailsProps {
  task: HistoryTask;
  t: (key: string) => string;
  canInspectRaw?: boolean;
}

export function TaskErrorDetails({ task, t, canInspectRaw = false }: TaskErrorDetailsProps) {
  const errors = task.item_errors || [];
  const failedItems = task.failed_items ?? 0;
  if (failedItems === 0 && errors.length === 0) return null;

  return (
    <div className="space-y-2" data-testid="task-item-errors">
      <div className="text-xs font-medium">
        {t("tasks.log_failed_items")}: {failedItems}
      </div>
      <ul className="space-y-2">
        {errors.map((error) => {
          const contextUrl = trustedContextUrl(error.context_url);
          return (
            <li key={error.object_id} className="rounded border border-border p-2 text-xs">
              <div className="font-medium break-all">
                {contextUrl ? <a href={contextUrl} className="underline">{error.display_name}</a> : error.display_name}
              </div>
              <div className="text-muted-foreground">
                <EnumDisplay category="error_stage" value={error.stage} t={t} /> · <EnumDisplay category="error_code" value={error.code} t={t} />
                <EnumDiagnostic category="error_stage" value={error.stage} t={t} canInspectRaw={canInspectRaw} />
                <EnumDiagnostic category="error_code" value={error.code} t={t} canInspectRaw={canInspectRaw} />
              </div>
              <div>{error.summary}</div>
            </li>
          );
        })}
      </ul>
      {task.item_errors_truncated && (
        <p className="text-xs text-muted-foreground" data-testid="task-item-errors-truncated">
          {t("tasks.log_item_errors_truncated").replace("{count}", String(errors.length))}
        </p>
      )}
    </div>
  );
}
