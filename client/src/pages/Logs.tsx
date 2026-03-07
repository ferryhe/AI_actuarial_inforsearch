import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ScrollText,
  RefreshCw,
  Search,
  ArrowDown,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Clock,
  Square,
  X,
  Filter,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  source?: string;
}

interface HistoryTask {
  id: string;
  name: string;
  type: string;
  status: string;
  started_at: string;
  items_processed: number;
}

const LOG_LEVELS = ["ALL", "INFO", "WARNING", "ERROR", "DEBUG"] as const;

function parseLogs(raw: string): LogEntry[] {
  if (!raw) return [];
  const lines = raw.split("\n").filter((l) => l.trim());
  return lines.map((line) => {
    const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.,]?\d*)\s*/);
    const levelMatch = line.match(/\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b/i);
    return {
      timestamp: tsMatch ? tsMatch[1] : "",
      level: levelMatch ? levelMatch[1].toUpperCase() : "INFO",
      message: line,
    };
  });
}

function levelColor(level: string) {
  switch (level) {
    case "ERROR":
    case "CRITICAL":
      return "text-red-500 dark:text-red-400";
    case "WARNING":
      return "text-amber-500 dark:text-amber-400";
    case "DEBUG":
      return "text-muted-foreground";
    case "INFO":
    default:
      return "text-blue-500 dark:text-blue-400";
  }
}

function levelBg(level: string) {
  switch (level) {
    case "ERROR":
    case "CRITICAL":
      return "bg-red-500/10";
    case "WARNING":
      return "bg-amber-500/10";
    case "DEBUG":
      return "bg-muted/30";
    default:
      return "";
  }
}

function LevelIcon({ level }: { level: string }) {
  switch (level) {
    case "ERROR":
    case "CRITICAL":
      return <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />;
    case "WARNING":
      return <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
    case "DEBUG":
      return <Info className="w-3.5 h-3.5 text-muted-foreground shrink-0" />;
    default:
      return <Info className="w-3.5 h-3.5 text-blue-500 shrink-0" />;
  }
}

