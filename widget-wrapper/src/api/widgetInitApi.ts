import type { ApiClient } from "./client";

export type WidgetInitRequest = {
  widgetId: string;
  origin: string;
  resumeSessionId?: string;
};

export type WidgetInitResponseData = {
  token: string;
  sessionId: string;
};

export function initializeWidget(client: ApiClient, request: WidgetInitRequest) {
  return client.post<WidgetInitResponseData>("/api/widget/init", request);
}

export function refreshWidget(client: ApiClient, token: string) {
  return client.post<WidgetInitResponseData>("/api/widget/refresh", { token });
}
