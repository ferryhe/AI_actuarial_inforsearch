import { Search } from "lucide-react";
import { InputField } from "@/components/FormFields";

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
        <option value="site_config">Site Config</option>
        <option value="web_crawl">Web Crawl</option>
        <option value="adhoc_url">URL</option>
        <option value="file_import">File Import</option>
        <option value="web_search">Search</option>
        <option value="catalog">Catalog</option>
        <option value="markdown">Markdown</option>
        <option value="chunk">Chunk</option>
      </select>
    </div>
  );
}
