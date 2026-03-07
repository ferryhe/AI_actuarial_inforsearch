import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Square,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  Globe,
  FileUp,
  Search,
  BookOpen,
  FileText,
  Layers,
  Database,
  Link2,
  X,
  ScrollText,
  Inbox,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";

interface Task {
  id: string;
  name: string;
  type: string;
  status: string;
  progress: number;
  started_at: string;
  current_activity: string;
  items_processed: number;
  items_total: number;
}

interface SiteConfig {
  name: string;
  url?: string;
  type?: string;
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.4, ease: "easeOut" as const },
  }),
};

function statusIcon(status: string) {
  switch (status) {
    case "running":
      return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
    case "success":
    case "completed":
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
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

const taskTypes = [
  { type: "scheduled", icon: Globe, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  { type: "adhoc_url", icon: Link2, color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400" },
  { type: "file_import", icon: FileUp, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  { type: "web_search", icon: Search, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { type: "catalog", icon: BookOpen, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  { type: "markdown", icon: FileText, color: "bg-pink-500/10 text-pink-600 dark:text-pink-400" },
  { type: "chunk", icon: Layers, color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  { type: "rag_index", icon: Database, color: "bg-teal-500/10 text-teal-600 dark:text-teal-400" },
];

export default function Tasks() {
  const { t } = useTranslation();
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [historyTasks, setHistoryTasks] = useState<Task[]>([]);
  const [sites, setSites] = useState<SiteConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [logModal, setLogModal] = useState<{ taskId: string; log: string } | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [startingTask, setStartingTask] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const [activeRes, historyRes] = await Promise.all([
        apiGet<{ tasks: Task[] }>("/api/tasks/active"),
        apiGet<{ tasks: Task[] }>("/api/tasks/history?limit=20"),
      ]);
      setActiveTasks(activeRes.tasks || []);
      setHistoryTasks(historyRes.tasks || []);
    } catch (e) {
      console.error("Failed to fetch tasks:", e);
    }
  }, []);

  const fetchSites = useCallback(async () => {
    try {
      const res = await apiGet<{ sites: SiteConfig[] }>("/api/config/sites");
      setSites(res.sites || []);
    } catch {
      setSites([]);
    }
  }, []);

  useEffect(() => {
    Promise.all([fetchTasks(), fetchSites()]).finally(() => setLoading(false));
    intervalRef.current = setInterval(fetchTasks, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchTasks, fetchSites]);

  const stopTask = async (taskId: string) => {
    try {
      await apiPost(`/api/tasks/stop/${taskId}`);
      await fetchTasks();
    } catch (e) {
      console.error("Failed to stop task:", e);
    }
  };

  const viewLog = async (taskId: string) => {
    setLogLoading(true);
    setLogModal({ taskId, log: "" });
    try {
      const res = await apiGet<{ log: string }>(`/api/tasks/log/${taskId}`);
      setLogModal({ taskId, log: res.log || "No log available." });
    } catch {
      setLogModal({ taskId, log: "Failed to load log." });
    } finally {
      setLogLoading(false);
    }
  };

  const startTask = async (type: string) => {
    setStartingTask(type);
    try {
      await apiPost("/api/collections/run", { type, name: type });
      await fetchTasks();
    } catch (e) {
      console.error("Failed to start task:", e);
    } finally {
      setStartingTask(null);
    }
  };

  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">
          {t("tasks.title")}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
          {t("tasks.subtitle")}
        </p>
      </motion.div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">{t("tasks.active")}</h2>
          <button
            onClick={fetchTasks}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-refresh-tasks"
            title={t("tasks.refresh")}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[...Array(2)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
            ))}
          </div>
        ) : activeTasks.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-12 rounded-xl border border-dashed border-border bg-card"
            data-testid="text-no-active-tasks"
          >
            <CheckCircle2 className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("tasks.no_active")}</p>
          </motion.div>
        ) : (
          <div className="space-y-3">
            {activeTasks.map((task, i) => (
              <motion.div
                key={task.id}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
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
                      <p className="text-xs text-muted-foreground mt-1 truncate" data-testid={`text-activity-${task.id}`}>
                        {task.current_activity}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => stopTask(task.id)}
                    className="shrink-0 p-2 rounded-lg bg-red-500/10 text-red-600 hover:bg-red-500/20 transition-colors"
                    data-testid={`button-stop-task-${task.id}`}
                    title={t("tasks.stop")}
                  >
                    <Square className="w-4 h-4" />
                  </button>
                </div>

                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>
                      {task.items_processed}/{task.items_total || "?"}
                    </span>
                    <span>{Math.round(task.progress)}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                    <motion.div
                      className="h-full rounded-full bg-primary"
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(task.progress, 100)}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                </div>

                <p className="text-[11px] text-muted-foreground mt-2">
                  {t("tasks.started")}: {formatDate(task.started_at)}
                </p>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.new_task")}</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {taskTypes.map(({ type, icon: Icon, color }, i) => (
            <motion.button
              key={type}
              custom={i}
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              onClick={() => startTask(type)}
              disabled={startingTask === type}
              className={cn(
                "flex flex-col items-center gap-2 p-4 rounded-xl border border-border bg-card hover:border-primary/30 hover:shadow-md transition-all duration-300 disabled:opacity-50"
              )}
              data-testid={`button-start-${type}`}
            >
              <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", color)}>
                {startingTask === type ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Icon className="w-5 h-5" strokeWidth={1.8} />
                )}
              </div>
              <span className="text-xs font-medium text-center">{t(`tasks.type.${type}`)}</span>
            </motion.button>
          ))}
        </div>
        {sites.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="text-xs text-muted-foreground self-center">{t("tasks.configured_sites")}:</span>
            {sites.map((site) => (
              <span
                key={site.name}
                className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
                data-testid={`text-site-${site.name}`}
              >
                {site.name}
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.history")}</h2>
        {loading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : historyTasks.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-12 rounded-xl border border-dashed border-border bg-card"
            data-testid="text-no-history"
          >
            <Inbox className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("tasks.no_history")}</p>
          </motion.div>
        ) : (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="hidden sm:grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>{t("tasks.col.name")}</span>
              <span>{t("tasks.col.type")}</span>
              <span>{t("tasks.col.status")}</span>
              <span>{t("tasks.col.started")}</span>
              <span>{t("tasks.col.items")}</span>
            </div>
            {historyTasks.map((task, i) => (
              <motion.div
                key={task.id}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                className="grid sm:grid-cols-[1fr_100px_100px_120px_60px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
                onClick={() => viewLog(task.id)}
                data-testid={`row-history-task-${task.id}`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <ScrollText className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                  <span className="text-sm font-medium truncate">{task.name}</span>
                </div>
                <span className="text-xs text-muted-foreground hidden sm:flex items-center">
                  {task.type}
                </span>
                <span className="hidden sm:flex items-center">{statusBadge(task.status)}</span>
                <span className="text-xs text-muted-foreground hidden sm:flex items-center">
                  {formatDate(task.started_at)}
                </span>
                <span className="text-xs text-muted-foreground hidden sm:flex items-center">
                  {task.items_processed}
                </span>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {logModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
            onClick={() => setLogModal(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-card rounded-xl border border-border shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
              data-testid="modal-task-log"
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h3 className="font-semibold text-sm">
                  {t("tasks.log_title")} — {logModal.taskId}
                </h3>
                <button
                  onClick={() => setLogModal(null)}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                  data-testid="button-close-log"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">
                {logLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <pre
                    className="text-xs font-mono whitespace-pre-wrap text-muted-foreground leading-relaxed"
                    data-testid="text-task-log"
                  >
                    {logModal.log}
                  </pre>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
