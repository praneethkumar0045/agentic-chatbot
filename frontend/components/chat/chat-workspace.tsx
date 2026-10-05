"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { authenticatedFetch } from "@/lib/auth/client";
import type { User } from "@/lib/auth/types";
import { API_BASE_URL } from "@/lib/api/config";

type Message = { role: "user" | "assistant"; content: string };
type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
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

function makeConversation(): Conversation {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    messages: [],
    updatedAt: Date.now(),
  };
}

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
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeConversation = conversations.find((item) => item.id === activeId);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("agentic-chat-conversations");
      const saved = stored ? (JSON.parse(stored) as Conversation[]) : [];
      if (Array.isArray(saved) && saved.length) {
        // Restore browser-persisted conversations after the client mounts.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setConversations(saved);
        setActiveId(saved[0].id);
      } else {
        const fresh = makeConversation();
        setConversations([fresh]);
        setActiveId(fresh.id);
      }
    } catch {
      const fresh = makeConversation();
      setConversations([fresh]);
      setActiveId(fresh.id);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready) localStorage.setItem("agentic-chat-conversations", JSON.stringify(conversations));
  }, [conversations, ready]);

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

  const startConversation = useCallback(() => {
    if (isLoading) return;
    const fresh = makeConversation();
    setConversations((items) => [fresh, ...items]);
    setActiveId(fresh.id);
    setDraft("");
    setError("");
    setSidebarOpen(false);
  }, [isLoading]);

  const sendMessage = async (event?: FormEvent, initialText?: string) => {
    event?.preventDefault();
    const content = (initialText ?? draft).trim();
    if (!content || isLoading || !activeConversation) return;

    const conversationId = activeConversation.id;
    const userMessage: Message = { role: "user", content };
    const assistantMessage: Message = { role: "assistant", content: "" };
    setDraft("");
    setError("");
    setIsLoading(true);
    setConversations((items) =>
      items.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              title: item.messages.length ? item.title : content.slice(0, 42),
              messages: [...item.messages, userMessage, assistantMessage],
              updatedAt: Date.now(),
            }
          : item,
      ),
    );

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await authenticatedFetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: conversationId,
          messages: [{ role: "user", content }],
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
            return { ...item, messages, updatedAt: Date.now() };
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
          const eventData = JSON.parse(data) as { content?: string; type?: string };
          if (eventData.type !== "tool") appendChunk(eventData.content ?? "");
        }
        if (done) break;
      }
      setIsOnline(true);
    } catch (caught) {
      const wasAborted = caught instanceof DOMException && caught.name === "AbortError";
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
      if (!wasAborted) {
        setError(caught instanceof Error ? caught.message : "Something went wrong.");
        setIsOnline(false);
      }
    } finally {
      abortRef.current = null;
      setIsLoading(false);
    }
  };

  const stopResponse = () => abortRef.current?.abort();

  return (
    <main className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-top">
          <a className="brand" href="#" aria-label="Medha home" onClick={() => startConversation()}>
            <span className="brand-mark"><Icon name="spark" size={19} /></span>
            <span>Medha</span>
          </a>
          <button className="icon-button mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
            <Icon name="close" />
          </button>
          <button className="new-chat-button" onClick={startConversation}>
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
              <button
                key={conversation.id}
                className={`conversation-item ${conversation.id === activeId ? "conversation-active" : ""}`}
                onClick={() => {
                  if (!isLoading) {
                    setActiveId(conversation.id);
                    setSidebarOpen(false);
                    setError("");
                  }
                }}
                title={conversation.title}
              >
                <span className="conversation-dot" />
                <span>{conversation.title}</span>
              </button>
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
          {activeConversation?.messages.length ? (
            <div className="messages">
              {activeConversation.messages.map((message, index) => (
                <div className={`message-row ${message.role === "user" ? "message-user" : "message-assistant"}`} key={`${activeConversation.id}-${index}`}>
                  {message.role === "assistant" && <div className="avatar avatar-assistant"><Icon name="spark" size={16} /></div>}
                  <div className={`message-content ${message.role === "user" ? "user-bubble" : ""}`}>
                    {message.content || (isLoading && index === activeConversation.messages.length - 1 ? <span className="typing"><i /><i /><i /></span> : null)}
                  </div>
                  {message.role === "user" && <div className="avatar avatar-user">Y</div>}
                </div>
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
                  <button className="suggestion-card" key={suggestion.title} onClick={() => sendMessage(undefined, suggestion.prompt)}>
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
          <form className="composer" onSubmit={(event) => sendMessage(event)}>
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
                <button className="send-button" type="submit" disabled={!draft.trim()} aria-label="Send message"><Icon name="send" size={17} /></button>
              )}
            </div>
          </form>
          <p className="disclaimer">Medha can make mistakes. Consider checking important information.</p>
        </div>
      </section>
    </main>
  );
}
