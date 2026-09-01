import type { WidgetInitResponseData } from "../api";
import { createLocalStorageAdapter, type StorageAdapter } from "../storage";

export type WidgetAuthSession = {
  token: string;
  widgetId?: string;
  sessionId?: string;
  resumeToken?: string;
  expiresAt: number;
};

const DEFAULT_STORAGE_KEY = "askvera_widget_auth_session";

export class WidgetSessionStore {
  constructor(
    private readonly storageKey = DEFAULT_STORAGE_KEY,
    // localStorage (not sessionStorage) so a second tab can resume the same
    // backend session instead of always minting a new one (TRB-19188).
    private readonly storage: StorageAdapter = createLocalStorageAdapter()
  ) {}

  read(): WidgetAuthSession | undefined {
    try {
      const raw = this.storage.getItem(this.storageKey);
      if (!raw) return undefined;
      return JSON.parse(raw) as WidgetAuthSession;
    } catch {
      return undefined;
    }
  }

  write(response: WidgetInitResponseData, previous?: WidgetAuthSession): WidgetAuthSession {
    const claims = decodeJwtPayload(response.token);
    const session = {
      token: response.token,
      widgetId: typeof claims.widgetId === "string" ? claims.widgetId : undefined,
      sessionId: response.sessionId || (typeof claims.sessionId === "string" ? claims.sessionId : undefined),
      resumeToken: response.resumeToken || previous?.resumeToken,
      expiresAt: typeof claims.exp === "number" ? claims.exp * 1000 : Date.now() + 15 * 60 * 1000
    };
    this.storage.setItem(this.storageKey, JSON.stringify(session));
    return session;
  }

  clear() {
    this.storage.removeItem(this.storageKey);
  }
}

export function createWidgetSessionStore(storageKey?: string, storage?: StorageAdapter) {
  return new WidgetSessionStore(storageKey, storage);
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
