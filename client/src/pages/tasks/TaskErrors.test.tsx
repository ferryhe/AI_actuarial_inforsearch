import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { TaskErrorDetails, trustedTaskIdFromSearch } from "./TaskErrors";

test("renders only authorized and stage-appropriate task error links", () => {
const taskId = "task_1780000000000_0123456789abcdef";
assert.equal(trustedTaskIdFromSearch(`?task_id=${taskId}`), taskId);
assert.equal(trustedTaskIdFromSearch("?task_id=external-task"), null);
assert.equal(trustedTaskIdFromSearch("?task_id=task_1_0123456789abcdef&retry=true"), null);
const fileId = "793";

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
          file_id: fileId,
          context_url: `/file-detail?file_id=${fileId}`,
        },
        {
          object_id: "file:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
          display_name: "Mismatched file ID",
          stage: "catalog",
          code: "catalog_failed",
          summary: "The catalog source failed.",
          file_id: fileId,
          context_url: "/file-detail?file_id=794",
        },
        {
          object_id: "chunk:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
          display_name: "Chunk abcdef012345",
          stage: "embedding",
          code: "provider_error",
          summary: "Embedding provider failed.",
          context_url: `/tasks?task_id=${taskId}`,
        },
      ],
    }}
    canReadFiles
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
assert.match(markup, /href="\/file-detail\?file_id=793"/);
assert.match(markup, new RegExp(`/tasks\\?task_id=${taskId}`));
assert.match(markup, /Mismatched file ID/);
assert.doesNotMatch(markup, /form|retry|POST/i);

const noFilePermission = renderToStaticMarkup(
  <TaskErrorDetails
    task={{
      item_errors: [{
        object_id: "file:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        display_name: "File abcdef012345",
        stage: "catalog",
        code: "catalog_failed",
        summary: "Catalog failed.",
        file_id: fileId,
        context_url: `/file-detail?file_id=${fileId}`,
      }],
    }}
    t={(key) => key}
  />,
);
assert.doesNotMatch(noFilePermission, /href=/);

console.log("Task error link assertions passed");
});
