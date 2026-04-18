import { useState } from "react";
import { useTranslation } from "@/components/Layout";
import TagSelect, { PRESET_FILE_EXTENSIONS } from "@/components/TagSelect";
import { FormField, CheckboxField, RunButton } from "@/components/FormFields";

export function AdhocUrlForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
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
