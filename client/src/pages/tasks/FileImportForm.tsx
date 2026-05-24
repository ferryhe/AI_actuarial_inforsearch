import { useRef, useState } from "react";
import { Upload, FolderUp } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiPostForm } from "@/lib/api";
import TagSelect, { PRESET_FILE_EXTENSIONS } from "@/components/TagSelect";
import { FormField, RunButton } from "@/components/FormFields";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

type ImportBatchResponse = {
  success?: boolean;
  upload_batch_id: string;
  file_count?: number;
  total_bytes?: number;
};

type FileInputWithDirectory = HTMLInputElement & { webkitdirectory?: boolean };

function selectedExtensions(extensions: string[]): Set<string> {
  return new Set(extensions.map((ext) => ext.toLowerCase().replace(/^\./, "")).filter(Boolean));
}

function fileMatchesExtensions(file: File, allowedExts: Set<string>): boolean {
  if (allowedExts.size === 0) return true;
  const ext = (file.webkitRelativePath || file.name).split(".").pop()?.toLowerCase() || "";
  return allowedExts.has(ext);
}

function appendFiles(formData: FormData, fileList: FileList | null, allowedExts: Set<string>): number {
  if (!fileList) return 0;
  let count = 0;
  Array.from(fileList).forEach((file) => {
    if (!fileMatchesExtensions(file, allowedExts)) return;
    formData.append("files", file, file.name);
    formData.append("relative_paths", file.webkitRelativePath || file.name);
    count += 1;
  });
  return count;
}

export function FileImportForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [extensions, setExtensions] = useState<string[]>([".pdf", ".docx", ".pptx"]);
  const [selectedLabel, setSelectedLabel] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const filesInputRef = useRef<HTMLInputElement | null>(null);
  const directoryInputRef = useRef<HTMLInputElement | null>(null);

  const buildTask = (): Record<string, unknown> | null => null;

  const updateSelectedLabel = () => {
    const fileCount = (filesInputRef.current?.files?.length || 0) + (directoryInputRef.current?.files?.length || 0);
    setSelectedLabel(fileCount > 0 ? t("tasks.form.selected_files").replace("{count}", String(fileCount)) : "");
  };

  const runImport = async () => {
    const formData = new FormData();
    const allowedExts = selectedExtensions(extensions);
    const count = appendFiles(formData, filesInputRef.current?.files || null, allowedExts) + appendFiles(formData, directoryInputRef.current?.files || null, allowedExts);
    if (count <= 0) {
      setUploadError(t("tasks.form.select_files_required"));
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const batch = await apiPostForm<ImportBatchResponse>("/api/files/import-batches", formData);
      onSubmit({
        type: "file",
        name: `File Import: ${batch.file_count || count} files`,
        upload_batch_id: batch.upload_batch_id,
        extensions: extensions.length > 0 ? extensions : undefined,
      });
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : t("tasks.form.upload_error"));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.file_upload_desc")}</p>
      <FormField label={t("tasks.form.local_files")} hint={t("tasks.form.local_files_hint")}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-6 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground">
            <Upload className="h-4 w-4" />
            <span>{t("tasks.form.choose_files")}</span>
            <input
              ref={filesInputRef}
              type="file"
              multiple
              className="hidden"
              data-testid="input-local-files"
              onChange={updateSelectedLabel}
            />
          </label>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-6 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground">
            <FolderUp className="h-4 w-4" />
            <span>{t("tasks.form.choose_folder")}</span>
            <input
              ref={(node) => {
                directoryInputRef.current = node;
                if (node) (node as FileInputWithDirectory).webkitdirectory = true;
              }}
              type="file"
              multiple
              className="hidden"
              data-testid="input-local-directory"
              onChange={updateSelectedLabel}
            />
          </label>
        </div>
        {selectedLabel && <p className="mt-2 text-xs text-muted-foreground" data-testid="text-selected-files">{selectedLabel}</p>}
      </FormField>
      <FormField label={t("tasks.form.file_extensions")} hint={t("tasks.form.file_exts_hint")}>
        <TagSelect value={extensions} onChange={setExtensions} presets={PRESET_FILE_EXTENSIONS} placeholder="Add extension..." testId="input-extensions" />
      </FormField>
      {uploadError && <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive" data-testid="text-file-upload-error">{uploadError}</p>}
      <RunButton
        label={uploading ? t("tasks.form.uploading") : t("tasks.form.run")}
        submitting={submitting || uploading}
        disabled={submitting || uploading}
        onClick={runImport}
      />
      <ScheduleFromTaskButton buildTask={buildTask} disabled />
    </div>
  );
}
