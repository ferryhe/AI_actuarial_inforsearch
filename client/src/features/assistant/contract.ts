import { z } from "zod";

export const helpSchema = z.object({ doc_id: z.string(), section_id: z.string(), language: z.enum(["en", "zh"]), title: z.string(), source_version: z.string(), content_hash: z.string().regex(/^[a-f0-9]{64}$/) });
const helpCitationSchema = helpSchema.extend({ source_type: z.literal("help").default("help"), link: z.string().optional() });
const sourceCitationSchema = z.object({ source_type: z.enum(["catalog", "kb"]), file_id: z.string(), section_id: z.string(), kb_id: z.string().nullable(), title: z.string(), link: z.string().regex(/^\/file-detail\?url=/), source_version: z.string().nullable(), source_date: z.string().nullable(), stale: z.boolean() });

export const responseSchema = z.object({
  schema_version: z.literal("1.0"),
  intent: z.enum(["feedback", "usage", "catalog", "knowledge", "clarify", "answer"]),
  answer: z.string(),
  citations: z.array(z.union([helpCitationSchema, sourceCitationSchema])),
  evidence_ids: z.array(z.string()),
  selected_target: z.object({ kb_id: z.string(), file_id: z.string() }).nullable(),
  feedback_draft: z.string().nullable(),
  availability: z.enum(["available", "unavailable", "error"]),
  error_code: z.string().nullable(),
  stop_reason: z.enum(["finish", "clarify", "error"]),
});

export type HelpCitation = z.infer<typeof helpSchema>;
export type Reply = z.infer<typeof responseSchema>;
type Query = { message: string; locale: "en" | "zh"; selected_target: Reply["selected_target"]; recent_questions: string[] };
export type QueryTransport = (query: Query, signal: AbortSignal) => Promise<Reply>;
