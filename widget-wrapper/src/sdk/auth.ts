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

export async function authenticateWidget(config: AskVeraRuntimeConfig): Promise<WidgetAuthResult> {
  if (!config.widgetId || !config.publishableKey) {
    return {};
  }

  const store = createWidgetSessionStore(config.widgetAuthStorageKey);
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
    publishableKey: config.publishableKey,
    origin: getCurrentOrigin()
  });
  if (!envelope.data) {
    throw new Error("Widget initialization did not return a session token.");
  }
  const session = store.write(envelope.data);
  return { token: session.token, expiresAt: session.expiresAt, session };
}
