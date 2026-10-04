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

test("uses bilingual shared status labels and safe privileged fallback for summary and stage", () => {
  const steps = [
    { step: "scheduled", label: "Scheduled Collection", testId: "pipeline-scheduled" },
    { step: "catalog", label: "Catalog", testId: "pipeline-catalog" },
  ] satisfies Parameters<typeof PipelineBatonResults>[0]["steps"];
  const makeView = (status: string, stageStatus: string): PipelineView => ({
    config: { overrides: {} },
    state: { round_status: status },
    summary: { status, successful_stages: 0, failed_stages: 0, stopped_stages: 0, latest_failure: null },
    stages: steps.map((step) => ({ ...step, status: step.step === "catalog" ? stageStatus : "idle", tasks: [], failures: [] })),
  });
  const translations = {
    en: { "enum.unknown": "Unknown status", "enum.diagnostic_details": "Diagnostic details", "enum.error_code.index_launch_failed": "Index launch failed", "tasks.pipeline.idle": "Idle", "tasks.pipeline.completed_with_errors": "Completed with errors", "tasks.pipeline.index_launch_failed_summary": "Knowledge base {kbId} could not start indexing", "tasks.pipeline.kb_failure_summary": "Knowledge base {kbId} failed", "tasks.pipeline.failure_summary": "The pipeline stage failed" },
    zh: { "enum.unknown": "未知状态", "enum.diagnostic_details": "诊断详情", "enum.error_code.index_launch_failed": "索引启动失败", "tasks.pipeline.idle": "空闲", "tasks.pipeline.completed_with_errors": "完成但有错误", "tasks.pipeline.index_launch_failed_summary": "知识库 {kbId} 无法启动索引", "tasks.pipeline.kb_failure_summary": "知识库 {kbId} 处理失败", "tasks.pipeline.failure_summary": "流程阶段处理失败" },
  };
  const render = (status: string, stageStatus: string, locale: "en" | "zh", canInspectRaw = false) => renderToStaticMarkup(
    <PipelineBatonResults view={makeView(status, stageStatus)} steps={steps} expanded={null} showFailuresOnly={false} onShowFailuresOnly={() => undefined} onToggle={() => undefined} onViewLog={() => undefined} renderSettings={() => null} t={(key) => translations[locale][key as keyof typeof translations.en] || key} canInspectRaw={canInspectRaw} />,
  );

  for (const locale of ["en", "zh"] as const) {
    const idle = render("idle", "idle", locale);
    const completedWithErrors = render("completed_with_errors", "completed_with_errors", locale);
    assert.match(idle, new RegExp(locale === "en" ? "Idle" : "空闲"));
    assert.match(completedWithErrors, new RegExp(locale === "en" ? "Completed with errors" : "完成但有错误"));
  }

  const customer = render("private_phase", "private_phase", "zh");
  assert.match(customer, /未知状态/);
  assert.doesNotMatch(customer, /private_phase|<details/);
  const operator = render("private_phase", "private_phase", "zh", true);
  assert.equal((operator.match(/<details/g) || []).length, 2);
  assert.equal((operator.match(/<details open/g) || []).length, 0);
  assert.equal((operator.match(/private_phase/g) || []).length, 2);
  assert.match(operator, /<button[^>]*>.*?未知状态/s);
});

