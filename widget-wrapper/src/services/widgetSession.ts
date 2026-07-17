import type { WidgetInitResponseData } from "../api";

export type WidgetAuthSession = {
  token: string;
  widgetId?: string;
  sessionId?: string;
  expiresAt: number;
};

const DEFAULT_STORAGE_KEY = "askvera_widget_auth_session";

export class WidgetSessionStore {
  constructor(private readonly storageKey = DEFAULT_STORAGE_KEY) {}

  read(): WidgetAuthSession | undefined {
    try {
      const raw = window.sessionStorage.getItem(this.storageKey);
      if (!raw) return undefined;
      const session = JSON.parse(raw) as WidgetAuthSession;
      if (!session.expiresAt || session.expiresAt <= Date.now()) {
        this.clear();
        return undefined;
      }
      return session;
    } catch {
      return undefined;
    }
  }

  write(response: WidgetInitResponseData): WidgetAuthSession {
    const claims = decodeJwtPayload(response.token);
    const session = {
      token: response.token,
      widgetId: typeof claims.widgetId === "string" ? claims.widgetId : undefined,
      sessionId: response.sessionId || (typeof claims.sessionId === "string" ? claims.sessionId : undefined),
      expiresAt: typeof claims.exp === "number" ? claims.exp * 1000 : Date.now() + 15 * 60 * 1000
    };
    window.sessionStorage.setItem(this.storageKey, JSON.stringify(session));
    return session;
  }

  clear() {
    window.sessionStorage.removeItem(this.storageKey);
  }
}

export function createWidgetSessionStore(storageKey?: string) {
  return new WidgetSessionStore(storageKey);
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const payload = token.split(".")[1];
    if (!payload) return {};
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + (4 - normalized.length % 4) % 4, "=");
    return JSON.parse(window.atob(padded)) as Record<string, unknown>;
  } catch {
    return {};
  }
}
