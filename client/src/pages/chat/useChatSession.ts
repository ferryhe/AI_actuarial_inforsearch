import { useCallback, useState } from "react";
import {
  createChatConversation,
  deleteChatConversation,
  fetchChatConversation,
  fetchChatConversations,
} from "./api";
import type { ChatMode, Conversation, Message } from "./types";

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
  const [loadingConvs, setLoadingConvs] = useState(initialLoading);

  const resetSession = useCallback(() => {
    setConversations([]);
    setActiveConvId(null);
    setMessages([]);
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
    setActiveConvId(id);
    try {
      setMessages(await fetchChatConversation(id));
    } catch {
      setMessages([]);
    }
  }, [canUseConversations]);

  const createConversation = useCallback(async () => {
    if (!canUseConversations) return false;
    try {
      const newId = await createChatConversation(getMode());
      if (newId) {
        const newConv: Conversation = {
          id: newId,
          title: newConversationTitle,
          created_at: new Date().toISOString(),
        };
        setConversations((prev) => [newConv, ...prev]);
        setActiveConvId(newId);
        setMessages([]);
        return true;
      }
    } catch {
      setActiveConvId(null);
      setMessages([]);
    }
    return false;
  }, [canUseConversations, getMode, newConversationTitle]);

  const removeConversation = useCallback(async (id: string) => {
    if (!canUseConversations) return;
    try {
      await deleteChatConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      setActiveConvId((current) => {
        if (current === id) {
          setMessages([]);
          return null;
        }
        return current;
      });
    } catch {}
  }, [canUseConversations]);

  return {
    conversations,
    setConversations,
    activeConvId,
    setActiveConvId,
    messages,
    setMessages,
    loadingConvs,
    setLoadingConvs,
    resetSession,
    loadConversations,
    loadConversation,
    createConversation,
    removeConversation,
  };
}
