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
  ArrowLeft,
  AlertCircle,
  Compass,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Plus,
  Pencil,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Timer,
  Zap,
  Save,
  Download,
  FolderOpen,
  Folder,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";
import TagSelect, { PRESET_FILE_EXTENSIONS, PRESET_LANGUAGES, PRESET_COUNTRIES } from "@/components/TagSelect";
import { useTaskOptions } from "@/hooks/use-task-options";

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
  max_pages?: number;
  max_depth?: number;
  keywords?: string[];
  exclude_keywords?: string[];
  exclude_prefixes?: string[];
  schedule_interval?: string;
  content_selector?: string;
}

interface KBItem {
  kb_id: string;
  name: string;
}

interface ScheduledTask {
  name: string;
  type: string;
  interval: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

interface ScheduleJob {
  tag: string;
  interval: string;
  next_run?: string;
  last_run?: string;
}

interface ScheduleStatus {
  jobs: ScheduleJob[];
  global_schedule?: string;
  job_count?: number;
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
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

const taskTypes = [
  { type: "site_config", apiType: "scheduled", icon: Globe, color: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  { type: "web_crawl", apiType: "quick_check", icon: Compass, color: "bg-orange-500/10 text-orange-600 dark:text-orange-400" },
  { type: "adhoc_url", apiType: "url", icon: Link2, color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400" },
  { type: "file_import", apiType: "file", icon: FileUp, color: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
  { type: "web_search", apiType: "search", icon: Search, color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { type: "catalog", apiType: "catalog", icon: BookOpen, color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  { type: "markdown", apiType: "markdown_conversion", icon: FileText, color: "bg-pink-500/10 text-pink-600 dark:text-pink-400" },
  { type: "chunk", apiType: "chunk_generation", icon: Layers, color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  { type: "rag_index", apiType: "rag_indexing", icon: Database, color: "bg-teal-500/10 text-teal-600 dark:text-teal-400" },
];

function FormField({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground/70">{hint}</p>}
    </div>
  );
}

function InputField({ value, onChange, placeholder, type = "text", testId }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; testId?: string;
}) {
  return (
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId} />
  );
}

function SelectField({ value, onChange, options, testId }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; testId?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      data-testid={testId}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function CheckboxField({ checked, onChange, label, testId }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; testId?: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded" data-testid={testId} />
      {label}
    </label>
  );
}

function RunButton({ onClick, disabled, submitting, label }: {
  onClick: () => void; disabled: boolean; submitting: boolean; label: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
      data-testid="button-run-task">
      {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
      {label}
    </button>
  );
}

function StatsBanner({ items }: { items: { label: string; value: string | number | null | undefined }[] }) {
  const valid = items.filter((i) => i.value != null);
  if (valid.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="stats-banner">
      {valid.map((item) => (
        <div key={item.label}>
          <p className="text-[11px] text-muted-foreground">{item.label}</p>
          <p className="text-sm font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function SiteConfigForm({ sites, onSubmit, submitting, onSitesChanged }: { sites: SiteConfig[]; onSubmit: (d: Record<string, unknown>) => void; submitting: boolean; onSitesChanged: () => void }) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<"merge" | "overwrite">("merge");
  const [importPreview, setImportPreview] = useState<{ count: number; names: string[] } | null>(null);
  const [importing, setImporting] = useState(false);
  const [importYamlText, setImportYamlText] = useState("");
  const [importResult, setImportResult] = useState<string | null>(null);

  const [showAddSite, setShowAddSite] = useState(false);
  const [editingSite, setEditingSite] = useState<SiteConfig | null>(null);
  const [deletingSite, setDeletingSite] = useState<string | null>(null);
  const [expandedSite, setExpandedSite] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [site, setSite] = useState("");
  const [maxPages, setMaxPages] = useState("");
  const [maxDepth, setMaxDepth] = useState("");

  const [formName, setFormName] = useState("");
  const [formUrl, setFormUrl] = useState("");
  const [formMaxPages, setFormMaxPages] = useState("");
  const [formMaxDepth, setFormMaxDepth] = useState("");
  const [formKeywords, setFormKeywords] = useState("");
  const [formExcludeKw, setFormExcludeKw] = useState("");
  const [formExcludePfx, setFormExcludePfx] = useState("");
  const [formSelector, setFormSelector] = useState("");
  const [formInterval, setFormInterval] = useState("");

  const [backups, setBackups] = useState<Array<{ filename: string; timestamp?: string; size?: number }>>([]);
  const [showBackups, setShowBackups] = useState(false);
  const [loadingBackups, setLoadingBackups] = useState(false);

  const resetSiteForm = () => {
    setFormName(""); setFormUrl(""); setFormMaxPages(""); setFormMaxDepth("");
    setFormKeywords(""); setFormExcludeKw(""); setFormExcludePfx("");
    setFormSelector(""); setFormInterval("");
    setShowAddSite(false); setEditingSite(null);
  };

  const openEditForm = (s: SiteConfig) => {
    setEditingSite(s);
    setFormName(s.name);
    setFormUrl(s.url || "");
    setFormMaxPages(s.max_pages?.toString() || "");
    setFormMaxDepth(s.max_depth?.toString() || "");
    setFormKeywords(s.keywords?.join(", ") || "");
    setFormExcludeKw(s.exclude_keywords?.join(", ") || "");
    setFormExcludePfx(s.exclude_prefixes?.join(", ") || "");
    setFormSelector(s.content_selector || "");
    setFormInterval(s.schedule_interval || "");
    setShowAddSite(true);
  };

  const handleSaveSite = async () => {
    if (!formName.trim() || !formUrl.trim()) return;
    setSaving(true);
    try {
      const data: Record<string, unknown> = {
        name: formName.trim(), url: formUrl.trim(),
        max_pages: formMaxPages || undefined, max_depth: formMaxDepth || undefined,
        keywords: formKeywords || undefined, exclude_keywords: formExcludeKw || undefined,
        exclude_prefixes: formExcludePfx || undefined,
        content_selector: formSelector || undefined, schedule_interval: formInterval || undefined,
      };
      if (editingSite) {
        data.original_name = editingSite.name;
        await apiPost("/api/config/sites/update", data);
      } else {
        await apiPost("/api/config/sites/add", data);
      }
      resetSiteForm();
      onSitesChanged();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const handleDeleteSite = async (name: string) => {
    setSaving(true);
    try {
      await apiPost("/api/config/sites/delete", { name });
      setDeletingSite(null);
      onSitesChanged();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportFile(file);
    const reader = new FileReader();
    reader.onload = async (ev) => {
      const yamlText = ev.target?.result as string;
      setImportYamlText(yamlText);
      try {
        const res = await apiPost<{ count?: number; names?: string[] }>("/api/config/sites/import", { yaml_text: yamlText, preview: true });
        setImportPreview({ count: res.count || 0, names: res.names || [] });
      } catch { setImportPreview(null); }
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleConfirmImport = async () => {
    setImporting(true);
    try {
      const res = await apiPost<{ imported?: number; skipped?: number }>("/api/config/sites/import", { yaml_text: importYamlText, mode: importMode });
      setImportResult(t("tasks.sites.import_result").replace("{imported}", String(res.imported || 0)).replace("{skipped}", String(res.skipped || 0)));
      onSitesChanged();
      setImportPreview(null);
      setImportFile(null);
      setImportYamlText("");
      setTimeout(() => setImportResult(null), 4000);
    } catch { /* ignore */ }
    finally { setImporting(false); }
  };

  const fetchBackups = async () => {
    setLoadingBackups(true);
    try {
      const res = await apiGet<{ backups?: Array<{ filename: string; timestamp?: string; size?: number }> }>("/api/config/backups");
      setBackups(res.backups || []);
    } catch { setBackups([]); }
    finally { setLoadingBackups(false); }
  };

  const handleRestoreBackup = async (filename: string) => {
    if (!confirm(t("tasks.sites.restore_confirm"))) return;
    try {
      await apiPost("/api/config/backups/restore", { filename });
      onSitesChanged();
    } catch { /* ignore */ }
  };

  const handleDeleteBackup = async (filename: string) => {
    try {
      await apiPost("/api/config/backups/delete", { filename });
      await fetchBackups();
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-5">
      <input ref={fileInputRef} type="file" accept=".yaml,.yml" className="hidden" onChange={handleFileSelect} data-testid="input-import-file" />
      <div className="flex flex-wrap gap-2">
        <button onClick={() => fileInputRef.current?.click()}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5"
          data-testid="button-import-yaml">
          <FileUp className="w-3 h-3" />{t("tasks.sites.import_yaml")}
        </button>
        <button onClick={async () => {
            try {
              const res = await fetch("/api/config/sites/export");
              if (!res.ok) return;
              const blob = await res.blob();
              const cd = res.headers.get("content-disposition") || "";
              const match = cd.match(/filename=([^;]+)/);
              const fname = match ? match[1] : "sites_export.yaml";
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = fname;
              a.click();
              URL.revokeObjectURL(a.href);
            } catch { /* ignore */ }
          }}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5"
          data-testid="button-export-current">
          <Download className="w-3 h-3" />{t("tasks.sites.export_current")}
        </button>
        <button onClick={async () => {
            try {
              const res = await fetch("/api/config/sites/sample");
              if (!res.ok) return;
              const blob = await res.blob();
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "sites_sample.yaml";
              a.click();
              URL.revokeObjectURL(a.href);
            } catch { /* ignore */ }
          }}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5"
          data-testid="button-download-sample">
          <Download className="w-3 h-3" />{t("tasks.sites.download_sample")}
        </button>
      </div>

      {importResult && (
        <div className="text-xs px-2.5 py-1.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" data-testid="text-import-result">{importResult}</div>
      )}

      {importPreview && (
        <div className="rounded-lg border border-primary/30 bg-card p-4 space-y-3" data-testid="panel-import-preview">
          <p className="text-sm font-medium">{t("tasks.sites.import_preview").replace("{n}", String(importPreview.count))}</p>
          <div className="flex flex-wrap gap-1">
            {importPreview.names.map((name) => (
              <span key={name} className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{name}</span>
            ))}
          </div>
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">{t("tasks.sites.import_mode")}</p>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="radio" name="importMode" checked={importMode === "merge"} onChange={() => setImportMode("merge")} data-testid="radio-mode-merge" />
              {t("tasks.sites.mode_merge")}
            </label>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="radio" name="importMode" checked={importMode === "overwrite"} onChange={() => setImportMode("overwrite")} data-testid="radio-mode-overwrite" />
              {t("tasks.sites.mode_overwrite")}
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleConfirmImport} disabled={importing}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              data-testid="button-confirm-import">
              {importing && <Loader2 className="w-3 h-3 animate-spin" />}
              {t("tasks.sites.import_confirm")}
            </button>
            <button onClick={() => { setImportPreview(null); setImportFile(null); setImportYamlText(""); }}
              className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
              data-testid="button-cancel-import">{t("tasks.sched.cancel")}</button>
          </div>
        </div>
      )}

      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("tasks.form.scheduled_desc")}</p>
        <FormField label={t("tasks.form.target_site")}>
          <SelectField value={site} onChange={setSite} testId="select-site"
            options={[{ value: "", label: t("tasks.form.all_sites") + ` (${sites.length})` }, ...sites.map((s) => ({ value: s.name, label: s.name }))]} />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label={t("tasks.form.max_pages")} hint={t("tasks.form.default_hint") + " 200"}>
            <InputField value={maxPages} onChange={setMaxPages} placeholder="200" type="number" testId="input-max-pages" />
          </FormField>
          <FormField label={t("tasks.form.max_depth")} hint={t("tasks.form.default_hint") + " 2"}>
            <InputField value={maxDepth} onChange={setMaxDepth} placeholder="2" type="number" testId="input-max-depth" />
          </FormField>
        </div>
        <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting}
          onClick={() => onSubmit({ type: "scheduled", name: site ? `Scheduled: ${site}` : "Scheduled Collection",
            site: site || undefined, max_pages: maxPages ? parseInt(maxPages) : undefined, max_depth: maxDepth ? parseInt(maxDepth) : undefined })} />
      </div>

      <div className="border-t border-border pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{sites.length} {t("tasks.configured_sites").toLowerCase()}</p>
          <button onClick={() => { resetSiteForm(); setShowAddSite(true); }}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5"
            data-testid="button-add-site">
            <Plus className="w-3 h-3" />{t("tasks.sched.add_site")}
          </button>
        </div>

        {showAddSite && (
          <div className="rounded-lg border border-primary/30 bg-card p-4 space-y-3" data-testid="form-site">
            <h4 className="text-sm font-medium">{editingSite ? t("tasks.sched.edit_site") : t("tasks.sched.add_site")}</h4>
            <div className="grid grid-cols-2 gap-3">
              <FormField label={t("tasks.sched.site_name")}>
                <InputField value={formName} onChange={setFormName} placeholder="SOA" testId="input-site-name" />
              </FormField>
              <FormField label={t("tasks.sched.site_url")}>
                <InputField value={formUrl} onChange={setFormUrl} placeholder="https://www.soa.org" testId="input-site-url" />
              </FormField>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <FormField label={t("tasks.form.max_pages")}>
                <InputField value={formMaxPages} onChange={setFormMaxPages} placeholder="200" type="number" testId="input-site-max-pages" />
              </FormField>
              <FormField label={t("tasks.form.max_depth")}>
                <InputField value={formMaxDepth} onChange={setFormMaxDepth} placeholder="2" type="number" testId="input-site-max-depth" />
              </FormField>
              <FormField label={t("tasks.sched.schedule_interval_site")}>
                <InputField value={formInterval} onChange={setFormInterval} placeholder="weekly" testId="input-site-interval" />
              </FormField>
            </div>
            <FormField label={t("tasks.form.keywords")} hint={t("tasks.form.comma_separated")}>
              <InputField value={formKeywords} onChange={setFormKeywords} placeholder="artificial intelligence, actuarial" testId="input-site-keywords" />
            </FormField>
            <FormField label={t("tasks.form.exclude_keywords")} hint={t("tasks.form.comma_separated")}>
              <InputField value={formExcludeKw} onChange={setFormExcludeKw} placeholder="newsletter" testId="input-site-exclude-kw" />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label={t("tasks.sched.exclude_prefixes")} hint={t("tasks.form.comma_separated")}>
                <InputField value={formExcludePfx} onChange={setFormExcludePfx} placeholder="/archive, /old" testId="input-site-exclude-pfx" />
              </FormField>
              <FormField label={t("tasks.form.content_selector")}>
                <InputField value={formSelector} onChange={setFormSelector} placeholder="article.content" testId="input-site-selector" />
              </FormField>
            </div>
            <div className="flex items-center gap-2 justify-end">
              <button onClick={resetSiteForm}
                className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
                data-testid="button-cancel-site">{t("tasks.sched.cancel")}</button>
              <button onClick={handleSaveSite} disabled={saving || !formName.trim() || !formUrl.trim()}
                className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                data-testid="button-save-site">
                {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                {saving ? t("tasks.sched.saving") : t("tasks.sched.save")}
              </button>
            </div>
          </div>
        )}

        {sites.length === 0 && !showAddSite ? (
          <div className="text-center py-8 rounded-lg border border-dashed border-border bg-card" data-testid="text-no-sites">
            <Globe className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
            <p className="text-sm font-medium text-muted-foreground">{t("tasks.sched.no_sites")}</p>
            <p className="text-xs text-muted-foreground/70 mt-1">{t("tasks.sched.no_sites_desc")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {sites.map((s) => (
              <div key={s.name} className="rounded-lg border border-border bg-card overflow-hidden" data-testid={`card-site-${s.name}`}>
                <div className="flex items-center gap-3 px-3.5 py-2.5">
                  <button onClick={() => setExpandedSite(expandedSite === s.name ? null : s.name)}
                    className="flex items-center gap-3 flex-1 min-w-0 text-left hover:bg-muted/50 -m-1 p-1 rounded transition-colors">
                    <Globe className="w-4 h-4 text-primary shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium truncate block">{s.name}</span>
                      {s.url && <span className="text-[11px] text-muted-foreground truncate block">{s.url}</span>}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {s.schedule_interval && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">{s.schedule_interval}</span>
                      )}
                      {expandedSite === s.name ? <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />}
                    </div>
                  </button>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => onSubmit({ type: "scheduled", name: `Scheduled: ${s.name}`, site: s.name })}
                      className="p-1.5 rounded hover:bg-emerald-500/10 transition-colors text-muted-foreground hover:text-emerald-600"
                      data-testid={`button-run-site-${s.name}`} title={t("tasks.sites.run_crawl")}><Play className="w-3.5 h-3.5" /></button>
                    <button onClick={() => openEditForm(s)}
                      className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                      data-testid={`button-edit-site-${s.name}`}><Pencil className="w-3.5 h-3.5" /></button>
                    {deletingSite === s.name ? (
                      <div className="flex items-center gap-1">
                        <button onClick={() => handleDeleteSite(s.name)}
                          className="text-[10px] px-2 py-1 rounded bg-destructive text-destructive-foreground"
                          data-testid={`button-confirm-delete-site-${s.name}`}>{t("tasks.sched.confirm_delete")}</button>
                        <button onClick={() => setDeletingSite(null)}
                          className="text-[10px] px-2 py-1 rounded border border-border">{t("tasks.sched.cancel")}</button>
                      </div>
                    ) : (
                      <button onClick={() => setDeletingSite(s.name)}
                        className="p-1.5 rounded hover:bg-red-500/10 transition-colors text-muted-foreground hover:text-red-600"
                        data-testid={`button-delete-site-${s.name}`}><Trash2 className="w-3.5 h-3.5" /></button>
                    )}
                  </div>
                </div>
                {expandedSite === s.name && (
                  <div className="px-3.5 pb-3 pt-1 border-t border-border space-y-2 text-xs">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                      <div><span className="text-muted-foreground">{t("tasks.form.max_pages")}:</span> <span className="font-medium">{s.max_pages ?? "—"}</span></div>
                      <div><span className="text-muted-foreground">{t("tasks.form.max_depth")}:</span> <span className="font-medium">{s.max_depth ?? "—"}</span></div>
                    </div>
                    {s.keywords && s.keywords.length > 0 && (
                      <div>
                        <span className="text-muted-foreground">{t("tasks.form.keywords")}:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {s.keywords.map((kw) => (
                            <span key={kw} className="px-1.5 py-0.5 rounded bg-muted text-[10px]">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {s.exclude_keywords && s.exclude_keywords.length > 0 && (
                      <div>
                        <span className="text-muted-foreground">{t("tasks.form.exclude_keywords")}:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {s.exclude_keywords.map((kw) => (
                            <span key={kw} className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-600 dark:text-red-400 text-[10px]">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {s.content_selector && (
                      <div><span className="text-muted-foreground">{t("tasks.form.content_selector")}:</span> <code className="text-[10px] bg-muted px-1 rounded">{s.content_selector}</code></div>
                    )}
                    {s.url && (
                      <a href={s.url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline mt-1">
                        <ExternalLink className="w-3 h-3" />{t("tasks.form.visit_site")}
                      </a>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-border pt-4">
        <button onClick={() => { if (!showBackups) fetchBackups(); setShowBackups(!showBackups); }}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5"
          data-testid="button-toggle-backups">
          {showBackups ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {t("tasks.sites.backups")}
        </button>
        {showBackups && (
          <div className="mt-3 space-y-2">
            {loadingBackups ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /></div>
            ) : backups.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">{t("tasks.sites.no_backups")}</p>
            ) : (
              backups.map((b) => (
                <div key={b.filename} className="flex items-center justify-between px-3 py-2 rounded-lg border border-border bg-card text-xs" data-testid={`row-backup-${b.filename}`}>
                  <div className="flex-1 min-w-0">
                    <span className="font-medium truncate block">{b.filename}</span>
                    <div className="flex items-center gap-3 text-muted-foreground mt-0.5">
                      {b.timestamp && <span>{formatDate(b.timestamp)}</span>}
                      {b.size != null && <span>{(b.size / 1024).toFixed(1)} KB</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => handleRestoreBackup(b.filename)}
                      className="text-[10px] px-2 py-1 rounded border border-border hover:bg-muted transition-colors"
                      data-testid={`button-restore-backup-${b.filename}`}>{t("tasks.sites.restore")}</button>
                    <button onClick={() => handleDeleteBackup(b.filename)}
                      className="text-[10px] px-2 py-1 rounded hover:bg-red-500/10 text-muted-foreground hover:text-red-600 transition-colors"
                      data-testid={`button-delete-backup-${b.filename}`}><Trash2 className="w-3 h-3" /></button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ScheduledTasksSection() {
  const { t } = useTranslation();
  const [scheduleStatus, setScheduleStatus] = useState<ScheduleStatus | null>(null);
  const [scheduledTasks, setScheduledTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [deletingTask, setDeletingTask] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reinitMsg, setReinitMsg] = useState<string | null>(null);

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

  const openEditForm = (task: ScheduledTask) => {
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
    setSaving(true);
    try {
      let params = {};
      try { params = JSON.parse(formParams); } catch { /* keep empty */ }

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
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const handleDelete = async (name: string) => {
    setSaving(true);
    try {
      await apiPost("/api/scheduled-tasks/delete", { name });
      setDeletingTask(null);
      await fetchData();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const handleReinit = async () => {
    try {
      const res = await apiPost<{ success?: boolean; job_count?: number }>("/api/schedule/reinit");
      setReinitMsg(res.success ? `${t("tasks.sched.reinit_success")} (${res.job_count || 0} jobs)` : t("tasks.sched.reinit_fail"));
      await fetchData();
    } catch { setReinitMsg(t("tasks.sched.reinit_fail")); }
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
          {scheduleStatus && (
            <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Timer className="w-4 h-4 text-primary" />
                  <span className="text-sm font-medium">{t("tasks.sched.scheduler_jobs")}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                    {scheduleStatus.job_count || scheduleStatus.jobs?.length || 0} {t("tasks.sched.job_count").toLowerCase()}
                  </span>
                </div>
                <button onClick={handleReinit}
                  className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors flex items-center gap-1.5"
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
                      <span className="font-medium truncate flex-1">{job.tag || `Job ${i + 1}`}</span>
                      <div className="flex items-center gap-3 shrink-0 text-muted-foreground">
                        <span>{job.interval}</span>
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
              <button onClick={() => { resetForm(); setShowAddForm(true); }}
                className="text-xs px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5"
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
                          className="p-1.5 rounded hover:bg-red-500/10 transition-colors text-muted-foreground hover:text-red-600"
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

function WebCrawlForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [maxPages, setMaxPages] = useState("10");
  const [maxDepth, setMaxDepth] = useState("1");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [fileExts, setFileExts] = useState<string[]>([]);
  const [checkDb, setCheckDb] = useState(false);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.web_crawl_desc")}</p>
      <FormField label={t("tasks.form.crawl_url")}>
        <InputField value={url} onChange={setUrl} placeholder="https://example.org/reports/" testId="input-crawl-url" />
      </FormField>
      <FormField label={t("tasks.form.crawl_name")} hint={t("tasks.form.crawl_name_hint")}>
        <InputField value={name} onChange={setName} placeholder="Quick Check" testId="input-crawl-name" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.max_pages")} hint={t("tasks.form.default_hint") + " 10"}>
          <InputField value={maxPages} onChange={setMaxPages} placeholder="10" type="number" testId="input-crawl-max-pages" />
        </FormField>
        <FormField label={t("tasks.form.max_depth")} hint={t("tasks.form.default_hint") + " 1"}>
          <InputField value={maxDepth} onChange={setMaxDepth} placeholder="1" type="number" testId="input-crawl-max-depth" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.keywords")}>
        <TagSelect value={keywords} onChange={setKeywords} placeholder="Add keyword..." testId="input-crawl-keywords" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <TagSelect value={fileExts} onChange={setFileExts} presets={PRESET_FILE_EXTENSIONS} placeholder="Add extension..." testId="input-crawl-file-exts" />
      </FormField>
      <CheckboxField checked={checkDb} onChange={setCheckDb} label={t("tasks.form.check_database")} testId="checkbox-crawl-check-db" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !url.trim()}
        onClick={() => { if (!url.trim()) return;
          onSubmit({ type: "quick_check", name: name || "Quick Check", url: url.trim(),
            max_pages: parseInt(maxPages) || 10, max_depth: parseInt(maxDepth) || 1,
            keywords: keywords.length > 0 ? keywords : [],
            file_exts: fileExts.length > 0 ? fileExts : undefined,
            check_database: checkDb });
        }} />
    </div>
  );
}

function AdhocUrlForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [urls, setUrls] = useState("");
  const [fileExts, setFileExts] = useState<string[]>([".pdf", ".docx", ".pptx"]);
  const [checkDb, setCheckDb] = useState(true);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.url_desc")}</p>
      <FormField label={t("tasks.form.urls")}>
        <textarea value={urls} onChange={(e) => setUrls(e.target.value)} placeholder={t("tasks.form.urls_placeholder")} rows={4}
          className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          data-testid="input-urls" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")}>
        <TagSelect value={fileExts} onChange={setFileExts} presets={PRESET_FILE_EXTENSIONS} placeholder="Add extension..." testId="input-file-exts" />
      </FormField>
      <CheckboxField checked={checkDb} onChange={setCheckDb} label={t("tasks.form.check_database")} testId="checkbox-check-db" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !urls.trim()}
        onClick={() => {
          const urlList = urls.split("\n").map((u) => u.trim()).filter(Boolean);
          if (!urlList.length) return;
          onSubmit({ type: "url", name: `URL Collection (${urlList.length})`, urls: urlList,
            file_exts: fileExts.length > 0 ? fileExts : undefined, check_database: checkDb });
        }} />
    </div>
  );
}

interface BrowseEntry { name: string; type: "dir" | "file"; size?: number }

function FolderBrowser({ onSelect, onClose }: { onSelect: (path: string) => void; onClose: () => void }) {
  const { t } = useTranslation();
  const [currentPath, setCurrentPath] = useState("");
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const browse = useCallback(async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const q = path ? `?path=${encodeURIComponent(path)}` : "";
      const res = await apiGet<{ path: string; parent: string | null; entries: BrowseEntry[] }>(`/api/utils/browse-folder${q}`);
      setCurrentPath(res.path || "");
      setParentPath(res.parent || null);
      setEntries(res.entries || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("tasks.form.browse_error"));
    } finally { setLoading(false); }
  }, [t]);

  useEffect(() => { browse(); }, [browse]);

  const dirs = entries.filter((e) => e.type === "dir");
  const files = entries.filter((e) => e.type === "file");

  return (
    <div className="rounded-lg border border-primary/30 bg-card overflow-hidden" data-testid="panel-folder-browser">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <FolderOpen className="w-4 h-4 text-primary shrink-0" />
          <span className="text-xs font-mono truncate" data-testid="text-current-path">{currentPath || "/"}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => { onSelect(currentPath); onClose(); }}
            className="text-xs px-2.5 py-1 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            data-testid="button-select-folder">{t("tasks.form.select_folder")}</button>
          <button onClick={onClose}
            className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground"
            data-testid="button-close-browser"><X className="w-3.5 h-3.5" /></button>
        </div>
      </div>
      <div className="max-h-[280px] overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
        ) : error ? (
          <div className="px-3.5 py-4 text-xs text-destructive flex items-center gap-2"><AlertCircle className="w-4 h-4 shrink-0" />{error}</div>
        ) : (
          <div className="divide-y divide-border">
            {parentPath !== null && (
              <button onClick={() => browse(parentPath)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs hover:bg-muted/50 transition-colors text-left"
                data-testid="button-parent-dir">
                <ArrowLeft className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-muted-foreground font-medium">..</span>
              </button>
            )}
            {dirs.map((d) => (
              <button key={d.name} onClick={() => browse(currentPath.replace(/\/+$/, "") + "/" + d.name)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs hover:bg-muted/50 transition-colors text-left"
                data-testid={`button-dir-${d.name}`}>
                <Folder className="w-3.5 h-3.5 text-amber-500" />
                <span className="font-medium truncate">{d.name}</span>
              </button>
            ))}
            {files.map((f) => (
              <div key={f.name} className="flex items-center gap-2.5 px-3.5 py-2 text-xs text-muted-foreground">
                <FileText className="w-3.5 h-3.5" />
                <span className="truncate flex-1">{f.name}</span>
                {f.size != null && <span className="shrink-0 text-[10px]">{(f.size / 1024).toFixed(1)} KB</span>}
              </div>
            ))}
            {dirs.length === 0 && files.length === 0 && (
              <div className="px-3.5 py-4 text-xs text-muted-foreground text-center">{t("tasks.form.empty_folder")}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FileImportForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [dirPath, setDirPath] = useState("");
  const [extensions, setExtensions] = useState<string[]>([".pdf", ".docx", ".pptx"]);
  const [recursive, setRecursive] = useState(true);
  const [showBrowser, setShowBrowser] = useState(false);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.file_desc")}</p>
      <FormField label={t("tasks.form.directory_path")}>
        <div className="flex gap-2">
          <div className="flex-1">
            <InputField value={dirPath} onChange={setDirPath} placeholder="/path/to/files" testId="input-dir-path" />
          </div>
          <button onClick={() => setShowBrowser(!showBrowser)}
            className={cn(
              "shrink-0 px-3 py-2 rounded-lg border text-sm transition-colors flex items-center gap-1.5",
              showBrowser ? "border-primary bg-primary/10 text-primary" : "border-border hover:bg-muted text-muted-foreground hover:text-foreground"
            )}
            data-testid="button-browse-folder">
            <FolderOpen className="w-4 h-4" />
            <span className="text-xs">{t("tasks.form.browse")}</span>
          </button>
        </div>
      </FormField>
      {showBrowser && (
        <FolderBrowser onSelect={(p) => setDirPath(p)} onClose={() => setShowBrowser(false)} />
      )}
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <TagSelect value={extensions} onChange={setExtensions} presets={PRESET_FILE_EXTENSIONS} placeholder="Add extension..." testId="input-extensions" />
      </FormField>
      <CheckboxField checked={recursive} onChange={setRecursive} label={t("tasks.form.recursive")} testId="checkbox-recursive" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !dirPath.trim()}
        onClick={() => { if (!dirPath.trim()) return;
          onSubmit({ type: "file", name: `File Import: ${dirPath}`, directory_path: dirPath,
            extensions: extensions.length > 0 ? extensions : undefined, recursive });
        }} />
    </div>
  );
}

function WebSearchForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const { engines: dynamicEngines } = useTaskOptions();
  const [query, setQuery] = useState("");
  const [engine, setEngine] = useState("brave");
  const [count, setCount] = useState("20");
  const [site, setSite] = useState("");
  const [searchLang, setSearchLang] = useState<string[]>([]);
  const [searchCountry, setSearchCountry] = useState<string[]>([]);
  const [excludeKw, setExcludeKw] = useState<string[]>([]);
  const [fileExts, setFileExts] = useState<string[]>([]);
  const [useDefaults, setUseDefaults] = useState(true);

  const engineOptions = dynamicEngines.map((e) => ({ value: e.value, label: e.name + (e.available ? "" : " (unavailable)") }));

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.search_desc")}</p>
      <FormField label={t("tasks.form.search_query")}>
        <InputField value={query} onChange={setQuery} placeholder={t("tasks.form.search_query_placeholder")} testId="input-search-query" />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.search_engine")}>
          <SelectField value={engine} onChange={setEngine} options={engineOptions} testId="select-engine" />
        </FormField>
        <FormField label={t("tasks.form.max_results")}>
          <InputField value={count} onChange={setCount} placeholder="20" type="number" testId="input-count" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.site_filter")}>
        <InputField value={site} onChange={setSite} placeholder="example.com" testId="input-site-filter" />
      </FormField>
      <FormField label={t("tasks.form.search_lang")}>
        <TagSelect value={searchLang} onChange={setSearchLang} presets={PRESET_LANGUAGES} placeholder="Add language..." testId="input-search-lang" />
      </FormField>
      <FormField label={t("tasks.form.search_country")}>
        <TagSelect value={searchCountry} onChange={setSearchCountry} presets={PRESET_COUNTRIES} placeholder="Add country..." testId="input-search-country" />
      </FormField>
      <FormField label={t("tasks.form.exclude_keywords")}>
        <TagSelect value={excludeKw} onChange={setExcludeKw} placeholder="Add keyword to exclude..." testId="input-exclude-kw" />
      </FormField>
      <FormField label={t("tasks.form.file_extensions")}>
        <TagSelect value={fileExts} onChange={setFileExts} presets={PRESET_FILE_EXTENSIONS} placeholder="Add extension..." testId="input-search-file-exts" />
      </FormField>
      <CheckboxField checked={useDefaults} onChange={setUseDefaults} label={t("tasks.form.use_search_defaults")} testId="checkbox-use-defaults" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !query.trim()}
        onClick={() => { if (!query.trim()) return;
          onSubmit({ type: "search", name: `Search: ${query}`, query, engine, count: parseInt(count) || 20,
            site: site || undefined, search_lang: searchLang.length > 0 ? searchLang.join(",") : undefined,
            search_country: searchCountry.length > 0 ? searchCountry.join(",") : undefined,
            search_exclude_keywords: excludeKw.length > 0 ? excludeKw : undefined,
            file_exts: fileExts.length > 0 ? fileExts : undefined,
            use_search_defaults: useDefaults });
        }} />
    </div>
  );
}

function CatalogForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const { categories: dynamicCategories, catalogProviders } = useTaskOptions();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("100");
  const [startIndex, setStartIndex] = useState("1");
  const [inputSource, setInputSource] = useState("markdown");
  const [retryErrors, setRetryErrors] = useState(false);
  const [skipExisting, setSkipExisting] = useState(true);
  const [overwriteExisting, setOverwriteExisting] = useState(false);
  const [updateTitle, setUpdateTitle] = useState(false);
  const [outputLanguage, setOutputLanguage] = useState("auto");
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const loadStats = useCallback(async (cat?: string) => {
    setStatsLoading(true);
    try {
      const q = cat ? `?category=${encodeURIComponent(cat)}` : "";
      const res = await apiGet<{ data?: Record<string, unknown> } & Record<string, unknown>>(`/api/catalog/stats${q}`);
      setStats(res.data || res);
    } catch { setStats(null); }
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.catalog_desc")}</p>
      {statsLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("tasks.form.loading_stats")}</div>
      ) : stats && (
        <StatsBanner items={[
          { label: t("tasks.form.stat_local_files"), value: stats.total_local_files as number },
          { label: t("tasks.form.stat_cataloged"), value: stats.total_catalog_ok as number },
          { label: t("tasks.form.stat_candidates"), value: stats.candidate_total as number },
          { label: t("tasks.form.stat_first_candidate"), value: stats.first_candidate_index as number },
        ]} />
      )}
      <FormField label={t("tasks.form.provider")}>
        {catalogProviders.length > 0 ? (
          <div className="px-3 py-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 text-xs text-emerald-700 dark:text-emerald-400 flex items-center gap-2" data-testid="text-provider-info">
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
            {t("tasks.form.catalog_provider_configured")}: {catalogProviders.join(", ")}
          </div>
        ) : (
          <div className="px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/5 text-xs text-amber-700 dark:text-amber-400" data-testid="text-provider-info">
            {t("tasks.form.no_catalog_provider")}{" "}
            <a href="/settings" className="underline hover:no-underline">{t("tasks.form.go_to_settings")}</a>
          </div>
        )}
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.scope")}>
          <SelectField value={scopeMode} onChange={(v) => { setScopeMode(v); if (v === "index") loadStats(); }} testId="select-scope"
            options={[{ value: "index", label: t("tasks.form.scope_all") }, { value: "category", label: t("tasks.form.scope_category") }]} />
        </FormField>
        <FormField label={t("tasks.form.scan_count")} hint={t("tasks.form.max_hint") + " 2000"}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="100" type="number" testId="input-scan-count" />
        </FormField>
      </div>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} onBlur={handleCategoryBlur} placeholder="SOA, IAA..."
            list="catalog-categories-list"
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="input-category" />
          <datalist id="catalog-categories-list">
            {dynamicCategories.map((c) => <option key={c} value={c} />)}
          </datalist>
        </FormField>
      )}
      <FormField label={t("tasks.form.start_index")} hint={t("tasks.form.start_index_hint")}>
        <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-start-index" />
      </FormField>
      <FormField label={t("tasks.form.input_source")}>
        <SelectField value={inputSource} onChange={setInputSource} testId="select-input-source"
          options={[{ value: "markdown", label: "Markdown" }, { value: "source", label: "Source" }]} />
      </FormField>
      {catalogProviders.length > 0 && (
        <FormField label={t("tasks.form.output_language")}>
          <SelectField value={outputLanguage} onChange={setOutputLanguage} testId="select-output-language"
            options={[
              { value: "auto", label: t("tasks.form.lang_auto") },
              { value: "en", label: t("tasks.form.lang_en") },
              { value: "zh", label: t("tasks.form.lang_zh") },
            ]} />
        </FormField>
      )}
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={retryErrors} onChange={setRetryErrors} label={t("tasks.form.retry_errors")} testId="checkbox-retry-errors" />
        <CheckboxField checked={skipExisting} onChange={(v) => { setSkipExisting(v); if (v) setOverwriteExisting(false); }}
          label={t("tasks.form.skip_existing")} testId="checkbox-skip-existing" />
        <CheckboxField checked={overwriteExisting} onChange={(v) => { setOverwriteExisting(v); if (v) setSkipExisting(false); }}
          label={t("tasks.form.overwrite_existing")} testId="checkbox-overwrite-existing" />
        {catalogProviders.length > 0 && (
          <CheckboxField checked={updateTitle} onChange={setUpdateTitle}
            label={t("tasks.form.update_title")} testId="checkbox-update-title" />
        )}
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim()) || catalogProviders.length === 0}
        onClick={() => onSubmit({ type: "catalog", name: "AI Catalog", scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined, scan_count: parseInt(scanCount) || 100,
          scan_start_index: parseInt(startIndex) || 1, input_source: inputSource,
          retry_errors: retryErrors, skip_existing: skipExisting, overwrite_existing: overwriteExisting,
          update_title: updateTitle, output_language: outputLanguage })} />
    </div>
  );
}

function MarkdownForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const { conversionTools, categories: dynamicCategories } = useTaskOptions();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [startIndex, setStartIndex] = useState("");
  const [tool, setTool] = useState("docling");
  const [skipExisting, setSkipExisting] = useState(true);
  const [overwriteExisting, setOverwriteExisting] = useState(false);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const tools = conversionTools.length > 0
    ? conversionTools.map((t) => ({ value: t, label: t.charAt(0).toUpperCase() + t.slice(1) }))
    : [{ value: "docling", label: "Docling" }, { value: "marker", label: "Marker" }, { value: "mistral", label: "Mistral OCR" }, { value: "auto", label: "Auto" }];

  const loadStats = useCallback(async (cat?: string) => {
    setStatsLoading(true);
    try {
      const q = cat ? `?category=${encodeURIComponent(cat)}` : "";
      const res = await apiGet<{ data?: Record<string, unknown> } & Record<string, unknown>>(`/api/markdown_conversion/stats${q}`);
      setStats(res.data || res);
    } catch { setStats(null); }
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  useEffect(() => {
    if (stats && !startIndex) {
      const first = stats.first_without_markdown_index;
      if (first != null) setStartIndex(String(first));
    }
  }, [stats, startIndex]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.markdown_desc")}</p>
      {statsLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("tasks.form.loading_stats")}</div>
      ) : stats && (
        <StatsBanner items={[
          { label: t("tasks.form.stat_convertible"), value: stats.total_convertible as number },
          { label: t("tasks.form.stat_with_markdown"), value: stats.total_with_markdown as number },
          { label: t("tasks.form.stat_first_no_md"), value: stats.first_without_markdown_index as number },
        ]} />
      )}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.conversion_tool")}>
          <SelectField value={tool} onChange={setTool} options={tools} testId="select-tool" />
        </FormField>
        <FormField label={t("tasks.form.scan_count")} hint={t("tasks.form.max_hint") + " 2000"}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-md-scan-count" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.start_index")} hint={t("tasks.form.start_index_hint")}>
        <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-md-start-index" />
      </FormField>
      <FormField label={t("tasks.form.scope")}>
        <SelectField value={scopeMode} onChange={(v) => { setScopeMode(v); if (v === "index") loadStats(); }} testId="select-md-scope"
          options={[{ value: "index", label: t("tasks.form.scope_all") }, { value: "category", label: t("tasks.form.scope_category") }]} />
      </FormField>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} onBlur={handleCategoryBlur} placeholder="SOA, IAA..."
            list="md-categories-list"
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="input-md-category" />
          <datalist id="md-categories-list">
            {dynamicCategories.map((c) => <option key={c} value={c} />)}
          </datalist>
        </FormField>
      )}
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={skipExisting} onChange={(v) => { setSkipExisting(v); if (v) setOverwriteExisting(false); }}
          label={t("tasks.form.skip_existing")} testId="checkbox-md-skip" />
        <CheckboxField checked={overwriteExisting} onChange={(v) => { setOverwriteExisting(v); if (v) setSkipExisting(false); }}
          label={t("tasks.form.overwrite_existing")} testId="checkbox-md-overwrite" />
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim())}
        onClick={() => onSubmit({ type: "markdown_conversion", name: `Markdown (${tool})`, conversion_tool: tool,
          scope_mode: scopeMode, category: scopeMode === "category" ? category : undefined,
          scan_count: parseInt(scanCount) || 50, scan_start_index: startIndex ? parseInt(startIndex) : undefined,
          skip_existing: skipExisting, overwrite_existing: overwriteExisting })} />
    </div>
  );
}

function ChunkForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const { categories: dynamicCategories } = useTaskOptions();
  const [scopeMode, setScopeMode] = useState("index");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [startIndex, setStartIndex] = useState("");
  const [chunkSize, setChunkSize] = useState("800");
  const [chunkOverlap, setChunkOverlap] = useState("100");
  const [splitter, setSplitter] = useState("semantic");
  const [tokenizer, setTokenizer] = useState("cl100k_base");
  const [profileName, setProfileName] = useState("");
  const [overwriteSameProfile, setOverwriteSameProfile] = useState(false);
  const [kbId, setKbId] = useState("");
  const [kbs, setKbs] = useState<KBItem[]>([]);
  const [kbLoadError, setKbLoadError] = useState(false);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const loadStats = useCallback(async (cat?: string) => {
    setStatsLoading(true);
    try {
      const q = cat ? `?category=${encodeURIComponent(cat)}` : "";
      const res = await apiGet<{ data?: Record<string, unknown> } & Record<string, unknown>>(`/api/chunk_generation/stats${q}`);
      setStats(res.data || res);
    } catch { setStats(null); }
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => {
    apiGet<Record<string, unknown>>("/api/rag/knowledge-bases")
      .then((res) => {
        const d = res.data;
        const raw: Array<Record<string, string>> = Array.isArray(d) ? d : Array.isArray((d as Record<string, unknown>)?.knowledge_bases) ? (d as Record<string, unknown>).knowledge_bases as Array<Record<string, string>> : [];
        setKbs(raw.map((kb) => ({ kb_id: kb.kb_id || kb.id || "", name: kb.name || kb.kb_id || kb.id || "" })));
        setKbLoadError(false);
      }).catch(() => { setKbs([]); setKbLoadError(true); });
  }, []);

  useEffect(() => {
    if (stats && !startIndex) {
      const first = stats.first_without_chunks_index;
      if (first != null) setStartIndex(String(first));
    }
  }, [stats, startIndex]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.chunk_desc")}</p>
      {statsLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("tasks.form.loading_stats")}</div>
      ) : stats && (
        <StatsBanner items={[
          { label: t("tasks.form.stat_with_markdown"), value: stats.total_with_markdown as number },
          { label: t("tasks.form.stat_with_chunks"), value: stats.total_with_chunks as number },
          { label: t("tasks.form.stat_first_no_chunk"), value: stats.first_without_chunks_index as number },
        ]} />
      )}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.scan_count")} hint={t("tasks.form.max_hint") + " 2000"}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-chunk-scan-count" />
        </FormField>
        <FormField label={t("tasks.form.start_index")} hint={t("tasks.form.start_index_hint")}>
          <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-chunk-start-index" />
        </FormField>
      </div>
      <FormField label={t("tasks.form.scope")}>
        <SelectField value={scopeMode} onChange={(v) => { setScopeMode(v); if (v === "index") loadStats(); }} testId="select-chunk-scope"
          options={[{ value: "index", label: t("tasks.form.scope_all") }, { value: "category", label: t("tasks.form.scope_category") }]} />
      </FormField>
      {scopeMode === "category" && (
        <FormField label={t("tasks.form.category")}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} onBlur={handleCategoryBlur} placeholder="SOA, IAA..."
            list="chunk-categories-list"
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="input-chunk-category" />
          <datalist id="chunk-categories-list">
            {dynamicCategories.map((c) => <option key={c} value={c} />)}
          </datalist>
        </FormField>
      )}
      <div className="border-t border-border pt-3 mt-1">
        <p className="text-xs font-medium text-muted-foreground mb-3">{t("tasks.form.chunk_params")}</p>
        <div className="grid grid-cols-2 gap-3">
          <FormField label={t("tasks.form.chunk_size")} hint="64 – 8192">
            <InputField value={chunkSize} onChange={setChunkSize} placeholder="800" type="number" testId="input-chunk-size" />
          </FormField>
          <FormField label={t("tasks.form.chunk_overlap")} hint="0 – 2048">
            <InputField value={chunkOverlap} onChange={setChunkOverlap} placeholder="100" type="number" testId="input-chunk-overlap" />
          </FormField>
        </div>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <FormField label={t("tasks.form.splitter")}>
            <SelectField value={splitter} onChange={setSplitter} testId="select-splitter"
              options={[{ value: "semantic", label: "Semantic" }, { value: "recursive", label: "Recursive" }]} />
          </FormField>
          <FormField label={t("tasks.form.tokenizer")}>
            <SelectField value={tokenizer} onChange={setTokenizer} testId="select-tokenizer"
              options={[{ value: "cl100k_base", label: "cl100k_base" }, { value: "p50k_base", label: "p50k_base" }, { value: "o200k_base", label: "o200k_base" }]} />
          </FormField>
        </div>
        <div className="mt-3">
          <FormField label={t("tasks.form.chunk_profile")} hint={t("tasks.form.profile_hint")}>
            <InputField value={profileName} onChange={setProfileName} placeholder="task-profile" testId="input-chunk-profile" />
          </FormField>
        </div>
      </div>
      <div className="border-t border-border pt-3 mt-1">
        <p className="text-xs font-medium text-muted-foreground mb-3">{t("tasks.form.kb_binding")}</p>
        <FormField label={t("tasks.form.bind_to_kb")} hint={t("tasks.form.bind_hint")}>
          {kbLoadError ? (
            <div className="px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/5 text-xs text-amber-700 dark:text-amber-400">
              {t("tasks.form.kb_load_error")}
            </div>
          ) : (
            <SelectField value={kbId} onChange={setKbId} testId="select-chunk-kb"
              options={[{ value: "", label: t("tasks.form.no_binding") }, ...kbs.map((kb) => ({ value: kb.kb_id, label: kb.name }))]} />
          )}
        </FormField>
      </div>
      <CheckboxField checked={overwriteSameProfile} onChange={setOverwriteSameProfile}
        label={t("tasks.form.overwrite_same_profile")} testId="checkbox-overwrite-profile" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim())}
        onClick={() => onSubmit({ type: "chunk_generation", name: "Chunk Generation", scope_mode: scopeMode,
          category: scopeMode === "category" ? category : undefined, scan_count: parseInt(scanCount) || 50,
          scan_start_index: startIndex ? parseInt(startIndex) : undefined,
          chunk_size: parseInt(chunkSize) || 800, chunk_overlap: parseInt(chunkOverlap) || 100,
          splitter, tokenizer, profile_name: profileName || undefined,
          overwrite_same_profile: overwriteSameProfile, kb_id: kbId || undefined })} />
    </div>
  );
}

function RagIndexForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [kbId, setKbId] = useState("");
  const [kbs, setKbs] = useState<KBItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [forceReindex, setForceReindex] = useState(false);
  const [incremental, setIncremental] = useState(true);

  useEffect(() => {
    apiGet<Record<string, unknown>>("/api/rag/knowledge-bases")
      .then((res) => {
        const d = res.data;
        const raw: Array<Record<string, string>> = Array.isArray(d) ? d : Array.isArray((d as Record<string, unknown>)?.knowledge_bases) ? (d as Record<string, unknown>).knowledge_bases as Array<Record<string, string>> : [];
        setKbs(raw.map((kb) => ({ kb_id: kb.kb_id || kb.id || "", name: kb.name || kb.kb_id || kb.id || "" })));
      }).catch(() => setKbs([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.rag_desc")}</p>
      <FormField label={t("tasks.form.knowledge_base")}>
        {loading ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" />{t("tasks.form.loading_kbs")}</div>
        ) : kbs.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground"><AlertCircle className="w-4 h-4" />{t("tasks.form.no_kbs")}</div>
        ) : (
          <SelectField value={kbId} onChange={setKbId} testId="select-kb"
            options={[{ value: "", label: t("tasks.form.select_kb") }, ...kbs.map((kb) => ({ value: kb.kb_id, label: kb.name }))]} />
        )}
      </FormField>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={incremental} onChange={(v) => { setIncremental(v); if (v) setForceReindex(false); }}
          label={t("tasks.form.incremental")} testId="checkbox-incremental" />
        <CheckboxField checked={forceReindex} onChange={(v) => { setForceReindex(v); if (v) setIncremental(false); }}
          label={t("tasks.form.force_reindex")} testId="checkbox-force-reindex" />
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || !kbId}
        onClick={() => { if (!kbId) return;
          onSubmit({ type: "rag_indexing", name: `RAG Index: ${kbId}`, kb_id: kbId, force_reindex: forceReindex, incremental });
        }} />
    </div>
  );
}

interface HistoryTask {
  id?: string;
  name?: string;
  type?: string;
  status?: string;
  started_at?: string;
  completed_at?: string;
  items_processed?: number;
  items_downloaded?: number;
  items_skipped?: number;
  catalog_scanned?: number;
  catalog_ok?: number;
  catalog_skipped?: number;
  catalog_errors?: number;
  errors?: string[];
}

export default function Tasks() {
  const { t } = useTranslation();
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [sites, setSites] = useState<SiteConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeForm, setActiveForm] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(true);
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [logModal, setLogModal] = useState<{ taskId: string; taskName: string; log: string } | null>(null);
  const [logModalLoading, setLogModalLoading] = useState(false);

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

  // Auto-fetch history on load
  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const viewTaskLog = async (taskId: string | undefined, taskName: string | undefined) => {
    if (!taskId) return;
    setLogModalLoading(true);
    setLogModal({ taskId, taskName: taskName || taskId, log: "" });
    try {
      const res = await apiGet<{ log?: string }>(`/api/tasks/log/${encodeURIComponent(taskId)}?tail=500`);
      setLogModal({ taskId, taskName: taskName || taskId, log: res.log || "(no log available)" });
    } catch {
      setLogModal({ taskId, taskName: taskName || taskId, log: "(failed to load log)" });
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

  const activeTaskType = taskTypes.find((tt) => tt.type === activeForm);

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
      case "rag_index": return <RagIndexForm onSubmit={handleSubmitTask} submitting={submitting} />;
      default: return null;
    }
  }

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight">{t("tasks.title")}</h1>
        <p className="text-muted-foreground mt-1.5 text-sm max-w-2xl leading-relaxed">{t("tasks.subtitle")}</p>
      </motion.div>

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
          <p className="text-xs text-muted-foreground py-1" data-testid="text-no-active-tasks">
            {t("tasks.no_active")}
          </p>
        ) : (
          <div className="space-y-3">
            {activeTasks.map((task, i) => (
              <motion.div key={task.id} custom={i} variants={fadeUp} initial="hidden" animate="visible"
                className="rounded-xl border border-border bg-card p-5" data-testid={`card-active-task-${task.id}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {statusBadge(task.status)}
                      <span className="font-semibold text-sm truncate">{task.name}</span>
                    </div>
                    {task.current_activity && (
                      <p className="text-xs text-muted-foreground mt-1 truncate" data-testid={`text-activity-${task.id}`}>{task.current_activity}</p>
                    )}
                  </div>
                  <button onClick={() => stopTask(task.id)}
                    className="shrink-0 p-2 rounded-lg bg-red-500/10 text-red-600 hover:bg-red-500/20 transition-colors"
                    data-testid={`button-stop-task-${task.id}`} title={t("tasks.stop")}><Square className="w-4 h-4" /></button>
                </div>
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                    <span>{task.items_processed}/{task.items_total || "?"}</span>
                    <span>{Math.round(task.progress)}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                    <motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }}
                      animate={{ width: `${Math.min(task.progress, 100)}%` }} transition={{ duration: 0.5 }} />
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">{t("tasks.started")}: {formatDate(task.started_at)}</p>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Task History (after active tasks) */}
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
            {historyLoading ? (
              <div className="flex items-center justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            ) : historyTasks.length === 0 ? (
              <div className="text-center py-8 rounded-xl border border-dashed border-border bg-card" data-testid="text-no-history">
                <History className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" />
                <p className="text-sm font-medium text-muted-foreground">{t("tasks.no_history")}</p>
              </div>
            ) : (
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
                            <button onClick={() => viewTaskLog(task.id, task.name)}
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
            )}
          </div>
        )}
      </div>

      <ScheduledTasksSection />

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
              <div className="flex-1 overflow-y-auto p-4">
                {logModalLoading ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <pre className="text-xs font-mono whitespace-pre-wrap break-all text-foreground/80 leading-relaxed">
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
