"use client";

import { FormEvent, memo, useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { authenticatedFetch } from "@/lib/auth/client";
import type { User } from "@/lib/auth/types";
import { API_BASE_URL } from "@/lib/api/config";
import {
  createConversation as createConversationRequest,
  deleteConversation as deleteConversationRequest,
  getConversation,
  listConversations,
  type ConversationSummary,
} from "@/lib/conversations/client";

type Message = { role: "user" | "assistant"; content: string };
type PendingApproval = { type: "approval_required"; tool: string; query: string };
type Conversation = ConversationSummary & {
  messages: Message[];
  pending_approval?: PendingApproval | null;
};

const markdownComponents: Components = {
  table: ({ children, ...props }) => (
    <div className="markdown-table-wrap">
      <table {...props}>{children}</table>
    </div>
  ),
};

const suggestions = [
  { icon: "✦", title: "Brainstorm ideas", prompt: "Help me brainstorm ideas for a new project." },
  { icon: "⌘", title: "Write something", prompt: "Help me write a clear and engaging introduction." },
  { icon: "↗", title: "Learn something", prompt: "Explain a complex topic in a simple way." },
  { icon: "⌕", title: "Solve a problem", prompt: "Help me think through a problem step by step." },
];

function Icon({
  name,
  size = 18,
}: {
  name: "spark" | "plus" | "chevron" | "send" | "stop" | "menu" | "close";
  size?: number;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };

  if (name === "spark")
    return <svg {...common}><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" /><path d="m19 16 .9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9L19 16Z" /></svg>;
  if (name === "plus")
    return <svg {...common}><path d="M12 5v14M5 12h14" /></svg>;
  if (name === "chevron")
    return <svg {...common}><path d="m9 18 6-6-6-6" /></svg>;
  if (name === "send")
    return <svg {...common}><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg>;
  if (name === "stop")
    return <svg {...common}><rect x="6" y="6" width="12" height="12" rx="2" /></svg>;
  if (name === "menu")
    return <svg {...common}><path d="M4 6h16M4 12h16M4 18h16" /></svg>;
  return <svg {...common}><path d="m18 6-12 12M6 6l12 12" /></svg>;
}

const ChatMessageRow = memo(function ChatMessageRow({
  message,
  isLoadingLast,
  toolStatus,
  pendingApproval,
  approvalBusy,
  onApproval,
}: {
  message: Message;
  isLoadingLast: boolean;
  toolStatus: string;
  pendingApproval: PendingApproval | null;
  approvalBusy: boolean;
  onApproval: (decision: "approve" | "reject") => void;
}) {
  return (
    <div className={`message-row ${message.role === "user" ? "message-user" : "message-assistant"}`}>
      {message.role === "assistant" && <div className="avatar avatar-assistant"><Icon name="spark" size={16} /></div>}
      <div className={`message-content ${message.role === "user" ? "user-bubble" : "markdown-body"}`}>
        {message.role === "assistant" && message.content ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {message.content}
          </ReactMarkdown>
        ) : message.content ? (
          message.content
        ) : isLoadingLast ? (
          toolStatus ? (
            <span className="tool-status" role="status">
              <span className="tool-status-spinner" aria-hidden="true" />
              <span>{toolStatus}</span>
            </span>
          ) : (
            <span className="typing"><i /><i /><i /></span>
          )
        ) : null}
        {pendingApproval && (
          <div className="approval-card">
            <strong>Approve web search?</strong>
            <span>Medha wants to search the web for:</span>
            <q>{pendingApproval.query}</q>
            <div className="approval-actions">
              <button type="button" disabled={approvalBusy} onClick={() => onApproval("reject")}>Reject</button>
              <button type="button" disabled={approvalBusy} onClick={() => onApproval("approve")}>Approve search</button>
            </div>
          </div>
        )}
      </div>
      {message.role === "user" && <div className="avatar avatar-user">Y</div>}
    </div>
  );
});

