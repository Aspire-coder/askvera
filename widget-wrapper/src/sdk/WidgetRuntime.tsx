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
  loadWidgetConfig,
  sendMessage,
  submitConsent,
  submitFeedback,
  type ConfigResponseData
} from "../api";
import { buildThemeConfig, buildWidgetConfig, type BackendConfig } from "../config";
import { widgetEventBus, widgetEventTypes } from "../events";
import { GenericWidgetWrapper } from "../generic-widget/GenericWidgetWrapper";
import type { ConsentEventPayload, GenericWidgetConfig, GenericWidgetRenderState, MessageEventPayload, WidgetMessage } from "../generic-widget/types";
import { authenticateWidget } from "./auth";

type WidgetRuntimeProps = {
  apiBaseUrl: string;
  widgetId?: string;
  authToken?: string;
  openSignal?: number;
  closeSignal?: number;
  resetSignal?: number;
  clearConversationSignal?: number;
  sdkMessage?: { id: string; text: string };
};

type ChatErrorPresentation = {
  category: "network" | "timeout" | "backend_unavailable" | "rate_limited" | "consent_required" | "validation" | "unknown";
  title: string;
  body: string;
  actionLabel?: string;
};

const baseWidgetConfig: GenericWidgetConfig = {
  brandName: "ASK Vera",
  assistantName: "ASK Vera",
  assistantSubtitle: "Enterprise Knowledge Assistant",
  launcherTitle: "Open ASK Vera",
  footerText: "Answers are generated from approved company documentation.",
  welcomeText: "I can help you find clear answers from approved company documentation.",
  loadingText: "Thinking...",
  loadingMessages: {
    thinking: "Thinking...",
    searching: "Searching approved documentation...",
    generating: "Preparing your answer...",
    reconnecting: "Connection interrupted. Retrying...",
    slowResponse: "Still working..."
  },
  successText: "Privacy saved. Chat is ready.",
  labels: {
    launcherAriaLabel: "Open assistant",
    closeAriaLabel: "Close assistant",
    menuAriaLabel: "Open assistant menu",
    countryLabel: "Market",
    languageLabel: "Language",
    countryPlaceholder: "Select a market",
    languagePlaceholder: "Select a language",
    continueLabel: "Continue",
    acceptConsentLabel: "I agree",
    rejectConsentLabel: "Not now",
    messageInputLabel: "Message",
    messageInputPlaceholder: "Ask a question",
    sendMessageLabel: "Send message",
    suggestedTopicsLabel: "Suggested topics",
    legalLinksLabel: "Legal links",
    childrenRegionLabel: "Embedded assistant",
    successDismissLabel: "Dismiss confirmation"
  },
  menu: {
    settings: "Settings",
    history: "History",
    newChat: "New chat",
    escalate: "Contact support"
  },
  consent: {
    title: "Privacy and Terms",
    body: "To use ASK Vera, review and accept the legal documents below.",
    eyebrow: "One quick privacy step",
    acknowledgmentLabel: "I have read and agree to the required privacy and terms documents.",
    loadingText: "Loading legal documents before consent can be recorded.",
    declineTitle: "No problem. ASK Vera will be here when you are ready.",
    declineBody: "Thanks for your response. To start chatting, please come back and accept the privacy and terms when you are ready.",
    declineActionLabel: "Review privacy terms",
    policyVersion: "2026.1",
    categories: ["chat-processing", "market-language-preferences"],
    storageKey: "askvera_widget_consent",
    requireConsentBeforeMessaging: true
  },
  policyLinks: [],
  countries: [{ code: "US", label: "United States", languageCodes: ["en"] }],
  languages: [{ code: "en", label: "English", countryCodes: ["US"] }],
  provider: { name: "ASK Vera API", type: "custom-react" },
  persistConsent: false,
  sessionStorageKey: "askvera_session_id",
  sessionMetadataStorageKey: "askvera_session_metadata",
  visitorStorageKey: "askvera_visitor_id"
};

const buildId = (prefix: string) => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const legalViewerHref = () => "#";

function getLegalDocuments(config: ConfigResponseData | undefined) {
  return config?.legalDocuments?.length ? config.legalDocuments : config?.legalDocs || [];
}

