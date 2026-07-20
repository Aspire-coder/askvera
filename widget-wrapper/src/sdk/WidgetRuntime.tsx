import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiNetworkError,
  ApiRequestError,
  ApiTimeoutError,
  ApiUnauthorizedError,
  BackendUnavailableError,
  createApiClient,
  describeApiError,
  healthCheck,
  loadConfig,
  loadPrivacy,
  loadWidgetConfig,
  sendMessage,
  submitConsent,
  submitFeedback,
  submitSupportRequest,
  type ConfigResponseData
} from "../api";
import { buildThemeConfig, buildWidgetConfig, type BackendConfig } from "../config";
import { widgetEventBus, widgetEventTypes } from "../events";
import { GenericWidgetWrapper } from "../generic-widget/GenericWidgetWrapper";
import { SupportRequestForm } from "../generic-widget/SupportRequestForm";
import type { ConsentEventPayload, GenericWidgetConfig, GenericWidgetRenderState, MessageEventPayload, WidgetMessage } from "../generic-widget/types";
import { authenticateWidget, renewWidgetAuth } from "./auth";
import { getWidgetCopy } from "../localization/widgetCopy";
import {
  readLocalePreference,
  writeLocalePreference,
  type LocalePreference
} from "../storage/localePreference";

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
  brandName: "AskVera",
  assistantName: "AskVera",
  assistantSubtitle: "Enterprise Knowledge Assistant",
  launcherTitle: "Open AskVera",
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
    endChat: "End chat",
    confirmEndChat: "End this chat",
    cancelEndChat: "Cancel",
    escalate: "Contact support"
  },
  consent: {
    title: "Privacy and Terms",
    body: "To use AskVera, review and accept the legal documents below.",
    eyebrow: "One quick privacy step",
    acknowledgmentLabel: "I have read and agree to the required privacy and terms documents.",
    loadingText: "Loading legal documents before consent can be recorded.",
    declineTitle: "No problem. AskVera will be here when you are ready.",
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
  provider: { name: "AskVera API", type: "custom-react" },
  persistConsent: true,
  sessionIdleTimeoutMinutes: 30,
  sessionStorageKey: "askvera_session_id",
  sessionMetadataStorageKey: "askvera_session_metadata",
  visitorStorageKey: "askvera_visitor_id"
};

const conversationStorageKey = "askvera_widget_conversation";

function sessionIdFromToken(token?: string): string | undefined {
  if (!token) return undefined;
  try {
    const payload = token.split(".")[1];
    if (!payload) return undefined;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + (4 - normalized.length % 4) % 4, "=");
    const claims = JSON.parse(window.atob(padded)) as Record<string, unknown>;
    return typeof claims.sessionId === "string" ? claims.sessionId : undefined;
  } catch {
    return undefined;
  }
}

function storedLocale(widgetId?: string, expectedSessionId?: string): LocalePreference {
  if (typeof window === "undefined") return { country: "US", language: "en" };
  try {
    const rawMetadata = window.localStorage.getItem("askvera_session_metadata");
    if (rawMetadata) {
      const metadata = JSON.parse(rawMetadata) as Record<string, string>;
      if (!expectedSessionId || metadata.sessionId === expectedSessionId) {
        return { country: metadata.country || "US", language: metadata.language || "en" };
      }
    }
    if (!expectedSessionId) {
      const preference = readLocalePreference(window.localStorage, widgetId);
      if (preference) return preference;
    }
    const migrated = { country: "US", language: "en" };
    writeLocalePreference(window.localStorage, migrated, widgetId);
    return migrated;
  } catch {
    return { country: "US", language: "en" };
  }
}

function storedMessages(expectedSessionId?: string): WidgetMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const sessionId = expectedSessionId || window.localStorage.getItem("askvera_session_id");
    const stored = JSON.parse(window.localStorage.getItem(conversationStorageKey) || "{}") as {
      sessionId?: string;
      messages?: Array<Omit<WidgetMessage, "content"> & { content: string }>;
    };
    return stored.sessionId === sessionId && Array.isArray(stored.messages) ? stored.messages : [];
  } catch {
    return [];
  }
}

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

  const marketEnvelope = await loadConfig(apiClient);
  const countries = marketEnvelope?.data?.countries?.length ? marketEnvelope.data.countries : widgetConfig.countries;
  const country = countries.find((candidate) => candidate.code === selectedCountry) || countries[0];
  const language = country?.languages.find((candidate) => candidate.code === selectedLanguage) || country?.languages[0];
  const privacyEnvelope = country && language
    ? await loadPrivacy(apiClient, country.code, language.code)
    : undefined;
  const loadedLegalDocuments = privacyEnvelope?.data?.documents?.length
    ? privacyEnvelope.data.documents
    : getLegalDocuments(widgetConfig);

  return {
    ...widgetConfig,
    countries,
    privacyVersion: privacyEnvelope?.data?.version || marketEnvelope?.data?.privacyVersion || widgetConfig.privacyVersion,
    legalDocuments: loadedLegalDocuments,
    legalDocs: loadedLegalDocuments
  };
}

