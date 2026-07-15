import type { ApiClient } from "./client";

export type FeedbackRequest = {
  sessionId: string;
  messageId?: string;
  rating?: number;
  comment?: string;
  requestType?: "feedback" | "support";
  metadata?: Record<string, unknown>;
};

export type FeedbackResponseData = { queued?: boolean; requestType?: string; ticketId?: string };

export function submitFeedback(client: ApiClient, request: FeedbackRequest) {
  return client.post<FeedbackResponseData>("/api/feedback", request);
}
