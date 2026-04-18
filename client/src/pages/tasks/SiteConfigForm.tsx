import { useState, useRef, useCallback } from "react";
import {
  FileUp, Download, Plus, Pencil, Trash2, Save, Loader2,
  Globe, ExternalLink, ChevronDown, ChevronUp, RefreshCw, FolderOpen, X,
} from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost } from "@/lib/api";
import { FormField, InputField } from "@/components/FormFields";

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

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

export function SiteConfigForm({ sites, onSubmit, submitting, onSitesChanged }: {
  sites: SiteConfig[]; onSubmit: (d: Record<string, unknown>) => void; submitting: boolean; onSitesChanged: () => void;
}) {
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
          <select value={site} onChange={(e) => setSite(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="select-site">
            <option value="">{t("tasks.form.all_sites")} ({sites.length})</option>
            {sites.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
          </select>
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label={t("tasks.form.max_pages")} hint={t("tasks.form.default_hint") + " 200"}>
            <InputField value={maxPages} onChange={setMaxPages} placeholder="200" type="number" testId="input-max-pages" />
          </FormField>
          <FormField label={t("tasks.form.max_depth")} hint={t("tasks.form.default_hint") + " 2"}>
            <InputField value={maxDepth} onChange={setMaxDepth} placeholder="2" type="number" testId="input-max-depth" />
          </FormField>
        </div>
        <button onClick={() => onSubmit({ type: "scheduled", name: site ? `Scheduled: ${site}` : "Scheduled Collection",
            site: site || undefined, max_pages: maxPages ? parseInt(maxPages) : undefined, max_depth: maxDepth ? parseInt(maxDepth) : undefined })}
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          data-testid="button-run-task">
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {t("tasks.form.run")}
        </button>
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
                      data-testid={`button-run-site-${s.name}`} title={t("tasks.sites.run_crawl")}><Plus className="w-3.5 h-3.5" /></button>
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
