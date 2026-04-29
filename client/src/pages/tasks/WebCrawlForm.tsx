import { useState } from "react";
import { useTranslation } from "@/components/Layout";
import TagSelect, { PRESET_FILE_EXTENSIONS } from "@/components/TagSelect";
import { FormField, InputField, SelectField, CheckboxField, RunButton } from "@/components/FormFields";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

export function WebCrawlForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [maxPages, setMaxPages] = useState("10");
  const [maxDepth, setMaxDepth] = useState("1");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [fileExts, setFileExts] = useState<string[]>([]);
  const [checkDb, setCheckDb] = useState(false);

  const buildTask = (): Record<string, unknown> | null => {
    if (!url.trim()) return null;
    return {
      type: "quick_check",
      name: name || "Quick Check",
      url: url.trim(),
      max_pages: parseInt(maxPages) || 10,
      max_depth: parseInt(maxDepth) || 1,
      keywords: keywords.length > 0 ? keywords : [],
      file_exts: fileExts.length > 0 ? fileExts : undefined,
      check_database: checkDb,
    };
  };

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
        onClick={() => {
          const task = buildTask();
          if (task) onSubmit(task);
        }} />
      <ScheduleFromTaskButton buildTask={buildTask} disabled={!url.trim()} />
    </div>
  );
}
