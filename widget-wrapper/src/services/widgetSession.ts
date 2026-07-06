import type { WidgetInitResponseData } from "../api";

export type WidgetAuthSession = WidgetInitResponseData & {
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
    const session = {
      ...response,
      expiresAt: Date.now() + response.expiresIn * 1000
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
