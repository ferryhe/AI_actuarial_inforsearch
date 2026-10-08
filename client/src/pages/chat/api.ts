import { apiDelete, apiGet, apiPost } from "@/lib/api";
import type { FilePage, FilePageFilters } from "@/hooks/use-paged-files";
import type {
  AvailableDocument,
  CategoryOption,
  ChatConversationDetail,
  ChatMode,
  Citation,
  Conversation,
  DocumentScopeSource,
  KnowledgeBase,
  MarkdownResponse,
  Message,
  RetrievedBlock,
} from "./types";

export async function fetchChatConversations(): Promise<Conversation[]> {
  const res = await apiGet<{ success?: boolean; data?: { conversations?: Conversation[] }; conversations?: Conversation[] }>("/api/chat/conversations");
  const convs = res.data?.conversations || res.conversations || [];
  return convs.map((c) => ({
    ...c,
    id: c.id || c.conversation_id || "",
  }));
}

export async function fetchChatConversation(id: string): Promise<ChatConversationDetail> {
  const res = await apiGet<{ success?: boolean; data?: { messages?: Message[]; conversation?: Conversation }; messages?: Message[] }>(
    `/api/chat/conversations/${id}`
  );
  const metadata = res.data?.conversation?.metadata;
  const rawScope = metadata && Array.isArray(metadata.document_scope)
    ? metadata.document_scope
    : [];
  const documentScope: DocumentScopeSource[] = rawScope.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const source = item as Record<string, unknown>;
    if (typeof source.file_url !== "string" || !source.file_url.trim()) return [];
    return [{
      file_url: source.file_url,
      filename: typeof source.filename === "string" ? source.filename : "",
      title: typeof source.title === "string" ? source.title : "",
    }];
  });
  return { messages: res.data?.messages || res.messages || [], documentScope };
}

export async function createChatConversation(mode: ChatMode): Promise<string | null> {
  const res = await apiPost<{ success?: boolean; data?: { conversation_id?: string; conversation?: Conversation }; conversation?: Conversation }>("/api/chat/conversations", {
    mode,
  });
  return res.data?.conversation_id || res.data?.conversation?.id || res.conversation?.id || null;
}

export async function deleteChatConversation(id: string): Promise<void> {
  await apiDelete(`/api/chat/conversations/${id}`);
}

export async function clearChatDocumentScope(id: string): Promise<void> {
  await apiDelete(`/api/chat/conversations/${id}/document-scope`);
}

export async function fetchKnowledgeBases(): Promise<KnowledgeBase[]> {
  const res = await apiGet<{ success?: boolean; data?: { knowledge_bases?: KnowledgeBase[] }; knowledge_bases?: KnowledgeBase[] }>("/api/chat/knowledge-bases");
  return res.data?.knowledge_bases || res.knowledge_bases || [];
}

export async function fetchDocumentCategories(): Promise<Array<string | CategoryOption>> {
  const res = await apiGet<{ categories?: Array<string | CategoryOption> }>("/api/categories?mode=used");
  return res.categories || [];
}

export async function fetchAvailableDocuments(filters: FilePageFilters, signal?: AbortSignal): Promise<FilePage<AvailableDocument>> {
  const params = new URLSearchParams({ limit: String(filters.limit), offset: String(filters.offset) });
  filters.categories.forEach((category) => params.append("category", category));
  if (filters.search) params.set("query", filters.search);
  const res = await apiGet<{ data: FilePage<AvailableDocument> }>(`/api/chat/available-documents?${params}`, { signal });
  return res.data;
}

export async function fetchDocumentMarkdown(fileUrl: string): Promise<MarkdownResponse> {
  return apiGet<MarkdownResponse>(`/api/files/${encodeURIComponent(fileUrl)}/markdown`);
}

export interface ChatQueryResponse {
  success?: boolean;
  data?: {
    conversation_id?: string;
    response?: string;
    citations?: Citation[];
    retrieved_blocks?: RetrievedBlock[] | string;
    metadata?: Record<string, unknown>;
  };
  response?: string;
  citations?: Citation[];
}

export async function queryChat(payload: Record<string, unknown>): Promise<ChatQueryResponse> {
  return apiPost<ChatQueryResponse>("/api/chat/query", payload);
}
