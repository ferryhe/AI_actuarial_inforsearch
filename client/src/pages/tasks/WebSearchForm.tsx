import { useState } from "react";
import { useTranslation } from "@/components/Layout";
import TagSelect, { PRESET_FILE_EXTENSIONS, PRESET_LANGUAGES, PRESET_COUNTRIES } from "@/components/TagSelect";
import { useTaskOptions } from "@/hooks/use-task-options";
import { FormField, InputField, SelectField, CheckboxField, RunButton } from "@/components/FormFields";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

export function WebSearchForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
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
  const buildTask = (): Record<string, unknown> | null => {
    if (!query.trim()) return null;
    return {
      type: "search",
      name: `Search: ${query}`,
      query,
      engine,
      count: parseInt(count) || 20,
      site: site || undefined,
      search_lang: searchLang.length > 0 ? searchLang.join(",") : undefined,
      search_country: searchCountry.length > 0 ? searchCountry.join(",") : undefined,
      search_exclude_keywords: excludeKw.length > 0 ? excludeKw : undefined,
      file_exts: fileExts.length > 0 ? fileExts : undefined,
      use_search_defaults: useDefaults,
    };
  };

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
        onClick={() => {
          const task = buildTask();
          if (task) onSubmit(task);
        }} />
      <ScheduleFromTaskButton buildTask={buildTask} disabled={!query.trim()} />
    </div>
  );
}
