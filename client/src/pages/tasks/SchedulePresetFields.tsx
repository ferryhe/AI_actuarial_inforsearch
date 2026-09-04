import { FormField } from "@/components/FormFields";
import { useTranslation } from "@/components/Layout";

type ScheduleFrequency = "minutes" | "hours" | "daily" | "weekly";
export type ScheduleTimezone = "UTC" | "Asia/Shanghai";

export interface SchedulePresetValue {
  frequency: ScheduleFrequency;
  quantity: string;
  time: string;
  timezone: ScheduleTimezone;
}

export const defaultSchedulePreset: SchedulePresetValue = {
  frequency: "daily",
  quantity: "1",
  time: "00:30",
  timezone: "UTC",
};

const fixedTimePattern = /^(daily|weekly) at (\d{1,2}):(\d{1,2})$/;
const canonicalTimePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

export function parseSchedulePreset(interval: string, timezone?: string): {
  value: SchedulePresetValue;
  isLegacy: boolean;
} {
  const normalized = String(interval || "").trim().toLowerCase();
  if (normalized === "daily" || normalized === "weekly") {
    return {
      value: { ...defaultSchedulePreset, frequency: normalized },
      isLegacy: true,
    };
  }
  const rollingParts = normalized.split(/\s+/);
  const rollingQuantity = rollingParts[1]?.replace(/^0+/, "");
  if (
    rollingParts.length === 3
    && rollingParts[0] === "every"
    && /^\d+$/.test(rollingParts[1])
    && rollingQuantity
    && ["minute", "minutes", "hour", "hours"].includes(rollingParts[2])
  ) {
    const frequency = rollingParts[2].startsWith("hour") ? "hours" : "minutes";
    const canonical = `every ${rollingQuantity} ${frequency}`;
    return {
      value: { ...defaultSchedulePreset, frequency, quantity: rollingQuantity },
      isLegacy: normalized !== canonical || Boolean(timezone),
    };
  }
  const fixedText = normalized.startsWith("daily at ")
    ? `daily at ${normalized.slice("daily at ".length).trim()}`
    : normalized;
  const fixed = fixedTimePattern.exec(fixedText);
  if (fixed) {
    const hour = Number(fixed[2]);
    const minute = Number(fixed[3]);
    if (hour <= 23 && minute <= 59) {
      const time = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
      const supportedTimezone = timezone === "Asia/Shanghai" ? "Asia/Shanghai" : "UTC";
      return {
        value: {
          ...defaultSchedulePreset,
          frequency: fixed[1] as ScheduleFrequency,
          time,
          timezone: supportedTimezone,
        },
        isLegacy: normalized !== `${fixed[1]} at ${time}` || timezone !== supportedTimezone,
      };
    }
  }
  return { value: { ...defaultSchedulePreset }, isLegacy: true };
}

export function buildScheduleFields(value: SchedulePresetValue): {
  interval: string;
  timezone?: ScheduleTimezone;
} {
  if (value.frequency === "minutes" || value.frequency === "hours") {
    return { interval: `every ${value.quantity.trim()} ${value.frequency}` };
  }
  return {
    interval: `${value.frequency} at ${value.time}`,
    timezone: value.timezone,
  };
}

export function weeklySummaryPreset(value: SchedulePresetValue): SchedulePresetValue {
  return { ...value, frequency: "weekly", timezone: "UTC" };
}

export function isSchedulePresetComplete(value: SchedulePresetValue): boolean {
  if (value.frequency === "minutes" || value.frequency === "hours") {
    return /^[1-9]\d*$/.test(value.quantity.trim());
  }
  return canonicalTimePattern.test(value.time);
}

export function shanghaiEquivalent(utcTime: string): { dayKey: string; time: string } | null {
  if (!canonicalTimePattern.test(utcTime)) return null;
  const [hourText, minuteText] = utcTime.split(":");
  const totalMinutes = Number(hourText) * 60 + Number(minuteText) + 8 * 60;
  const dayKey = totalMinutes >= 24 * 60 ? "tuesday" : "monday";
  const minutesInDay = totalMinutes % (24 * 60);
  const hour = Math.floor(minutesInDay / 60);
  const minute = minutesInDay % 60;
  return {
    dayKey,
    time: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
  };
}

