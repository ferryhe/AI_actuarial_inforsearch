import { apiPost } from "@/lib/api";
import { responseSchema, type QueryTransport } from "./contract";

export const queryAssistant: QueryTransport = async (query, signal) => responseSchema.parse(
  await apiPost("/api/assistant/v1/query", query, { signal }),
);
