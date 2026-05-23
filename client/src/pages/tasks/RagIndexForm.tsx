import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";
import { FormField, SelectField, CheckboxField, RunButton } from "@/components/FormFields";
import { ScheduleFromTaskButton } from "./ScheduleFromTaskButton";

interface KnowledgeBaseOption {
  kb_id: string;
  name: string;
  file_count?: number;
  availability?: string;
}

export function RagIndexForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseOption[]>([]);
  const [selectedKbId, setSelectedKbId] = useState("");
  const [incremental, setIncremental] = useState(true);
  const [forceReindex, setForceReindex] = useState(false);
  const [loadingKbs, setLoadingKbs] = useState(false);
  const [fileUrlsInput, setFileUrlsInput] = useState("");

  useEffect(() => {
    setLoadingKbs(true);
    apiGet<{ knowledge_bases?: KnowledgeBaseOption[]; data?: { knowledge_bases?: KnowledgeBaseOption[] } }>("/api/rag/knowledge-bases")
      .then((res) => {
        const kbs = res.knowledge_bases || res.data?.knowledge_bases || [];
        setKnowledgeBases(kbs);
        setSelectedKbId((current) => current || kbs[0]?.kb_id || "");
      })
      .catch(() => {
        setKnowledgeBases([]);
        setSelectedKbId("");
      })
      .finally(() => setLoadingKbs(false));
  }, []);

  const selectedKb = knowledgeBases.find((kb) => kb.kb_id === selectedKbId);

  function parseFileUrls(): string[] {
    return fileUrlsInput
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter((item, index, all) => Boolean(item) && all.indexOf(item) === index);
  }

  const buildTask = (): Record<string, unknown> | null => {
    if (!selectedKbId) return null;
    const fileUrls = parseFileUrls();
    return {
      type: "rag_indexing",
      name: selectedKb ? `RAG Indexing: ${selectedKb.name || selectedKb.kb_id}` : "RAG Indexing",
      kb_id: selectedKbId,
      file_urls: fileUrls.length > 0 ? fileUrls : undefined,
      incremental,
      force_reindex: forceReindex,
    };
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.rag_desc")}</p>
      {loadingKbs ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          {t("tasks.form.loading_kbs")}
        </div>
      ) : knowledgeBases.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="text-no-rag-kbs">{t("tasks.form.no_kbs")}</p>
      ) : (
        <FormField label={t("tasks.form.knowledge_base")}>
          <SelectField
            value={selectedKbId}
            onChange={setSelectedKbId}
            testId="select-rag-kb"
            options={knowledgeBases.map((kb) => ({
              value: kb.kb_id,
              label: `${kb.name || kb.kb_id}${kb.file_count != null ? ` (${kb.file_count})` : ""}`,
            }))}
          />
        </FormField>
      )}
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField
          checked={incremental}
          onChange={(value) => {
            setIncremental(value);
            if (value) setForceReindex(false);
          }}
          label={t("tasks.form.incremental")}
          testId="checkbox-rag-incremental"
        />
        <CheckboxField
          checked={forceReindex}
          onChange={(value) => {
            setForceReindex(value);
            if (value) setIncremental(false);
          }}
          label={t("tasks.form.force_reindex")}
          testId="checkbox-rag-force-reindex"
        />
      </div>
      <FormField label={t("tasks.form.file_urls_optional")} hint={t("tasks.form.file_urls_hint")}>
        <textarea
          value={fileUrlsInput}
          onChange={(e) => setFileUrlsInput(e.target.value)}
          rows={4}
          className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-border bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="https://example.com/report.pdf"
          data-testid="input-rag-file-urls"
        />
      </FormField>
      <RunButton
        label={t("tasks.form.run")}
        submitting={submitting}
        disabled={submitting || !selectedKbId || loadingKbs}
        onClick={() => {
          const task = buildTask();
          if (task) onSubmit(task);
        }}
      />
      <ScheduleFromTaskButton buildTask={buildTask} disabled={!selectedKbId || loadingKbs} />
    </div>
  );
}
