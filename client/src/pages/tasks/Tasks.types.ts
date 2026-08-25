export interface Task {
  id: string;
  name: string;
  type: string;
  status: string;
  progress: number;
  started_at: string;
  current_activity: string;
  items_processed: number;
  items_total: number;
}

export interface SiteConfig {
  name: string;
  url?: string;
  max_pages?: number;
  max_depth?: number;
  keywords?: string[];
  exclude_keywords?: string[];
  exclude_prefixes?: string[];
  schedule_interval?: string;
  content_selector?: string;
}

export interface ScheduledTask {
  name: string;
  type: string;
  interval: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

export interface ScheduleJob {
  tag: string;
  interval: string;
  next_run?: string;
  last_run?: string;
}

export interface ScheduleStatus {
  jobs: ScheduleJob[];
  global_schedule?: string;
  job_count?: number;
}

export interface HistoryTask {
  id?: string;
  name?: string;
  type?: string;
  status?: string;
  started_at?: string;
  completed_at?: string;
  items_processed?: number;
  items_downloaded?: number;
  items_skipped?: number;
  catalog_scanned?: number;
  catalog_ok?: number;
  catalog_skipped?: number;
  catalog_errors?: number;
  errors?: string[];
}

export interface LogModal {
  taskId: string;
  taskName: string;
  log: string;
  task?: HistoryTask;
}

export interface PipelineRun {
  run_id: string;
  correlation_id: string;
  source_type: string;
  status: string;
  watermark: string | null;
  lease_owner: string | null;
  lease_expires_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PipelineStage {
  run_id: string;
  stage_name: string;
  stage_order: number;
  options_json: string | null;
  status: string;
  checkpoint_json: string | null;
  retry_count: number;
  committed_artifacts_json: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PipelineChildRun {
  child_run_id: string;
  parent_run_id: string;
  correlation_id: string;
  status: string;
  partial: number;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PipelineRunDetail {
  run: PipelineRun;
  stages: PipelineStage[];
  child_runs: PipelineChildRun[];
}

export interface TaskTableProps {
  historyTasks: HistoryTask[];
  onViewLog: (id: string | undefined, name: string | undefined, task?: HistoryTask) => void;
}
