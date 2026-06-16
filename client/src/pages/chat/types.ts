export interface Conversation {
  id: string;
  conversation_id?: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  mode?: string;
}

export interface Citation {
  source?: string;
  filename?: string;
  title?: string;
  content?: string;
  quote?: string;
  score?: number;
  similarity_score?: number;
  kb_name?: string;
  file_url?: string;
  file_detail_url?: string;
  file_preview_url?: string;
}

export interface RetrievedBlock {
  filename?: string;
  kb_id?: string;
  kb_name?: string;
  chunk_id?: string;
  score?: number;
  similarity_score?: number;
  content?: string;
  quote?: string;
  source_url?: string;
  file_url?: string;
  file_detail_url?: string;
  file_preview_url?: string;
}

export interface AgenticToolTraceEntry {
  tool_name?: string;
  tool?: string;
  status?: string;
  result_count?: number;
  count?: number;
  error?: string | null;
}

export interface Message {
  id?: string;
  message_id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  metadata?: Record<string, unknown> & {
    retrieved_blocks?: RetrievedBlock[] | string;
    tool_trace?: AgenticToolTraceEntry[] | string;
  };
}

export interface KnowledgeBase {
  kb_id: string;
  name: string;
  description?: string;
  file_count?: number;
  chunk_count?: number;
  usable?: boolean;
  availability?: "ready" | "needs_reindex" | "building" | (string & {});
  manifest_profile?: string;
  profile?: string;
  agentic_ready_manifest?: {
    profile?: string;
    output_dir?: string;
    status?: string;
    doc_count?: number;
    section_count?: number;
  } | null;
}

export interface AvailableDocument {
  file_url: string;
  document_content?: string;
  filename: string;
  title: string;
  category: string;
  keywords: string[];
}

export interface CategoryOption {
  name: string;
  count?: number | null;
}

export interface MarkdownResponse {
  success?: boolean;
  markdown?: { markdown_content?: string | null } | null;
}

export interface DocumentContext {
  content: string;
  filename: string;
  fileUrl: string;
}

export const MODES = ["expert", "summary", "tutorial", "comparison"] as const;
export const RAG_MODES = ["standard", "agentic"] as const;
export const MAX_DOCUMENT_CONTEXT_SOURCES = 3;
export type ChatMode = (typeof MODES)[number];
export type RagMode = "standard" | "agentic";

export interface SendMessageOptions {
  text?: string;
  document?: AvailableDocument;
  documents?: AvailableDocument[];
  modeOverride?: ChatMode;
}

export interface ChatRouteState {
  explainDocument?: AvailableDocument;
}
