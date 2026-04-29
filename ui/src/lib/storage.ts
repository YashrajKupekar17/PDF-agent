import type { ChatMessage, Studio } from "./types";

const KEY = "pdf-agent:session:v1";

export type PersistedSession = {
  docId: string;
  filename: string;
  nPages: number;
  messages: ChatMessage[];
  sessionId: string;
  studio: Studio | null;
  page: number;
  updatedAt: number;
};

export function loadSession(): PersistedSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedSession;
  } catch {
    return null;
  }
}

export function saveSession(s: PersistedSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // quota / serialization — silently drop
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}