test("localizes the structured index launch failure and keeps its raw code privileged", () => {
  const steps = [{ step: "rag_indexing", label: "KB Index", testId: "pipeline-step-rag_indexing" }] as const;
  const rawSummary = "Knowledge base kb-demo failed: index_launch_failed.";
  const view: PipelineView = {
    config: { overrides: {} },
    state: { round_status: "completed" },
    summary: { status: "completed_with_errors", successful_stages: 0, failed_stages: 1, stopped_stages: 0, latest_failure: { task_id: null, stage: "rag_indexing", error_count: 1, first_error_code: "index_launch_failed", summary: rawSummary } },
    stages: [{ step: "rag_indexing", status: "failed", tasks: [], failures: [{ task_id: null, first_error_code: "index_launch_failed", first_error_summary: rawSummary }] }],
  };
  const translations = {
    en: { "enum.diagnostic_details": "Diagnostic details", "enum.error_code.index_launch_failed": "Index launch failed", "tasks.pipeline.index_launch_failed_summary": "Knowledge base {kbId} could not start indexing" },
    zh: { "enum.diagnostic_details": "诊断详情", "enum.error_code.index_launch_failed": "索引启动失败", "tasks.pipeline.index_launch_failed_summary": "知识库 {kbId} 无法启动索引" },
  };
  const render = (locale: "en" | "zh", canInspectRaw: boolean) => renderToStaticMarkup(
    <PipelineBatonResults view={view} steps={[...steps]} expanded={null} showFailuresOnly={false} onShowFailuresOnly={() => undefined} onToggle={() => undefined} onViewLog={() => undefined} renderSettings={() => null} t={(key) => translations[locale][key as keyof typeof translations.en] || key} canInspectRaw={canInspectRaw} />,
  );

  for (const locale of ["en", "zh"] as const) {
    const expected = locale === "en" ? "Knowledge base kb-demo could not start indexing" : "知识库 kb-demo 无法启动索引";
    const customer = render(locale, false);
    assert.equal((customer.match(new RegExp(expected, "g")) || []).length, 2);
    assert.doesNotMatch(customer, /index_launch_failed|<details/);
    const operator = render(locale, true);
    assert.equal((operator.match(/<details/g) || []).length, 2);
    assert.equal((operator.match(/<details open/g) || []).length, 0);
    assert.equal((operator.match(/index_launch_failed/g) || []).length, 4);
  }
});

test("hides Ready Data error prefixes when projection normalizes the error code to empty", () => {
  const steps = [{ step: "rag_indexing", label: "KB Index", testId: "pipeline-step-rag_indexing" }] as const;
  const translations = {
    en: { "enum.diagnostic_details": "Diagnostic details", "tasks.pipeline.ready_data_failure_summary": "Ready Data operation failed" },
    zh: { "enum.diagnostic_details": "诊断详情", "tasks.pipeline.ready_data_failure_summary": "就绪数据处理失败" },
  };
  const render = (prefix: string, locale: "en" | "zh", canInspectRaw: boolean) => {
    const rawSummary = `${prefix}: Ready Data operation could not complete`;
    const view: PipelineView = {
      config: { overrides: {} },
      state: { round_status: "completed" },
      summary: { status: "failed", successful_stages: 0, failed_stages: 1, stopped_stages: 0, latest_failure: { task_id: null, stage: "rag_indexing", error_count: 1, first_error_code: "", summary: rawSummary } },
      stages: [{ step: "rag_indexing", status: "failed", tasks: [], failures: [{ task_id: null, first_error_code: "", first_error_summary: rawSummary }] }],
    };
    return renderToStaticMarkup(<PipelineBatonResults view={view} steps={[...steps]} expanded={null} showFailuresOnly={false} onShowFailuresOnly={() => undefined} onToggle={() => undefined} onViewLog={() => undefined} renderSettings={() => null} t={(key) => translations[locale][key as keyof typeof translations.en] || key} canInspectRaw={canInspectRaw} />);
  };

  for (const prefix of ["build_failure", "publish_failure", "stale_snapshot", "invalid_selector"]) {
    for (const locale of ["en", "zh"] as const) {
      const safeLabel = locale === "en" ? "Ready Data operation failed" : "就绪数据处理失败";
      const rawSummary = `${prefix}: Ready Data operation could not complete`;
      const customer = render(prefix, locale, false);
      assert.equal((customer.match(new RegExp(safeLabel, "g")) || []).length, 2);
      assert.doesNotMatch(customer, new RegExp(`${prefix}|Ready Data operation could not complete|<details`));
      const operator = render(prefix, locale, true);
      assert.equal((operator.match(/<details/g) || []).length, 2);
      assert.equal((operator.match(/<details open/g) || []).length, 0);
      assert.equal((operator.match(new RegExp(prefix, "g")) || []).length, 2);
      assert.equal((operator.match(new RegExp(rawSummary, "g")) || []).length, 2);
    }
  }
});
