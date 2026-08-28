import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { TaskTable } from "./TaskTable";
import type { HistoryTask } from "./Tasks.types";

function renderMetrics(task: HistoryTask): string {
  return renderToStaticMarkup(<TaskTable historyTasks={[task]} onViewLog={() => undefined} />);
}

function assertTableItemCount(markup: string, expected: number): void {
  const itemCell = markup.match(
    /<div class="flex items-center gap-2"><span class="text-xs text-muted-foreground hidden md:block">(\d+)<\/span><\/div><\/div>/,
  );
  assert.ok(itemCell, "TaskTable Items cell was not found");
  assert.equal(Number(itemCell[1]), expected);
}

const acquisition = renderMetrics({
  type: "web_search",
  items_processed: 4,
  items_downloaded: 3,
  items_skipped: 1,
});
assert.match(acquisition, /tasks\.stats\.downloaded[^0-9]*3/);
assert.match(acquisition, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(acquisition, /tasks\.stats\.processed/);

const activeAcquisition = renderMetrics({
  type: "web_search",
  status: "running",
  items_processed: 5,
  items_downloaded: 0,
  items_skipped: 1,
});
assert.match(activeAcquisition, /tasks\.stats\.processed[^0-9]*5/);
assert.match(activeAcquisition, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(activeAcquisition, /tasks\.stats\.downloaded/);

for (const type of ["file", "file_import"] as const) {
  const localImport = renderMetrics({
    type,
    items_processed: 4,
    items_downloaded: 3,
    items_skipped: 1,
  });
  assertTableItemCount(localImport, 3);
  assert.match(localImport, /tasks\.stats\.processed[^0-9]*3/);
  assert.match(localImport, /tasks\.stats\.skipped[^0-9]*1/);
  assert.doesNotMatch(localImport, /tasks\.stats\.downloaded/);

  const activeLocalImport = renderMetrics({
    type,
    status: "running",
    items_processed: 5,
    items_downloaded: 0,
    items_skipped: 1,
  });
  assert.match(activeLocalImport, /tasks\.stats\.processed[^0-9]*5/);
  assert.match(activeLocalImport, /tasks\.stats\.skipped[^0-9]*1/);
  assert.doesNotMatch(activeLocalImport, /tasks\.stats\.downloaded/);
}

const markdown = renderMetrics({
  type: "markdown_conversion",
  items_downloaded: 2,
  items_skipped: 1,
  result: { files: [{ status: "ready" }, { status: "ready" }, { status: "ready" }] },
});
assert.match(markdown, /tasks\.stats\.converted[^0-9]*2/);
assert.match(markdown, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(markdown, /tasks\.stats\.downloaded/);

const legacyMarkdown = renderMetrics({
  type: "markdown_conversion",
  items_processed: 4,
});
assert.match(legacyMarkdown, /tasks\.stats\.converted[^0-9]*4/);

const zeroMarkdown = renderMetrics({
  type: "markdown_conversion",
  items_processed: 4,
  items_downloaded: 0,
});
assert.match(zeroMarkdown, /tasks\.stats\.converted[^0-9]*0/);
assert.doesNotMatch(zeroMarkdown, /tasks\.stats\.converted[^0-9]*4/);

const activeMarkdown = renderMetrics({
  type: "markdown_conversion",
  status: "running",
  items_processed: 5,
  items_downloaded: 0,
  items_skipped: 1,
});
assert.match(activeMarkdown, /tasks\.stats\.processed[^0-9]*5/);
assert.match(activeMarkdown, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(activeMarkdown, /tasks\.stats\.(?:converted|downloaded)/);

const chunk = renderMetrics({
  type: "chunk_generation",
  items_downloaded: 1,
  result: {
    chunk_sets: [
      { chunk_count: 3, reused_existing: false },
      { chunk_count: 2, reused_existing: true },
    ],
  },
});
assert.match(chunk, /tasks\.stats\.chunk_sets[^0-9]*2/);
assert.match(chunk, /tasks\.stats\.chunks[^0-9]*5/);
assert.match(chunk, /tasks\.stats\.reused[^0-9]*1/);
assert.doesNotMatch(chunk, /tasks\.stats\.downloaded/);

const legacyChunk = renderMetrics({
  type: "chunk_generation",
  status: "running",
  items_processed: 5,
  items_downloaded: 0,
  items_skipped: 1,
});
assert.match(legacyChunk, /tasks\.stats\.processed[^0-9]*5/);
assert.match(legacyChunk, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(legacyChunk, /tasks\.stats\.(?:chunk_sets|chunks|reused|downloaded)/);

const legacyChunkWithoutProgress = renderMetrics({
  type: "chunk_generation",
  status: "completed",
  items_processed: 7,
  items_downloaded: 2,
});
assert.match(legacyChunkWithoutProgress, /tasks\.stats\.processed[^0-9]*2/);

const zeroChunk = renderMetrics({
  type: "chunk_generation",
  items_processed: 7,
  items_downloaded: 2,
  result: { chunk_sets: [] },
});
assertTableItemCount(zeroChunk, 0);
assert.match(zeroChunk, /tasks\.stats\.chunk_sets[^0-9]*0/);
assert.doesNotMatch(zeroChunk, /tasks\.stats\.(?:processed|downloaded)/);

const embedding = renderMetrics({
  type: "embedding_generation",
  status: "running",
  items_processed: 3,
  items_downloaded: 0,
  result: {
    expected_count: 4,
    ready_count: 3,
    generated: 0,
    reused: 2,
    invalid_regenerated: 1,
    failed: 1,
  },
});
for (const [key, value] of [
  ["expected", 4],
  ["ready", 3],
  ["generated", 0],
  ["reused", 2],
  ["invalid_regenerated", 1],
  ["failed", 1],
] as const) {
  assert.match(embedding, new RegExp(`tasks\\.stats\\.${key}[^0-9]*${value}`));
}
assert.doesNotMatch(embedding, /tasks\.stats\.downloaded/);

const legacyEmbedding = renderMetrics({
  type: "embedding_generation",
  status: "running",
  items_processed: 5,
  items_downloaded: 0,
  items_skipped: 1,
});
assert.match(legacyEmbedding, /tasks\.stats\.processed[^0-9]*5/);
assert.match(legacyEmbedding, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(
  legacyEmbedding,
  /tasks\.stats\.(?:expected|ready|generated|reused|invalid_regenerated|failed|downloaded)/,
);

const legacyEmbeddingWithoutProgress = renderMetrics({
  type: "embedding_generation",
  status: "completed",
  items_processed: 7,
  items_downloaded: 2,
});
assert.match(legacyEmbeddingWithoutProgress, /tasks\.stats\.processed[^0-9]*2/);

const zeroEmbedding = renderMetrics({
  type: "embedding_generation",
  items_processed: 5,
  items_downloaded: 2,
  result: {
    expected_count: 0,
    ready_count: 0,
    generated: 0,
    reused: 0,
    invalid_regenerated: 0,
    failed: 0,
  },
});
assertTableItemCount(zeroEmbedding, 0);
for (const key of [
  "expected",
  "ready",
  "generated",
  "reused",
  "invalid_regenerated",
  "failed",
] as const) {
  assert.match(zeroEmbedding, new RegExp(`tasks\\.stats\\.${key}[^0-9]*0`));
}
assert.doesNotMatch(zeroEmbedding, /tasks\.stats\.(?:processed|downloaded)/);

const catalog = renderMetrics({
  type: "catalog",
  items_processed: 8,
  items_downloaded: 6,
  items_skipped: 1,
  errors: ["catalog failed"],
});
assertTableItemCount(catalog, 6);
assert.match(catalog, /tasks\.stats\.scanned[^0-9]*8/);
assert.match(catalog, /tasks\.stats\.ok[^0-9]*6/);
assert.match(catalog, /tasks\.stats\.skipped[^0-9]*1/);
assert.match(catalog, /tasks\.stats\.errors[^0-9]*1/);

const catalogZeroOverrides = renderMetrics({
  type: "catalog",
  items_processed: 8,
  items_downloaded: 6,
  items_skipped: 4,
  errors: ["catalog failed"],
  catalog_scanned: 0,
  catalog_ok: 0,
  catalog_skipped: 0,
  catalog_errors: 0,
});
assertTableItemCount(catalogZeroOverrides, 0);
for (const key of ["scanned", "ok", "skipped", "errors"] as const) {
  assert.match(catalogZeroOverrides, new RegExp(`tasks\\.stats\\.${key}[^0-9]*0`));
}
assert.doesNotMatch(catalogZeroOverrides, /tasks\.stats\.(?:scanned|ok|skipped|errors)[^0-9]*[1468]/);

const activeCatalog = renderMetrics({
  type: "catalog",
  status: "pending",
  items_processed: 5,
  items_downloaded: 0,
  items_skipped: 1,
});
assert.match(activeCatalog, /tasks\.stats\.processed[^0-9]*5/);
assert.match(activeCatalog, /tasks\.stats\.skipped[^0-9]*1/);
assert.doesNotMatch(activeCatalog, /tasks\.stats\.(?:scanned|ok|downloaded|errors)/);

const legacy = renderMetrics({
  type: "legacy_pipeline",
  items_processed: 9,
  items_downloaded: 3,
  items_skipped: 2,
});
assert.match(legacy, /tasks\.stats\.processed[^0-9]*3/);
assert.match(legacy, /tasks\.stats\.skipped[^0-9]*2/);
assert.doesNotMatch(legacy, /tasks\.stats\.downloaded/);

for (const status of ["pending", "queued", "stopping"] as const) {
  const activeLegacy = renderMetrics({
    type: "legacy_pipeline",
    status,
    items_processed: 5,
    items_downloaded: 0,
  });
  assert.match(activeLegacy, /tasks\.stats\.processed[^0-9]*5/);
  assert.doesNotMatch(activeLegacy, /tasks\.stats\.downloaded/);
}

console.log("task metric UI runtime assertions passed");
