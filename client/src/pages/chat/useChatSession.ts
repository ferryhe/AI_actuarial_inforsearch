import { useCallback, useRef, useState } from "react";
import {
  createChatConversation,
  deleteChatConversation,
  fetchChatConversation,
  fetchChatConversations,
} from "./api";
import type { ChatMode, Conversation, DocumentScopeSource, Message } from "./types";

interface UseChatSessionOptions {
  canUseConversations: boolean;
  initialLoading?: boolean;
  newConversationTitle: string;
  getMode: () => ChatMode;
}

export function useChatSession({
  canUseConversations,
  initialLoading = true,
  newConversationTitle,
  getMode,
}: UseChatSessionOptions) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [documentScope, setDocumentScope] = useState<DocumentScopeSource[]>([]);
  const [loadingConvs, setLoadingConvs] = useState(initialLoading);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [conversationLoadError, setConversationLoadError] = useState(false);
  const conversationLoadId = useRef(0);

  const resetSession = useCallback(() => {
    conversationLoadId.current += 1;
    setConversations([]);
    setActiveConvId(null);
    setMessages([]);
    setDocumentScope([]);
    setLoadingConversation(false);
    setConversationLoadError(false);
    setLoadingConvs(false);
  }, []);

  const loadConversations = useCallback(async () => {
    if (!canUseConversations) return;
    setLoadingConvs(true);
    try {
      setConversations(await fetchChatConversations());
    } catch {
      setConversations([]);
    } finally {
      setLoadingConvs(false);
    }
  }, [canUseConversations]);

  const loadConversation = useCallback(async (id: string) => {
    if (!canUseConversations) return;
    const loadId = ++conversationLoadId.current;
    setActiveConvId(id);
    setMessages([]);
    setDocumentScope([]);
    setLoadingConversation(true);
    setConversationLoadError(false);
    try {
      const detail = await fetchChatConversation(id);
      if (loadId !== conversationLoadId.current) return;
      setMessages(detail.messages);
      setDocumentScope(detail.documentScope);
    } catch {
      if (loadId === conversationLoadId.current) {
        setMessages([]);
        setDocumentScope([]);
        setConversationLoadError(true);
      }
    } finally {
      if (loadId === conversationLoadId.current) setLoadingConversation(false);
    }
  }, [canUseConversations]);

  const createConversation = useCallback(async () => {
    if (!canUseConversations) return false;
    const loadId = ++conversationLoadId.current;
    setLoadingConversation(true);
    setConversationLoadError(false);
    try {
      const newId = await createChatConversation(getMode());
      if (loadId !== conversationLoadId.current) return false;
      if (newId) {
        const newConv: Conversation = {
          id: newId,
          title: newConversationTitle,
          created_at: new Date().toISOString(),
        };
        setConversations((prev) => [newConv, ...prev]);
        setActiveConvId(newId);
        setMessages([]);
        setDocumentScope([]);
        setConversationLoadError(false);
        return true;
      }
    } catch {
      if (loadId === conversationLoadId.current) {
        setActiveConvId(null);
        setMessages([]);
        setDocumentScope([]);
        setConversationLoadError(false);
      }
    } finally {
      if (loadId === conversationLoadId.current) setLoadingConversation(false);
    }
    return false;
  }, [canUseConversations, getMode, newConversationTitle]);

  const removeConversation = useCallback(async (id: string) => {
    if (!canUseConversations) return;
    const loadId = conversationLoadId.current;
    try {
      await deleteChatConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id && loadId === conversationLoadId.current) {
        conversationLoadId.current += 1;
        setActiveConvId(null);
        setMessages([]);
        setDocumentScope([]);
        setLoadingConversation(false);
        setConversationLoadError(false);
      }
    } catch {}
  }, [activeConvId, canUseConversations]);

  return {
    conversations,
    setConversations,
    activeConvId,
    setActiveConvId,
    messages,
    setMessages,
    documentScope,
    setDocumentScope,
    loadingConversation,
    conversationLoadError,
    loadingConvs,
    setLoadingConvs,
    resetSession,
    loadConversations,
    loadConversation,
    createConversation,
    removeConversation,
  };
}
