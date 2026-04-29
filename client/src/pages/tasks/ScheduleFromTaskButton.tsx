import { useState } from "react";
import { AlertCircle, CalendarPlus, CheckCircle2, Loader2, X } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { ApiError, apiPost } from "@/lib/api";
import { FormField, InputField } from "@/components/FormFields";

interface ScheduleFromTaskButtonProps {
  buildTask: () => Record<string, unknown> | null;
  disabled?: boolean;
}

function taskParamsFromPayload(task: Record<string, unknown>): Record<string, unknown> {
  const params = { ...task };
  delete params.type;
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== undefined));
}

export function ScheduleFromTaskButton({ buildTask, disabled = false }: ScheduleFromTaskButtonProps) {
  const { t } = useTranslation();
  const { permissions } = useAuth();
  const canManageSchedule = permissions.includes("schedule.write");
  const [expanded, setExpanded] = useState(false);
  const [taskName, setTaskName] = useState("");
  const [interval, setInterval] = useState("daily");
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const formatError = (error: unknown) => {
    if (error instanceof ApiError) return error.detail || error.message;
    if (error instanceof Error) return error.message;
    return t("tasks.sched.save_fail");
  };

  const openForm = () => {
    if (!canManageSchedule) {
      setErrorMsg(t("tasks.sched.write_access_required"));
      return;
    }
    const task = buildTask();
    if (!task) {
      setErrorMsg(t("tasks.schedule.invalid_config"));
      return;
    }
    setTaskName(String(task.name || ""));
    setInterval("daily");
    setErrorMsg(null);
    setSuccessMsg(null);
    setExpanded(true);
  };

  const saveSchedule = async () => {
    if (!taskName.trim() || !interval.trim()) return;
    if (!canManageSchedule) {
      setErrorMsg(t("tasks.sched.write_access_required"));
      return;
    }
    const task = buildTask();
    if (!task) {
      setErrorMsg(t("tasks.schedule.invalid_config"));
      return;
    }
    const type = String(task.type || "");
    if (!type) {
      setErrorMsg(t("tasks.schedule.invalid_config"));
      return;
    }
    setSaving(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      await apiPost("/api/scheduled-tasks/add", {
        name: taskName.trim(),
        type,
        interval: interval.trim(),
        enabled: true,
        params: taskParamsFromPayload(task),
      });
      await apiPost("/api/schedule/reinit").catch(() => null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("scheduled-tasks:changed"));
      }
      setExpanded(false);
      setSuccessMsg(t("tasks.schedule.added"));
    } catch (error) {
      setErrorMsg(formatError(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={openForm}
        disabled={disabled || !canManageSchedule}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-border bg-background text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        data-testid="button-add-to-schedule"
      >
        <CalendarPlus className="w-4 h-4" />
        {t("tasks.schedule.add_from_task")}
      </button>

      {successMsg && (
        <div className="px-3 py-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2" data-testid="text-add-schedule-success">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs flex items-center gap-2" data-testid="text-add-schedule-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{errorMsg}</span>
          <button type="button" onClick={() => setErrorMsg(null)} className="shrink-0">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {expanded && (
        <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-3" data-testid="form-add-to-schedule">
          <FormField label={t("tasks.sched.task_name")}>
            <InputField value={taskName} onChange={setTaskName} placeholder="Daily Catalog" testId="input-schedule-task-name" />
          </FormField>
          <FormField label={t("tasks.sched.schedule_interval")} hint={t("tasks.sched.interval_hint")}>
            <InputField value={interval} onChange={setInterval} placeholder="daily at 02:00" testId="input-schedule-interval" />
          </FormField>
          <div className="flex items-center gap-2 justify-end">
            <button
              type="button"
              onClick={() => {
                setExpanded(false);
                setErrorMsg(null);
              }}
              className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
              data-testid="button-cancel-add-schedule"
            >
              {t("tasks.sched.cancel")}
            </button>
            <button
              type="button"
              onClick={saveSchedule}
              disabled={saving || !taskName.trim() || !interval.trim()}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid="button-confirm-add-schedule"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CalendarPlus className="w-3 h-3" />}
              {saving ? t("tasks.sched.saving") : t("tasks.schedule.confirm")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
