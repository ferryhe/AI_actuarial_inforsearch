import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { ScheduledTasksSection } from "./ScheduledTasksSection";

const status = {
  count: 2,
  jobs: [
    {
      job_key: "configured-307",
      kind: "configured_task" as const,
      source: "Pricing Catalog",
      display_name: "Pricing Catalog",
      interval: "every 2 hours",
      last_run: null,
      next_run: "2026-09-01T12:00:00",
      managed: true,
      deletable: true,
    },
    {
      job_key: "pipeline-307",
      kind: "pipeline_baton" as const,
      source: "pipeline_baton",
      display_name: "Pipeline Baton",
      interval: "every 30 minutes",
      last_run: null,
      next_run: "2026-09-01T10:30:00",
      managed: false,
      deletable: false,
    },
  ],
};
const tasks = [
  {
    name: "Pricing Catalog",
    type: "catalog",
    interval: "every 2 hours",
    enabled: true,
    params: {},
  },
];

const readerMarkup = renderToStaticMarkup(
  <ScheduledTasksSection
    initialScheduleStatus={status}
    initialScheduledTasks={tasks}
    initialLoading={false}
    canManageScheduleOverride={false}
  />,
);
assert.match(readerMarkup, /tasks\.sched\.effective_scheduler_jobs/);
assert.match(readerMarkup, /tasks\.sched\.configured_recurring_tasks/);
assert.match(readerMarkup, /Pricing Catalog/);
assert.match(readerMarkup, /Pipeline Baton/);
assert.match(readerMarkup, /tasks\.sched\.effective/);
assert.doesNotMatch(readerMarkup, /button-add-scheduled-task/);
assert.doesNotMatch(readerMarkup, /button-reinit-scheduler/);
assert.doesNotMatch(readerMarkup, /button-edit-sched/);
assert.doesNotMatch(readerMarkup, /button-delete-sched/);
assert.doesNotMatch(readerMarkup, /button-delete-job/);

const writerMarkup = renderToStaticMarkup(
  <ScheduledTasksSection
    initialScheduleStatus={status}
    initialScheduledTasks={tasks}
    initialLoading={false}
    canManageScheduleOverride
  />,
);
assert.match(writerMarkup, /button-add-scheduled-task/);
assert.match(writerMarkup, /button-reinit-scheduler/);
assert.match(writerMarkup, /button-edit-sched-Pricing Catalog/);
assert.match(writerMarkup, /button-delete-sched-Pricing Catalog/);
assert.doesNotMatch(writerMarkup, /button-delete-job/);

console.log("Issue 307 scheduled tasks component assertions passed");
