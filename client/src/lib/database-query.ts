export const DATABASE_PAGE_SIZE = 20;

export type SortField = "title" | "source_site" | "last_seen" | "first_seen" | "bytes";
export type SortDir = "asc" | "desc";

export interface DatabaseQueryState {
  offset: number;
  query: string;
  source: string;
  category: string;
  includeDeleted: boolean;
  orderBy: SortField;
  orderDir: SortDir;
  snapshotId: string;
  firstSeenFrom: string;
  firstSeenBefore: string;
}

const VALID_SORT_FIELDS: readonly SortField[] = [
  "title",
  "source_site",
  "last_seen",
  "first_seen",
  "bytes",
];

export function parseDatabaseQueryState(search: string): DatabaseQueryState {
  const params = new URLSearchParams(search);
  const rawPage = Number(params.get("page") || "1");
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const rawOrderBy = params.get("order_by") || "";
  const rawOrderDir = params.get("order_dir") || "";
  return {
    offset: (page - 1) * DATABASE_PAGE_SIZE,
    query: params.get("query") || "",
    source: params.get("source") || "",
    category: params.get("category") || "",
    includeDeleted: params.get("include_deleted") === "true",
    orderBy: VALID_SORT_FIELDS.includes(rawOrderBy as SortField)
      ? rawOrderBy as SortField
      : "last_seen",
    orderDir: rawOrderDir === "asc" ? "asc" : "desc",
    snapshotId: params.get("snapshot_id") || "",
    firstSeenFrom: params.get("first_seen_from") || "",
    firstSeenBefore: params.get("first_seen_before") || "",
  };
}

function addContextParams(params: URLSearchParams, state: DatabaseQueryState): void {
  if (state.snapshotId) params.set("snapshot_id", state.snapshotId);
  if (state.firstSeenFrom) params.set("first_seen_from", state.firstSeenFrom);
  if (state.firstSeenBefore) params.set("first_seen_before", state.firstSeenBefore);
}

export function buildFilesParams(state: DatabaseQueryState): URLSearchParams {
  const params = new URLSearchParams({
    limit: String(DATABASE_PAGE_SIZE),
    offset: String(state.offset),
    order_by: state.orderBy,
    order_dir: state.orderDir,
  });
  if (state.query) params.set("query", state.query);
  if (state.source) params.set("source", state.source);
  if (state.category) params.set("category", state.category);
  if (state.includeDeleted) params.set("include_deleted", "true");
  addContextParams(params, state);
  return params;
}

export function buildDatabaseLocation(state: DatabaseQueryState): string {
  const page = Math.floor(state.offset / DATABASE_PAGE_SIZE) + 1;
  const params = new URLSearchParams({
    page: String(page),
    order_by: state.orderBy,
    order_dir: state.orderDir,
  });
  if (state.query) params.set("query", state.query);
  if (state.source) params.set("source", state.source);
  if (state.category) params.set("category", state.category);
  if (state.includeDeleted) params.set("include_deleted", "true");
  addContextParams(params, state);
  return `/database?${params.toString()}`;
}
