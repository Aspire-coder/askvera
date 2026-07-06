import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiRequestError,
  createApiClient,
  describeApiError,
  loadConfig,
  loadPrivacy,
  sendMessage,
  submitConsent,
  type ConfigResponseData,
  type LegalDocument
} from "../../api";
import { buildWidgetConfig, type BackendConfig } from "../../config";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { ConsentEventPayload, MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

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

const legalViewerHref = (apiBaseUrl: string, country: string, language: string, documentId: string) => {
  const params = new URLSearchParams({
    api: apiBaseUrl,
    country,
    lang: language,
    doc: documentId
  });
  return `/legal?${params.toString()}`;
};

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
  const apiClient = useMemo(() => createApiClient({ baseUrl: apiBaseUrl }), [apiBaseUrl]);
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

    loadConfig(apiClient)
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
  }, [apiClient, upsertMessage]);

  useEffect(() => {
    let active = true;
    loadPrivacy(apiClient, selectedLocale.country, selectedLocale.language)
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
  }, [apiClient, selectedLocale.country, selectedLocale.language, upsertMessage]);

  const handleConsent = async (payload: ConsentEventPayload) => {
    const envelope = await submitConsent(apiClient, {
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
      const envelope = await sendMessage(apiClient, {
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
