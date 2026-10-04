import { Search } from "lucide-react";
import { useTranslation } from "@/components/Layout";
import { resolveEnumLabel } from "@/lib/enum-display";

const taskTypeFilters = ["scheduled", "quick_check", "url", "file", "search", "recategory", "catalog", "markdown_conversion", "chunk_generation", "rag_indexing", "embedding_generation", "ready_data_build"];

interface FilterBarProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  statusFilter: string;
  onStatusChange: (s: string) => void;
  typeFilter: string;
  onTypeChange: (t: string) => void;
}

export function FilterBar({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusChange,
  typeFilter,
  onTypeChange,
}: FilterBarProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap gap-3 items-center">
      <div className="relative flex-1 min-w-[200px]">
        <label htmlFor="input-task-filter-search" className="text-xs font-medium text-muted-foreground">Search tasks</label>
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search tasks..."
          id="input-task-filter-search"
          className="w-full min-h-[44px] pl-9 pr-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <label className="text-xs font-medium text-muted-foreground">{t("tasks.col.status")}
      <select id="select-task-filter-status"
        value={statusFilter}
        onChange={(e) => onStatusChange(e.target.value)}
        className="block min-h-[44px] px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="">{t("tasks.filter.all_status")}</option>
        {["running", "completed", "error", "stopped"].map((status) => <option key={status} value={status}>{resolveEnumLabel("status", status, t)}</option>)}
      </select></label>
      <label className="text-xs font-medium text-muted-foreground">{t("tasks.col.type")}
      <select id="select-task-filter-type"
        value={typeFilter}
        onChange={(e) => onTypeChange(e.target.value)}
        className="block min-h-[44px] px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="">{t("tasks.filter.all_types")}</option>
        {taskTypeFilters.map((type) => <option key={type} value={type}>{resolveEnumLabel("task_type", type, t)}</option>)}
      </select></label>
    </div>
  );
}
