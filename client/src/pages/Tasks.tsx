import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play, Square, Clock, CheckCircle2, XCircle, Loader2, RefreshCw,
  Globe, Search, BookOpen, FileText, Layers, Link2, X, ArrowLeft,
  AlertCircle, Compass, ExternalLink, ChevronDown, ChevronUp, Plus,
  Pencil, Trash2, ToggleLeft, ToggleRight, Timer, Zap, Save, Download,
  FolderOpen, FileUp, History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { apiGet, apiPost } from "@/lib/api";
import { SiteConfigForm } from "./tasks/SiteConfigForm";
import { ScheduledTasksSection } from "./tasks/ScheduledTasksSection";
import { WebCrawlForm } from "./tasks/WebCrawlForm";
import { AdhocUrlForm } from "./tasks/AdhocUrlForm";
import { FileImportForm } from "./tasks/FileImportForm";
import { FolderBrowser } from "./tasks/FolderBrowser";
import { WebSearchForm } from "./tasks/WebSearchForm";
import { CatalogForm } from "./tasks/CatalogForm";
import { MarkdownForm } from "./tasks/MarkdownForm";
import { ChunkForm } from "./tasks/ChunkForm";
import { FilterBar } from "./tasks/FilterBar";
import { TaskCard, statusBadge, formatDate } from "./tasks/TaskCard";
import { TaskTable } from "./tasks/TaskTable";
import { Pagination } from "./tasks/Pagination";
import type { Task, SiteConfig, HistoryTask, LogModal } from "./tasks/Tasks.types";

