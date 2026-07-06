import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildWidgetConfig, type BackendConfig } from "../../config";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { ConsentEventPayload, MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: { code: string; message: string; legalVersion?: string };
  correlationId: string;
};

class ApiRequestError extends Error {
  code?: string;
  legalVersion?: string;
  status?: number;
  correlationId?: string;

  constructor(message: string, code?: string, legalVersion?: string, status?: number, correlationId?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.legalVersion = legalVersion;
    this.status = status;
    this.correlationId = correlationId;
  }
}

class ApiTimeoutError extends Error {
  constructor(message = "The request timed out. Please try again.") {
    super(message);
    this.name = "ApiTimeoutError";
  }
}

class ApiNetworkError extends Error {
  constructor(message = "The API could not be reached. Please check the connection and try again.") {
    super(message);
    this.name = "ApiNetworkError";
  }
}

type ChatResponseData = {
  response: string;
  sources?: Array<{ title: string; uri: string; excerpt?: string }>;
  confidence?: number;
  correlationId?: string;
};

type ApiCountry = {
  code: string;
  name: string;
  languages: Array<{ code: string; name: string }>;
};

type ConfigResponseData = {
  countries: ApiCountry[];
  privacyVersion: string;
};

type LegalDocument = {
  id: string;
  title: string;
  required: boolean;
  html: string;
};

type PrivacyResponseData = {
  version: string;
  documents: LegalDocument[];
};

export type BackendChatDemoProps = {
  apiBaseUrl?: string;
};

const REQUEST_TIMEOUT_MS = 30000;

const buildId = (prefix: string) => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

const legalViewerHref = (apiBaseUrl: string, country: string, language: string, documentId: string) => {
  const params = new URLSearchParams({
    api: apiBaseUrl,
    country,
    lang: language,
    doc: documentId
  });
  return `/legal?${params.toString()}`;
};

async function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiTimeoutError();
    }
    throw new ApiNetworkError(error instanceof Error ? error.message : undefined);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  try {
    return (await response.json()) as ApiEnvelope<T>;
  } catch {
    return {
      success: false,
      correlationId: response.headers.get("x-correlation-id") || "",
      error: { code: "INVALID_RESPONSE", message: "The API returned an unreadable response." }
    };
  }
}

