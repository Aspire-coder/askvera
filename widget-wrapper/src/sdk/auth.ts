import { createApiClient, initializeWidget, refreshWidget } from "../api";
import { createWidgetSessionStore, type WidgetAuthSession } from "../services";
import { TOKEN_REFRESH_WINDOW_MS } from "../constants";
import { getCurrentOrigin } from "../utils/browser";
import type { AskVeraRuntimeConfig } from "./AskVera";

export type WidgetAuthResult = {
  token?: string;
  expiresAt?: number;
  session?: WidgetAuthSession;
};

export type WidgetAuthOptions = {
  forceNew?: boolean;
};

export async function authenticateWidget(config: AskVeraRuntimeConfig, options: WidgetAuthOptions = {}): Promise<WidgetAuthResult> {
  if (!config.widgetId) {
    return {};
  }

  const store = createWidgetSessionStore(config.widgetAuthStorageKey);
  if (options.forceNew) {
    store.clear();
  }
  const existing = store.read();
  if (existing && existing.widgetId === config.widgetId && existing.expiresAt - Date.now() > TOKEN_REFRESH_WINDOW_MS) {
    return { token: existing.token, expiresAt: existing.expiresAt, session: existing };
  }

  const client = createApiClient({ baseUrl: config.apiUrl });
  if (existing && existing.widgetId === config.widgetId) {
    try {
      const refreshEnvelope = await refreshWidget(client, existing.token);
      if (refreshEnvelope.data) {
        const refreshed = store.write(refreshEnvelope.data);
        return { token: refreshed.token, expiresAt: refreshed.expiresAt, session: refreshed };
      }
    } catch {
      store.clear();
    }
  }

  const envelope = await initializeWidget(client, {
    widgetId: config.widgetId,
    origin: getCurrentOrigin()
  });
  if (!envelope.data) {
    throw new Error("Widget initialization did not return a session token.");
  }
  const session = store.write(envelope.data);
  return { token: session.token, expiresAt: session.expiresAt, session };
}

/**
 * Renews the in-memory widget token after a protected API request receives a
 * 401. If the old token cannot be renewed, initialization is used as the
 * normal, origin-validated fallback.
 */
export async function renewWidgetAuth(config: AskVeraRuntimeConfig, currentToken?: string): Promise<WidgetAuthResult> {
  if (!config.widgetId) {
    return {};
  }

  const store = createWidgetSessionStore(config.widgetAuthStorageKey);
  const client = createApiClient({ baseUrl: config.apiUrl });

  if (currentToken) {
    try {
      const refreshEnvelope = await refreshWidget(client, currentToken);
      if (refreshEnvelope.data) {
        const session = store.write(refreshEnvelope.data);
        return { token: session.token, expiresAt: session.expiresAt, session };
      }
    } catch {
      // A fully expired token cannot be refreshed. Initialize a new session below.
    }
  }

  const envelope = await initializeWidget(client, {
    widgetId: config.widgetId,
    origin: getCurrentOrigin()
  });
  if (!envelope.data) {
    throw new Error("Widget initialization did not return a session token.");
  }
  const session = store.write(envelope.data);
  return { token: session.token, expiresAt: session.expiresAt, session };
}