// Task type definitions
const taskTypes = [
  { type: "site_config", apiType: "scheduled", icon: Globe, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  { type: "web_crawl", apiType: "quick_check", icon: Compass, color: "bg-orange-500/10 text-orange-600 dark:text-orange-400" },
  { type: "adhoc_url", apiType: "url", icon: Link2, color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400" },
  { type: "file_import", apiType: "file", icon: FileUp, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  { type: "web_search", apiType: "search", icon: Search, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { type: "catalog", apiType: "catalog", icon: BookOpen, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  { type: "markdown", apiType: "markdown_conversion", icon: FileText, color: "bg-pink-500/10 text-pink-600 dark:text-pink-400" },
  { type: "chunk", apiType: "chunk_generation", icon: Layers, color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
];

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.4, ease: "easeOut" as const },
  }),
};

export default function Tasks() {
  const { t } = useTranslation();
  const { user, isLoggedIn } = useAuth();
  const isGuest = !isLoggedIn || user?.role === "guest";
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [sites, setSites] = useState<SiteConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeForm, setActiveForm] = useState<string | null>(null);
  const [taskView, setTaskView] = useState<"run" | "scheduled">("run");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(true);
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [logModal, setLogModal] = useState<LogModal | null>(null);
  const [logModalLoading, setLogModalLoading] = useState(false);
  const logContentRef = useRef<HTMLPreElement | null>(null);

  // Filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await apiGet<{ tasks?: HistoryTask[]; history?: HistoryTask[] }>("/api/tasks/history?limit=20");
      setHistoryTasks(res.tasks || res.history || []);
    } catch { setHistoryTasks([]); }
    finally { setHistoryLoading(false); }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const activeRes = await apiGet<{ tasks: Task[] }>("/api/tasks/active");
      setActiveTasks(activeRes.tasks || []);
    } catch (e) { console.error("Failed to fetch tasks:", e); }
  }, []);

  const fetchSites = useCallback(async () => {
    try {
      const res = await apiGet<{ sites: SiteConfig[] }>("/api/config/sites");
      setSites(res.sites || []);
    } catch { setSites([]); }
  }, []);

  useEffect(() => {
    Promise.all([fetchTasks(), fetchSites()]).finally(() => setLoading(false));
    intervalRef.current = setInterval(fetchTasks, 5000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchTasks, fetchSites]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  useEffect(() => {
    if (!logModalLoading && logModal && logContentRef.current) {
      logContentRef.current.scrollTop = logContentRef.current.scrollHeight;
    }
  }, [logModalLoading, logModal]);

  const viewTaskLog = async (taskId: string | undefined, taskName: string | undefined, task?: HistoryTask) => {
    if (!taskId) return;
    if (isGuest) {
      setLogModal({ taskId, taskName: taskName || taskId, log: t("tasks.guest_detail_disabled"), task });
      return;
    }
    setLogModalLoading(true);
    setLogModal({ taskId, taskName: taskName || taskId, log: "", task });
    try {
      const res = await apiGet<{ log?: string }>(`/api/tasks/log/${encodeURIComponent(taskId)}?tail=500`);
      setLogModal({ taskId, taskName: taskName || taskId, log: res.log || "(no log available)", task });
    } catch {
      setLogModal({ taskId, taskName: taskName || taskId, log: "(failed to load log)", task });
    } finally {
      setLogModalLoading(false);
    }
  };

  const stopTask = async (taskId: string) => {
    try { await apiPost(`/api/tasks/stop/${taskId}`); await fetchTasks(); }
    catch (e) { console.error("Failed to stop task:", e); }
  };

  const handleSubmitTask = async (data: Record<string, unknown>) => {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      const res = await apiPost<{ success?: boolean; job_id?: string; error?: string }>("/api/collections/run", data);
      if (res.error) { setSubmitError(res.error); return; }
      setSubmitSuccess(res.job_id ? `${t("tasks.form.started")} (${res.job_id})` : t("tasks.form.started"));
      await fetchTasks();
      setTimeout(() => { setActiveForm(null); setSubmitSuccess(null); }, 2000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t("tasks.form.start_error");
      setSubmitError(msg);
    } finally { setSubmitting(false); }
  };

  // Filter history tasks
  const filteredHistoryTasks = historyTasks.filter((task) => {
    if (searchQuery && !(task.name || "").toLowerCase().includes(searchQuery.toLowerCase())) return false;
    if (statusFilter && task.status !== statusFilter) return false;
    if (typeFilter && task.type !== typeFilter) return false;
    return true;
  });

  const totalPages = Math.ceil(filteredHistoryTasks.length / pageSize);
  const paginatedHistoryTasks = filteredHistoryTasks.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  // Clamp currentPage when totalPages changes to prevent empty table
  useEffect(() => {
    setCurrentPage((prev) => {
      if (totalPages === 0) return 1;
      if (prev > totalPages) return totalPages;
      return prev;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalPages]);

  function renderForm() {
    switch (activeForm) {
      case "site_config": return <SiteConfigForm sites={sites} onSubmit={handleSubmitTask} submitting={submitting} onSitesChanged={fetchSites} />;
      case "web_crawl": return <WebCrawlForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "adhoc_url": return <AdhocUrlForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "file_import": return <FileImportForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "web_search": return <WebSearchForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "catalog": return <CatalogForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "markdown": return <MarkdownForm onSubmit={handleSubmitTask} submitting={submitting} />;
      case "chunk": return <ChunkForm onSubmit={handleSubmitTask} submitting={submitting} />;
      default: return null;
    }
  }

  const activeTaskType = taskTypes.find((tt) => tt.type === activeForm);

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">{t("tasks.title")}</h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">{t("tasks.subtitle")}</p>
      </motion.div>

      <div className="inline-flex rounded-lg border border-border bg-muted/40 p-1" data-testid="tasks-view-tabs">
        <button
          type="button"
          onClick={() => setTaskView("run")}
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            taskView === "run" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
          )}
          data-testid="tab-run-tasks"
        >
          <Play className="w-4 h-4" />
          {t("tasks.view.run_tasks")}
        </button>
        <button
          type="button"
          onClick={() => setTaskView("scheduled")}
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            taskView === "scheduled" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
          )}
          data-testid="tab-scheduled-tasks"
        >
          <Clock className="w-4 h-4" />
          {t("tasks.view.scheduled_tasks")}
        </button>
      </div>

      {taskView === "scheduled" ? (
        <ScheduledTasksSection />
      ) : (
        <>
      {/* 1. All Tasks (task type selection grid) */}
      <div>
        <h2 className="text-lg font-semibold mb-3">{t("tasks.new_task")}</h2>
        <AnimatePresence mode="wait">
          {activeForm ? (
            <motion.div key="form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }} className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
                <button onClick={() => { setActiveForm(null); setSubmitError(null); setSubmitSuccess(null); }}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors" data-testid="button-back-tasks">
                  <ArrowLeft className="w-4 h-4" /></button>
                {activeTaskType && (
                  <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", activeTaskType.color)}>
                    <activeTaskType.icon className="w-5 h-5" strokeWidth={1.8} /></div>
                )}
                <h3 className="font-semibold text-sm">{t(`tasks.type.${activeForm}`)}</h3>
              </div>
              <div className="p-5 space-y-0">
                {submitError && (
                  <div className="mb-4 px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs flex items-center gap-2" data-testid="text-submit-error">
                    <AlertCircle className="w-4 h-4 shrink-0" /><span className="flex-1">{submitError}</span>
                    <button onClick={() => setSubmitError(null)} className="shrink-0"><X className="w-3.5 h-3.5" /></button>
                  </div>
                )}
                {submitSuccess && (
                  <div className="mb-4 px-3 py-2 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2" data-testid="text-submit-success">
                    <CheckCircle2 className="w-4 h-4 shrink-0" /><span>{submitSuccess}</span></div>
                )}
                {renderForm()}
              </div>
            </motion.div>
          ) : (
            <motion.div key="grid" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="grid grid-cols-3 sm:grid-cols-5 gap-3">
              {taskTypes.map(({ type, icon: Icon, color }, i) => (
                <motion.button key={type} custom={i} variants={fadeUp} initial="hidden" animate="visible"
                  onClick={() => { setActiveForm(type); setSubmitError(null); setSubmitSuccess(null); }}
                  className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border bg-card hover:border-primary/30 hover:shadow-md transition-all duration-300"
                  data-testid={`button-start-${type}`}>
                  <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", color)}>
                    <Icon className="w-5 h-5" strokeWidth={1.8} /></div>
                  <span className="text-xs font-medium text-center">{t(`tasks.type.${type}`)}</span>
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* 2. Active Tasks */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">{t("tasks.active")}</h2>
          <button onClick={fetchTasks} className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            data-testid="button-refresh-tasks" title={t("tasks.refresh")}><RefreshCw className="w-4 h-4" /></button>
        </div>
        {loading ? (
          <div className="space-y-3">{[...Array(2)].map((_, i) => <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />)}</div>
        ) : activeTasks.length === 0 ? (
          <p className="text-xs text-muted-foreground py-1" data-testid="text-no-active-tasks">{t("tasks.no_active")}</p>
        ) : (
          <div className="space-y-3">
            {activeTasks.map((task, i) => (
              <TaskCard key={task.id} task={task} index={i} onStop={stopTask} />
            ))}
          </div>
        )}
      </div>

      {/* 3. Task History */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <button onClick={() => { if (!historyExpanded) fetchHistory(); setHistoryExpanded(!historyExpanded); }}
            className="flex items-center gap-2 text-left"
            data-testid="button-toggle-history">
            <History className="w-5 h-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold">{t("tasks.history")}</h2>
            {historyExpanded ? <ChevronUp className="w-5 h-5 text-muted-foreground" /> : <ChevronDown className="w-5 h-5 text-muted-foreground" />}
          </button>
          {historyExpanded && (
            <button onClick={fetchHistory} className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              data-testid="button-refresh-history" title={t("tasks.refresh")}><RefreshCw className="w-4 h-4" /></button>
          )}
        </div>
        {historyExpanded && (
          <div>
            <FilterBar
              searchQuery={searchQuery}
              onSearchChange={(q) => { setSearchQuery(q); setCurrentPage(1); }}
              statusFilter={statusFilter}
              onStatusChange={(s) => { setStatusFilter(s); setCurrentPage(1); }}
              typeFilter={typeFilter}
              onTypeChange={(t) => { setTypeFilter(t); setCurrentPage(1); }}
            />
            <div className="mt-3">
              {historyLoading ? (
                <div className="flex items-center justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
              ) : (
                <>
                  <TaskTable historyTasks={paginatedHistoryTasks} onViewLog={viewTaskLog} />
                  <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
                </>
              )}
            </div>
          </div>
        )}
      </div>

        </>
      )}

      {/* Log Modal */}
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
              className="bg-card rounded-xl border border-border shadow-xl w-full max-w-3xl max-h-[80vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
              data-testid="modal-task-log"
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <div className="flex items-center gap-2 min-w-0">
                  <History className="w-4 h-4 text-muted-foreground shrink-0" />
                  <h3 className="font-semibold text-sm truncate">{t("tasks.log_title")} — {logModal.taskName}</h3>
                </div>
                <button onClick={() => setLogModal(null)}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground"
                  data-testid="button-close-log-modal">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Box 1: Summary stats */}
                {logModal.task && (
                  <div className="rounded-lg border border-border bg-muted/30 p-3">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">{t("tasks.log_summary") || "Summary"}</h4>
                    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs">
                      <div className="flex gap-1">
                        <dt className="text-muted-foreground">{t("tasks.log_status") || "Status"}:</dt>
                        <dd>{logModal.task.status ? statusBadge(logModal.task.status) : "-"}</dd>
                      </div>
                      <div className="flex gap-1">
                        <dt className="text-muted-foreground">{t("tasks.log_started") || "Started"}:</dt>
                        <dd>{logModal.task.started_at ? formatDate(logModal.task.started_at) : "-"}</dd>
                      </div>
                      <div className="flex gap-1">
                        <dt className="text-muted-foreground">{t("tasks.log_completed") || "Completed"}:</dt>
                        <dd>{logModal.task.completed_at ? formatDate(logModal.task.completed_at) : "-"}</dd>
                      </div>
                      {logModal.task.type === "catalog" ? (
                        <>
                          {logModal.task.catalog_scanned != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.scanned") || "Scanned"}:</dt><dd>{logModal.task.catalog_scanned}</dd></div>
                          )}
                          {logModal.task.catalog_ok != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.ok") || "OK"}:</dt><dd className="text-emerald-600 dark:text-emerald-400">{logModal.task.catalog_ok}</dd></div>
                          )}
                          {logModal.task.catalog_skipped != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.skipped") || "Skipped"}:</dt><dd>{logModal.task.catalog_skipped}</dd></div>
                          )}
                          {logModal.task.catalog_errors != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.errors") || "Errors"}:</dt><dd className={logModal.task.catalog_errors > 0 ? "text-red-500" : ""}>{logModal.task.catalog_errors}</dd></div>
                          )}
                        </>
                      ) : (
                        <>
                          {logModal.task.items_processed != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.log_items_processed") || "Processed"}:</dt><dd>{logModal.task.items_processed}</dd></div>
                          )}
                          {logModal.task.items_downloaded != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.downloaded") || "New/Updated"}:</dt><dd>{logModal.task.items_downloaded}</dd></div>
                          )}
                          {logModal.task.items_skipped != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.skipped") || "Skipped"}:</dt><dd>{logModal.task.items_skipped}</dd></div>
                          )}
                          {logModal.task.errors != null && (
                            <div className="flex gap-1"><dt className="text-muted-foreground">{t("tasks.stats.errors") || "Errors"}:</dt><dd className={logModal.task.errors.length > 0 ? "text-red-500" : ""}>{logModal.task.errors.length}</dd></div>
                          )}
                        </>
                      )}
                    </dl>
                  </div>
                )}

                {/* Box 2: Error details */}
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">{t("tasks.log_error_details") || "Error Details"}</h4>
                  {logModal.task?.errors && logModal.task.errors.length > 0 ? (
                    <ul className="text-xs space-y-1">
                      {logModal.task.errors.map((e, i) => (
                        <li key={i} className="text-red-500 break-all">• {e}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">{t("tasks.log_no_errors") || "No errors"}</p>
                  )}
                </div>

                {/* Box 3: Application log */}
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("tasks.log_app_log") || "Application Log"}</h4>
                    <button
                      onClick={() => viewTaskLog(logModal.taskId, logModal.taskName, logModal.task)}
                      className="text-[10px] px-2 py-0.5 rounded border border-border hover:bg-muted transition-colors text-muted-foreground"
                    >
                      {t("common.refresh") || "Refresh"}
                    </button>
                  </div>
                  {logModalLoading ? (
                    <div className="flex items-center justify-center py-6">
                      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : (
                    <pre ref={logContentRef} className="text-xs font-mono whitespace-pre-wrap break-all text-foreground/80 leading-relaxed max-h-64 overflow-y-auto focus:outline-none focus:ring-1 focus:ring-primary/40 rounded" tabIndex={0} role="region" aria-label="application log">
                      {logModal.log}
                    </pre>
                  )}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