function isConsentInstructionMessage(message: WidgetMessage): boolean {
  return message.id.includes("consent-required");
}

function presentChatError(error: unknown, localized: ReturnType<typeof getWidgetCopy>, assistantName = "AskVera"): ChatErrorPresentation {
  if (error instanceof ApiTimeoutError) {
    return { category: "timeout", title: assistantName, body: localized.slowResponse, actionLabel: localized.retry };
  }
  if (error instanceof ApiNetworkError) {
    return { category: "network", title: assistantName, body: localized.retrying, actionLabel: localized.retry };
  }
  if (error instanceof BackendUnavailableError) {
    return { category: "backend_unavailable", title: assistantName, body: localized.unavailable, actionLabel: localized.retry };
  }
  if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
    return { category: "consent_required", title: localized.privacyTitle, body: localized.consentRequired };
  }
  if (error instanceof ApiRequestError && error.status === 429) {
    return { category: "rate_limited", title: assistantName, body: localized.waiting, actionLabel: localized.retry };
  }
  if (error instanceof ApiRequestError && (error.status === 400 || error.status === 422)) {
    return { category: "validation", title: assistantName, body: localized.unavailable, actionLabel: localized.retry };
  }
  if (error instanceof ApiUnauthorizedError) {
    return { category: "validation", title: assistantName, body: localized.unavailable, actionLabel: localized.retry };
  }
  return { category: "unknown", title: assistantName, body: localized.unavailable, actionLabel: localized.retry };
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
  const [selectedLocale, setSelectedLocale] = useState<LocalePreference>(() => storedLocale(widgetId, sessionIdFromToken(authToken)));
  const [messages, setMessages] = useState<WidgetMessage[]>(() => storedMessages(sessionIdFromToken(authToken)));
  const [loading, setLoading] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<MessageEventPayload | null>(null);
  const [consentRequiredSignal, setConsentRequiredSignal] = useState(0);
  const [activeAuthToken, setActiveAuthToken] = useState(authToken);
  const [activeAuthSessionId, setActiveAuthSessionId] = useState(() => sessionIdFromToken(authToken));
  const [lifecycleResetSignal, setLifecycleResetSignal] = useState(0);
  const firstMessageSentRef = useRef(false);
  const requestInFlightRef = useRef(false);
  const conversationGenerationRef = useRef(0);

  const selectLocale = useCallback((locale: LocalePreference) => {
    if (typeof window !== "undefined") {
      writeLocalePreference(window.localStorage, locale, widgetId);
    }
    setApiConfig((current) => current
      ? { ...current, legalDocuments: [], legalDocs: [] }
      : current
    );
    setSelectedLocale(locale);
  }, [widgetId]);

  const activeAuthTokenRef = useRef(authToken);
  const authRefreshPromiseRef = useRef<Promise<string | undefined> | null>(null);
  const apiClient = useMemo(() => createApiClient({ baseUrl: apiBaseUrl, authToken: () => activeAuthToken }), [activeAuthToken, apiBaseUrl]);
  const healthClient = useMemo(() => createApiClient({ baseUrl: apiBaseUrl }), [apiBaseUrl]);

  const checkBackendHealth = useCallback(async () => {
    const envelope = await healthCheck(healthClient);
    return envelope.success !== false && Boolean(envelope.data);
  }, [healthClient]);

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
    const built = buildWidgetConfig({
      baseConfig: baseWidgetConfig,
      runtimeConfig: {
        apiUrl: apiBaseUrl,
        providerName: "AskVera API",
        companyName: "AskVera",
        assistantName: "AskVera",
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
    const localized = getWidgetCopy(selectedLocale.language);
    return {
      ...built,
      genericConfig: {
        ...built.genericConfig,
        brandName: "AskVera",
        assistantName: "AskVera",
        assistantSubtitle: localized.assistantSubtitle,
        launcherTitle: localized.openAssistant,
        welcomeText: localized.welcomeBody,
        footerText: localized.footer,
        loadingText: localized.thinking,
        loadingMessages: {
          thinking: localized.thinking,
          searching: localized.searching,
          generating: localized.generating,
          reconnecting: localized.retrying,
          slowResponse: localized.slowResponse
        },
        successText: localized.privacySaved,
        onboarding: {
          eyebrow: localized.welcomeEyebrow,
          title: localized.welcomeTitle,
          body: localized.welcomeBody,
          next: localized.welcomeNext
        },
        statusLabels: { online: localized.online, offline: localized.offline, reconnecting: localized.reconnecting },
        messageActions: {
          copy: localized.copy,
          copied: localized.copied,
          helpful: localized.helpful,
          notHelpful: localized.notHelpful
        },
        citationLabels: {
          references: localized.references,
          sourcesUsed: localized.sourcesUsed,
          primarySource: localized.primarySource,
          supportingSource: localized.supportingSource,
          source: localized.source,
          section: localized.section
        },
        composerStatus: {
          consentRequired: localized.consentRequired,
          unavailable: localized.unavailable,
          waiting: localized.waiting
        },
        labels: {
          ...built.genericConfig.labels,
          launcherAriaLabel: localized.openAssistant,
          closeAriaLabel: localized.closeAssistant,
          menuAriaLabel: localized.openMenu,
          countryLabel: localized.market,
          languageLabel: localized.language,
          countryPlaceholder: localized.selectMarket,
          languagePlaceholder: localized.selectLanguage,
          acceptConsentLabel: localized.accept,
          rejectConsentLabel: localized.decline,
          messageInputLabel: localized.inputPlaceholder,
          messageInputPlaceholder: localized.inputPlaceholder,
          sendMessageLabel: localized.send,
          legalLinksLabel: localized.reviewDocuments,
          childrenRegionLabel: localized.openAssistant,
          successDismissLabel: localized.closeAssistant,
          panelAriaLabel: localized.openAssistant,
          onboardingAriaLabel: localized.welcomeEyebrow,
          attachFileLabel: localized.inputPlaceholder,
          composerHint: localized.composerHint,
          userRoleLabel: localized.you,
          systemRoleLabel: localized.system,
          messageActionsLabel: localized.copy,
          copyResponseLabel: localized.copy,
          markHelpfulLabel: localized.helpful,
          markNotHelpfulLabel: localized.notHelpful,
          responseCopiedLabel: localized.copied,
          legalReviewTitle: localized.reviewDocuments,
          saveDocumentLabel: localized.saveAsPdf,
          closeLegalDocumentLabel: localized.closeLegal,
          savingConsentLabel: localized.privacySaving
        },
        menu: { ...built.genericConfig.menu, newChat: localized.newChat, endChat: localized.endChat, confirmEndChat: localized.confirmEndChat, cancelEndChat: localized.cancelEndChat, escalate: localized.support },
        consent: {
          ...built.genericConfig.consent,
          eyebrow: localized.privacyEyebrow,
          title: localized.privacyTitle,
          body: localized.privacyBody,
          acknowledgmentLabel: localized.privacyAcknowledgment,
          loadingText: localized.privacyLoading,
          declineTitle: localized.declineTitle,
          declineBody: localized.declineBody,
          declineActionLabel: localized.reviewPrivacy
        }
      }
    };
  }, [apiBaseUrl, apiConfig, selectedLocale.country, selectedLocale.language]);

  const config = widgetConfig.genericConfig;
  const supportAvailable = Boolean(apiConfig?.supportCountries?.includes(selectedLocale.country));

  const appendMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const sessionId = window.localStorage.getItem("askvera_session_id");
    const serializable = messages.filter((message) => typeof message.content === "string");
    window.localStorage.setItem(conversationStorageKey, JSON.stringify({ sessionId, messages: serializable }));
  }, [messages]);

  useEffect(() => {
    setActiveAuthToken(authToken);
    activeAuthTokenRef.current = authToken;
    setActiveAuthSessionId(sessionIdFromToken(authToken));
  }, [authToken]);

  const refreshWidgetAuth = useCallback(async () => {
    if (!widgetId) return undefined;
    if (authRefreshPromiseRef.current) return authRefreshPromiseRef.current;

    const refreshPromise = renewWidgetAuth({ apiUrl: apiBaseUrl, widgetId }, activeAuthTokenRef.current)
      .then((refreshed) => {
        setActiveAuthToken(refreshed.token);
        activeAuthTokenRef.current = refreshed.token;
        setActiveAuthSessionId(refreshed.session?.sessionId || sessionIdFromToken(refreshed.token));
        return refreshed.token;
      })
      .finally(() => {
        authRefreshPromiseRef.current = null;
      });
    authRefreshPromiseRef.current = refreshPromise;
    return refreshPromise;
  }, [apiBaseUrl, widgetId]);

  const withWidgetAuthRetry = useCallback(async <T,>(request: (client: ReturnType<typeof createApiClient>) => Promise<T>) => {
    try {
      return await request(apiClient);
    } catch (error) {
      if (!(error instanceof ApiUnauthorizedError)) throw error;
      const refreshedToken = await refreshWidgetAuth();
      if (!refreshedToken) throw error;
      return request(createApiClient({ baseUrl: apiBaseUrl, authToken: refreshedToken }));
    }
  }, [apiBaseUrl, apiClient, refreshWidgetAuth]);

  const upsertMessage = useCallback((message: WidgetMessage) => {
    setMessages((current) => {
      const existingIndex = current.findIndex((item) => item.id === message.id);
      if (existingIndex === -1) return [...current, message];
      return current.map((item, index) => (index === existingIndex ? message : item));
    });
  }, []);

  useEffect(() => {
    let active = true;
    withWidgetAuthRetry((client) => loadCompleteWidgetConfig(client, selectedLocale.country, selectedLocale.language))
      .then((loadedConfig) => {
        if (!active) return;
        widgetEventBus.emit(widgetEventTypes.BACKEND_CONNECTED, {});
        setApiConfig(loadedConfig);
        const firstCountry = loadedConfig.countries[0];
        const firstLanguage = firstCountry?.languages[0];
        const selectedCountryConfig = loadedConfig.countries.find((country) => country.code === selectedLocale.country);
        const selectedLanguageConfig = selectedCountryConfig?.languages.find((language) => language.code === selectedLocale.language);
        if (!selectedCountryConfig && firstCountry && firstLanguage) {
          selectLocale({ country: firstCountry.code, language: firstLanguage.code });
        } else if (selectedCountryConfig && !selectedLanguageConfig) {
          const fallbackLanguage = selectedCountryConfig.languages[0];
          if (fallbackLanguage) {
            selectLocale({ country: selectedCountryConfig.code, language: fallbackLanguage.code });
          }
        }
      })
      .catch((error) => {
        if (!active) return;
        widgetEventBus.emit(widgetEventTypes.BACKEND_DISCONNECTED, { error: describeApiError(error) });
        upsertMessage({ id: "config-warning", role: "system", content: getWidgetCopy(selectedLocale.language).unavailable });
      });
    return () => {
      active = false;
    };
  }, [selectLocale, selectedLocale.country, selectedLocale.language, upsertMessage, withWidgetAuthRetry]);

  useEffect(() => {
    if (!clearConversationSignal) return;
    setMessages([{ id: buildId("clear-chat"), role: "assistant", content: getWidgetCopy(selectedLocale.language).conversationCleared }]);
  }, [clearConversationSignal, selectedLocale.language]);

  const submitChatRequest = async (payload: MessageEventPayload) => {
    return withWidgetAuthRetry((client) => sendMessage(client, {
      message: payload.message,
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      language: payload.selectedLanguage,
      role: "new_prospect"
    }));
  };

  const sendChat = async (payload: MessageEventPayload, showUserMessage = true) => {
    if (requestInFlightRef.current) return;
    const conversationGeneration = conversationGenerationRef.current;
    requestInFlightRef.current = true;
    widgetEventBus.emit(widgetEventTypes.CHAT_STARTED, { visitorId: payload.visitorId, sessionId: payload.sessionId });
    if (!firstMessageSentRef.current) {
      firstMessageSentRef.current = true;
      widgetEventBus.emit(widgetEventTypes.FIRST_MESSAGE, { visitorId: payload.visitorId, sessionId: payload.sessionId, message: payload });
    }
    if (showUserMessage) appendMessage({ id: buildId("user"), role: "user", content: payload.message });
    setLoading(true);
    try {
      const envelope = await submitChatRequest(payload);
      if (conversationGeneration !== conversationGenerationRef.current) return;
      const correlationId = envelope.data?.correlationId || envelope.correlationId;
      const localized = getWidgetCopy(payload.selectedLanguage);
      const assistantMessage: WidgetMessage = {
        id: buildId("assistant"),
        role: "assistant",
        content: envelope.data?.response || localized.unavailable,
        metadata: {
          sources: envelope.data?.sources || [],
          confidence: envelope.data?.confidence,
          correlationId,
          responseMetadata: envelope.data?.metadata,
          supportRecommended: Boolean(envelope.data?.metadata?.failureLayer),
          supportLabel: localized.support,
          supportCreatingLabel: localized.supportCreating,
          supportRequestedLabel: localized.supportRequested,
          actionCopyLabel: localized.copy,
          actionCopiedLabel: localized.copied,
          actionHelpfulLabel: localized.helpful,
          actionNotHelpfulLabel: localized.notHelpful
        }
      };
      appendMessage(assistantMessage);
      widgetEventBus.emit(widgetEventTypes.MESSAGE_RECEIVED, { visitorId: payload.visitorId, sessionId: payload.sessionId, correlationId, message: assistantMessage });
    } catch (error) {
      if (conversationGeneration !== conversationGenerationRef.current) return;
      if (error instanceof ApiRequestError && error.code === "CONSENT_REQUIRED") {
        const localized = getWidgetCopy(payload.selectedLanguage);
        setPendingMessage(payload);
        setConsentRequiredSignal((value) => value + 1);
        appendMessage({ id: buildId("consent-required"), role: "system", content: <ErrorMessageContent presentation={presentChatError(error, localized, config.assistantName || config.brandName)} /> });
        return;
      }
      if (error instanceof ApiRequestError && (error.code === "SESSION_EXPIRED" || error.code === "SESSION_MISMATCH")) {
        setLifecycleResetSignal((value) => value + 1);
        return;
      }
      const presentation = presentChatError(error, getWidgetCopy(payload.selectedLanguage), config.assistantName || config.brandName);
      emitErrorEvent(error, presentation, payload);
      appendMessage({
        id: buildId("api-error"),
        role: "system",
        content: <ErrorMessageContent presentation={presentation} onRetry={() => void sendChat(payload, false)} />,
        metadata: { errorCategory: presentation.category }
      });
    } finally {
      if (conversationGeneration === conversationGenerationRef.current) {
        requestInFlightRef.current = false;
        setLoading(false);
      }
    }
  };

  const handleConsent = async (payload: ConsentEventPayload) => {
    await withWidgetAuthRetry((client) => submitConsent(client, {
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      lang: payload.selectedLanguage,
      timestamp: payload.timestamp,
      version: payload.policyVersion
    }));
    setMessages((current) => current.filter((message) => !isConsentInstructionMessage(message)));
    setMessages((current) => current.length ? current : [
      { id: buildId("greeting"), role: "assistant", content: getWidgetCopy(payload.selectedLanguage).greeting }
    ]);
    if (pendingMessage) {
      const retryPayload = { ...pendingMessage, sessionId: payload.sessionId };
      setPendingMessage(null);
      await sendChat(retryPayload, false);
    }
  };

  const handleMessageFeedback = async (message: WidgetMessage, rating: number, state: GenericWidgetRenderState) => {
    try {
      await withWidgetAuthRetry((client) => submitFeedback(client, {
        sessionId: state.sessionId,
        messageId: message.id,
        rating,
        metadata: {
          country: state.selectedCountry?.code,
          language: state.selectedLanguage?.code,
          correlationId: message.metadata?.correlationId,
          confidence: message.metadata?.confidence
        }
      }));
    } catch (error) {
      widgetEventBus.emit(widgetEventTypes.API_ERROR, { visitorId: state.visitorId, sessionId: state.sessionId, error: describeApiError(error) });
    }
  };

  const handleSupportRequest = async (state: GenericWidgetRenderState, message?: WidgetMessage) => {
    const localized = getWidgetCopy(state.selectedLanguage?.code);
    const messageIndex = message ? messages.findIndex((item) => item.id === message.id) : -1;
    const relatedQuestion = messageIndex > 0
      ? [...messages.slice(0, messageIndex)].reverse().find((item) => item.role === "user" && typeof item.content === "string")
      : undefined;
    const formId = buildId("support-form");

    const closeForm = () => setMessages((current) => current.filter((item) => item.id !== formId));
    const formMessage: WidgetMessage = {
      id: formId,
      role: "system",
      content: (
        <SupportRequestForm
          labels={{
            title: localized.supportFormTitle,
            body: localized.supportFormBody,
            firstName: localized.supportFirstName,
            email: localized.supportEmail,
            question: localized.supportQuestion,
            submit: localized.supportSubmit,
            cancel: localized.supportCancel,
            privacy: localized.supportPrivacy,
            invalidEmail: localized.supportInvalidEmail
          }}
          initialQuestion={typeof relatedQuestion?.content === "string" ? relatedQuestion.content : ""}
          onCancel={closeForm}
          onSubmit={async (values) => {
            try {
              const envelope = await withWidgetAuthRetry((client) => submitSupportRequest(client, {
                sessionId: state.sessionId,
                messageId: message?.id || "user-requested-support",
                firstName: values.firstName,
                email: values.email,
                question: values.question,
                country: state.selectedCountry?.code || "",
                language: state.selectedLanguage?.code || ""
              }));
              const ticketId = envelope.data?.ticketId || envelope.correlationId;
              upsertMessage({ id: formId, role: "system", content: localized.supportQueued.replace("{id}", ticketId) });
            } catch (error) {
              if (error instanceof ApiRequestError && error.code === "SUPPORT_ROUTE_UNAVAILABLE") {
                throw new Error(localized.supportNoRoute);
              }
              throw new Error(localized.supportFailed);
            }
          }}
        />
      ),
      metadata: { supportForm: true, copyText: "" }
    };
    setMessages((current) => [...current.filter((item) => !item.metadata?.supportForm), formMessage]);
  };

  return (
    <GenericWidgetWrapper
      key={apiConfig ? "configured" : "loading"}
      config={config}
      messages={messages}
      loading={loading}
      openByDefault
      openSignal={openSignal}
      closeSignal={closeSignal}
      resetSignal={resetSignal + lifecycleResetSignal}
      sessionId={activeAuthSessionId}
      outboundMessage={sdkMessage}
      consentRequiredSignal={consentRequiredSignal}
      onHealthCheck={checkBackendHealth}
      onAcceptConsent={handleConsent}
      onCountryChange={(payload) => selectLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
      onLanguageChange={(payload) => selectLocale({ country: payload.selectedCountry, language: payload.selectedLanguage })}
      onSendMessage={(payload) => void sendChat(payload)}
      onMessageFeedback={handleMessageFeedback}
      onEscalate={supportAvailable ? (payload) => void handleSupportRequest({
        isOpen: true,
        selectedCountry: config.countries.find((country) => country.code === payload.selectedCountry),
        selectedLanguage: config.languages.find((language) => language.code === payload.selectedLanguage),
        consentAccepted: true,
        visitorId: payload.visitorId,
        sessionId: payload.sessionId
      }) : undefined}
      onRequestSupport={supportAvailable ? (message, state) => handleSupportRequest(state, message) : undefined}
      onNewChat={async (payload, reason = "new_chat") => {
        try {
          await withWidgetAuthRetry((client) => client.post("/api/session/end", { sessionId: payload.sessionId, reason }));
        } catch (error) {
          if (!(error instanceof ApiRequestError) || !["SESSION_EXPIRED", "SESSION_MISMATCH"].includes(error.code || "")) throw error;
        }
        const freshAuth = await authenticateWidget({ apiUrl: apiBaseUrl, widgetId }, { forceNew: true });
        const freshSessionId = freshAuth.session?.sessionId || sessionIdFromToken(freshAuth.token);
        if (!freshAuth.token || !freshSessionId) throw new Error("A new authenticated chat session could not be created.");
        setActiveAuthToken(freshAuth.token);
        activeAuthTokenRef.current = freshAuth.token;
        setActiveAuthSessionId(freshSessionId);
        conversationGenerationRef.current += 1;
        requestInFlightRef.current = false;
        setLoading(false);
        setPendingMessage(null);
        setMessages([]);
        window.localStorage.setItem(conversationStorageKey, JSON.stringify({ sessionId: freshSessionId, messages: [] }));
        const defaultLocale = { country: "US", language: "en" };
        writeLocalePreference(window.localStorage, defaultLocale, widgetId);
        setSelectedLocale(defaultLocale);
        firstMessageSentRef.current = false;
        return { sessionId: freshSessionId };
      }}
    />
  );
}
