import { useEffect, useState } from "react";
import { useTranslation } from "@/components/Layout";
import { useTaskOptions } from "@/hooks/use-task-options";
import { apiGet } from "@/lib/api";
import { FormField, InputField, SelectField, CheckboxField, RunButton } from "@/components/FormFields";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

interface KnowledgeBaseOption {
  kb_id: string;
  name?: string;
  file_count?: number;
}

function parseUrls(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter((item, index, all) => Boolean(item) && all.indexOf(item) === index);
}

export function FullPipelineForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const { categories: dynamicCategories } = useTaskOptions();
  const [sourceType, setSourceType] = useState("scheduled");
  const [site, setSite] = useState("");
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [urlsInput, setUrlsInput] = useState("");
  const [category, setCategory] = useState("");
  const [scanCount, setScanCount] = useState("50");
  const [startIndex, setStartIndex] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [overwriteExisting, setOverwriteExisting] = useState(false);
  const [chunkSize, setChunkSize] = useState("800");
  const [chunkOverlap, setChunkOverlap] = useState("100");
  const [runRagIndexing, setRunRagIndexing] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseOption[]>([]);
  const [selectedKbId, setSelectedKbId] = useState("");

  useEffect(() => {
    apiGet<{ knowledge_bases?: KnowledgeBaseOption[]; data?: { knowledge_bases?: KnowledgeBaseOption[] } }>("/api/rag/knowledge-bases")
      .then((res) => {
        const kbs = res.knowledge_bases || res.data?.knowledge_bases || [];
        setKnowledgeBases(kbs);
        setSelectedKbId((current) => current || kbs[0]?.kb_id || "");
      })
      .catch(() => {
        setKnowledgeBases([]);
        setSelectedKbId("");
      });
  }, []);

  const categoryOptions = [
    { value: "", label: t("tasks.form.scope_all") },
    ...dynamicCategories.map((c) => ({ value: c, label: c })),
  ];

  const buildTask = (): Record<string, unknown> | null => {
    const urls = parseUrls(urlsInput);
    if (sourceType === "quick_check" && !url.trim()) return null;
    if (sourceType === "url" && urls.length === 0) return null;
    if (sourceType === "search" && !query.trim()) return null;
    if (runRagIndexing && !selectedKbId) return null;
    return {
      type: "full_pipeline",
      name: "Full Pipeline",
      source_collection_type: sourceType,
      site: site.trim() || undefined,
      query: sourceType === "search" ? query.trim() : undefined,
      url: sourceType === "quick_check" ? url.trim() : undefined,
      urls: sourceType === "url" ? urls : undefined,
      category: category.trim() || undefined,
      scope_mode: category.trim() ? "category" : "index",
      scan_count: parseInt(scanCount, 10) || 50,
      scan_start_index: startIndex ? parseInt(startIndex, 10) : undefined,
      skip_existing: skipExisting,
      overwrite_existing: overwriteExisting,
      chunk_size: parseInt(chunkSize, 10) || 800,
      chunk_overlap: parseInt(chunkOverlap, 10) || 100,
      run_rag_indexing: runRagIndexing,
      kb_id: runRagIndexing ? selectedKbId : undefined,
    };
  };

  const formDisabled = submitting
    || (sourceType === "quick_check" && !url.trim())
    || (sourceType === "url" && parseUrls(urlsInput).length === 0)
    || (sourceType === "search" && !query.trim())
    || (runRagIndexing && !selectedKbId);

  return (
    <div className="space-y-4" data-testid="form-full-pipeline">
      <p className="text-sm text-muted-foreground">{t("tasks.form.full_pipeline_desc")}</p>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.source_collection") }>
          <SelectField
            value={sourceType}
            onChange={setSourceType}
            testId="select-full-source"
            options={[
              { value: "scheduled", label: t("tasks.type.scheduled") },
              { value: "quick_check", label: t("tasks.type.web_crawl") },
              { value: "url", label: t("tasks.type.adhoc_url") },
              { value: "search", label: t("tasks.type.web_search") },
            ]}
          />
        </FormField>
        <FormField label={t("tasks.sched.param.site")} hint={t("tasks.form.full_pipeline_site_hint")}>
          <InputField value={site} onChange={setSite} placeholder="SOA" testId="input-full-site" />
        </FormField>
      </div>
      {sourceType === "quick_check" && (
        <FormField label={t("tasks.sched.param.url")}>
          <InputField value={url} onChange={setUrl} placeholder="https://example.com" testId="input-full-url" />
        </FormField>
      )}
      {sourceType === "search" && (
        <FormField label={t("tasks.form.search_query")}>
          <InputField value={query} onChange={setQuery} placeholder={t("tasks.form.search_query_placeholder")} testId="input-full-query" />
        </FormField>
      )}
      {sourceType === "url" && (
        <FormField label={t("tasks.form.urls")}>
          <textarea
            value={urlsInput}
            onChange={(e) => setUrlsInput(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-border bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder={t("tasks.form.urls_placeholder")}
            data-testid="input-full-urls"
          />
        </FormField>
      )}
      <div className="grid grid-cols-3 gap-3">
        <FormField label={t("tasks.form.category")}>
          <SelectField value={category} onChange={setCategory} options={categoryOptions} testId="select-full-category" />
        </FormField>
        <FormField label={t("tasks.form.scan_count")}>
          <InputField value={scanCount} onChange={setScanCount} placeholder="50" type="number" testId="input-full-scan-count" />
        </FormField>
        <FormField label={t("tasks.form.start_index")}>
          <InputField value={startIndex} onChange={setStartIndex} placeholder="1" type="number" testId="input-full-start-index" />
        </FormField>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField checked={skipExisting} onChange={(v) => { setSkipExisting(v); if (v) setOverwriteExisting(false); }}
          label={t("tasks.form.skip_existing")} testId="checkbox-full-skip" />
        <CheckboxField checked={overwriteExisting} onChange={(v) => { setOverwriteExisting(v); if (v) setSkipExisting(false); }}
          label={t("tasks.form.overwrite_existing")} testId="checkbox-full-overwrite" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t("tasks.form.chunk_size")}>
          <InputField value={chunkSize} onChange={setChunkSize} placeholder="800" type="number" testId="input-full-chunk-size" />
        </FormField>
        <FormField label={t("tasks.form.chunk_overlap")}>
          <InputField value={chunkOverlap} onChange={setChunkOverlap} placeholder="100" type="number" testId="input-full-chunk-overlap" />
        </FormField>
      </div>
      <div className="border-t border-border pt-3 space-y-3">
        <CheckboxField checked={runRagIndexing} onChange={setRunRagIndexing}
          label={t("tasks.form.run_rag_indexing")} testId="checkbox-full-rag" />
        {runRagIndexing && (
          <FormField label={t("tasks.form.knowledge_base")}>
            <SelectField
              value={selectedKbId}
              onChange={setSelectedKbId}
              testId="select-full-kb"
              options={knowledgeBases.length === 0
                ? [{ value: "", label: t("tasks.form.no_knowledge_bases") }]
                : knowledgeBases.map((kb) => ({
                  value: kb.kb_id,
                  label: `${kb.name || kb.kb_id}${kb.file_count != null ? ` (${kb.file_count})` : ""}`,
                }))}
            />
          </FormField>
        )}
      </div>
      <RunButton label={t("tasks.form.run")} submitting={submitting} disabled={formDisabled}
        onClick={() => {
          const task = buildTask();
          if (task) onSubmit(task);
        }} />
      <ScheduleFromTaskButton buildTask={buildTask} disabled={formDisabled} />
    </div>
  );
}
