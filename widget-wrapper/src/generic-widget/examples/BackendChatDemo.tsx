import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiNetworkError,
  ApiRequestError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  BackendUnavailableError,
  createApiClient,
  describeApiError,
  loadConfig,
  loadPrivacy,
  sendMessage,
  submitFeedback,
  submitConsent,
  type ConfigResponseData,
  type LegalDocument
} from "../../api";
import { buildWidgetConfig, type BackendConfig } from "../../config";
import { widgetEventBus, widgetEventTypes } from "../../events";
import { createAnalyticsService } from "../../services";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { ConsentEventPayload, GenericWidgetRenderState, MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

type ChatErrorCategory =
  | "network"
  | "timeout"
  | "backend_unavailable"
  | "rate_limited"
  | "consent_required"
  | "validation"
  | "unknown";

type ChatErrorPresentation = {
  category: ChatErrorCategory;
  title: string;
  body: string;
  actionLabel?: string;
};

export type BackendChatDemoProps = {
  apiBaseUrl?: string;
  openSignal?: number;
  closeSignal?: number;
  resetSignal?: number;
  clearConversationSignal?: number;
  sdkMessage?: { id: string; text: string };
  country?: string;
  language?: string;
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

function isConsentInstructionMessage(message: WidgetMessage): boolean {
  return message.id === "backend-welcome" || message.id.includes("consent-required");
}

function isValidationStatus(status?: number) {
  return status === 400 || status === 422;
}

function presentChatError(error: unknown): ChatErrorPresentation {
  if (error instanceof ApiTimeoutError) {
    return {
      category: "timeout",
      title: "ASK Vera is taking longer than expected",
      body: "This can happen when searching large knowledge bases.",
      actionLabel: "Retry"
    };
  }

  if (error instanceof ApiNetworkError) {
    return {
      category: "network",
      title: "Unable to reach ASK Vera",
      body: "Please check your internet connection and try again.",
      actionLabel: "Retry"
    };
  }

  if (error instanceof BackendUnavailableError) {
    return {
      category: "backend_unavailable",
      title: "ASK Vera is temporarily unavailable",
      body: "Please try again in a few moments.",
      actionLabel: "Retry"
    };
  }

  if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
    return {
      category: "consent_required",
      title: "Consent is required",
      body: "Please accept the legal documents before chatting. Your message will be sent after consent is recorded."
    };
  }

  if (error instanceof ApiRequestError && error.status === 429) {
    return {
      category: "rate_limited",
      title: "ASK Vera is receiving a lot of requests",
      body: "Please wait a moment, then try again.",
      actionLabel: "Retry"
    };
  }

  if (error instanceof ApiRequestError && isValidationStatus(error.status)) {
    return {
      category: "validation",
      title: "ASK Vera could not send that request",
      body: "Please review your message and try again.",
      actionLabel: "Retry"
    };
  }

  if (error instanceof ApiUnauthorizedError) {
    return {
      category: "validation",
      title: "ASK Vera cannot complete this request",
      body: "Please refresh your session or try again in a few moments.",
      actionLabel: "Retry"
    };
  }

  return {
    category: "unknown",
    title: "Something went wrong",
    body: "Please try again in a few moments.",
    actionLabel: "Retry"
  };
}

function emitErrorEvent(error: unknown, presentation: ChatErrorPresentation, payload: MessageEventPayload) {
  const eventPayload = {
    visitorId: payload.visitorId,
    sessionId: payload.sessionId,
    error: describeApiError(error),
    metadata: { category: presentation.category }
  };

  if (presentation.category === "network") {
    widgetEventBus.emit(widgetEventTypes.NETWORK_ERROR, eventPayload);
  } else if (presentation.category === "timeout") {
    widgetEventBus.emit(widgetEventTypes.TIMEOUT_ERROR, eventPayload);
  } else if (presentation.category === "validation") {
    widgetEventBus.emit(widgetEventTypes.VALIDATION_ERROR, eventPayload);
  } else if (presentation.category === "unknown") {
    widgetEventBus.emit(widgetEventTypes.UNKNOWN_ERROR, eventPayload);
  } else {
    widgetEventBus.emit(widgetEventTypes.API_ERROR, eventPayload);
  }
}

function ErrorMessageContent({
  presentation,
  onRetry
}: {
  presentation: ChatErrorPresentation;
  onRetry?: () => void;
}) {
  return (
    <div className={`gw-error-message gw-error-message-${presentation.category}`} role="alert" aria-live="assertive">
      <div className="gw-error-message-icon" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M12 9v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <path d="M12 17h.01" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
          <path d="M10.3 4.2 2.7 17.4A2 2 0 0 0 4.4 20h15.2a2 2 0 0 0 1.7-2.6L13.7 4.2a2 2 0 0 0-3.4 0Z" stroke="currentColor" strokeWidth="2" />
        </svg>
      </div>
      <div className="gw-error-message-copy">
        <strong>{presentation.title}</strong>
        <p>{presentation.body}</p>
        {onRetry && presentation.actionLabel ? (
          <button type="button" className="gw-inline-action-button" onClick={onRetry}>
            {presentation.actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function BackendChatDemo({
  apiBaseUrl = "https://api.vera-api.xyz",
  openSignal = 0,
  closeSignal = 0,
  resetSignal = 0,
  clearConversationSignal = 0,
  sdkMessage,
  country,
  language
}: BackendChatDemoProps) {
  const [apiConfig, setApiConfig] = useState<ConfigResponseData | null>(null);
  const [selectedLocale, setSelectedLocale] = useState({ country: "US", language: "en" });
  const [legalDocuments, setLegalDocuments] = useState<LegalDocument[]>([]);
  const [legalVersion, setLegalVersion] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<MessageEventPayload | null>(null);
  const [consentRequiredSignal, setConsentRequiredSignal] = useState(0);
  const firstMessageSentRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const apiClient = useMemo(() => createApiClient({ baseUrl: apiBaseUrl }), [apiBaseUrl]);
  const widgetConfig = useMemo(
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
      });
    },
    [apiBaseUrl, apiConfig, legalDocuments, legalVersion, selectedLocale.country, selectedLocale.language]
  );
  const config = widgetConfig.genericConfig;

  useEffect(() => {
    const analytics = createAnalyticsService({
      enabled: widgetConfig.features.analytics,
      debug: widgetConfig.runtime.debug,
      context: {
        companyName: widgetConfig.runtime.companyName,
        apiUrl: widgetConfig.runtime.apiUrl,
        country: selectedLocale.country,
        language: selectedLocale.language
      }
    });
    analytics.attachToEventBus(widgetEventBus);
    return () => analytics.detach();
  }, [
    selectedLocale.country,
    selectedLocale.language,
    widgetConfig.features.analytics,
    widgetConfig.runtime.apiUrl,
    widgetConfig.runtime.companyName,
    widgetConfig.runtime.debug
  ]);
  const [messages, setMessages] = useState<WidgetMessage[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!country && !language) return;
    setSelectedLocale((current) => ({
      country: country || current.country,
      language: language || current.language
    }));
  }, [country, language]);

  useEffect(() => {
    if (!clearConversationSignal) return;
    setMessages([
      {
        id: buildId("clear-chat"),
        role: "assistant",
        content: "Conversation cleared. Your selected market and language will stay active."
      }
    ]);
  }, [clearConversationSignal]);

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
          widgetEventBus.emit(widgetEventTypes.BACKEND_CONNECTED, { correlationId: envelope.correlationId });
          setApiConfig(envelope.data);
        }
      })
      .catch((error) => {
        if (active) {
          widgetEventBus.emit(widgetEventTypes.BACKEND_DISCONNECTED, { error: describeApiError(error) });
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
          widgetEventBus.emit(widgetEventTypes.BACKEND_CONNECTED, { correlationId: envelope.correlationId });
          setLegalDocuments(envelope.data.documents);
          setLegalVersion(envelope.data.version);
        }
      })
      .catch((error) => {
        if (active) {
          widgetEventBus.emit(widgetEventTypes.API_ERROR, { error: describeApiError(error) });
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
    setMessages((current) => current.filter((message) => !isConsentInstructionMessage(message)));
    if (pendingMessage) {
      const retryPayload = { ...pendingMessage, sessionId: payload.sessionId };
      setPendingMessage(null);
      widgetEventBus.emit(widgetEventTypes.MESSAGE_RETRIED, {
        visitorId: payload.visitorId,
        sessionId: payload.sessionId,
        message: retryPayload
      });
      await sendChat(retryPayload, false);
    }
  };

  const sendChat = async (payload: MessageEventPayload, showUserMessage = true) => {
    if (requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    widgetEventBus.emit(widgetEventTypes.CHAT_STARTED, {
      visitorId: payload.visitorId,
      sessionId: payload.sessionId
    });
    if (!firstMessageSentRef.current) {
      firstMessageSentRef.current = true;
      widgetEventBus.emit(widgetEventTypes.FIRST_MESSAGE, {
        visitorId: payload.visitorId,
        sessionId: payload.sessionId,
        message: payload
      });
    }
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
      const assistantMessage: WidgetMessage = {
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || "I could not find a response for that question.",
        metadata: {
          sources: envelope.data?.sources || [],
          confidence: envelope.data?.confidence,
          correlationId
        }
      };
      appendMessage(assistantMessage);
      widgetEventBus.emit(widgetEventTypes.MESSAGE_RECEIVED, {
        visitorId: payload.visitorId,
        sessionId: payload.sessionId,
        correlationId,
        message: assistantMessage
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
        const presentation = presentChatError(error);
        setPendingMessage(payload);
        setConsentRequiredSignal((value) => value + 1);
        widgetEventBus.emit(widgetEventTypes.CONSENT_REQUIRED, {
          visitorId: payload.visitorId,
          sessionId: payload.sessionId,
          reason: "api_consent_required"
        });
        appendMessage({
          id: buildId("consent-required"),
          role: "system",
          content: <ErrorMessageContent presentation={presentation} />
        });
        return;
      }
      const presentation = presentChatError(error);
      emitErrorEvent(error, presentation, payload);
      widgetEventBus.emit(widgetEventTypes.MESSAGE_FAILED, {
        visitorId: payload.visitorId,
        sessionId: payload.sessionId,
        error: describeApiError(error),
        metadata: { category: presentation.category }
      });
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: (
          <ErrorMessageContent
            presentation={presentation}
            onRetry={() => {
              widgetEventBus.emit(widgetEventTypes.MESSAGE_RETRIED, {
                visitorId: payload.visitorId,
                sessionId: payload.sessionId,
                message: payload,
                metadata: { category: presentation.category }
              });
              void sendChat(payload, false);
            }}
          />
        ),
        metadata: { errorCategory: presentation.category }
      });
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleMessage = async (payload: MessageEventPayload) => {
    await sendChat(payload);
  };

  const handleMessageFeedback = async (message: WidgetMessage, rating: number, state: GenericWidgetRenderState) => {
    try {
      await submitFeedback(apiClient, {
        sessionId: state.sessionId,
        messageId: message.id,
        rating,
        metadata: {
          country: state.selectedCountry?.code,
          language: state.selectedLanguage?.code,
          correlationId: message.metadata?.correlationId,
          confidence: message.metadata?.confidence
        }
      });
      widgetEventBus.emit(widgetEventTypes.FEEDBACK_SUBMITTED, {
        visitorId: state.visitorId,
        sessionId: state.sessionId,
        correlationId: typeof message.metadata?.correlationId === "string" ? message.metadata.correlationId : undefined,
        metadata: { messageId: message.id, rating }
      });
    } catch (error) {
      widgetEventBus.emit(widgetEventTypes.API_ERROR, {
        visitorId: state.visitorId,
        sessionId: state.sessionId,
        error: describeApiError(error),
        metadata: { action: "message_feedback", messageId: message.id, rating }
      });
    }
  };

  return (
    <GenericWidgetWrapper
      config={config}
      messages={messages}
      loading={loading}
      openByDefault
      openSignal={openSignal}
      closeSignal={closeSignal}
      resetSignal={resetSignal}
      outboundMessage={sdkMessage}
      consentRequiredSignal={consentRequiredSignal}
      onAcceptConsent={handleConsent}
      onCountryChange={(payload) => setSelectedLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
      onLanguageChange={(payload) => setSelectedLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
      onSendMessage={handleMessage}
      onMessageFeedback={handleMessageFeedback}
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
