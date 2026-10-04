import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { TaskErrorDetails, trustedTaskIdFromSearch } from "./TaskErrors";

test("renders Issue 368 task errors", () => {
const taskId = "task_1780000000000_0123456789abcdef";
assert.equal(trustedTaskIdFromSearch(`?task_id=${taskId}`), taskId);
assert.equal(trustedTaskIdFromSearch("?task_id=external-task"), null);
assert.equal(trustedTaskIdFromSearch("?task_id=task_1_0123456789abcdef&retry=true"), null);

const markup = renderToStaticMarkup(
  <TaskErrorDetails
    task={{
      failed_items: 51,
      item_errors_truncated: true,
      item_errors: [
        {
          object_id: "file:abcdef0123456789",
          display_name: "File abcdef012345",
          stage: "catalog",
          code: "file_not_found",
          summary: "The catalog source was not found.",
          context_url: `/tasks?task_id=${taskId}`,
        },
      ],
    }}
    t={(key) => ({
      "tasks.log_failed_items": "Failed items",
      "tasks.log_item_errors_truncated": "Only the first {count} failures are shown.",
      "enum.error_stage.catalog": "Catalog stage",
      "enum.error_code.file_not_found": "File not found",
    }[key] || key)}
  />,
);

assert.match(markup, /Failed items[^0-9]*51/);
assert.match(markup, /File abcdef012345/);
assert.match(markup, /Catalog stage/);
assert.match(markup, /File not found/);
assert.doesNotMatch(markup, /file_not_found/);
assert.match(markup, /The catalog source was not found/);
assert.match(markup, /Only the first 1 failures are shown/);
assert.match(markup, new RegExp(`/tasks\\?task_id=${taskId}`));
assert.doesNotMatch(markup, /form|retry|POST/i);

console.log("Issue 368 task error UI assertions passed");
});