async function loadCompleteWidgetConfig(
  apiClient: ReturnType<typeof createApiClient>,
  selectedCountry: string,
  selectedLanguage: string
): Promise<ConfigResponseData> {
  const widgetEnvelope = await loadWidgetConfig(apiClient);
  const widgetConfig = widgetEnvelope.data;
  if (!widgetConfig) {
    throw new Error("Widget configuration response did not include data.");
  }

  const needsMarketConfig = !widgetConfig.countries?.length || widgetConfig.countries.length <= 1;
  const currentLegalDocuments = getLegalDocuments(widgetConfig);
  const needsLegalDocuments = !currentLegalDocuments.length;

  const [marketEnvelope, privacyEnvelope] = await Promise.all([
    needsMarketConfig ? loadConfig(apiClient) : Promise.resolve(undefined),
    needsLegalDocuments ? loadPrivacy(apiClient, selectedCountry, selectedLanguage) : Promise.resolve(undefined)
  ]);
  const loadedLegalDocuments = privacyEnvelope?.data?.documents?.length ? privacyEnvelope.data.documents : currentLegalDocuments;

  return {
    ...widgetConfig,
    countries: marketEnvelope?.data?.countries?.length ? marketEnvelope.data.countries : widgetConfig.countries,
    privacyVersion: privacyEnvelope?.data?.version || marketEnvelope?.data?.privacyVersion || widgetConfig.privacyVersion,
    legalDocuments: loadedLegalDocuments,
    legalDocs: loadedLegalDocuments
  };
}

function isConsentInstructionMessage(message: WidgetMessage): boolean {
  return message.id.includes("consent-required");
}

function presentChatError(error: unknown, assistantName = "ASK Vera"): ChatErrorPresentation {
  if (error instanceof ApiTimeoutError) {
    return { category: "timeout", title: `${assistantName} is taking longer than expected`, body: "Please try again.", actionLabel: "Retry" };
  }
  if (error instanceof ApiNetworkError) {
    return { category: "network", title: "Unable to reach ASK Vera", body: "Please check your connection and try again.", actionLabel: "Retry" };
  }
  if (error instanceof BackendUnavailableError) {
    return { category: "backend_unavailable", title: `${assistantName} is temporarily unavailable`, body: "Please try again in a few moments.", actionLabel: "Retry" };
  }
  if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
    return { category: "consent_required", title: "Consent is required", body: "Please accept the legal documents before chatting." };
  }
  if (error instanceof ApiRequestError && error.status === 429) {
    return { category: "rate_limited", title: `${assistantName} is receiving a lot of requests`, body: "Please wait a moment, then try again.", actionLabel: "Retry" };
  }
  if (error instanceof ApiRequestError && (error.status === 400 || error.status === 422)) {
    return { category: "validation", title: `${assistantName} could not send that request`, body: "Please review your message and try again.", actionLabel: "Retry" };
  }
  if (error instanceof ApiUnauthorizedError) {
    return { category: "validation", title: `${assistantName} cannot complete this request`, body: "Please refresh your session or try again.", actionLabel: "Retry" };
  }
  return { category: "unknown", title: "Something went wrong", body: "Please try again in a few moments.", actionLabel: "Retry" };
}

