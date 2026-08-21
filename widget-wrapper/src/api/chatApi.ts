import type { ApiClient } from "./client";

export type ChatRequest = {
  message: string;
  sessionId: string;
  country: string;
  language: string;
  role: string;
  trafficSource: "widget";
};

export type ChatSource = {
  title: string;
  uri: string;
  excerpt?: string;
  page?: string;
  section?: string;
  sectionTitle?: string;
  documentVersion?: string;
  country?: string;
  language?: string;
  score?: number;
};

export type ChatCard = {
  id: string;
  label: string;
  prompt: string;
};

export type ChatResponseData = {
  response: string;
  sources?: ChatSource[];
  confidence?: number;
  correlationId?: string;
  metadata?: Record<string, unknown>;
  cards?: ChatCard[];
};

export function sendMessage(client: ApiClient, request: ChatRequest) {
  return client.post<ChatResponseData>("/api/chat", request);
}

export function streamMessage() {
  throw new Error("Streaming chat is not implemented yet.");
}
