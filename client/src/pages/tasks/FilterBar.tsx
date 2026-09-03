import { Search } from "lucide-react";
import { useTranslation } from "@/components/Layout";

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
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search tasks..."
          className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <select
        value={statusFilter}
        onChange={(e) => onStatusChange(e.target.value)}
        className="px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="">All Status</option>
        <option value="running">Running</option>
        <option value="completed">Completed</option>
        <option value="error">Error</option>
        <option value="stopped">Stopped</option>
      </select>
      <select
        value={typeFilter}
        onChange={(e) => onTypeChange(e.target.value)}
        className="px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="">All Types</option>
        <option value="scheduled">{t("tasks.type.site_config")}</option>
        <option value="quick_check">{t("tasks.type.web_crawl")}</option>
        <option value="url">{t("tasks.type.adhoc_url")}</option>
        <option value="file">{t("tasks.type.file_import")}</option>
        <option value="search">{t("tasks.type.web_search")}</option>
        <option value="recategory">{t("tasks.type.recategory")}</option>
        <option value="catalog">{t("tasks.type.catalog")}</option>
        <option value="markdown_conversion">{t("tasks.type.markdown")}</option>
        <option value="chunk_generation">{t("tasks.type.chunk")}</option>
        <option value="rag_indexing">{t("tasks.type.rag_index")}</option>
      </select>
    </div>
  );
}