function ErrorMessageContent({ presentation, onRetry }: { presentation: ChatErrorPresentation; onRetry?: () => void }) {
  return (
    <div className={`gw-error-message gw-error-message-${presentation.category}`} role="alert" aria-live="assertive">
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

function emitErrorEvent(error: unknown, presentation: ChatErrorPresentation, payload: MessageEventPayload) {
  const eventPayload = {
    visitorId: payload.visitorId,
    sessionId: payload.sessionId,
    error: describeApiError(error),
    metadata: { category: presentation.category }
  };
  if (presentation.category === "network") widgetEventBus.emit(widgetEventTypes.NETWORK_ERROR, eventPayload);
  else if (presentation.category === "timeout") widgetEventBus.emit(widgetEventTypes.TIMEOUT_ERROR, eventPayload);
  else if (presentation.category === "validation") widgetEventBus.emit(widgetEventTypes.VALIDATION_ERROR, eventPayload);
  else if (presentation.category === "unknown") widgetEventBus.emit(widgetEventTypes.UNKNOWN_ERROR, eventPayload);
  else widgetEventBus.emit(widgetEventTypes.API_ERROR, eventPayload);
}

export function WidgetRuntime({
  apiBaseUrl,
  widgetId,
  authToken,
  openSignal = 0,
  closeSignal = 0,
  resetSignal = 0,
  clearConversationSignal = 0,
  sdkMessage
}: WidgetRuntimeProps) {
  const [apiConfig, setApiConfig] = useState<ConfigResponseData | null>(null);
  const [selectedLocale, setSelectedLocale] = useState({ country: "US", language: "en" });
  const [messages, setMessages] = useState<WidgetMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<MessageEventPayload | null>(null);
  const [consentRequiredSignal, setConsentRequiredSignal] = useState(0);
  const [activeAuthToken, setActiveAuthToken] = useState(authToken);
  const firstMessageSentRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const apiClient = useMemo(() => createApiClient({ baseUrl: apiBaseUrl, authToken: () => activeAuthToken }), [activeAuthToken, apiBaseUrl]);

  const widgetConfig = useMemo(() => {
    const backendConfig: BackendConfig | undefined = apiConfig
      ? {
          widgetId: apiConfig.widgetId,
          companyName: apiConfig.companyName,
          logo: apiConfig.logo,
          theme: apiConfig.theme,
          primaryColor: apiConfig.primaryColor,
          countries: apiConfig.countries,
          privacyVersion: apiConfig.privacyVersion,
          legalDocuments: getLegalDocuments(apiConfig),
          starterTopics: apiConfig.starterTopics,
          contextualTopics: apiConfig.contextualTopics,
          copy: apiConfig.copy
        }
      : undefined;
    const primaryColor = apiConfig?.primaryColor || "#2D7FF9";
    const theme = buildThemeConfig({ mode: apiConfig?.theme === "dark" ? "dark" : "light" }, primaryColor);
    return buildWidgetConfig({
      baseConfig: baseWidgetConfig,
      runtimeConfig: {
        apiUrl: apiBaseUrl,
        providerName: apiConfig?.companyName || "ASK Vera API",
        companyName: apiConfig?.companyName || "ASK Vera",
        assistantName: "ASK Vera",
        logoUrl: apiConfig?.logo,
        launcherIconUrl: apiConfig?.logo,
        accentColor: primaryColor,
        defaultCountry: selectedLocale.country,
        defaultLanguage: selectedLocale.language,
        theme
      },
      backendConfig,
      selectedCountry: selectedLocale.country,
      selectedLanguage: selectedLocale.language,
      legalLinkBuilder: legalViewerHref
    });
  }, [apiBaseUrl, apiConfig, selectedLocale.country, selectedLocale.language]);

  const config = widgetConfig.genericConfig;

  const appendMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  }, []);

  useEffect(() => {
    setActiveAuthToken(authToken);
  }, [authToken]);

  const upsertMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => {
      const existingIndex = current.findIndex((item) => item.id === message.id);
      if (existingIndex === -1) return [...current, message];
      return current.map((item, index) => (index === existingIndex ? message : item));
    });
  }, []);

  useEffect(() => {
    let active = true;
    loadCompleteWidgetConfig(apiClient, selectedLocale.country, selectedLocale.language)
      .then((loadedConfig) => {
        if (!active) return;
        widgetEventBus.emit(widgetEventTypes.BACKEND_CONNECTED, {});
        setApiConfig(loadedConfig);
        const firstCountry = loadedConfig.countries[0];
        const firstLanguage = firstCountry?.languages[0];
        const selectedCountryConfig = loadedConfig.countries.find((country) => country.code === selectedLocale.country);
        const selectedLanguageConfig = selectedCountryConfig?.languages.find((language) => language.code === selectedLocale.language);
        if (!selectedCountryConfig && firstCountry && firstLanguage) {
          setSelectedLocale({ country: firstCountry.code, language: firstLanguage.code });
        } else if (selectedCountryConfig && !selectedLanguageConfig) {
          const fallbackLanguage = selectedCountryConfig.languages[0];
          if (fallbackLanguage) {
            setSelectedLocale({ country: selectedCountryConfig.code, language: fallbackLanguage.code });
          }
        }
      })
      .catch((error) => {
        if (!active) return;
        widgetEventBus.emit(widgetEventTypes.BACKEND_DISCONNECTED, { error: describeApiError(error) });
        upsertMessage({ id: "config-warning", role: "system", content: `Widget configuration could not load. ${describeApiError(error)}` });
      });
    return () => {
      active = false;
    };
  }, [apiClient, selectedLocale.country, selectedLocale.language, upsertMessage]);

  useEffect(() => {
    if (!clearConversationSignal) return;
    setMessages([{ id: buildId("clear-chat"), role: "assistant", content: "Conversation cleared." }]);
  }, [clearConversationSignal]);

  const refreshWidgetAuth = async () => {
    if (!widgetId) return undefined;
    const refreshed = await authenticateWidget({ apiUrl: apiBaseUrl, widgetId }, { forceNew: true });
    setActiveAuthToken(refreshed.token);
    return refreshed.token;
  };

  const submitChatRequest = async (payload: MessageEventPayload, tokenOverride?: string) => {
    const client = tokenOverride
      ? createApiClient({ baseUrl: apiBaseUrl, authToken: tokenOverride })
      : apiClient;
    return sendMessage(client, {
      message: payload.message,
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      language: payload.selectedLanguage,
      role: "new_prospect"
    });
  };

  const sendChat = async (payload: MessageEventPayload, showUserMessage = true) => {
    if (requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    widgetEventBus.emit(widgetEventTypes.CHAT_STARTED, { visitorId: payload.visitorId, sessionId: payload.sessionId });
    if (!firstMessageSentRef.current) {
      firstMessageSentRef.current = true;
      widgetEventBus.emit(widgetEventTypes.FIRST_MESSAGE, { visitorId: payload.visitorId, sessionId: payload.sessionId, message: payload });
    }
    if (showUserMessage) appendMessage({ id: buildId("user"), role: "user", content: payload.message });
    setLoading(true);
    try {
      let envelope;
      try {
        envelope = await submitChatRequest(payload);
      } catch (error) {
        if (!(error instanceof ApiUnauthorizedError)) throw error;
        const refreshedToken = await refreshWidgetAuth();
        if (!refreshedToken) throw error;
        envelope = await submitChatRequest(payload, refreshedToken);
      }
      const correlationId = envelope.data?.correlationId || envelope.correlationId;
      const assistantMessage: WidgetMessage = {
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || "I could not find a response for that question.",
        metadata: { sources: envelope.data?.sources || [], confidence: envelope.data?.confidence, correlationId }
      };
      appendMessage(assistantMessage);
      widgetEventBus.emit(widgetEventTypes.MESSAGE_RECEIVED, { visitorId: payload.visitorId, sessionId: payload.sessionId, correlationId, message: assistantMessage });
    } catch (error) {
      if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
        setPendingMessage(payload);
        setConsentRequiredSignal((value) => value + 1);
        appendMessage({ id: buildId("consent-required"), role: "system", content: <ErrorMessageContent presentation={presentChatError(error, config.assistantName || config.brandName)} /> });
        return;
      }
      const presentation = presentChatError(error, config.assistantName || config.brandName);
      emitErrorEvent(error, presentation, payload);
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: <ErrorMessageContent presentation={presentation} onRetry={() => void sendChat(payload, false)} />,
        metadata: { errorCategory: presentation.category }
      });
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleConsent = async (payload: ConsentEventPayload) => {
    await submitConsent(apiClient, {
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      lang: payload.selectedLanguage,
      timestamp: payload.timestamp,
      version: payload.policyVersion
    });
    setMessages((current) => current.filter((message) => !isConsentInstructionMessage(message)));
    if (pendingMessage) {
      const retryPayload = { ...pendingMessage, sessionId: payload.sessionId };
      setPendingMessage(null);
      await sendChat(retryPayload, false);
    }
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
    } catch (error) {
      widgetEventBus.emit(widgetEventTypes.API_ERROR, { visitorId: state.visitorId, sessionId: state.sessionId, error: describeApiError(error) });
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
      onSendMessage={(payload) => void sendChat(payload)}
      onMessageFeedback={handleMessageFeedback}
      onNewChat={() => setMessages([{ id: buildId("new-chat"), role: "assistant", content: "New chat started." }])}
    />
  );
}
