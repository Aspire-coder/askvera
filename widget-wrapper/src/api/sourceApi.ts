import type { ApiClient } from "./client";

export type SourceLinkRequest = {
  sessionId: string;
  country: string;
  language: string;
  uri: string;
  page?: string;
};

export function createSourceLink(client: ApiClient, request: SourceLinkRequest) {
  return client.post<{ url: string; expiresIn: number }>("/api/source-link", request);
}