async function postJson<T>(baseUrl: string, path: string, body: unknown): Promise<ApiEnvelope<T>> {
  const response = await fetchWithTimeout(joinUrl(baseUrl, path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const envelope = await parseEnvelope<T>(response);
  if (!response.ok || !envelope.success) {
    throw new ApiRequestError(
      envelope.error?.message || `Request failed with status ${response.status}`,
      envelope.error?.code,
      envelope.error?.legalVersion,
      response.status,
      envelope.correlationId || response.headers.get("x-correlation-id") || undefined
    );
  }
  return envelope;
}

async function getJson<T>(baseUrl: string, path: string): Promise<ApiEnvelope<T>> {
  const response = await fetchWithTimeout(joinUrl(baseUrl, path));
  const envelope = await parseEnvelope<T>(response);
  if (!response.ok || !envelope.success) {
    throw new ApiRequestError(
      envelope.error?.message || `Request failed with status ${response.status}`,
      envelope.error?.code,
      envelope.error?.legalVersion,
      response.status,
      envelope.correlationId || response.headers.get("x-correlation-id") || undefined
    );
  }
  return envelope;
}

function describeApiError(error: unknown): string {
  if (error instanceof ApiTimeoutError) {
    return "The request timed out. Please try again in a moment.";
  }
  if (error instanceof ApiNetworkError) {
    return `The API could not be reached: ${error.message}`;
  }
  if (error instanceof ApiRequestError) {
    const status = error.status ? `HTTP ${error.status}` : "API error";
    return `${status}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected API error occurred.";
}

function logCorrelationId(label: string, correlationId?: string) {
  if (!correlationId || window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") return;
  console.info(`[ASK Vera] ${label} correlation ID: ${correlationId}`);
}

export function BackendChatDemo({ apiBaseUrl = "https://api.vera-api.xyz" }: BackendChatDemoProps) {
  const [apiConfig, setApiConfig] = useState<ConfigResponseData | null>(null);
  const [selectedLocale, setSelectedLocale] = useState({ country: "US", language: "en" });
  const [legalDocuments, setLegalDocuments] = useState<LegalDocument[]>([]);
  const [legalVersion, setLegalVersion] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<MessageEventPayload | null>(null);
  const [consentRequiredSignal, setConsentRequiredSignal] = useState(0);
  const requestInFlightRef = useRef(false);
  const config = useMemo(
    () => {
      const backendConfig: BackendConfig | undefined = apiConfig
        ? {
            countries: apiConfig.countries,
            privacyVersion: legalVersion || apiConfig.privacyVersion,
            legalDocuments
          }
        : undefined;

      return buildWidgetConfig({
        baseConfig: foreverDemoConfig,
        runtimeConfig: {
          apiUrl: apiBaseUrl,
          companyName: foreverDemoConfig.brandName,
          defaultCountry: selectedLocale.country,
          defaultLanguage: selectedLocale.language,
          theme: foreverDemoConfig.theme
        },
        backendConfig,
        selectedCountry: selectedLocale.country,
        selectedLanguage: selectedLocale.language,
        legalLinkBuilder: legalViewerHref
      }).genericConfig;
    },
    [apiBaseUrl, apiConfig, legalDocuments, legalVersion, selectedLocale.country, selectedLocale.language]
  );
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: "backend-welcome",
      role: "assistant",
      content: "Accept the privacy terms, then ask a question. This demo sends messages to the Python API."
    }
  ]);
  const [loading, setLoading] = useState(false);

  const appendMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  }, []);

  const upsertMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => {
      const existingIndex = current.findIndex((item) => item.id === message.id);
      if (existingIndex === -1) return [...current, message];
      return current.map((item, index) => (index === existingIndex ? message : item));
    });
  }, []);

  useEffect(() => {
    let active = true;

    getJson<ConfigResponseData>(apiBaseUrl, "/api/config")
      .then((envelope) => {
        if (active && envelope.data) {
          logCorrelationId("config", envelope.correlationId);
          setApiConfig(envelope.data);
        }
      })
      .catch((error) => {
        if (active) {
          upsertMessage({
            id: "config-warning",
            role: "system",
            content: `Using demo market list because API config could not load. ${describeApiError(error)}`
          });
        }
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl, upsertMessage]);

  useEffect(() => {
    let active = true;
    const path = `/api/privacy?country=${encodeURIComponent(selectedLocale.country)}&lang=${encodeURIComponent(selectedLocale.language)}`;

    getJson<PrivacyResponseData>(apiBaseUrl, path)
      .then((envelope) => {
        if (active && envelope.data) {
          logCorrelationId("privacy", envelope.correlationId);
          setLegalDocuments(envelope.data.documents);
          setLegalVersion(envelope.data.version);
        }
      })
      .catch((error) => {
        if (active) {
          setLegalDocuments([]);
          upsertMessage({
            id: "privacy-warning",
            role: "system",
            content: `Legal documents could not load yet. ${describeApiError(error)}`
          });
        }
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedLocale.country, selectedLocale.language, upsertMessage]);

  const handleConsent = async (payload: ConsentEventPayload) => {
    const envelope = await postJson(apiBaseUrl, "/api/consent", {
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      lang: payload.selectedLanguage,
      timestamp: payload.timestamp,
      version: payload.policyVersion
    });
    logCorrelationId("consent", envelope.correlationId);
    if (pendingMessage) {
      const retryPayload = { ...pendingMessage, sessionId: payload.sessionId };
      setPendingMessage(null);
      await sendChat(retryPayload, false);
    }
  };

  const sendChat = async (payload: MessageEventPayload, showUserMessage = true) => {
    if (requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    if (showUserMessage) appendMessage({ id: buildId("user"), role: "user", content: payload.message });
    setLoading(true);
    try {
      const envelope = await postJson<ChatResponseData>(apiBaseUrl, "/api/chat", {
        message: payload.message,
        sessionId: payload.sessionId,
        country: payload.selectedCountry,
        language: payload.selectedLanguage,
        role: "new_prospect"
      });
      const correlationId = envelope.data?.correlationId || envelope.correlationId;
      logCorrelationId("chat", correlationId);
      appendMessage({
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || "I could not find a response for that question.",
        metadata: {
          sources: envelope.data?.sources || [],
          confidence: envelope.data?.confidence,
          correlationId
        }
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
        setPendingMessage(payload);
        setConsentRequiredSignal((value) => value + 1);
        appendMessage({
          id: buildId("consent-required"),
          role: "system",
          content: "Please accept the legal documents before chatting. Your message will be sent after consent is recorded."
        });
        return;
      }
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: `The message could not be sent. ${describeApiError(error)}`
      });
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleMessage = async (payload: MessageEventPayload) => {
    await sendChat(payload);
  };

  return (
    <GenericWidgetWrapper
      config={config}
      messages={messages}
      loading={loading}
      openByDefault
      consentRequiredSignal={consentRequiredSignal}
      onAcceptConsent={handleConsent}
      onCountryChange={(payload) => setSelectedLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
      onLanguageChange={(payload) => setSelectedLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
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
