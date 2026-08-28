import type { TaskContractResult } from "./Tasks.types";

const MARKDOWN_TYPES = new Set(["markdown", "markdown_conversion"]);
const CHUNK_TYPES = new Set(["chunk", "chunk_generation"]);
const EMBEDDING_TYPES = new Set(["embedding", "embedding_generation"]);
const LOCAL_IMPORT_TYPES = new Set(["file", "file_import"]);
const ACTIVE_STATUSES = new Set(["running", "pending", "queued", "stopping"]);
const ACQUISITION_TYPES = new Set([
  "search",
  "url",
  "scheduled",
  "adhoc",
  "quick_check",
  "web_crawl",
  "web_search",
  "adhoc_url",
]);

export interface TaskMetricData {
  type?: string;
  status?: string;
  items_processed?: number;
  items_downloaded?: number;
  items_skipped?: number;
  catalog_scanned?: number;
  catalog_ok?: number;
  catalog_skipped?: number;
  catalog_errors?: number;
  errors?: string[];
  result?: TaskContractResult;
}

export interface TaskMetric {
  labelKey: string;
  value: number;
}

function metric(label: string, value: number): TaskMetric {
  return { labelKey: `tasks.stats.${label}`, value };
}

function optionalMetric(label: string, value: number | null | undefined): TaskMetric[] {
  return value == null ? [] : [metric(label, value)];
}

function processedMetrics(task: TaskMetricData): TaskMetric[] {
  return [
    ...optionalMetric("processed", task.items_downloaded ?? task.items_processed),
    ...optionalMetric("skipped", task.items_skipped),
  ];
}

function progressMetrics(task: TaskMetricData): TaskMetric[] {
  return [
    ...optionalMetric("processed", task.items_processed ?? task.items_downloaded),
    ...optionalMetric("skipped", task.items_skipped),
  ];
}

export function getTaskMetrics(task: TaskMetricData): TaskMetric[] {
  const type = String(task.type || "").toLowerCase();
  const status = String(task.status || "").toLowerCase();
  const isActive = ACTIVE_STATUSES.has(status);

  if (CHUNK_TYPES.has(type)) {
    if (task.result?.chunk_sets == null) {
      return isActive ? progressMetrics(task) : processedMetrics(task);
    }
    const chunkSets = task.result.chunk_sets;
    return [
      metric("chunk_sets", chunkSets.length),
      metric("chunks", chunkSets.reduce((total, row) => total + (row.chunk_count ?? 0), 0)),
      metric("reused", chunkSets.filter((row) => row.reused_existing === true).length),
    ];
  }

  if (EMBEDDING_TYPES.has(type)) {
    const result = task.result;
    const hasCanonicalResult = result && [
      result.expected_count,
      result.ready_count,
      result.generated,
      result.reused,
      result.invalid_regenerated,
      result.failed,
    ].some((value) => value != null);
    if (result && hasCanonicalResult) {
      return [
        metric("expected", result.expected_count ?? 0),
        metric("ready", result.ready_count ?? 0),
        metric("generated", result.generated ?? 0),
        metric("reused", result.reused ?? 0),
        metric("invalid_regenerated", result.invalid_regenerated ?? 0),
        metric("failed", result.failed ?? 0),
      ];
    }
    return isActive ? progressMetrics(task) : processedMetrics(task);
  }

  if (isActive) return progressMetrics(task);

  if (type === "catalog") {
    return [
      ...optionalMetric("scanned", task.catalog_scanned ?? task.items_processed),
      ...optionalMetric("ok", task.catalog_ok ?? task.items_downloaded),
      ...optionalMetric("skipped", task.catalog_skipped ?? task.items_skipped),
      ...optionalMetric("errors", task.catalog_errors ?? task.errors?.length),
    ];
  }

  if (MARKDOWN_TYPES.has(type)) {
    return [
      metric("converted", task.items_downloaded ?? task.items_processed ?? 0),
      metric("skipped", task.items_skipped ?? 0),
    ];
  }

  if (LOCAL_IMPORT_TYPES.has(type)) return processedMetrics(task);

  if (ACQUISITION_TYPES.has(type)) {
    return [
      ...optionalMetric("downloaded", task.items_downloaded),
      ...optionalMetric("skipped", task.items_skipped),
    ];
  }

  return processedMetrics(task);
}

export function getTaskItemCount(task: TaskMetricData): number {
  const type = String(task.type || "").toLowerCase();
  if (type === "catalog") return task.catalog_ok ?? task.items_downloaded ?? task.items_processed ?? 0;
  if (MARKDOWN_TYPES.has(type)) return task.items_downloaded ?? task.items_processed ?? 0;
  if (CHUNK_TYPES.has(type)) return task.result?.chunk_sets?.length ?? task.items_downloaded ?? task.items_processed ?? 0;
  if (EMBEDDING_TYPES.has(type)) return task.result?.ready_count ?? task.items_processed ?? 0;
  if (ACQUISITION_TYPES.has(type)) return task.items_downloaded ?? task.items_processed ?? 0;
  return task.items_downloaded ?? task.items_processed ?? 0;
}

interface TaskMetricsProps {
  task: TaskMetricData;
  t: (key: string) => string;
  className?: string;
  metricClassName?: string;
  labelClassName?: string;
}

export function TaskMetrics({
  task,
  t,
  className = "flex flex-wrap gap-3 text-[11px] text-muted-foreground",
  metricClassName = "flex gap-1",
  labelClassName,
}: TaskMetricsProps) {
  const metrics = getTaskMetrics(task);
  const type = String(task.type || "").toLowerCase();
  const embeddingIdentity = EMBEDDING_TYPES.has(type) && task.result && (
    task.result.provider || task.result.model || task.result.dimension != null
  )
    ? `${task.result.provider || "?"} / ${task.result.model || "?"} / ${task.result.dimension ?? "?"}`
    : null;

  if (metrics.length === 0 && !embeddingIdentity) return null;

  return (
    <div className={className} data-testid={`task-metrics-${type || "unknown"}`}>
      {embeddingIdentity && <div className={metricClassName}>{embeddingIdentity}</div>}
      {metrics.map((row) => (
        <div className={metricClassName} key={row.labelKey}>
          <span className={labelClassName}>{t(row.labelKey)}:</span>
          <span>{row.value}</span>
        </div>
      ))}
    </div>
  );
}
