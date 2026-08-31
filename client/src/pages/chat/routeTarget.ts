import {
  getAskAiChatTargetKey,
  type AskAiChatTarget,
} from "@/lib/navigation";
import { isChatKnowledgeBaseAvailable } from "@/lib/chat-knowledge-bases";
import type { KnowledgeBase, RagMode } from "./types";

export interface ChatRouteSelection {
  ragMode: RagMode;
  selectedKbs: [string];
}

export interface ChatRouteInitialization {
  processedTargetKey: string | null;
  selection: ChatRouteSelection | null;
}

export function resolveAskAiRouteInitialization(options: {
  target: AskAiChatTarget | null;
  knowledgeBases: readonly KnowledgeBase[];
  knowledgeBasesLoaded: boolean;
  processedTargetKey: string | null;
}): ChatRouteInitialization {
  const {
    target,
    knowledgeBases,
    knowledgeBasesLoaded,
    processedTargetKey,
  } = options;
  if (!target) {
    return { processedTargetKey: null, selection: null };
  }

  const targetKey = getAskAiChatTargetKey(target);
  if (!knowledgeBasesLoaded || processedTargetKey === targetKey) {
    return { processedTargetKey, selection: null };
  }

  const targetKb = knowledgeBases.find((kb) => kb.kb_id === target.kbId);
  return {
    processedTargetKey: targetKey,
    selection: isChatKnowledgeBaseAvailable(targetKb)
      ? { ragMode: target.ragMode, selectedKbs: [target.kbId] }
      : null,
  };
}
