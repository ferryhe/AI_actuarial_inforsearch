import { useEffect, useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Plus,
  MessageSquare,
  Trash2,
  Bot,
  User,
  BookOpen,
  Loader2,
  ChevronDown,
  X,
  FileText,
  Inbox,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { apiGet, apiPost, apiDelete } from "@/lib/api";

interface Conversation {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
}

interface Citation {
  source?: string;
  title?: string;
  content?: string;
  score?: number;
}

interface Message {
  id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  metadata?: Record<string, unknown>;
}

interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
}

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: "easeOut" as const },
  }),
};

const MODES = ["expert", "summary", "tutorial", "comparison"] as const;
type ChatMode = (typeof MODES)[number];

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-4 py-3">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-2 h-2 rounded-full bg-muted-foreground/40"
            animate={{ y: [0, -6, 0] }}
            transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
          />
        ))}
      </div>
    </div>
  );
}

function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  return (
    <div
      className="inline-flex items-start gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs max-w-xs"
      data-testid={`citation-${index}`}
    >
      <FileText className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" strokeWidth={1.8} />
      <div className="min-w-0">
        <p className="font-medium truncate">{citation.title || citation.source || "Source"}</p>
        {citation.content && (
          <p className="text-muted-foreground line-clamp-2 mt-0.5">{citation.content}</p>
        )}
      </div>
    </div>
  );
}

