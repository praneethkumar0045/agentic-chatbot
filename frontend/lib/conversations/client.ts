import { apiErrorFromResponse } from "@/lib/api/errors";
import { authenticatedFetch } from "@/lib/auth/client";

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Conversation = ConversationSummary & {
  messages: { role: "user" | "assistant"; content: string }[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(path, init);
  if (!response.ok) throw await apiErrorFromResponse(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function listConversations(): Promise<ConversationSummary[]> {
  return request("/conversations");
}

export function createConversation(title = "New conversation"): Promise<ConversationSummary> {
  return request("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export function getConversation(threadId: string): Promise<Conversation> {
  return request(`/conversations/${encodeURIComponent(threadId)}`);
}

export function deleteConversation(threadId: string): Promise<void> {
  return request(`/conversations/${encodeURIComponent(threadId)}`, { method: "DELETE" });
}