function historyStatusIcon(status: string) {
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

function historyStatusBadge(status: string) {
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
      data-testid={`status-badge-log-${status}`}
    >
      {historyStatusIcon(status)}
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

export default function LogsPage() {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [levelFilter, setLevelFilter] = useState<string>("ALL");
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyFetched, setHistoryFetched] = useState(false);
  const [logModal, setLogModal] = useState<{ taskId: string; log: string } | null>(null);
  const [logModalLoading, setLogModalLoading] = useState(false);
  const [logsApiDisabled, setLogsApiDisabled] = useState(false);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await apiGet<{ log?: string; logs?: string }>("/api/logs/global");
      const raw = res.log || res.logs || "";
      setLogs(parseLogs(typeof raw === "string" ? raw : JSON.stringify(raw)));
      setLogsApiDisabled(false);
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      const msg = String((err as { message?: string })?.message || "");
      if (status === 401 || status === 403 || msg.includes("403") || msg.includes("401") || msg.toLowerCase().includes("forbidden") || msg.toLowerCase().includes("not enabled") || msg.toLowerCase().includes("unauthorized")) {
        setLogsApiDisabled(true);
      }
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleRefresh = () => {
    setLoading(true);
    fetchLogs();
  };

  const scrollToBottom = () => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  };

  const filteredLogs = logs.filter((entry) => {
    if (levelFilter !== "ALL" && entry.level !== levelFilter) return false;
    if (searchQuery && !entry.message.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await apiGet<{ tasks: HistoryTask[] }>("/api/tasks/history?limit=50");
      setHistoryTasks(res.tasks || []);
    } catch {
      setHistoryTasks([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const handleHistoryToggle = () => {
    const next = !historyExpanded;
    setHistoryExpanded(next);
    if (next && !historyFetched) {
      setHistoryFetched(true);
      fetchHistory();
    }
  };

  const viewTaskLog = async (taskId: string) => {
    setLogModalLoading(true);
    setLogModal({ taskId, log: "" });
    try {
      const res = await apiGet<{ log: string }>(`/api/tasks/log/${taskId}`);
      setLogModal({ taskId, log: res.log || t("tasks.form.no_log") });
    } catch {
      setLogModal({ taskId, log: t("tasks.form.log_error") });
    } finally {
      setLogModalLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight" data-testid="text-logs-title">
            {t("logs.title")}
          </h1>
          <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">
            {t("logs.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={scrollToBottom}
            className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-scroll-bottom"
            title={t("logs.scroll_bottom")}
          >
            <ArrowDown className="w-4 h-4" />
          </button>
          <button
            onClick={handleRefresh}
            className={cn(
              "p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
              loading && "animate-spin"
            )}
            data-testid="button-refresh-logs"
            title={t("logs.refresh")}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="flex flex-col sm:flex-row gap-3"
      >
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("logs.search_placeholder")}
            className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-2 focus:ring-primary/30"
            data-testid="input-log-search"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground shrink-0" />
          {LOG_LEVELS.map((level) => (
            <button
              key={level}
              onClick={() => setLevelFilter(level)}
              className={cn(
                "px-3 py-1.5 text-xs font-semibold rounded-full transition-colors",
                levelFilter === level
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground"
              )}
              data-testid={`button-filter-${level.toLowerCase()}`}
            >
              {level}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer shrink-0">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="rounded"
            data-testid="checkbox-auto-scroll"
          />
          {t("logs.auto_scroll")}
        </label>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.2 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
        data-testid="section-system-logs"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2">
            <ScrollText className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm font-semibold">{t("logs.system_logs")}</span>
          </div>
          <span className="text-xs text-muted-foreground" data-testid="text-log-count">
            {filteredLogs.length} {t("logs.entries")}
          </span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : logsApiDisabled ? (
          <div className="text-center py-16" data-testid="text-logs-disabled">
            <AlertTriangle className="w-10 h-10 mx-auto text-amber-500/60 mb-3" />
            <p className="font-medium text-foreground mb-1">{t("logs.api_disabled_title")}</p>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">{t("logs.api_disabled_desc")}</p>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="text-center py-16" data-testid="text-no-logs">
            <ScrollText className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
            <p className="font-medium text-muted-foreground">{t("logs.no_logs")}</p>
          </div>
        ) : (
          <div
            ref={logContainerRef}
            className="max-h-[60vh] overflow-y-auto font-mono text-xs leading-relaxed"
            data-testid="container-log-entries"
          >
            {filteredLogs.map((entry, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-start gap-2 px-4 py-1.5 border-b border-border/50 hover:bg-muted/20 transition-colors",
                  levelBg(entry.level)
                )}
                data-testid={`log-entry-${i}`}
              >
                <LevelIcon level={entry.level} />
                <span className={cn("shrink-0 font-semibold w-16 text-[10px] uppercase", levelColor(entry.level))}>
                  {entry.level}
                </span>
                <span className="flex-1 whitespace-pre-wrap break-all text-foreground/90">
                  {entry.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.3 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
        data-testid="section-task-history"
      >
        <button
          onClick={handleHistoryToggle}
          className="w-full flex items-center justify-between px-5 py-4 hover:bg-muted/30 transition-colors"
          data-testid="button-toggle-task-history"
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <Clock className="w-4.5 h-4.5" strokeWidth={1.8} />
            </div>
            <div className="text-left">
              <h2 className="text-lg font-semibold font-serif">{t("logs.task_history")}</h2>
              <p className="text-xs text-muted-foreground">{t("logs.task_history_desc")}</p>
            </div>
          </div>
          {historyExpanded ? <ChevronUp className="w-5 h-5 text-muted-foreground" /> : <ChevronDown className="w-5 h-5 text-muted-foreground" />}
        </button>

        {historyExpanded && (
          <div className="border-t border-border">
            {historyLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : historyTasks.length === 0 ? (
              <div className="text-center py-10" data-testid="text-no-history">
                <Clock className="w-10 h-10 mx-auto text-muted-foreground/40 mb-2" />
                <p className="font-medium text-muted-foreground">{t("tasks.no_history")}</p>
              </div>
            ) : (
              <div>
                <div className="hidden sm:grid grid-cols-[1fr_100px_100px_120px_60px] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  <span>{t("tasks.col.name")}</span>
                  <span>{t("tasks.col.type")}</span>
                  <span>{t("tasks.col.status")}</span>
                  <span>{t("tasks.col.started")}</span>
                  <span>{t("tasks.col.items")}</span>
                </div>
                {historyTasks.map((task) => (
                  <div
                    key={task.id}
                    className="grid sm:grid-cols-[1fr_100px_100px_120px_60px] gap-1 sm:gap-4 px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
                    onClick={() => viewTaskLog(task.id)}
                    data-testid={`row-history-task-${task.id}`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <ScrollText className="w-4 h-4 text-muted-foreground shrink-0" strokeWidth={1.5} />
                      <span className="text-sm font-medium truncate">{task.name}</span>
                    </div>
                    <span className="text-xs text-muted-foreground hidden sm:flex items-center">{task.type}</span>
                    <span className="hidden sm:flex items-center">{historyStatusBadge(task.status)}</span>
                    <span className="text-xs text-muted-foreground hidden sm:flex items-center">{formatDate(task.started_at)}</span>
                    <span className="text-xs text-muted-foreground hidden sm:flex items-center">{task.items_processed}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </motion.div>

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
                <h3 className="font-semibold text-sm">{t("tasks.log_title")} — {logModal.taskId}</h3>
                <button
                  onClick={() => setLogModal(null)}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                  data-testid="button-close-log"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">
                {logModalLoading ? (
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