function MessageBubble({ message, index }: { message: Message; index: number }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      custom={index}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      className={cn("flex gap-3 max-w-3xl", isUser ? "ml-auto flex-row-reverse" : "")}
      data-testid={`message-${index}`}
    >
      <div
        className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={cn("flex flex-col gap-2", isUser ? "items-end" : "items-start")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
            isUser
              ? "bg-primary text-primary-foreground rounded-br-md"
              : "bg-card border border-border rounded-bl-md"
          )}
        >
          {message.content}
        </div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1">
            {message.citations.map((c, i) => (
              <CitationCard key={i} citation={c} index={i} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

export default function Chat() {
  const { t } = useTranslation();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbs, setSelectedKbs] = useState<string[]>([]);
  const [mode, setMode] = useState<ChatMode>("expert");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showKbDropdown, setShowKbDropdown] = useState(false);
  const [showModeDropdown, setShowModeDropdown] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, scrollToBottom]);

  useEffect(() => {
    loadConversations();
    loadKnowledgeBases();
  }, []);

  async function loadConversations() {
    setLoadingConvs(true);
    try {
      const data = await apiGet<{ conversations?: Conversation[] }>("/api/chat/conversations");
      setConversations(data.conversations || []);
    } catch {
      setConversations([]);
    } finally {
      setLoadingConvs(false);
    }
  }

  async function loadKnowledgeBases() {
    try {
      const data = await apiGet<{ knowledge_bases?: KnowledgeBase[] }>("/api/chat/knowledge-bases");
      setKnowledgeBases(data.knowledge_bases || []);
    } catch {
      setKnowledgeBases([]);
    }
  }

  async function loadConversation(id: string) {
    setActiveConvId(id);
    try {
      const data = await apiGet<{ messages?: Message[]; conversation?: Conversation }>(
        `/api/chat/conversations/${id}`
      );
      setMessages(data.messages || []);
    } catch {
      setMessages([]);
    }
  }

  async function createConversation() {
    try {
      const data = await apiPost<{ conversation?: Conversation }>("/api/chat/conversations", {
        title: t("chat.new_conversation"),
      });
      if (data.conversation) {
        setConversations((prev) => [data.conversation!, ...prev]);
        setActiveConvId(data.conversation.id);
        setMessages([]);
      }
    } catch {
      setActiveConvId(null);
      setMessages([]);
    }
  }

  async function deleteConversation(id: string) {
    try {
      await apiDelete(`/api/chat/conversations/${id}`);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {}
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);

    try {
      const data = await apiPost<{
        success?: boolean;
        data?: {
          conversation_id?: string;
          response?: string;
          citations?: Citation[];
          metadata?: Record<string, unknown>;
        };
        response?: string;
        citations?: Citation[];
      }>("/api/chat/query", {
        conversation_id: activeConvId,
        message: text,
        kb_ids: selectedKbs.length > 0 ? selectedKbs : undefined,
        mode,
      });

      const responseText =
        data.data?.response || data.response || t("chat.no_response");
      const citations = data.data?.citations || data.citations || [];

      if (data.data?.conversation_id && !activeConvId) {
        setActiveConvId(data.data.conversation_id);
        loadConversations();
      }

      const assistantMsg: Message = {
        role: "assistant",
        content: responseText,
        citations,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const assistantMsg: Message = {
        role: "assistant",
        content: t("chat.error_sending"),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function toggleKb(id: string) {
    setSelectedKbs((prev) =>
      prev.includes(id) ? prev.filter((k) => k !== id) : [...prev, id]
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] -mx-4 sm:-mx-6 -my-6 overflow-hidden">
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-r border-border bg-card flex flex-col shrink-0 overflow-hidden"
          >
            <div className="p-3 border-b border-border flex items-center gap-2">
              <button
                onClick={createConversation}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                data-testid="button-new-conversation"
              >
                <Plus className="w-4 h-4" />
                {t("chat.new_conversation")}
              </button>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-2 rounded-lg hover:bg-muted text-muted-foreground"
                data-testid="button-close-chat-sidebar"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {loadingConvs ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : conversations.length === 0 ? (
                <div className="text-center py-8 text-sm text-muted-foreground">
                  {t("chat.no_conversations")}
                </div>
              ) : (
                conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={cn(
                      "group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors text-sm",
                      activeConvId === conv.id
                        ? "bg-primary/10 text-primary"
                        : "hover:bg-muted text-foreground"
                    )}
                    onClick={() => loadConversation(conv.id)}
                    data-testid={`conversation-${conv.id}`}
                  >
                    <MessageSquare className="w-4 h-4 shrink-0" strokeWidth={1.8} />
                    <span className="truncate flex-1">{conv.title || t("chat.untitled")}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteConversation(conv.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 hover:text-destructive transition-all"
                      data-testid={`button-delete-conversation-${conv.id}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex flex-col min-w-0">
        {!sidebarOpen && (
          <div className="p-2 border-b border-border">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground"
              data-testid="button-open-chat-sidebar"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.4 }}
              >
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <Bot className="w-8 h-8 text-primary" />
                </div>
                <h2 className="text-xl font-serif font-bold mb-2">{t("chat.welcome")}</h2>
                <p className="text-sm text-muted-foreground max-w-md">
                  {t("chat.welcome_desc")}
                </p>
              </motion.div>
            </div>
          ) : (
            <>
              {messages.map((msg, i) => (
                <MessageBubble key={i} message={msg} index={i} />
              ))}
              {sending && <TypingIndicator />}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-border bg-card/80 backdrop-blur-sm px-4 sm:px-6 py-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="relative">
              <button
                onClick={() => setShowModeDropdown(!showModeDropdown)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted hover:bg-muted/80 transition-colors"
                data-testid="button-mode-selector"
              >
                {t(`chat.mode.${mode}`)}
                <ChevronDown className="w-3 h-3" />
              </button>
              {showModeDropdown && (
                <div className="absolute bottom-full mb-1 left-0 z-50 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[140px]">
                  {MODES.map((m) => (
                    <button
                      key={m}
                      onClick={() => {
                        setMode(m);
                        setShowModeDropdown(false);
                      }}
                      className={cn(
                        "w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors",
                        mode === m && "text-primary font-medium"
                      )}
                      data-testid={`mode-option-${m}`}
                    >
                      {t(`chat.mode.${m}`)}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="relative">
              <button
                onClick={() => setShowKbDropdown(!showKbDropdown)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted hover:bg-muted/80 transition-colors"
                data-testid="button-kb-selector"
              >
                <BookOpen className="w-3 h-3" />
                {selectedKbs.length > 0
                  ? `${selectedKbs.length} ${t("chat.kbs_selected")}`
                  : t("chat.select_kb")}
                <ChevronDown className="w-3 h-3" />
              </button>
              {showKbDropdown && (
                <div className="absolute bottom-full mb-1 left-0 z-50 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[200px] max-h-48 overflow-y-auto">
                  {knowledgeBases.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-muted-foreground">
                      {t("chat.no_kbs")}
                    </div>
                  ) : (
                    knowledgeBases.map((kb) => (
                      <button
                        key={kb.id}
                        onClick={() => toggleKb(kb.id)}
                        className={cn(
                          "w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors flex items-center gap-2",
                          selectedKbs.includes(kb.id) && "text-primary font-medium"
                        )}
                        data-testid={`kb-option-${kb.id}`}
                      >
                        <div
                          className={cn(
                            "w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0",
                            selectedKbs.includes(kb.id)
                              ? "bg-primary border-primary"
                              : "border-border"
                          )}
                        >
                          {selectedKbs.includes(kb.id) && (
                            <svg className="w-2.5 h-2.5 text-primary-foreground" viewBox="0 0 12 12">
                              <path d="M10 3L4.5 8.5 2 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          )}
                        </div>
                        <span className="truncate">{kb.name}</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t("chat.input_placeholder")}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-border bg-background px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition-shadow min-h-[42px] max-h-[120px]"
              style={{ height: "auto" }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 120) + "px";
              }}
              data-testid="input-chat-message"
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || sending}
              className={cn(
                "p-2.5 rounded-xl transition-colors shrink-0",
                input.trim() && !sending
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed"
              )}
              data-testid="button-send-message"
            >
              {sending ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