export function ChatWorkspace({
  user,
  onSignOut,
}: {
  user: User;
  onSignOut: () => Promise<void>;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [toolStatus, setToolStatus] = useState("");
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isConversationBusy, setIsConversationBusy] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeConversation = conversations.find((item) => item.id === activeId);

  const withPendingPlaceholder = (conversation: Awaited<ReturnType<typeof getConversation>>): Conversation => ({
    ...conversation,
    messages:
      conversation.pending_approval &&
      conversation.messages[conversation.messages.length - 1]?.role !== "assistant"
        ? [...conversation.messages, { role: "assistant", content: "" }]
        : conversation.messages,
  });

  useEffect(() => {
    let cancelled = false;
    const loadConversations = async () => {
      try {
        let summaries = await listConversations();
        if (summaries.length === 0) {
          summaries = [await createConversationRequest()];
        }
        if (cancelled) return;
        setConversations(summaries.map((conversation) => ({ ...conversation, messages: [] })));
        setActiveId(summaries[0].id);
        const detail = await getConversation(summaries[0].id);
        if (!cancelled) {
          setConversations((items) =>
            items.map((conversation) =>
              conversation.id === detail.id ? withPendingPlaceholder(detail) : conversation,
            ),
          );
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Unable to load your conversations.");
        }
      } finally {
        if (!cancelled) setIsConversationBusy(false);
      }
    };
    void loadConversations();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/health`, { signal: controller.signal })
      .then((response) => setIsOnline(response.ok))
      .catch(() => setIsOnline(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation?.messages]);

  const startConversation = useCallback(async () => {
    if (isLoading || isConversationBusy) return;
    setIsConversationBusy(true);
    setError("");
    try {
      const created = await createConversationRequest();
      setConversations((items) => [{ ...created, messages: [] }, ...items]);
      setActiveId(created.id);
      setDraft("");
      setSidebarOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create a conversation.");
    } finally {
      setIsConversationBusy(false);
    }
  }, [isConversationBusy, isLoading]);

  const selectConversation = async (conversationId: string) => {
    if (isLoading || isConversationBusy || conversationId === activeId) return;
    setActiveId(conversationId);
    setSidebarOpen(false);
    setError("");
    setIsConversationBusy(true);
    try {
      const detail = await getConversation(conversationId);
      setConversations((items) =>
        items.map((conversation) =>
          conversation.id === detail.id ? withPendingPlaceholder(detail) : conversation,
        ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load this conversation.");
    } finally {
      setIsConversationBusy(false);
    }
  };

  const removeConversation = async (conversationId: string) => {
    if (isLoading || isConversationBusy || !window.confirm("Delete this conversation?")) return;
    setIsConversationBusy(true);
    setError("");
    try {
      await deleteConversationRequest(conversationId);
      const remaining = conversations.filter((conversation) => conversation.id !== conversationId);
      if (remaining.length === 0) {
        const created = await createConversationRequest();
        setConversations([{ ...created, messages: [] }]);
        setActiveId(created.id);
      } else {
        setConversations(remaining);
        if (activeId === conversationId) {
          setActiveId(remaining[0].id);
          const detail = await getConversation(remaining[0].id);
          setConversations((items) =>
            items.map((conversation) =>
              conversation.id === detail.id ? withPendingPlaceholder(detail) : conversation,
            ),
          );
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to delete this conversation.");
    } finally {
      setIsConversationBusy(false);
    }
  };

  const sendMessage = async (
    event?: FormEvent,
    initialText?: string,
    approvalDecision?: "approve" | "reject",
  ) => {
    event?.preventDefault();
    const content = (initialText ?? draft).trim();
    const isResuming = approvalDecision !== undefined;
    if ((!isResuming && !content) || isLoading || isConversationBusy || !activeConversation) return;
    if (isResuming && !activeConversation.pending_approval) return;

    const conversationId = activeConversation.id;
    const userMessage: Message = { role: "user", content };
    const assistantMessage: Message = { role: "assistant", content: "" };
    if (!isResuming) setDraft("");
    setError("");
    setToolStatus("");
    setIsLoading(true);
    if (!isResuming) {
      setConversations((items) =>
        items.map((item) =>
          item.id === conversationId
            ? {
                ...item,
                title: item.messages.length ? item.title : content.slice(0, 42),
                updated_at: new Date().toISOString(),
                messages: [...item.messages, userMessage, assistantMessage],
              }
            : item,
        ),
      );
    }

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await authenticatedFetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: conversationId,
          ...(isResuming
            ? { messages: [], approval_decision: approvalDecision }
            : { messages: [{ role: "user", content }] }),
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Request failed (${response.status})`);
      }
      if (!response.body) throw new Error("The server did not return a response stream.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const appendChunk = (chunk: string) => {
        if (!chunk) return;
        setConversations((items) =>
          items.map((item) => {
            if (item.id !== conversationId) return item;
            const messages = [...item.messages];
            const last = messages[messages.length - 1];
            if (last?.role === "assistant") {
              messages[messages.length - 1] = { ...last, content: last.content + chunk };
            }
            return { ...item, messages, updated_at: new Date().toISOString() };
          }),
        );
      };

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const eventText of events) {
          const data = eventText
            .split("\n")
            .find((line) => line.startsWith("data: "))
            ?.slice(6);
          if (!data) continue;
          const eventData = JSON.parse(data) as {
            content?: string;
            type?: string;
            tool?: string;
            query?: string;
          };
          if (eventData.type === "status") {
            setToolStatus(eventData.content ?? "");
          } else if (eventData.type === "approval_required") {
            setToolStatus("");
            setConversations((items) =>
              items.map((item) =>
                item.id === conversationId
                  ? {
                      ...item,
                      pending_approval: {
                        type: "approval_required",
                        tool: eventData.tool ?? "tavily_search",
                        query: eventData.query ?? "",
                      },
                    }
                  : item,
              ),
            );
          } else if (eventData.type === "message") {
            setToolStatus("");
            setConversations((items) =>
              items.map((item) =>
                item.id === conversationId ? { ...item, pending_approval: null } : item,
              ),
            );
            appendChunk(eventData.content ?? "");
          }
        }
        if (done) break;
      }
      setIsOnline(true);
      try {
        const summaries = await listConversations();
        setConversations((items) =>
          summaries.map((summary) => ({
            ...summary,
            messages: items.find((item) => item.id === summary.id)?.messages ?? [],
            pending_approval:
              items.find((item) => item.id === summary.id)?.pending_approval ?? null,
          })),
        );
      } catch {
        setError("Your reply arrived, but the conversation list could not be refreshed.");
      }
    } catch (caught) {
      const wasAborted = caught instanceof DOMException && caught.name === "AbortError";
      if (!isResuming) {
        setConversations((items) =>
          items.map((item) =>
            item.id === conversationId
              ? {
                  ...item,
                  messages: item.messages.filter(
                    (message, index) =>
                      !(index === item.messages.length - 1 && message.role === "assistant" && !message.content),
                  ),
                }
              : item,
          ),
        );
      }
      if (!wasAborted) {
        setError(caught instanceof Error ? caught.message : "Something went wrong.");
        setIsOnline(false);
      }
    } finally {
      abortRef.current = null;
      setToolStatus("");
      setIsLoading(false);
    }
  };

  const respondToApproval = (decision: "approve" | "reject") => {
    void sendMessage(undefined, undefined, decision);
  };

  const stopResponse = () => abortRef.current?.abort();

  return (
    <main className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-top">
          <a className="brand" href="#" aria-label="Medha home" onClick={(event) => { event.preventDefault(); void startConversation(); }}>
            <span className="brand-mark"><Icon name="spark" size={19} /></span>
            <span>Medha</span>
          </a>
          <button className="icon-button mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
            <Icon name="close" />
          </button>
          <button className="new-chat-button" onClick={() => void startConversation()} disabled={isConversationBusy || isLoading}>
            <Icon name="plus" size={17} />
            <span>New conversation</span>
            <kbd>⌘ K</kbd>
          </button>
          <div className="nav-label">WORKSPACE</div>
          <div className="workspace-link">
            <span className="workspace-icon">✳</span>
            <span>Personal space</span>
            <span className="workspace-chevron">⌄</span>
          </div>
          <div className="nav-label history-label">YOUR CHATS</div>
          <div className="conversation-list">
            {conversations.map((conversation) => (
              <div className="conversation-entry" key={conversation.id}>
                <button
                  className={`conversation-item ${conversation.id === activeId ? "conversation-active" : ""}`}
                  onClick={() => void selectConversation(conversation.id)}
                  disabled={isLoading || isConversationBusy}
                  title={conversation.title}
                >
                  <span className="conversation-dot" />
                  <span>{conversation.title}</span>
                </button>
                <button
                  className="conversation-delete"
                  type="button"
                  aria-label={`Delete ${conversation.title}`}
                  title="Delete conversation"
                  disabled={isLoading || isConversationBusy}
                  onClick={() => void removeConversation(conversation.id)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
        <div className="sidebar-bottom">
          <div className="plan-card">
            <div className="plan-icon"><Icon name="spark" size={16} /></div>
            <div><strong>Your ideas, in motion.</strong><span>A thoughtful AI, ready when you are.</span></div>
          </div>
          <div className="profile-row">
            <div className="avatar avatar-user">{user.name.slice(0, 1).toUpperCase()}</div>
            <div className="profile-copy"><strong>{user.name}</strong><span>{user.email}</span></div>
            <button className="profile-menu" type="button" onClick={() => void onSignOut()} aria-label="Sign out" title="Sign out">↪</button>
          </div>
        </div>
      </aside>

      {sidebarOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setSidebarOpen(false)} />}
      <section className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setSidebarOpen(true)}>
            <Icon name="menu" />
          </button>
          <div className="model-select"><span className="model-indicator" /><span>Medha 1.0</span><span className="model-beta">BETA</span><span className="model-caret">⌄</span></div>
          <div className="topbar-right">
            <span className={`connection ${isOnline === false ? "connection-offline" : ""}`}>
              <span className="connection-dot" />{isOnline === null ? "Connecting" : isOnline ? "All systems normal" : "API unavailable"}
            </span>
            <button className="help-button" aria-label="Help">?</button>
          </div>
        </header>

        <div className={`chat-area ${activeConversation?.messages.length ? "chat-area-active" : ""}`}>
          {isConversationBusy && !activeConversation ? (
            <div className="welcome-loading">Loading your conversations…</div>
          ) : activeConversation?.messages.length ? (
            <div className="messages">
              {activeConversation.messages.map((message, index) => (
                <ChatMessageRow
                  key={`${activeConversation.id}-${index}`}
                  message={message}
                  isLoadingLast={isLoading && index === activeConversation.messages.length - 1}
                  toolStatus={index === activeConversation.messages.length - 1 ? toolStatus : ""}
                  pendingApproval={
                    index === activeConversation.messages.length - 1
                      ? activeConversation.pending_approval ?? null
                      : null
                  }
                  approvalBusy={isLoading}
                  onApproval={respondToApproval}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          ) : (
            <div className="welcome">
              <div className="welcome-orbit">
                <span className="orbit orbit-one" /><span className="orbit orbit-two" />
                <div className="welcome-mark"><Icon name="spark" size={27} /></div>
                <span className="orbit-dot orbit-dot-one" /><span className="orbit-dot orbit-dot-two" />
              </div>
              <div className="eyebrow"><span /> A LITTLE MORE CLARITY, EVERY DAY</div>
              <h1>Good ideas start<br />with a <em>conversation.</em></h1>
              <p className="welcome-subtitle">I’m Medha. Bring a question, a half-formed thought,<br className="desktop-break" /> or something you’re curious about.</p>
              <div className="suggestions">
                {suggestions.map((suggestion) => (
                  <button className="suggestion-card" key={suggestion.title} onClick={() => void sendMessage(undefined, suggestion.prompt)} disabled={isConversationBusy}>
                    <span className="suggestion-icon">{suggestion.icon}</span>
                    <span><strong>{suggestion.title}</strong><small>{suggestion.prompt}</small></span>
                    <Icon name="chevron" size={16} />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="composer-wrap">
          {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
          <form className="composer" onSubmit={(event) => void sendMessage(event)}>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder="Ask anything, or just start with a thought..."
              rows={1}
              aria-label="Your message"
            />
            <div className="composer-footer">
              <div className="composer-hint"><span className="hint-spark">✳</span> Thoughtful answers, one prompt at a time</div>
              {isLoading ? (
                <button className="send-button stop-button" type="button" onClick={stopResponse} aria-label="Stop response"><Icon name="stop" size={17} /></button>
              ) : (
                <button className="send-button" type="submit" disabled={!draft.trim() || isConversationBusy} aria-label="Send message"><Icon name="send" size={17} /></button>
              )}
            </div>
          </form>
          <p className="disclaimer">Medha can make mistakes. Consider checking important information.</p>
        </div>
      </section>
    </main>
  );
}
