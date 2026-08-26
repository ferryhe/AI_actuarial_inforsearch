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

export interface TaskTableProps {
  historyTasks: HistoryTask[];
  onViewLog: (id: string | undefined, name: string | undefined, task?: HistoryTask) => void;
}
