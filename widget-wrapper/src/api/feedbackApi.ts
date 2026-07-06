import type { ApiClient } from "./client";

export type FeedbackRequest = {
  sessionId: string;
  messageId?: string;
  rating?: number;
  comment?: string;
  metadata?: Record<string, unknown>;
};

export type FeedbackResponseData = Record<string, unknown>;

export function submitFeedback(client: ApiClient, request: FeedbackRequest) {
  return client.post<FeedbackResponseData>("/api/feedback", request);
}
