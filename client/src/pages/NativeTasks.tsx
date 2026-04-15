import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Clock3, History, ListTodo, Globe, Loader2, AlertCircle } from "lucide-react";
import { apiGet } from "@/lib/api";

interface TaskItem {
  id: string;
  name: string;
  type: string;
  status: string;
  progress?: number;
  started_at?: string;
  completed_at?: string;
  current_activity?: string;
  items_processed?: number;
  items_total?: number;
  items_downloaded?: number;
}

interface SiteConfig {
  name: string;
  url?: string;
  max_pages?: number;
  max_depth?: number;
  keywords?: string[];
  schedule_interval?: string;
}

interface ScheduledTask {
  name: string;
  type: string;
  interval: string;
  enabled: boolean;
  params?: Record<string, unknown>;
}

interface ScheduleStatus {
  jobs: Array<{ label: string; next_run?: string; last_run?: string }>;
  count?: number;
}

function fmtDate(value?: string) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
      : status === "failed" || status === "error"
        ? "bg-red-500/10 text-red-600 dark:text-red-400"
        : status === "running"
          ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
          : "bg-muted text-muted-foreground";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}>{status}</span>;
}

export default function NativeTasks() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sites, setSites] = useState<SiteConfig[]>([]);
  const [scheduleStatus, setScheduleStatus] = useState<ScheduleStatus>({ jobs: [] });
  const [scheduledTasks, setScheduledTasks] = useState<ScheduledTask[]>([]);
  const [activeTasks, setActiveTasks] = useState<TaskItem[]>([]);
  const [historyTasks, setHistoryTasks] = useState<TaskItem[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sitesRes, scheduleRes, scheduledRes, activeRes, historyRes] = await Promise.all([
        apiGet<{ sites: SiteConfig[] }>("/api/config/sites"),
        apiGet<ScheduleStatus>("/api/schedule/status"),
        apiGet<{ tasks: ScheduledTask[] }>("/api/scheduled-tasks"),
        apiGet<{ tasks: TaskItem[] }>("/api/tasks/active"),
        apiGet<{ tasks: TaskItem[] }>("/api/tasks/history?limit=20"),
      ]);
      setSites(sitesRes.sites || []);
      setScheduleStatus(scheduleRes || { jobs: [] });
      setScheduledTasks(scheduledRes.tasks || []);
      setActiveTasks(activeRes.tasks || []);
      setHistoryTasks(historyRes.tasks || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-serif font-bold tracking-tight">任务中心</h1>
          <p className="mt-1 text-sm text-muted-foreground">FastAPI-native 只读视图，覆盖 PR1 的任务与配置读取接口。</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">PR1 read-only</span>
          <button
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> 刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> 正在加载任务与配置…
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center gap-2">
                <Clock3 className="h-4 w-4 text-primary" />
                <h2 className="font-semibold">调度状态</h2>
              </div>
              {scheduleStatus.jobs.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无调度任务。</p>
              ) : (
                <div className="space-y-3">
                  {scheduleStatus.jobs.map((job, idx) => (
                    <div key={`${job.label}-${idx}`} className="rounded-lg border border-border p-3 text-sm">
                      <div className="font-medium">{job.label}</div>
                      <div className="mt-1 text-xs text-muted-foreground">下次运行：{fmtDate(job.next_run)} · 上次运行：{fmtDate(job.last_run)}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center gap-2">
                <ListTodo className="h-4 w-4 text-primary" />
                <h2 className="font-semibold">已配置的计划任务</h2>
              </div>
              {scheduledTasks.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无已配置计划任务。</p>
              ) : (
                <div className="space-y-3">
                  {scheduledTasks.map((task) => (
                    <div key={task.name} className="rounded-lg border border-border p-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium">{task.name}</div>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${task.enabled ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground"}`}>
                          {task.enabled ? "enabled" : "disabled"}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">{task.type} · {task.interval}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-primary" />
              <h2 className="font-semibold">运行中的任务</h2>
            </div>
            {activeTasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">当前没有运行中的任务。</p>
            ) : (
              <div className="space-y-3">
                {activeTasks.map((task) => (
                  <div key={task.id} className="rounded-lg border border-border p-4 text-sm">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="font-medium">{task.name}</div>
                        <div className="mt-1 text-xs text-muted-foreground">{task.type} · 开始于 {fmtDate(task.started_at)}</div>
                      </div>
                      <StatusPill status={task.status} />
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground">{task.current_activity || "-"}</div>
                    <div className="mt-2 h-2 rounded-full bg-muted">
                      <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.min(task.progress || 0, 100)}%` }} />
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">{task.items_processed || 0}/{task.items_total || "?"} · {Math.round(task.progress || 0)}%</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2">
              <History className="h-4 w-4 text-primary" />
              <h2 className="font-semibold">最近任务历史</h2>
            </div>
            {historyTasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无任务历史。</p>
            ) : (
              <div className="space-y-3">
                {historyTasks.map((task) => (
                  <div key={task.id} className="rounded-lg border border-border p-4 text-sm">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="font-medium">{task.name}</div>
                        <div className="mt-1 text-xs text-muted-foreground">{task.type} · 开始于 {fmtDate(task.started_at)} · 结束于 {fmtDate(task.completed_at)}</div>
                      </div>
                      <StatusPill status={task.status} />
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">处理 {task.items_processed || 0} 项 · 下载 {task.items_downloaded || 0} 项</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2">
              <Globe className="h-4 w-4 text-primary" />
              <h2 className="font-semibold">站点配置</h2>
            </div>
            {sites.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无站点配置。</p>
            ) : (
              <div className="space-y-3">
                {sites.map((site) => (
                  <div key={site.name} className="rounded-lg border border-border p-4 text-sm">
                    <div className="font-medium">{site.name}</div>
                    <div className="mt-1 break-all text-xs text-muted-foreground">{site.url || "-"}</div>
                    <div className="mt-2 text-xs text-muted-foreground">max_pages={site.max_pages ?? "-"} · max_depth={site.max_depth ?? "-"} · schedule={site.schedule_interval || "-"}</div>
                    {site.keywords && site.keywords.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {site.keywords.map((keyword) => (
                          <span key={keyword} className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">{keyword}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
