import { useEffect, useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { useTaskOptions } from "@/hooks/use-task-options";
import { apiGet } from "@/lib/api";
import { FormField, InputField, SelectField, CheckboxField, StatsBanner, RunButton } from "@/components/FormFields";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

export function ChunkForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
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
    if (stats && !startIndex) {
      const first = stats.first_without_chunks_index;
      if (first != null) setStartIndex(String(first));
    }
  }, [stats, startIndex]);

  const handleCategoryBlur = () => {
    if (scopeMode === "category" && category.trim()) loadStats(category.trim());
  };

  const buildTask = (): Record<string, unknown> | null => {
    if (scopeMode === "category" && !category.trim()) return null;
    return {
      type: "chunk_generation",
      name: "Chunk Generation",
      scope_mode: scopeMode,
      category: scopeMode === "category" ? category : undefined,
      scan_count: parseInt(scanCount) || 50,
      scan_start_index: startIndex ? parseInt(startIndex) : undefined,
      chunk_size: parseInt(chunkSize) || 800,
      chunk_overlap: parseInt(chunkOverlap) || 100,
      splitter,
      tokenizer,
      profile_name: profileName || undefined,
      overwrite_same_profile: overwriteSameProfile,
    };
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
      <div className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        {t("tasks.form.chunk_kb_binding_notice")}
      </div>
      <CheckboxField checked={overwriteSameProfile} onChange={setOverwriteSameProfile}
        label={t("tasks.form.overwrite_same_profile")} testId="checkbox-overwrite-profile" />
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={submitting || (scopeMode === "category" && !category.trim())}
        onClick={() => {
          const task = buildTask();
          if (task) onSubmit(task);
        }} />
      <ScheduleFromTaskButton buildTask={buildTask} disabled={scopeMode === "category" && !category.trim()} />
    </div>
  );
}
