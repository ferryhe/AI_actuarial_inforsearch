import { useState } from "react";
import { useTranslation } from "@/components/Layout";
import { FormField, SelectField, RunButton } from "@/components/FormFields";

export function RecategoryForm({ onSubmit, submitting }: { onSubmit: (d: Record<string, unknown>) => void; submitting: boolean }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState("plan");

  const buildTask = (): Record<string, unknown> => ({
    type: "recategory",
    name: "Re-categorize",
    mode,
  });

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("tasks.form.recategory_desc")}</p>
      <FormField label={t("tasks.form.mode")}>
        <SelectField
          value={mode}
          onChange={setMode}
          testId="select-recategory-mode"
          options={[
            { value: "plan", label: t("tasks.form.mode_plan") },
            { value: "apply", label: t("tasks.form.mode_apply") },
          ]}
        />
      </FormField>
      <RunButton
        label={t("tasks.form.run")}
        submitting={submitting}
        disabled={submitting}
        onClick={() => onSubmit(buildTask())}
      />
    </div>
  );
}
