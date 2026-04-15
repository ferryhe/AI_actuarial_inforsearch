import { useCallback, useEffect, useState } from "react";
import { FileText, Loader2, RefreshCw, AlertCircle } from "lucide-react";
import { apiGet } from "@/lib/api";

interface HistoryTask {
  id: string;
  name: string;
  type: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  items_processed?: number;
}

function fmtDate(value?: string) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function NativeLogs() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<HistoryTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [selectedLog, setSelectedLog] = useState<string>("");
  const [logLoading, setLogLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<{ tasks: HistoryTask[] }>("/api/tasks/history?limit=50");
      setTasks(res.tasks || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const openLog = useCallback(async (taskId: string) => {
    setSelectedTask(taskId);
    setLogLoading(true);
    try {
      const res = await apiGet<{ log?: string }>(`/api/tasks/log/${taskId}?tail=500`);
      setSelectedLog(res.log || "");
    } catch (err) {
      setSelectedLog(err instanceof Error ? err.message : "日志加载失败");
    } finally {
      setLogLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-serif font-bold tracking-tight">任务日志</h1>
          <p className="mt-1 text-sm text-muted-foreground">FastAPI-native 只读日志页，读取任务历史与单任务日志。</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">PR1 read-only</span>
          <button onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted">
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

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 font-semibold">最近任务</h2>
          {loading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载中…</div>
          ) : tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无任务历史。</p>
          ) : (
            <div className="space-y-3">
              {tasks.map((task) => (
                <button
                  key={task.id}
                  onClick={() => void openLog(task.id)}
                  className={`w-full rounded-lg border p-4 text-left text-sm transition-colors ${selectedTask === task.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"}`}
                >
                  <div className="font-medium">{task.name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{task.type} · {task.status}</div>
                  <div className="mt-2 text-xs text-muted-foreground">开始：{fmtDate(task.started_at)}</div>
                  <div className="text-xs text-muted-foreground">结束：{fmtDate(task.completed_at)}</div>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <div className="mb-4 flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <h2 className="font-semibold">任务日志内容</h2>
          </div>
          {!selectedTask ? (
            <p className="text-sm text-muted-foreground">从左侧选择一个任务查看日志。</p>
          ) : logLoading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在加载日志…</div>
          ) : (
            <pre className="max-h-[720px] overflow-auto whitespace-pre-wrap rounded-lg bg-muted/40 p-4 text-sm leading-6">{selectedLog || "暂无日志。"}</pre>
          )}
        </section>
      </div>
    </div>
  );
}
