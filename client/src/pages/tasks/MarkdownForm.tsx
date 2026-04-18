import { useEffect, useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { useTaskOptions } from "@/hooks/use-task-options";
import { apiGet } from "@/lib/api";
import { FormField, InputField, SelectField, CheckboxField, StatsBanner, RunButton } from "@/components/FormFields";

export function MarkdownForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
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
