import { useMemo, useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { ConsentEventPayload, MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: { code: string; message: string };
  correlationId: string;
};

type ChatResponseData = {
  response: string;
  sources?: Array<{ title: string; uri: string; excerpt?: string }>;
  confidence?: number;
  correlationId?: string;
};

export type BackendChatDemoProps = {
  apiBaseUrl?: string;
};

const buildId = (prefix: string) => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

async function postJson<T>(baseUrl: string, path: string, body: unknown): Promise<ApiEnvelope<T>> {
  const response = await fetch(joinUrl(baseUrl, path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error?.message || `Request failed with status ${response.status}`);
  }
  return envelope;
}

export function BackendChatDemo({ apiBaseUrl = "http://127.0.0.1:8000" }: BackendChatDemoProps) {
  const config = useMemo(
    () => ({
      ...foreverDemoConfig,
      provider: { name: "ASK Vera API", type: "custom-react" },
      policyLinks: foreverDemoConfig.policyLinks.map((link) => ({
        ...link,
        href: link.href.startsWith("/api/") ? joinUrl(apiBaseUrl, link.href) : link.href
      }))
    }),
    [apiBaseUrl]
  );
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: "backend-welcome",
      role: "assistant",
      content: "Accept the privacy terms, then ask a question. This demo sends messages to the Python API."
    }
  ]);
  const [loading, setLoading] = useState(false);

  const appendMessage = (message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  };

  const handleConsent = async (payload: ConsentEventPayload) => {
    try {
      await postJson(apiBaseUrl, "/api/consent", {
        sessionId: payload.sessionId,
        country: payload.selectedCountry,
        lang: payload.selectedLanguage,
        timestamp: payload.timestamp,
        version: payload.policyVersion
      });
    } catch (error) {
      appendMessage({
        id: buildId("consent-warning"),
        role: "system",
        content: error instanceof Error ? `Consent accepted locally, but the API could not record it: ${error.message}` : "Consent accepted locally, but the API could not record it."
      });
    }
  };

  const handleMessage = async (payload: MessageEventPayload) => {
    appendMessage({ id: buildId("user"), role: "user", content: payload.message });
    setLoading(true);
    try {
      const envelope = await postJson<ChatResponseData>(apiBaseUrl, "/api/chat", {
        message: payload.message,
        sessionId: payload.sessionId,
        country: payload.selectedCountry,
        language: payload.selectedLanguage,
        role: "new_prospect"
      });
      appendMessage({
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || "I could not find a response for that question.",
        metadata: {
          sources: envelope.data?.sources || [],
          confidence: envelope.data?.confidence,
          correlationId: envelope.data?.correlationId || envelope.correlationId
        }
      });
    } catch (error) {
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: error instanceof Error ? `The API is not ready yet: ${error.message}` : "The API is not ready yet."
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <GenericWidgetWrapper
      config={config}
      messages={messages}
      loading={loading}
      openByDefault
      onAcceptConsent={handleConsent}
      onSendMessage={handleMessage}
      onNewChat={() =>
        setMessages([
          {
            id: buildId("new-chat"),
            role: "assistant",
            content: "New chat started. Your selected market and language will stay active."
          }
        ])
      }
    />
  );
}
