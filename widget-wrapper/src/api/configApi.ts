import type { ApiClient } from "./client";

export type ApiLanguage = {
  code: string;
  name: string;
};

export type ApiCountry = {
  code: string;
  name: string;
  languages: ApiLanguage[];
};

export type ConfigResponseData = {
  widgetId?: string;
  companyName?: string;
  logo?: string;
  theme?: "light" | "dark" | "custom" | string;
  primaryColor?: string;
  sdkVersion?: string;
  countries: ApiCountry[];
  privacyVersion: string;
  legalDocuments?: Array<{
    id: string;
    title: string;
    required: boolean;
    html?: string;
  }>;
  legalDocs?: Array<{
    id: string;
    title: string;
    required: boolean;
    html?: string;
  }>;
  starterTopics?: Array<{ id: string; label: string; prompt?: string; metadata?: Record<string, unknown> }>;
  contextualTopics?: Array<{ id: string; label: string; prompt?: string; metadata?: Record<string, unknown> }>;
  supportCountries?: string[];
  copy?: Record<string, string>;
};

export function loadConfig(client: ApiClient) {
  return client.get<ConfigResponseData>("/api/config");
}

export function loadWidgetConfig(client: ApiClient) {
  return client.get<ConfigResponseData>("/api/widget/config");
}
