import { useEffect, useState, useCallback } from "react";
import { Loader2, CheckCircle2 } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { useTaskOptions } from "@/hooks/use-task-options";
import { apiGet } from "@/lib/api";
import { FormField, InputField, SelectField, CheckboxField, StatsBanner, RunButton } from "@/components/FormFields";

export function CatalogForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
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
