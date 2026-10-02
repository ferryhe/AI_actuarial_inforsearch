import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { PipelineBatonResults, type PipelineView } from "./PipelineBatonResults";

test("renders Issue 348 Pipeline Baton results", () => {
const steps = [
  { step: "scheduled", label: "Scheduled Collection", testId: "scheduled" },
  { step: "markdown_conversion", label: "Markdown", testId: "markdown" },
  { step: "catalog", label: "Catalog", testId: "catalog" },
  { step: "chunk_generation", label: "Chunk & Embedding", testId: "chunk" },
  { step: "rag_indexing", label: "KB Index & Ready Data", testId: "rag" },
] satisfies Parameters<typeof PipelineBatonResults>[0]["steps"];
const t = (key: string) => key.replace("tasks.pipeline.", "");
const idleStages: PipelineView["stages"] = steps.map((step) => ({ ...step, status: "idle", tasks: [], failures: [] }));

function view(status: string, stages = idleStages): PipelineView {
  return {
    config: { overrides: {} },
    state: { round_status: status },
    summary: { status, successful_stages: 0, failed_stages: 0, stopped_stages: 0, latest_failure: null },
    stages,
  };
}

function render(current: PipelineView, showFailuresOnly = false): string {
  return renderToStaticMarkup(<PipelineBatonResults view={current} steps={steps} expanded={null} showFailuresOnly={showFailuresOnly} onShowFailuresOnly={() => undefined} onToggle={() => undefined} onViewLog={() => undefined} renderSettings={() => null} t={t} />);
}

const completed = render(view("completed"));
assert.match(completed, /completed/);
assert.equal((completed.match(/data-testid="(?:scheduled|markdown|catalog|chunk|rag)"/g) || []).length, 5);

const running = render(view("running"));
assert.match(running, /running/);

const failedStages = idleStages.map((stage) => stage.step === "catalog" ? {
  ...stage,
  status: "failed",
  tasks: [{ task_id: "catalog-1", status: "completed", error_count: 1, first_error_code: "catalog_failed", first_error_summary: "Catalog processing failed.", failed_items: 5 }],
} : stage);
const completedWithErrors = view("completed_with_errors", failedStages);
completedWithErrors.summary = { ...completedWithErrors.summary, failed_stages: 1, latest_failure: { task_id: "catalog-1", stage: "catalog", error_count: 1, first_error_code: "catalog_failed", summary: "Catalog processing failed." } };
const failedMarkup = render(completedWithErrors, true);
assert.match(failedMarkup, /aria-expanded="true"/);
assert.match(failedMarkup, /errors: 1/);
assert.match(failedMarkup, /failed_items: 5/);
assert.match(failedMarkup, /Catalog processing failed/);
assert.doesNotMatch(failedMarkup, /Scheduled Collection/);

const stoppedMarkup = render(view("stopped", idleStages.map((stage) => stage.step === "markdown_conversion" ? { ...stage, status: "stopped" } : stage)));
assert.match(stoppedMarkup, /stopped/);
const hardError = view("error", idleStages.map((stage) => stage.step === "catalog" ? { ...stage, status: "failed" } : stage));
hardError.summary = { ...hardError.summary, failed_stages: 1, latest_failure: { task_id: null, stage: "catalog", error_count: 1, first_error_code: "orchestration_error", summary: "Pipeline orchestration failed." } };
const hardErrorMarkup = render(hardError, true);
assert.match(hardErrorMarkup, /error/);
assert.match(hardErrorMarkup, /failed: 1/);
assert.match(hardErrorMarkup, /Pipeline orchestration failed/);
assert.match(hardErrorMarkup, /aria-expanded="true"/);
assert.doesNotMatch(hardErrorMarkup, /Scheduled Collection/);
assert.doesNotMatch(hardErrorMarkup, /button-pipeline-latest-failure/);

const combinedHardError = view("error", idleStages.map((stage) => stage.step === "catalog" || stage.step === "chunk_generation" ? { ...stage, status: "failed" } : stage));
combinedHardError.summary = { ...combinedHardError.summary, failed_stages: 2, latest_failure: { task_id: null, stage: "chunk_generation", error_count: 1, first_error_code: "orchestration_error", summary: "Pipeline orchestration failed." } };
const combinedHardErrorMarkup = render(combinedHardError, true);
assert.match(combinedHardErrorMarkup, /failed: 2/);
assert.match(combinedHardErrorMarkup, /data-testid="catalog"/);
assert.match(combinedHardErrorMarkup, /data-testid="chunk"/);
assert.match(combinedHardErrorMarkup, /Pipeline orchestration failed/);
assert.doesNotMatch(combinedHardErrorMarkup, /Scheduled Collection/);

let viewed: [string, string] | null = null;
let toggled: string | null = null;
const element = PipelineBatonResults({ view: completedWithErrors, steps, expanded: null, showFailuresOnly: false, onShowFailuresOnly: () => undefined, onToggle: (step) => { toggled = step; }, onViewLog: (id, name) => { viewed = [id, name]; }, renderSettings: () => null, t }) as { props?: { children?: unknown } };
function findLatestButton(node: unknown): { props?: { onClick?: () => void; children?: unknown; "data-testid"?: string } } | null {
  if (!node || typeof node !== "object") return null;
  const value = node as { props?: { onClick?: () => void; children?: unknown; "data-testid"?: string } };
  if (value.props?.["data-testid"] === "button-pipeline-latest-failure") return value;
  const children = value.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = findLatestButton(child);
    if (found) return found;
  }
  return null;
}
const latestButton = findLatestButton(element);
assert.ok(latestButton?.props?.onClick);
latestButton.props.onClick();
assert.deepEqual(viewed, ["catalog-1", "catalog"]);

function findButton(node: unknown, testId: string): { props?: { onClick?: () => void; children?: unknown; "data-testid"?: string } } | null {
  if (!node || typeof node !== "object") return null;
  const value = node as { props?: { onClick?: () => void; children?: unknown; "data-testid"?: string } };
  if (value.props?.["data-testid"] === testId) return value;
  const children = value.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = findButton(child, testId);
    if (found) return found;
  }
  return null;
}
const catalogToggle = findButton(element, "button-pipeline-stage-catalog");
assert.ok(catalogToggle?.props?.onClick);
catalogToggle.props.onClick();
assert.equal(toggled, "catalog");

console.log("Issue 348 Pipeline Baton results component assertions passed");
});
