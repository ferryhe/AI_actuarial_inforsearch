import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import TagSelect, { PRESET_FILE_EXTENSIONS } from "@/components/TagSelect";
import { FormField, InputField, CheckboxField, RunButton } from "@/components/FormFields";
import { FolderBrowser } from "./FolderBrowser";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

export function FileImportForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [dirPath, setDirPath] = useState("");
  const [extensions, setExtensions] = useState<string[]>([".pdf", ".docx", ".pptx"]);
  const [recursive, setRecursive] = useState(true);
  const [showBrowser, setShowBrowser] = useState(false);

  const buildTask = (): Record<string, unknown> | null => {
    if (!dirPath.trim()) return null;
    return {
      type: "file",
      name: `File Import: ${dirPath}`,
      directory_path: dirPath,
      extensions: extensions.length > 0 ? extensions : undefined,
      recursive,
    };
  };

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
        onClick={() => {
          const task = buildTask();
          if (task) onSubmit(task);
        }} />
      <ScheduleFromTaskButton buildTask={buildTask} disabled={!dirPath.trim()} />
    </div>
  );
}
