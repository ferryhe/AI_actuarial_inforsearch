export interface TaskContractResult {
  contract_version?: number;
  files?: Array<{
    file_url?: string;
    status?: string;
  }>;
  chunk_sets?: Array<{
    chunk_set_id?: string;
    chunk_count?: number;
    reused_existing?: boolean;
  }>;
  provider?: string;
  model?: string;
  dimension?: number;
  expected_count?: number;
  ready_count?: number;
  generated?: number;
  reused?: number;
  invalid_regenerated?: number;
  failed?: number;
}

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
  items_downloaded?: number;
  items_skipped?: number;
  catalog_scanned?: number;
  catalog_ok?: number;
  catalog_skipped?: number;
  catalog_errors?: number;
  errors?: string[];
  result?: TaskContractResult;
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
  result?: TaskContractResult;
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