export function SchedulePresetFields({
  value,
  onChange,
  taskType,
  testIdPrefix,
  legacy = false,
  legacySummaryReadOnly = false,
  legacyProcessLocal = false,
  onMigrateLegacySummary,
}: {
  value: SchedulePresetValue;
  onChange: (value: SchedulePresetValue) => void;
  taskType: string;
  testIdPrefix: string;
  legacy?: boolean;
  legacySummaryReadOnly?: boolean;
  legacyProcessLocal?: boolean;
  onMigrateLegacySummary?: () => void;
}) {
  const { t } = useTranslation();
  const isWeeklySummary = taskType === "weekly_summary";
  const current = isWeeklySummary && !legacySummaryReadOnly
    ? weeklySummaryPreset(value)
    : value;
  const isRolling = current.frequency === "minutes" || current.frequency === "hours";
  const frequencyOptions = isWeeklySummary && !legacySummaryReadOnly
    ? [{ value: "weekly", label: t("tasks.sched.frequency.weekly") }]
    : [
      { value: "minutes", label: t("tasks.sched.frequency.minutes") },
      { value: "hours", label: t("tasks.sched.frequency.hours") },
      { value: "daily", label: t("tasks.sched.frequency.daily") },
      { value: "weekly", label: t("tasks.sched.frequency.weekly") },
    ];
  const equivalent = shanghaiEquivalent(current.time);

  return (
    <div className="space-y-3" data-testid={`schedule-preset-${testIdPrefix}`}>
      {legacy && !legacySummaryReadOnly && (
        <p className="text-[11px] rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-700 dark:text-amber-300">
          {t("tasks.sched.legacy_schedule_hint")}
        </p>
      )}
      {legacySummaryReadOnly && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-700 dark:text-amber-300">
          <p className="text-[11px]">{t("tasks.sched.legacy_weekly_summary_migration")}</p>
          <button
            type="button"
            onClick={onMigrateLegacySummary}
            className="text-xs px-2.5 py-1 rounded border border-amber-500/40 hover:bg-amber-500/10"
            data-testid={`button-${testIdPrefix}-migrate-weekly-utc`}
          >
            {t("tasks.sched.convert_weekly_summary_utc")}
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField label={t("tasks.sched.frequency")}>
          <select
            value={current.frequency}
            onChange={(event) => onChange({ ...current, frequency: event.target.value as ScheduleFrequency })}
            disabled={isWeeklySummary || legacySummaryReadOnly}
            className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-70"
            data-testid={`select-${testIdPrefix}-frequency`}
          >
            {frequencyOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </FormField>
        {isRolling ? (
          <FormField label={t("tasks.sched.quantity")}>
            <input
              type="number"
              min={1}
              step={1}
              value={current.quantity}
              onChange={(event) => onChange({ ...current, quantity: event.target.value })}
              disabled={legacySummaryReadOnly}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
              data-testid={`input-${testIdPrefix}-quantity`}
            />
          </FormField>
        ) : (
          <FormField label={t("tasks.sched.run_time")}>
            <input
              type="time"
              step={60}
              value={current.time}
              onChange={(event) => onChange({ ...current, time: event.target.value })}
              disabled={legacySummaryReadOnly}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
              data-testid={`input-${testIdPrefix}-time`}
            />
          </FormField>
        )}
      </div>
      {!isRolling && (
        <FormField label={t("tasks.sched.timezone")}>
          {legacySummaryReadOnly ? (
            <div
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-muted/40 text-muted-foreground"
              data-testid={`text-${testIdPrefix}-timezone`}
            >
              {legacyProcessLocal
                ? t("tasks.sched.timezone.process_local")
                : t(current.timezone === "Asia/Shanghai"
                  ? "tasks.sched.timezone.shanghai"
                  : "tasks.sched.timezone.utc")}
            </div>
          ) : (
            <select
              value={legacyProcessLocal ? "process-local" : current.timezone}
              onChange={(event) => onChange({ ...current, timezone: event.target.value as ScheduleTimezone })}
              disabled={isWeeklySummary}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-70"
              data-testid={`select-${testIdPrefix}-timezone`}
            >
              {legacyProcessLocal && (
                <option value="process-local" disabled>{t("tasks.sched.timezone.process_local")}</option>
              )}
              <option value="UTC">{t("tasks.sched.timezone.utc")}</option>
              {!isWeeklySummary && (
                <option value="Asia/Shanghai">{t("tasks.sched.timezone.shanghai")}</option>
              )}
            </select>
          )}
        </FormField>
      )}
      {isWeeklySummary && !legacySummaryReadOnly && (
        <p className="text-[11px] text-muted-foreground" data-testid={`text-${testIdPrefix}-weekly-summary-lock`}>
          {t("tasks.sched.weekly_summary_utc_lock")}
          {equivalent && <> {t("tasks.sched.shanghai_equivalent")
            .replace("{day}", t(`tasks.sched.weekday.${equivalent.dayKey}`))
            .replace("{time}", equivalent.time)}</>}
        </p>
      )}
    </div>
  );
}
