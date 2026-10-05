import { API_BASE_URL } from "@/lib/api/config";
import { apiErrorFromResponse } from "@/lib/api/errors";
import type { AccessSession, LoginInput, RegisterInput, User } from "@/lib/auth/types";

let session: AccessSession | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let refreshInFlight: Promise<AccessSession> | undefined;
let sessionVersion = 0;
const sessionListeners = new Set<(active: boolean) => void>();

function notifySession(active: boolean) {
  for (const listener of sessionListeners) listener(active);
}

function clearSession() {
  session = null;
  sessionVersion += 1;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = undefined;
  notifySession(false);
}

function setSession(nextSession: AccessSession) {
  session = nextSession;
  sessionVersion += 1;
  if (refreshTimer) clearTimeout(refreshTimer);

  const refreshDelay = Math.max(1_000, (nextSession.expires_in - 60) * 1_000);
  refreshTimer = setTimeout(() => {
    void refreshSession().catch(() => undefined);
  }, refreshDelay);
  notifySession(true);
}

export function subscribeToSession(listener: (active: boolean) => void) {
  sessionListeners.add(listener);
  return () => {
    sessionListeners.delete(listener);
  };
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: body === undefined ? { Accept: "application/json" } : {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    cache: "no-store",
  });
  if (!response.ok) throw await apiErrorFromResponse(response);
  return response.json() as Promise<T>;
}

export async function register(input: RegisterInput): Promise<User> {
  return postJson<User>("/api/auth/register", {
    name: input.name.trim(),
    email: input.email.trim().toLowerCase(),
    password: input.password,
  });
}

export async function login(input: LoginInput): Promise<void> {
  const nextSession = await postJson<AccessSession>("/api/auth/login", {
    email: input.email.trim().toLowerCase(),
    password: input.password,
  });
  setSession(nextSession);
}

export async function refreshSession(): Promise<AccessSession> {
  if (refreshInFlight) return refreshInFlight;

  const requestVersion = sessionVersion;
  refreshInFlight = postJson<AccessSession>("/api/auth/refresh", {})
    .then((nextSession) => {
      if (sessionVersion !== requestVersion) {
        throw new Error("Your session has changed. Please sign in again.");
      }
      setSession(nextSession);
      return nextSession;
    })
    .catch((error: unknown) => {
      if (sessionVersion === requestVersion) clearSession();
      throw error;
    })
    .finally(() => {
      refreshInFlight = undefined;
    });

  return refreshInFlight;
}

export async function getCurrentUser(): Promise<User> {
  const response = await authenticatedFetch("/auth/me");
  if (!response.ok) throw await apiErrorFromResponse(response);
  return response.json() as Promise<User>;
}

export async function authenticatedFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const send = (accessToken: string) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${accessToken}`);
    return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  };

  if (!session) throw new Error("Please sign in to continue.");
  let response = await send(session.access_token);
  if (response.status !== 401) return response;

  const refreshed = await refreshSession();
  response = await send(refreshed.access_token);
  if (response.status === 401) clearSession();
  return response;
}

export async function logout(): Promise<void> {
  try {
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok && response.status !== 401) {
      throw await apiErrorFromResponse(response);
    }
  } finally {
    clearSession();
  }
}
