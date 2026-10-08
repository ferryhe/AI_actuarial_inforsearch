import { useTranslation } from "@/components/Layout";
import { ApiError } from "@/lib/api";
import type { Message } from "./types";

const errorKeys: Record<string, string> = {
  CHAT_CONTEXT_TOO_LARGE: "chat.error.context_too_large",
  CHAT_PROVIDER_TIMEOUT: "chat.error.provider_timeout",
  CHAT_PROVIDER_UPSTREAM: "chat.error.provider_upstream",
  CHAT_PROVIDER_AUTH: "chat.error.provider_auth",
  CHAT_RETRIEVAL_FAILED: "chat.error.retrieval_failed",
  CHAT_KB_UNAVAILABLE: "chat.error.kb_unavailable",
  CHAT_CONVERSATION_FAILED: "chat.error.conversation_failed",
  CHAT_AGENTIC_UNAVAILABLE: "chat.error.agentic_unavailable",
  CHAT_PROCESSING_FAILED: "chat.error.processing_failed",
  CHAT_DOCUMENT_EMPTY: "chat.document_content_unavailable",
  CHAT_DOCUMENT_SCOPE_MISMATCH: "chat.document_scope_changed",
  KB_EMBEDDING_MISMATCH: "chat.error.embedding_mismatch",
};

export function FailedTurn({ message, onRetry }: { message: Message; onRetry: (message: Message) => void }) {
  const { t } = useTranslation();
  if (message.role !== "user" || message.metadata?.status !== "failed") return null;
  return (
    <div className="flex items-center gap-2 text-xs text-destructive" role="status">
      <span>{t(errorKeys[String(message.metadata.error_code)] || "chat.error_sending")}</span>
      {message.metadata.retryable && (
        <button type="button" className="underline" onClick={() => onRetry(message)}>
          {t("chat.retry")}
        </button>
      )}
    </div>
  );
}

export function chatFailurePayload(error: unknown): Record<string, unknown> | null {
  return error instanceof ApiError && error.payload && typeof error.payload === "object"
    ? error.payload as Record<string, unknown>
    : null;
}
