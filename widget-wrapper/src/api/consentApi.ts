import type { ApiClient } from "./client";

export type ConsentRequest = {
  sessionId: string;
  country: string;
  lang: string;
  timestamp: string;
  version: string;
};

export type ConsentResponseData = Record<string, unknown>;

export function submitConsent(client: ApiClient, request: ConsentRequest) {
  return client.post<ConsentResponseData>("/api/consent", request);
}
