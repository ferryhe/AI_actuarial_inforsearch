import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import {
  SchedulePresetFields,
  buildScheduleFields,
  isSchedulePresetComplete,
  parseSchedulePreset,
  shanghaiEquivalent,
  weeklySummaryPreset,
} from "./SchedulePresetFields";

const noop = () => undefined;

const minutesMarkup = renderToStaticMarkup(
  <SchedulePresetFields
    value={{ frequency: "minutes", quantity: "15", time: "00:30", timezone: "UTC" }}
    onChange={noop}
    taskType="catalog"
    testIdPrefix="test"
  />,
);
assert.match(minutesMarkup, /select-test-frequency/);
assert.match(minutesMarkup, /input-test-quantity/);
assert.doesNotMatch(minutesMarkup, /input-test-time/);
assert.doesNotMatch(minutesMarkup, /select-test-timezone/);

const dailyMarkup = renderToStaticMarkup(
  <SchedulePresetFields
    value={{ frequency: "daily", quantity: "1", time: "02:05", timezone: "Asia/Shanghai" }}
    onChange={noop}
    taskType="catalog"
    testIdPrefix="test"
  />,
);
assert.doesNotMatch(dailyMarkup, /input-test-quantity/);
assert.match(dailyMarkup, /input-test-time/);
assert.match(dailyMarkup, /select-test-timezone/);
assert.match(dailyMarkup, /tasks\.sched\.timezone\.shanghai/);

for (const legacyFixed of [
  { frequency: "daily" as const, time: "00:30" },
  { frequency: "weekly" as const, time: "00:30" },
  { frequency: "daily" as const, time: "02:03" },
]) {
  const markup = renderToStaticMarkup(
    <SchedulePresetFields
      value={{ ...legacyFixed, quantity: "1", timezone: "UTC" }}
      onChange={noop}
      taskType="catalog"
      testIdPrefix={`legacy-${legacyFixed.frequency}-${legacyFixed.time}`}
      legacy
      legacyProcessLocal
    />,
  );
  assert.match(markup, /value="process-local" disabled="" selected=""/);
  assert.match(markup, /tasks\.sched\.timezone\.process_local/);
  assert.match(markup, /tasks\.sched\.timezone\.utc/);
  assert.match(markup, /tasks\.sched\.timezone\.shanghai/);
}

const legacyRollingMarkup = renderToStaticMarkup(
  <SchedulePresetFields
    value={{ frequency: "hours", quantity: "6", time: "00:30", timezone: "UTC" }}
    onChange={noop}
    taskType="catalog"
    testIdPrefix="legacy-rolling"
    legacy
  />,
);
assert.match(legacyRollingMarkup, /tasks\.sched\.legacy_schedule_hint/);
assert.doesNotMatch(legacyRollingMarkup, /select-legacy-rolling-timezone/);

const summaryMarkup = renderToStaticMarkup(
  <SchedulePresetFields
    value={weeklySummaryPreset({ frequency: "daily", quantity: "1", time: "20:30", timezone: "Asia/Shanghai" })}
    onChange={noop}
    taskType="weekly_summary"
    testIdPrefix="summary"
  />,
);
assert.match(summaryMarkup, /select-summary-frequency/);
assert.match(summaryMarkup, /disabled=""/);
assert.match(summaryMarkup, /tasks\.sched\.weekly_summary_utc_lock/);
assert.match(summaryMarkup, /value="UTC" selected=""/);
assert.doesNotMatch(summaryMarkup, /tasks\.sched\.timezone\.process_local/);
assert.doesNotMatch(summaryMarkup, /button-summary-migrate-weekly-utc/);
assert.deepEqual(shanghaiEquivalent("20:30"), { dayKey: "tuesday", time: "04:30" });

const legacyDailySummaryMarkup = renderToStaticMarkup(
  <SchedulePresetFields
    value={{ frequency: "daily", quantity: "1", time: "02:03", timezone: "UTC" }}
    onChange={noop}
    taskType="weekly_summary"
    testIdPrefix="legacy-daily-summary"
    legacy
    legacySummaryReadOnly
    legacyProcessLocal
    onMigrateLegacySummary={noop}
  />,
);
assert.match(legacyDailySummaryMarkup, /value="daily" selected=""/);
assert.match(legacyDailySummaryMarkup, /value="02:03"/);
assert.match(legacyDailySummaryMarkup, /tasks\.sched\.timezone\.process_local/);
assert.match(legacyDailySummaryMarkup, /tasks\.sched\.legacy_weekly_summary_migration/);
assert.match(legacyDailySummaryMarkup, /button-legacy-daily-summary-migrate-weekly-utc/);
assert.doesNotMatch(legacyDailySummaryMarkup, /tasks\.sched\.weekly_summary_utc_lock/);

