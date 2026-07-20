import type { ApiClient } from "./client";

export type SupportRequest = {
  sessionId: string;
  messageId?: string;
  firstName: string;
  email: string;
  question: string;
  country: string;
  language: string;
};

export type SupportResponseData = {
  submitted: boolean;
  ticketId: string;
  department: string;
};

export function submitSupportRequest(client: ApiClient, request: SupportRequest) {
  return client.post<SupportResponseData>("/api/support", request);
}
