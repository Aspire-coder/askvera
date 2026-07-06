import type { WidgetCountryOption, WidgetLanguageOption, WidgetMessage } from "../generic-widget/types";

export type WidgetActivePanel = "chat" | "consent" | "settings" | "history";

export type WidgetState = {
  ui: {
    open: boolean;
    minimized: boolean;
    loading: boolean;
    typing: boolean;
    menuOpen: boolean;
    showSuccess: boolean;
    consentSubmitting: boolean;
    activePanel: WidgetActivePanel;
    draftMessage: string;
  };
  session: {
    visitorId: string;
    sessionId: string;
    createdAt: string;
    expiresAt?: string;
  };
  conversation: {
    messages: WidgetMessage[];
    pendingMessage?: string;
    requestInFlight: boolean;
  };
  consent: {
    accepted: boolean;
    version: string;
    pendingRetry: boolean;
    error?: string | null;
  };
  locale: {
    country?: WidgetCountryOption;
    language?: WidgetLanguageOption;
  };
  connection: {
    online: boolean;
    reconnecting: boolean;
    backendHealthy?: boolean;
  };
  errors: {
    lastError?: string | null;
    warnings: string[];
  };
  analytics: {
    openedAt?: string;
    lastEventAt?: string;
  };
};

export type CreateWidgetInitialStateOptions = {
  openByDefault: boolean;
  loading: boolean;
  initialConsentAccepted: boolean;
  initialShowSuccess: boolean;
  visitorId: string;
  sessionId: string;
  sessionCreatedAt: string;
  policyVersion: string;
  selectedCountry?: WidgetCountryOption;
  selectedLanguage?: WidgetLanguageOption;
  messages: WidgetMessage[];
};

export function createWidgetInitialState({
  openByDefault,
  loading,
  initialConsentAccepted,
  initialShowSuccess,
  visitorId,
  sessionId,
  sessionCreatedAt,
  policyVersion,
  selectedCountry,
  selectedLanguage,
  messages
}: CreateWidgetInitialStateOptions): WidgetState {
  const now = new Date().toISOString();

  return {
    ui: {
      open: openByDefault,
      minimized: false,
      loading,
      typing: false,
      menuOpen: false,
      showSuccess: initialShowSuccess,
      consentSubmitting: false,
      activePanel: initialConsentAccepted ? "chat" : "consent",
      draftMessage: ""
    },
    session: {
      visitorId,
      sessionId,
      createdAt: sessionCreatedAt
    },
    conversation: {
      messages,
      requestInFlight: false
    },
    consent: {
      accepted: initialConsentAccepted,
      version: policyVersion,
      pendingRetry: false,
      error: null
    },
    locale: {
      country: selectedCountry,
      language: selectedLanguage
    },
    connection: {
      online: true,
      reconnecting: false
    },
    errors: {
      lastError: null,
      warnings: []
    },
    analytics: {
      openedAt: openByDefault ? now : undefined,
      lastEventAt: now
    }
  };
}
