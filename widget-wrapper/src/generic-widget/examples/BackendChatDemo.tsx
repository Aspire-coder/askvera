import { useEffect, useMemo, useState } from "react";
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

type ApiCountry = {
  code: string;
  name: string;
  languages: Array<{ code: string; name: string }>;
};

type ConfigResponseData = {
  countries: ApiCountry[];
  privacyVersion: string;
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

  for (const country of countries) {
    for (const language of country.languages) {
      const current = languageMap.get(language.code) || { label: language.name, countryCodes: [] };
      if (!current.countryCodes.includes(country.code)) {
        current.countryCodes.push(country.code);
      }
      languageMap.set(language.code, current);
    }
  }

  return {
    countries: countries.map((country) => ({
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
  const config = useMemo(
    () => {
      const localeOptions = apiConfig ? buildLocaleOptions(apiConfig.countries) : null;

      return {
        ...foreverDemoConfig,
        provider: { name: "ASK Vera API", type: "custom-react" as const },
        consent: {
          ...foreverDemoConfig.consent,
          policyVersion: apiConfig?.privacyVersion || foreverDemoConfig.consent.policyVersion
        },
        countries: localeOptions?.countries || foreverDemoConfig.countries,
        languages: localeOptions?.languages || foreverDemoConfig.languages,
        policyLinks: foreverDemoConfig.policyLinks.map((link) => ({
          ...link,
          href: link.href.startsWith("/api/") ? joinUrl(apiBaseUrl, link.href) : link.href
        }))
      };
    },
    [apiBaseUrl, apiConfig]
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