const legacyRollingSummaryMarkup = renderToStaticMarkup(
  <SchedulePresetFields
    value={{ frequency: "hours", quantity: "6", time: "00:30", timezone: "UTC" }}
    onChange={noop}
    taskType="weekly_summary"
    testIdPrefix="legacy-rolling-summary"
    legacy
    legacySummaryReadOnly
    onMigrateLegacySummary={noop}
  />,
);
assert.match(legacyRollingSummaryMarkup, /value="hours" selected=""/);
assert.match(legacyRollingSummaryMarkup, /value="6"/);
assert.match(legacyRollingSummaryMarkup, /tasks\.sched\.legacy_weekly_summary_migration/);
assert.match(legacyRollingSummaryMarkup, /button-legacy-rolling-summary-migrate-weekly-utc/);
assert.doesNotMatch(legacyRollingSummaryMarkup, /tasks\.sched\.timezone\.process_local/);
assert.doesNotMatch(legacyRollingSummaryMarkup, /select-legacy-rolling-summary-timezone/);

for (const invalidTime of ["", "2:30", "24:00", "12:60", "invalid"]) {
  const incompleteSummary = weeklySummaryPreset({
    frequency: "weekly",
    quantity: "1",
    time: invalidTime,
    timezone: "UTC",
  });
  const incompleteMarkup = renderToStaticMarkup(
    <SchedulePresetFields
      value={incompleteSummary}
      onChange={noop}
      taskType="weekly_summary"
      testIdPrefix="incomplete-summary"
    />,
  );
  assert.equal(isSchedulePresetComplete(incompleteSummary), false);
  assert.equal(shanghaiEquivalent(invalidTime), null);
  assert.doesNotMatch(incompleteMarkup, /NaN/);
  assert.doesNotMatch(incompleteMarkup, /tasks\.sched\.shanghai_equivalent/);
}

assert.deepEqual(buildScheduleFields({ frequency: "minutes", quantity: "30", time: "00:30", timezone: "UTC" }), {
  interval: "every 30 minutes",
});
assert.deepEqual(buildScheduleFields({ frequency: "weekly", quantity: "1", time: "08:45", timezone: "Asia/Shanghai" }), {
  interval: "weekly at 08:45",
  timezone: "Asia/Shanghai",
});
assert.deepEqual(buildScheduleFields({ frequency: "daily", quantity: "1", time: "00:30", timezone: "UTC" }), {
  interval: "daily at 00:30",
  timezone: "UTC",
});

const legacy = parseSchedulePreset("weekly", undefined);
assert.equal(legacy.isLegacy, true);
assert.deepEqual(legacy.value, { frequency: "weekly", quantity: "1", time: "00:30", timezone: "UTC" });
const canonical = parseSchedulePreset("daily at 02:05", "UTC");
assert.equal(canonical.isLegacy, false);
assert.deepEqual(buildScheduleFields(canonical.value), { interval: "daily at 02:05", timezone: "UTC" });
for (const legacySchedule of [
  {
    interval: "every 06 hours",
    value: { frequency: "hours", quantity: "6", time: "00:30", timezone: "UTC" },
    canonical: { interval: "every 6 hours" },
  },
  {
    interval: "every  6 hours",
    value: { frequency: "hours", quantity: "6", time: "00:30", timezone: "UTC" },
    canonical: { interval: "every 6 hours" },
  },
  {
    interval: "daily at  2:03",
    value: { frequency: "daily", quantity: "1", time: "02:03", timezone: "UTC" },
    canonical: { interval: "daily at 02:03", timezone: "UTC" as const },
  },
]) {
  const parsed = parseSchedulePreset(legacySchedule.interval);
  assert.equal(parsed.isLegacy, true);
  assert.deepEqual(parsed.value, legacySchedule.value);
  assert.deepEqual(buildScheduleFields(parsed.value), legacySchedule.canonical);
}
for (const expected of [
  { interval: "every 3 minutes" },
  { interval: "every 4 hours" },
  { interval: "daily at 23:59", timezone: "UTC" as const },
  { interval: "weekly at 00:30", timezone: "Asia/Shanghai" as const },
]) {
  const parsed = parseSchedulePreset(expected.interval, expected.timezone);
  assert.equal(parsed.isLegacy, false);
  assert.deepEqual(buildScheduleFields(parsed.value), expected);
}

console.log("Issue 312 schedule preset component assertions passed");
