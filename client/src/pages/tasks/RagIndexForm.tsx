import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { apiGet } from "@/lib/api";
import { FormField, SelectField, CheckboxField, RunButton } from "@/components/FormFields";

interface KnowledgeBaseOption {
  kb_id: string;
  name: string;
  file_count?: number;
  availability?: string;
}

export function RagIndexForm({
  onSubmit,
  submitting,
  settingsMode = false,
}: {
  onSubmit: (d: Record<string, unknown>) => void;
  submitting: boolean;
  settingsMode?: boolean;
  initialTask?: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseOption[]>([]);
  const [selectedKbId, setSelectedKbId] = useState("");
  const [forceRebuild, setForceRebuild] = useState(false);
  const [loadingKbs, setLoadingKbs] = useState(false);

  useEffect(() => {
    if (settingsMode) return;
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
  }, [settingsMode]);

  const buildTask = (): Record<string, unknown> | null => {
    if (!selectedKbId) return null;
    return {
      kb_id: selectedKbId,
      force_rebuild: forceRebuild,
    };
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.rag_desc")}</p>
      {settingsMode ? (
        <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm" data-testid="pipeline-rag-fixed-settings">
          <p>{t("tasks.pipeline.all_indexable_kbs")}</p>
          <p className="text-xs text-muted-foreground mt-1">{t("tasks.form.incremental")}</p>
        </div>
      ) : loadingKbs ? (
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
      {!settingsMode && <div className="flex flex-wrap gap-x-5 gap-y-2">
        <CheckboxField
          checked={forceRebuild}
          onChange={setForceRebuild}
          label={t("tasks.form.force_reindex")}
          testId="checkbox-rag-force-reindex"
        />
      </div>}
      <RunButton
        label={settingsMode ? t("common.save") : t("tasks.form.run")}
        submitting={submitting}
        disabled={submitting || (!settingsMode && (!selectedKbId || loadingKbs))}
        onClick={() => {
          if (settingsMode) onSubmit({});
          else {
            const task = buildTask();
            if (task) onSubmit(task);
          }
        }}
      />
    </div>
  );
}
