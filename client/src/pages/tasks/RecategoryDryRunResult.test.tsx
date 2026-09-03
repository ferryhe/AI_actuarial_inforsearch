import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { RecategoryDryRunResult } from "./RecategoryDryRunResult";
import type { HistoryTask } from "./Tasks.types";

const translations: Record<string, string> = {
  "tasks.recategory_result.title": "Dry Run Result",
  "tasks.recategory_result.needed": "Recategorization is needed",
  "tasks.recategory_result.not_needed": "Recategorization is not needed",
  "tasks.recategory_result.removed": "Categories to remove",
  "tasks.recategory_result.added": "Categories to add",
  "tasks.recategory_result.article_count": "{count} articles",
  "tasks.recategory_result.no_changes": "No category changes detected",
  "tasks.recategory_result.unavailable": "Dry run completed, but result details are unavailable",
};

const t = (key: string) => translations[key] || key;

function render(task: HistoryTask): string {
  return renderToStaticMarkup(<RecategoryDryRunResult task={task} t={t} />);
}

const changed = render({
  type: "recategory",
  status: "completed",
  metadata: {
    dry_run: true,
    needs_recategory: true,
    removed_categories: ["Old category", "A very long removed category name that must wrap on narrow screens"],
    added_categories: ["New category"],
    removed_impact: {
      "Old category": 12,
      "A very long removed category name that must wrap on narrow screens": 3,
    },
    added_impact: { "New category": 8 },
  },
});
assert.match(changed, /data-testid="recategory-dry-run-result"/);
assert.match(changed, /Dry Run Result/);
assert.match(changed, /Recategorization is needed/);
assert.match(changed, /Old category/);
assert.match(changed, /12 articles/);
assert.match(changed, /New category/);
assert.match(changed, /8 articles/);
assert.match(changed, /break-words/);
assert.match(changed, /overflow-y-auto/);
assert.doesNotMatch(changed, /button/i);

const unchanged = render({
  type: "recategory",
  status: "completed",
  metadata: {
    dry_run: true,
    needs_recategory: false,
    removed_categories: [],
    added_categories: [],
    removed_impact: {},
    added_impact: {},
  },
});
assert.match(unchanged, /Recategorization is not needed/);
assert.match(unchanged, /No category changes detected/);
assert.doesNotMatch(unchanged, /Categories to (?:remove|add)/);

const incomplete = render({
  type: "recategory",
  status: "completed",
  metadata: {
    dry_run: true,
    needs_recategory: true,
    removed_categories: ["Safe category", null, "", 42],
    removed_impact: { "Safe category": "not-a-count" },
    added_categories: "wrong-shape",
  },
});
assert.match(incomplete, /Safe category/);
assert.doesNotMatch(incomplete, /not-a-count|null|undefined|42 articles/);

const unavailable = render({
  type: "recategory",
  status: "completed",
  metadata: { dry_run: true },
});
assert.match(unavailable, /Dry run completed, but result details are unavailable/);
assert.doesNotMatch(unavailable, /null|undefined/);

for (const ineligible of [
  { type: "catalog", status: "completed", metadata: changed },
  { type: "recategory", status: "running", metadata: { dry_run: true } },
  { type: "recategory", status: "completed", metadata: { dry_run: false } },
  { type: "recategory", status: "completed", metadata: { dry_run: "true" } },
  { type: "recategory", status: "completed" },
  { type: "recategory", status: "completed", metadata: [] },
  { type: "recategory", status: "completed", metadata: "legacy" },
] satisfies HistoryTask[]) {
  assert.equal(render(ineligible), "");
}

console.log("Issue 334 recategory dry-run component assertions passed");
