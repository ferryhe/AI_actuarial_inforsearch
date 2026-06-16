import { apiDelete, apiGet, apiPost } from "@/lib/api";
import type {
  AvailableDocument,
  CategoryOption,
  ChatMode,
  Citation,
  Conversation,
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

export async function fetchChatConversation(id: string): Promise<Message[]> {
  const res = await apiGet<{ success?: boolean; data?: { messages?: Message[]; conversation?: Conversation }; messages?: Message[] }>(
    `/api/chat/conversations/${id}`
  );
  return res.data?.messages || res.messages || [];
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

export async function fetchKnowledgeBases(): Promise<KnowledgeBase[]> {
  const res = await apiGet<{ success?: boolean; data?: { knowledge_bases?: KnowledgeBase[] }; knowledge_bases?: KnowledgeBase[] }>("/api/chat/knowledge-bases");
  return res.data?.knowledge_bases || res.knowledge_bases || [];
}

export async function fetchDocumentCategories(): Promise<Array<string | CategoryOption>> {
  const res = await apiGet<{ categories?: Array<string | CategoryOption> }>("/api/categories?mode=used");
  return res.categories || [];
}

export async function fetchAvailableDocuments(filters?: { categories?: string[]; search?: string }): Promise<AvailableDocument[]> {
  let url = "/api/chat/available-documents";
  const params = new URLSearchParams();
  const categories = filters?.categories || [];
  const search = filters?.search || "";
  categories.forEach((category) => params.append("category", category));
  if (search) params.set("keywords", search);
  if (params.toString()) url += `?${params}`;

  const res = await apiGet<{ success?: boolean; data?: { documents?: AvailableDocument[] }; documents?: AvailableDocument[] }>(url);
  return res.data?.documents || res.documents || [];
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
