import { useEffect, useState, useCallback } from "react";
import { Clock, Loader2, Plus, Pencil, Trash2, Save, Timer, RefreshCw, ToggleLeft, ToggleRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import { FormField, InputField, SelectField } from "@/components/FormFields";

interface ScheduledTask {
  name: string;
  type: string;
  interval: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

interface ScheduleJob {
  label?: string;
  tag?: string;
  interval?: string;
  next_run?: string;
  last_run?: string;
}

interface ScheduleStatus {
  jobs: ScheduleJob[];
  global_schedule?: string;
  job_count?: number;
  count?: number;
}

export function ScheduledTasksSection() {
  const { t } = useTranslation();
  const { permissions } = useAuth();
  const canManageSchedule = permissions.includes("schedule.write");
  const [scheduleStatus, setScheduleStatus] = useState<ScheduleStatus | null>(null);
  const [scheduledTasks, setScheduledTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [deletingTask, setDeletingTask] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reinitMsg, setReinitMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [formName, setFormName] = useState("");
  const [formType, setFormType] = useState("catalog");
  const [formInterval, setFormInterval] = useState("daily");
  const [formEnabled, setFormEnabled] = useState(true);
  const [formParams, setFormParams] = useState("{}");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, tasksRes] = await Promise.all([
        apiGet<ScheduleStatus>("/api/schedule/status").catch(() => null),
        apiGet<{ tasks: ScheduledTask[] }>("/api/scheduled-tasks").catch(() => ({ tasks: [] })),
      ]);
      if (statusRes) setScheduleStatus(statusRes);
      setScheduledTasks(tasksRes.tasks || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const resetForm = () => {
    setFormName("");
    setFormType("catalog");
    setFormInterval("daily");
    setFormEnabled(true);
    setFormParams("{}");
    setShowAddForm(false);
    setEditingTask(null);
  };

  const formatError = (error: unknown, fallbackKey: string) => {
    if (error instanceof ApiError) {
      return error.detail || error.message;
    }
    if (error instanceof Error) {
      return error.message;
    }
    return t(fallbackKey);
  };

  const openEditForm = (task: ScheduledTask) => {
    if (!canManageSchedule) {
      setErrorMsg(t("tasks.sched.write_access_required"));
      return;
    }
    setErrorMsg(null);
    setEditingTask(task);
    setFormName(task.name);
    setFormType(task.type);
    setFormInterval(task.interval);
    setFormEnabled(task.enabled);
    setFormParams(JSON.stringify(task.params || {}, null, 2));
    setShowAddForm(true);
  };

  const handleSave = async () => {
    if (!formName.trim() || !formType || !formInterval.trim()) return;
    if (!canManageSchedule) {
      setErrorMsg(t("tasks.sched.write_access_required"));
      return;
    }
    setSaving(true);
    setErrorMsg(null);
    try {
      let params = {};
      try { params = JSON.parse(formParams); } catch { throw new Error(t("tasks.sched.invalid_params")); }

      if (editingTask) {
        await apiPost("/api/scheduled-tasks/update", {
          original_name: editingTask.name, name: formName.trim(), type: formType,
          interval: formInterval.trim(), enabled: formEnabled, params,
        });
      } else {
        await apiPost("/api/scheduled-tasks/add", {
          name: formName.trim(), type: formType, interval: formInterval.trim(),
          enabled: formEnabled, params,
        });
      }
      resetForm();
      await fetchData();
    } catch (error) { setErrorMsg(formatError(error, "tasks.sched.save_fail")); }
    finally { setSaving(false); }
  };

  const handleDelete = async (name: string) => {
    if (!canManageSchedule) {
      setErrorMsg(t("tasks.sched.write_access_required"));
      return;
    }
    setSaving(true);
    setErrorMsg(null);
    try {
      await apiPost("/api/scheduled-tasks/delete", { name });
      setDeletingTask(null);
      await fetchData();
    } catch (error) { setErrorMsg(formatError(error, "tasks.sched.delete_fail")); }
    finally { setSaving(false); }
  };

  const handleReinit = async () => {
    if (!canManageSchedule) {
      setErrorMsg(t("tasks.sched.write_access_required"));
      return;
    }
    setErrorMsg(null);
    try {
      const res = await apiPost<{ success?: boolean; job_count?: number }>("/api/schedule/reinit");
      if (res.success) {
        setReinitMsg(`${t("tasks.sched.reinit_success")} (${res.job_count || 0} jobs)`);
      } else {
        setReinitMsg(null);
        setErrorMsg(t("tasks.sched.reinit_fail"));
      }
      await fetchData();
    } catch (error) {
      const message = formatError(error, "tasks.sched.reinit_fail");
      setReinitMsg(null);
      setErrorMsg(message);
    }
    setTimeout(() => setReinitMsg(null), 3000);
  };

  const taskTypeOptions = [
    { value: "scheduled", label: t("tasks.type.scheduled") },
    { value: "quick_check", label: t("tasks.type.web_crawl") },
    { value: "catalog", label: t("tasks.type.catalog") },
    { value: "markdown_conversion", label: t("tasks.type.markdown") },
    { value: "chunk_generation", label: t("tasks.type.chunk") },
    { value: "rag_indexing", label: t("tasks.type.rag_index") },
    { value: "search", label: t("tasks.type.web_search") },
    { value: "url", label: t("tasks.type.adhoc_url") },
  ];
  const jobCount = scheduleStatus ? (scheduleStatus.job_count ?? scheduleStatus.count ?? scheduleStatus.jobs?.length ?? 0) : 0;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">{t("tasks.scheduled.title")}</h2>
        <p className="text-sm text-muted-foreground mt-0.5">{t("tasks.scheduled.desc")}</p>
      </div>

      {loading ? (
        <div className="space-y-3">{[...Array(3)].map((_, i) => <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />)}</div>
      ) : (
        <>
          {errorMsg && (
            <div className="px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs flex items-center justify-between gap-2" data-testid="text-scheduled-error">
              <span>{errorMsg}</span>
              <button onClick={() => setErrorMsg(null)} className="shrink-0 text-destructive/80 hover:text-destructive">
                x
              </button>
            </div>
          )}

          {!canManageSchedule && (
            <div className="px-3 py-2 rounded-lg border border-border bg-muted/40 text-xs text-muted-foreground">
              {t("tasks.sched.write_access_required")}
            </div>
          )}

          {scheduleStatus && (
            <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Timer className="w-4 h-4 text-primary" />
                  <span className="text-sm font-medium">{t("tasks.sched.scheduler_jobs")}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                    {jobCount} {t("tasks.sched.job_count").toLowerCase()}
                  </span>
                </div>
                <button onClick={handleReinit}
                  disabled={!canManageSchedule}
                  className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                  data-testid="button-reinit-scheduler">
                  <RefreshCw className="w-3 h-3" />{t("tasks.sched.reinit")}
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground">{t("tasks.sched.scheduler_jobs_desc")}</p>
              {reinitMsg && (
                <div className="text-xs px-2.5 py-1.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">{reinitMsg}</div>
              )}
              {scheduleStatus.global_schedule && (
                <div>
                  <div className="text-xs text-muted-foreground">
                    {t("tasks.sched.global_interval")}: <span className="font-medium text-foreground">{scheduleStatus.global_schedule}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground/70 mt-0.5">{t("tasks.sched.global_hint")}</p>
                </div>
              )}
              {scheduleStatus.jobs && scheduleStatus.jobs.length > 0 && (
                <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                  {scheduleStatus.jobs.map((job, i) => (
                    <div key={i} className="flex items-center justify-between text-xs px-2.5 py-2 rounded bg-background border border-border">
                      <span className="font-medium truncate flex-1">{job.label || job.tag || `Job ${i + 1}`}</span>
                      <div className="flex items-center gap-3 shrink-0 text-muted-foreground">
                        {job.interval && <span>{job.interval}</span>}
                        {job.last_run && <span>{t("tasks.sched.last_run")}: {job.last_run}</span>}
                        {job.next_run && <span>{t("tasks.sched.next_run")}: {job.next_run}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium">{t("tasks.sched.configured_tasks")}</h4>
                <p className="text-[11px] text-muted-foreground">{t("tasks.sched.configured_tasks_desc")}</p>
              </div>
              <button onClick={() => { resetForm(); setErrorMsg(null); setShowAddForm(true); }}
                disabled={!canManageSchedule}
                className="text-xs px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="button-add-scheduled-task">
                <Plus className="w-3 h-3" />{t("tasks.sched.add_task")}
              </button>
            </div>

            {showAddForm && (
              <div className="rounded-lg border border-primary/30 bg-card p-4 space-y-3" data-testid="form-scheduled-task">
                <h4 className="text-sm font-medium">{editingTask ? t("tasks.sched.edit_task") : t("tasks.sched.add_task")}</h4>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label={t("tasks.sched.task_name")}>
                    <InputField value={formName} onChange={setFormName} placeholder="Daily Catalog" testId="input-sched-name" />
                  </FormField>
                  <FormField label={t("tasks.sched.task_type")}>
                    <SelectField value={formType} onChange={setFormType} options={taskTypeOptions} testId="select-sched-type" />
                  </FormField>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label={t("tasks.sched.schedule_interval")} hint={t("tasks.sched.interval_hint")}>
                    <InputField value={formInterval} onChange={setFormInterval} placeholder="daily at 02:00" testId="input-sched-interval" />
                  </FormField>
                  <FormField label={t("tasks.sched.enabled")}>
                    <button type="button" onClick={() => setFormEnabled(!formEnabled)}
                      className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-border bg-background w-full"
                      data-testid="toggle-sched-enabled">
                      {formEnabled ? <ToggleRight className="w-5 h-5 text-primary" /> : <ToggleLeft className="w-5 h-5 text-muted-foreground" />}
                      {formEnabled ? t("tasks.sched.enabled") : t("tasks.sched.disabled")}
                    </button>
                  </FormField>
                </div>
                <FormField label={t("tasks.sched.parameters")} hint="JSON">
                  <textarea value={formParams} onChange={(e) => setFormParams(e.target.value)} rows={3}
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                    data-testid="input-sched-params" />
                </FormField>
                <div className="flex items-center gap-2 justify-end">
                  <button onClick={resetForm}
                    className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
                    data-testid="button-cancel-sched">{t("tasks.sched.cancel")}</button>
                  <button onClick={handleSave} disabled={saving || !formName.trim()}
                    className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                    data-testid="button-save-sched">
                    {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    {saving ? t("tasks.sched.saving") : t("tasks.sched.save")}
                  </button>
                </div>
              </div>
            )}

            {scheduledTasks.length === 0 && !showAddForm ? (
              <div className="text-center py-8 rounded-lg border border-dashed border-border bg-card" data-testid="text-no-scheduled-tasks">
                <Clock className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
                <p className="text-sm font-medium text-muted-foreground">{t("tasks.sched.no_jobs")}</p>
                <p className="text-xs text-muted-foreground/70 mt-1">{t("tasks.sched.no_jobs_desc")}</p>
              </div>
            ) : (
              <div className="space-y-2">
                {scheduledTasks.map((task) => (
                  <div key={task.name} className="flex items-center gap-3 px-3.5 py-3 rounded-lg border border-border bg-card hover:bg-muted/30 transition-colors"
                    data-testid={`row-sched-task-${task.name}`}>
                    <div className={cn("w-2 h-2 rounded-full shrink-0", task.enabled ? "bg-emerald-500" : "bg-muted-foreground/40")} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate">{task.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{task.type}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5 text-[11px] text-muted-foreground">
                        <span>{t("tasks.sched.interval")}: {task.interval}</span>
                        <span>{task.enabled ? t("tasks.sched.enabled") : t("tasks.sched.disabled")}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button onClick={() => openEditForm(task)}
                        disabled={!canManageSchedule}
                        className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                        data-testid={`button-edit-sched-${task.name}`}><Pencil className="w-3.5 h-3.5" /></button>
                      {deletingTask === task.name ? (
                        <div className="flex flex-col items-end gap-1">
                          <span className="text-[10px] text-muted-foreground">{t("tasks.sched.confirm_delete_msg")}</span>
                          <div className="flex items-center gap-1">
                            <button onClick={() => handleDelete(task.name)}
                              className="text-[10px] px-2 py-1 rounded bg-destructive text-destructive-foreground"
                              data-testid={`button-confirm-delete-sched-${task.name}`}>{t("tasks.sched.delete_task")}</button>
                            <button onClick={() => setDeletingTask(null)}
                              className="text-[10px] px-2 py-1 rounded border border-border">{t("tasks.sched.cancel")}</button>
                          </div>
                        </div>
                      ) : (
                        <button onClick={() => setDeletingTask(task.name)}
                          disabled={!canManageSchedule}
                          className="p-1.5 rounded hover:bg-red-500/10 transition-colors text-muted-foreground hover:text-red-600 disabled:opacity-50 disabled:cursor-not-allowed"
                          data-testid={`button-delete-sched-${task.name}`}><Trash2 className="w-3.5 h-3.5" /></button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
