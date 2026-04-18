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
  Database,
  Search,
  ChevronRight,
  ExternalLink,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/components/Layout";
import { useAuth } from "@/context/AuthContext";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useApiQuery } from "@/hooks/use-api-query";

interface Conversation {
  id: string;
  conversation_id?: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  mode?: string;
}

interface Citation {
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

interface RetrievedBlock {
  filename?: string;
  kb_id?: string;
  kb_name?: string;
  chunk_id?: string;
  similarity_score?: number;
  content?: string;
  quote?: string;
  source_url?: string;
  file_url?: string;
  file_detail_url?: string;
  file_preview_url?: string;
}

interface Message {
  id?: string;
  message_id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  metadata?: Record<string, unknown> & { retrieved_blocks?: RetrievedBlock[] | string };
}

interface KnowledgeBase {
  kb_id: string;
  name: string;
  description?: string;
  file_count?: number;
  chunk_count?: number;
  usable?: boolean;
  availability?: "ready" | "needs_reindex" | "building" | (string & {});
}

interface AvailableDocument {
  file_url: string;
  filename: string;
  title: string;
  category: string;
  keywords: string[];
}

const MODES = ["expert", "summary", "tutorial", "comparison"] as const;
type ChatMode = (typeof MODES)[number];

function TypingIndicator() {
  return (
    <div className="flex items-center gap-3 max-w-3xl">
      <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0">
        <Bot className="w-4 h-4 text-muted-foreground" />
      </div>
      <div className="flex gap-1 px-4 py-3 rounded-2xl bg-card border border-border rounded-bl-md">
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
  const title = citation.title || citation.filename || citation.source || "Source";
  const score = citation.similarity_score || citation.score;
  const snippet = citation.content || citation.quote;
  const detailHref = citation.file_detail_url || citation.file_url;
  const previewHref = citation.file_preview_url;

  return (
    <div
      className="inline-flex items-start gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs max-w-sm hover:border-primary/30 transition-colors"
      data-testid={`citation-${index}`}
    >
      <FileText className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" strokeWidth={1.8} />
      <div className="min-w-0">
        <p className="font-medium truncate">{title}</p>
        {citation.kb_name && (
          <p className="text-muted-foreground mt-0.5">{citation.kb_name}</p>
        )}
        {score != null && (
          <p className="text-muted-foreground mt-0.5">
            {(score * 100).toFixed(0)}%
          </p>
        )}
        {snippet && (
          <p className="text-muted-foreground line-clamp-3 mt-1 whitespace-pre-wrap">{snippet}</p>
        )}
        {(detailHref || previewHref) && (
          <div className="flex flex-wrap gap-2 mt-2">
            {detailHref && (
              <a
                href={detailHref}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                文件详情
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
            {previewHref && (
              <a
                href={previewHref}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                预览
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function normalizeRetrievedBlocks(value: unknown): RetrievedBlock[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is RetrievedBlock => Boolean(item && typeof item === "object"));
  }
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed)
        ? parsed.filter((item): item is RetrievedBlock => Boolean(item && typeof item === "object"))
        : [];
    } catch {
      return [];
    }
  }
  return [];
}

function RetrievedBlocks({ blocks }: { blocks: RetrievedBlock[] }) {
  if (blocks.length === 0) {
    return null;
  }

  return (
    <details className="w-full mt-2 rounded-lg border border-border/70 bg-muted/30 px-3 py-2">
      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
        Retrieved blocks ({blocks.length})
      </summary>
      <div className="mt-3 space-y-3">
        {blocks.map((block, index) => {
          const score = Number(block.similarity_score);
          const scoreText = Number.isFinite(score) ? score.toFixed(3) : "-";
          const filename = block.filename || "unknown";
          const kbName = block.kb_name || block.kb_id || "Unknown KB";
          const detailHref = block.file_detail_url || block.file_url;
          const previewHref = block.file_preview_url;
          const blockContent = block.content || block.quote || "(empty chunk)";

          return (
            <div key={`${block.chunk_id || filename}-${index}`} className="rounded-md border border-border/60 bg-background/80 p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <strong className="text-foreground">{filename}</strong>
                <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">KB: {kbName}</span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">Chunk: {block.chunk_id || "n/a"}</span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">Score: {scoreText}</span>
                {(detailHref || previewHref) && (
                  <span className="flex flex-wrap items-center gap-2 ml-auto">
                    {detailHref && (
                      <a
                        href={detailHref}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        文件详情
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                    {previewHref && (
                      <a
                        href={previewHref}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        预览
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </span>
                )}
              </div>
              <pre className="mt-3 whitespace-pre-wrap break-words rounded-md bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground overflow-x-auto">
                {blockContent}
              </pre>
            </div>
          );
        })}
      </div>
    </details>
  );
}

function MessageBubble({ message, index }: { message: Message; index: number }) {
  const isUser = message.role === "user";
  const retrievedBlocks = normalizeRetrievedBlocks(message.metadata?.retrieved_blocks);
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3) }}
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
        {!isUser && <RetrievedBlocks blocks={retrievedBlocks} />}
      </div>
    </motion.div>
  );
}

type SidebarTab = "conversations" | "documents";

export default function Chat() {
  const { t } = useTranslation();
  const { user, isLoggedIn } = useAuth();
  const isGuest = !isLoggedIn || user?.role === "guest";
  const GUEST_CHAT_QUOTA = 5;
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
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("conversations");
  const [showKbDropdown, setShowKbDropdown] = useState(false);
  const [showModeDropdown, setShowModeDropdown] = useState(false);
  const [documents, setDocuments] = useState<AvailableDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [docSearch, setDocSearch] = useState("");
  const [docCategory, setDocCategory] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [quotaWarning, setQuotaWarning] = useState<string | null>(null);
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
      const res = await apiGet<{ success?: boolean; data?: { conversations?: Conversation[] }; conversations?: Conversation[] }>("/api/chat/conversations");
      const convs = res.data?.conversations || res.conversations || [];
      setConversations(convs.map(c => ({
        ...c,
        id: c.id || c.conversation_id || "",
      })));
    } catch {
      setConversations([]);
    } finally {
      setLoadingConvs(false);
    }
  }

  async function loadKnowledgeBases() {
    try {
      const res = await apiGet<{ success?: boolean; data?: { knowledge_bases?: KnowledgeBase[] }; knowledge_bases?: KnowledgeBase[] }>("/api/chat/knowledge-bases");
      const nextKnowledgeBases = res.data?.knowledge_bases || res.knowledge_bases || [];
      setKnowledgeBases(nextKnowledgeBases);
      setSelectedKbs((prev) => prev.filter((kbId) => nextKnowledgeBases.some((kb) => kb.kb_id === kbId && kb.usable !== false)));
    } catch {
      setKnowledgeBases([]);
      setSelectedKbs([]);
    }
  }


  async function loadDocuments() {
    setLoadingDocs(true);
    try {
      let url = "/api/chat/available-documents";
      const params = new URLSearchParams();
      if (docCategory) params.set("category", docCategory);
      if (docSearch) params.set("keywords", docSearch);
      if (params.toString()) url += `?${params}`;

      const res = await apiGet<{ success?: boolean; data?: { documents?: AvailableDocument[] }; documents?: AvailableDocument[] }>(url);
      setDocuments(res.data?.documents || res.documents || []);
    } catch {
      setDocuments([]);
    } finally {
      setLoadingDocs(false);
    }
  }

  useEffect(() => {
    if (sidebarTab === "documents") {
      loadDocuments();
    }
  }, [sidebarTab]);

  function searchDocuments() {
    loadDocuments();
  }

  async function loadConversation(id: string) {
    setActiveConvId(id);
    setErrorMsg(null);
    try {
      const res = await apiGet<{ success?: boolean; data?: { messages?: Message[]; conversation?: Conversation }; messages?: Message[] }>(
        `/api/chat/conversations/${id}`
      );
      setMessages(res.data?.messages || res.messages || []);
    } catch {
      setMessages([]);
    }
  }

  async function createConversation() {
    setErrorMsg(null);
    try {
      const res = await apiPost<{ success?: boolean; data?: { conversation_id?: string; conversation?: Conversation }; conversation?: Conversation }>("/api/chat/conversations", {
        mode,
      });
      const newId = res.data?.conversation_id || res.data?.conversation?.id || res.conversation?.id;
      if (newId) {
        const newConv: Conversation = {
          id: newId,
          title: t("chat.new_conversation"),
          created_at: new Date().toISOString(),
        };
        setConversations((prev) => [newConv, ...prev]);
        setActiveConvId(newId);
        setMessages([]);
        setSidebarTab("conversations");
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

  async function askAboutDocument(doc: AvailableDocument) {
    const questionText = `${t("chat.explain_document")}: "${doc.title || doc.filename}"`;
    setInput(questionText);
    setSidebarTab("conversations");
    inputRef.current?.focus();
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;

    // Check guest quota
    if (isGuest) {
      const userMessageCount = messages.filter((m) => m.role === "user").length;
      if (userMessageCount >= GUEST_CHAT_QUOTA) {
        setQuotaWarning(t("chat.quota_exceeded"));
        return;
      }
      if (userMessageCount === GUEST_CHAT_QUOTA - 1) {
        setQuotaWarning(t("chat.quota_last_message"));
      }
    }

    setShowKbDropdown(false);
    setShowModeDropdown(false);
    setSending(true);
    setErrorMsg(null);
    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    try {
      const res = await apiPost<{
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
        res.data?.response || res.response || t("chat.no_response");
      const citations = res.data?.citations || res.citations || [];
      const retrievedBlocks = normalizeRetrievedBlocks(
        res.data?.retrieved_blocks ?? res.data?.metadata?.retrieved_blocks
      );

      if (res.data?.conversation_id && !activeConvId) {
        setActiveConvId(res.data.conversation_id);
        loadConversations();
      }

      const assistantMsg: Message = {
        role: "assistant",
        content: responseText,
        citations,
        metadata: {
          ...(res.data?.metadata || {}),
          retrieved_blocks: retrievedBlocks,
        },
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const errorDetail = err instanceof Error ? err.message : t("chat.error_sending");
      setErrorMsg(errorDetail);
      const assistantMsg: Message = {
        role: "assistant",
        content: errorDetail,
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
    const target = knowledgeBases.find((kb) => kb.kb_id === id);
    if (target?.usable === false) {
      return;
    }
    setSelectedKbs((prev) =>
      prev.includes(id) ? prev.filter((k) => k !== id) : [...prev, id]
    );
    setShowKbDropdown(false);
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] -mx-4 sm:-mx-6 -my-6 overflow-hidden">
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 300, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-r border-border bg-card flex flex-col shrink-0 overflow-hidden"
          >
            <div className="p-3 border-b border-border space-y-2">
              <div className="flex items-center gap-2">
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

              <div className="flex rounded-lg bg-muted p-0.5">
                <button
                  onClick={() => setSidebarTab("conversations")}
                  className={cn(
                    "flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-xs font-medium transition-colors",
                    sidebarTab === "conversations"
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                  data-testid="tab-conversations"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  {t("chat.tab_history")}
                </button>
                <button
                  onClick={() => setSidebarTab("documents")}
                  className={cn(
                    "flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-xs font-medium transition-colors",
                    sidebarTab === "documents"
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                  data-testid="tab-documents"
                >
                  <Database className="w-3.5 h-3.5" />
                  {t("chat.tab_documents")}
                </button>
              </div>
            </div>

            {sidebarTab === "conversations" ? (
              <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
                {loadingConvs ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                  </div>
                ) : conversations.length === 0 ? (
                  <div className="text-center py-8 px-4">
                    <MessageSquare className="w-10 h-10 mx-auto text-muted-foreground/30 mb-2" strokeWidth={1.2} />
                    <p className="text-sm text-muted-foreground">{t("chat.no_conversations")}</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">{t("chat.no_conversations_desc")}</p>
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
                      <div className="flex-1 min-w-0">
                        <span className="truncate block text-sm">{conv.title || t("chat.untitled")}</span>
                        {conv.created_at && (
                          <span className="text-[10px] text-muted-foreground">
                            {new Date(conv.created_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
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
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="p-2 space-y-2 border-b border-border">
                  <div className="flex gap-1.5">
                    <div className="relative flex-1">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                      <input
                        type="text"
                        value={docSearch}
                        onChange={(e) => setDocSearch(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && searchDocuments()}
                        placeholder={t("chat.search_documents")}
                        className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                        data-testid="input-doc-search"
                      />
                    </div>
                    <button
                      onClick={searchDocuments}
                      className="px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs hover:bg-primary/90 transition-colors"
                      data-testid="button-doc-search"
                    >
                      <Search className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <input
                    type="text"
                    value={docCategory}
                    onChange={(e) => setDocCategory(e.target.value)}
                    placeholder={t("chat.filter_category")}
                    className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-ring"
                    data-testid="input-doc-category"
                  />
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                  {loadingDocs ? (
                    <div className="flex justify-center py-8">
                      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : documents.length === 0 ? (
                    <div className="text-center py-8 px-4">
                      <Database className="w-10 h-10 mx-auto text-muted-foreground/30 mb-2" strokeWidth={1.2} />
                      <p className="text-sm text-muted-foreground">{t("chat.no_documents")}</p>
                      <p className="text-xs text-muted-foreground/60 mt-1">{t("chat.no_documents_desc")}</p>
                    </div>
                  ) : (
                    <>
                      <div className="text-[10px] text-muted-foreground px-2 py-1">
                        {documents.length} {t("chat.documents_available")}
                      </div>
                      {documents.map((doc, i) => (
                        <div
                          key={doc.file_url || i}
                          className="group flex items-start gap-2 px-3 py-2.5 rounded-lg hover:bg-muted cursor-pointer transition-colors"
                          onClick={() => askAboutDocument(doc)}
                          data-testid={`document-${i}`}
                        >
                          <FileText className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground group-hover:text-primary transition-colors" strokeWidth={1.5} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">
                              {doc.title || doc.filename}
                            </p>
                            <div className="flex items-center gap-2 mt-0.5">
                              {doc.category && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                                  {doc.category}
                                </span>
                              )}
                              {doc.keywords && doc.keywords.length > 0 && (
                                <span className="text-[10px] text-muted-foreground truncate">
                                  {doc.keywords.slice(0, 3).join(", ")}
                                </span>
                              )}
                            </div>
                          </div>
                          <Sparkles className="w-3.5 h-3.5 shrink-0 mt-1 text-muted-foreground/30 group-hover:text-primary transition-colors" />
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex flex-col min-w-0">
        {!sidebarOpen && (
          <div className="p-2 border-b border-border flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground"
              data-testid="button-open-chat-sidebar"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <span className="text-xs text-muted-foreground">{t("chat.show_sidebar")}</span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.4 }}
                className="max-w-md"
              >
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                  <Bot className="w-8 h-8 text-primary" />
                </div>
                <h2 className="text-xl font-serif font-bold mb-2">{t("chat.welcome")}</h2>
                <p className="text-sm text-muted-foreground mb-6">
                  {t("chat.welcome_desc")}
                </p>
                <div className="grid grid-cols-2 gap-2 text-left">
                  <button
                    onClick={() => {
                      setInput(t("chat.suggestion_1"));
                      setShowKbDropdown(false);
                      setShowModeDropdown(false);
                    }}
                    className="p-3 rounded-lg border border-border bg-card hover:border-primary/30 hover:bg-muted/50 transition-all text-xs text-muted-foreground"
                    data-testid="suggestion-1"
                  >
                    {t("chat.suggestion_1")}
                  </button>
                  <button
                    onClick={() => {
                      setInput(t("chat.suggestion_2"));
                      setShowKbDropdown(false);
                      setShowModeDropdown(false);
                    }}
                    className="p-3 rounded-lg border border-border bg-card hover:border-primary/30 hover:bg-muted/50 transition-all text-xs text-muted-foreground"
                    data-testid="suggestion-2"
                  >
                    {t("chat.suggestion_2")}
                  </button>
                </div>
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

        {errorMsg && (
          <div className="mx-4 sm:mx-6 mb-2 px-3 py-2 rounded-lg bg-destructive/10 text-destructive text-xs flex items-center gap-2">
            <span className="flex-1">{errorMsg}</span>
            <button onClick={() => setErrorMsg(null)} className="shrink-0">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        <div className="border-t border-border bg-card/80 backdrop-blur-sm px-4 sm:px-6 py-3">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <div className="relative">
              <button
                onClick={() => {
                  setShowModeDropdown(!showModeDropdown);
                  setShowKbDropdown(false);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-muted hover:bg-muted/80 transition-colors"
                data-testid="button-mode-selector"
              >
                {t(`chat.mode.${mode}`)}
                <ChevronDown className="w-3 h-3" />
              </button>
              {showModeDropdown && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowModeDropdown(false)} />
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
                </>
              )}
            </div>

            <div className="relative">
              <button
                onClick={() => {
                  setShowKbDropdown(!showKbDropdown);
                  setShowModeDropdown(false);
                }}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  selectedKbs.length > 0
                    ? "bg-primary/10 text-primary hover:bg-primary/15"
                    : "bg-muted hover:bg-muted/80"
                )}
                data-testid="button-kb-selector"
              >
                <BookOpen className="w-3 h-3" />
                {selectedKbs.length > 0
                  ? `${selectedKbs.length} ${t("chat.kbs_selected")}`
                  : t("chat.select_kb")}
                <ChevronDown className="w-3 h-3" />
              </button>
              {showKbDropdown && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowKbDropdown(false)} />
                  <div className="absolute bottom-full mb-1 left-0 z-50 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[220px] max-h-48 overflow-y-auto">
                    {knowledgeBases.length === 0 ? (
                      <div className="px-3 py-2 text-xs text-muted-foreground">
                        {t("chat.no_kbs")}
                      </div>
                    ) : (
                      knowledgeBases.map((kb) => {
                        const isSelected = selectedKbs.includes(kb.kb_id);
                        const isUsable = kb.usable !== false;
                        const availabilityLabel = kb.availability === "needs_reindex"
                          ? "需重建"
                          : kb.availability === "building"
                            ? "构建中"
                            : kb.availability === "ready"
                              ? "可用"
                              : kb.availability || "";
                        return (
                        <button
                          key={kb.kb_id}
                          onClick={() => toggleKb(kb.kb_id)}
                          disabled={!isUsable}
                          className={cn(
                            "w-full text-left px-3 py-2 text-xs transition-colors flex items-center gap-2",
                            isUsable ? "hover:bg-muted" : "opacity-60 cursor-not-allowed bg-muted/20",
                            isSelected && "text-primary font-medium"
                          )}
                          data-testid={`kb-option-${kb.kb_id}`}
                        >
                          <div
                            className={cn(
                              "w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0",
                              isSelected
                                ? "bg-primary border-primary"
                                : "border-border"
                            )}
                          >
                            {isSelected && (
                              <svg className="w-2.5 h-2.5 text-primary-foreground" viewBox="0 0 12 12">
                                <path d="M10 3L4.5 8.5 2 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <span className="truncate block">{kb.name}</span>
                            <div className="flex items-center gap-2 min-w-0">
                              {kb.description && (
                                <span className="text-[10px] text-muted-foreground truncate block">{kb.description}</span>
                              )}
                              {availabilityLabel && (
                                <span className={cn(
                                  "shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-medium",
                                  kb.availability === "ready" && "bg-emerald-500/10 text-emerald-600",
                                  kb.availability === "needs_reindex" && "bg-amber-500/10 text-amber-700",
                                  kb.availability === "building" && "bg-slate-500/10 text-slate-600"
                                )}>
                                  {availabilityLabel}
                                </span>
                              )}
                            </div>
                          </div>
                          {kb.chunk_count != null && (
                            <span className="text-[10px] text-muted-foreground shrink-0">{kb.chunk_count} chunks</span>
                          )}
                        </button>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="flex items-end gap-2">
            {quotaWarning && (
              <div className="w-full mb-1 px-2 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400 text-xs flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                {quotaWarning}
              </div>
            )}
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={() => { setShowKbDropdown(false); setQuotaWarning(null); }}
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
              type="button"
              aria-label="Send message"
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
