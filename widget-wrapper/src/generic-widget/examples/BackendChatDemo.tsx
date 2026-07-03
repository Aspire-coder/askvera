import { useEffect, useMemo, useState } from "react";
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

  constructor(message: string, code?: string, legalVersion?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.legalVersion = legalVersion;
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

async function postJson<T>(baseUrl: string, path: string, body: unknown): Promise<ApiEnvelope<T>> {
  const response = await fetch(joinUrl(baseUrl, path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !envelope.success) {
    throw new ApiRequestError(
      envelope.error?.message || `Request failed with status ${response.status}`,
      envelope.error?.code,
      envelope.error?.legalVersion
    );
  }
  return envelope;
}

async function getJson<T>(baseUrl: string, path: string): Promise<ApiEnvelope<T>> {
  const response = await fetch(joinUrl(baseUrl, path));
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error?.message || `Request failed with status ${response.status}`);
  }
  return envelope;
}

function buildLocaleOptions(countries: ApiCountry[]) {
  const languageMap = new Map<string, { label: string; countryCodes: string[] }>();
  const sortedCountries = [...countries].sort((first, second) => first.name.localeCompare(second.name));

  for (const country of sortedCountries) {
    for (const language of country.languages) {
      const current = languageMap.get(language.code) || { label: language.name, countryCodes: [] };
      if (!current.countryCodes.includes(country.code)) {
        current.countryCodes.push(country.code);
      }
      languageMap.set(language.code, current);
    }
  }

  return {
    countries: sortedCountries.map((country) => ({
      code: country.code,
      label: country.name,
      languageCodes: country.languages.map((language) => language.code)
    })),
    languages: Array.from(languageMap.entries()).map(([code, language]) => ({
      code,
      label: language.label,
      countryCodes: language.countryCodes
    }))
  };
}

export function BackendChatDemo({ apiBaseUrl = "https://api.vera-api.xyz" }: BackendChatDemoProps) {
  const [apiConfig, setApiConfig] = useState<ConfigResponseData | null>(null);
  const [selectedLocale, setSelectedLocale] = useState({ country: "US", language: "en" });
  const [legalDocuments, setLegalDocuments] = useState<LegalDocument[]>([]);
  const [legalVersion, setLegalVersion] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<MessageEventPayload | null>(null);
  const [consentRequiredSignal, setConsentRequiredSignal] = useState(0);
  const config = useMemo(
    () => {
      const localeOptions = apiConfig ? buildLocaleOptions(apiConfig.countries) : null;
      const policyLinks = legalDocuments.length
        ? legalDocuments.map((document) => ({
            id: document.id,
            label: document.title,
            href: legalViewerHref(apiBaseUrl, selectedLocale.country, selectedLocale.language, document.id),
            target: "_blank" as const
          }))
        : foreverDemoConfig.policyLinks.map((link) => ({
            ...link,
            href: legalViewerHref(apiBaseUrl, selectedLocale.country, selectedLocale.language, link.id === "terms" ? "privacy" : link.id),
            target: "_blank" as const
          }));

      return {
        ...foreverDemoConfig,
        provider: { name: "ASK Vera API", type: "custom-react" as const },
        consent: {
          ...foreverDemoConfig.consent,
          policyVersion: legalVersion || apiConfig?.privacyVersion || foreverDemoConfig.consent.policyVersion
        },
        countries: localeOptions?.countries || foreverDemoConfig.countries,
        languages: localeOptions?.languages || foreverDemoConfig.languages,
        defaultCountryCode: selectedLocale.country,
        defaultLanguageCode: selectedLocale.language,
        policyLinks
      };
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

  const appendMessage = (message: WidgetMessage) => {
    setMessages((current) => [...current, message]);
  };

  useEffect(() => {
    let active = true;

    getJson<ConfigResponseData>(apiBaseUrl, "/api/config")
      .then((envelope) => {
        if (active && envelope.data) {
          setApiConfig(envelope.data);
        }
      })
      .catch((error) => {
        if (active) {
          appendMessage({
            id: buildId("config-warning"),
            role: "system",
            content: error instanceof Error ? `Using demo market list because API config could not load: ${error.message}` : "Using demo market list because API config could not load."
          });
        }
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl]);

  useEffect(() => {
    let active = true;
    const path = `/api/privacy?country=${encodeURIComponent(selectedLocale.country)}&lang=${encodeURIComponent(selectedLocale.language)}`;

    getJson<PrivacyResponseData>(apiBaseUrl, path)
      .then((envelope) => {
        if (active && envelope.data) {
          setLegalDocuments(envelope.data.documents);
          setLegalVersion(envelope.data.version);
        }
      })
      .catch((error) => {
        if (active) {
          setLegalDocuments([]);
          appendMessage({
            id: buildId("privacy-warning"),
            role: "system",
            content: error instanceof Error ? `Legal documents could not load yet: ${error.message}` : "Legal documents could not load yet."
          });
        }
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl, selectedLocale.country, selectedLocale.language]);

  const handleConsent = async (payload: ConsentEventPayload) => {
    await postJson(apiBaseUrl, "/api/consent", {
      sessionId: payload.sessionId,
      country: payload.selectedCountry,
      lang: payload.selectedLanguage,
      timestamp: payload.timestamp,
      version: payload.policyVersion
    });
    if (pendingMessage) {
      const retryPayload = { ...pendingMessage, sessionId: payload.sessionId };
      setPendingMessage(null);
      await sendChat(retryPayload, false);
    }
  };

  const sendChat = async (payload: MessageEventPayload, showUserMessage = true) => {
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
        content: error instanceof Error ? `The API is not ready yet: ${error.message}` : "The API is not ready yet."
      });
    } finally {
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
