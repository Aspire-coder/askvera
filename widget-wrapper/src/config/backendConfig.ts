import type { WidgetCountryOption, WidgetLanguageOption, WidgetPolicyLink, WidgetTopic } from "../generic-widget/types";

export type BackendLanguage = {
  code: string;
  name: string;
};

export type BackendCountry = {
  code: string;
  name: string;
  languages: BackendLanguage[];
};

export type LegalDocumentConfig = {
  id: string;
  title: string;
  required: boolean;
  html?: string;
};

export type BackendConfig = {
  widgetId?: string;
  companyName?: string;
  logo?: string;
  theme?: "light" | "dark" | "custom" | string;
  primaryColor?: string;
  countries: BackendCountry[];
  privacyVersion: string;
  legalDocuments?: LegalDocumentConfig[];
  starterTopics?: WidgetTopic[];
  contextualTopics?: WidgetTopic[];
  kbMetadata?: Record<string, unknown>;
  limits?: Record<string, unknown>;
};

export type NormalizedBackendConfig = {
  countries: WidgetCountryOption[];
  languages: WidgetLanguageOption[];
  policyVersion?: string;
  policyLinks?: WidgetPolicyLink[];
  starterTopics?: WidgetTopic[];
  contextualTopics?: WidgetTopic[];
  metadata: Record<string, unknown>;
};

export function normalizeBackendConfig(
  backendConfig: BackendConfig | undefined,
  options: {
    apiUrl: string;
    country: string;
    language: string;
    legalLinkBuilder?: (apiUrl: string, country: string, language: string, documentId: string) => string;
    fallbackPolicyLinks?: WidgetPolicyLink[];
  }
): NormalizedBackendConfig | undefined {
  if (!backendConfig) return undefined;

  const languageMap = new Map<string, { label: string; countryCodes: string[] }>();
  const sortedCountries = [...backendConfig.countries].sort((first, second) => first.name.localeCompare(second.name));

  for (const country of sortedCountries) {
    for (const language of country.languages) {
      const current = languageMap.get(language.code) || { label: language.name, countryCodes: [] };
      if (!current.countryCodes.includes(country.code)) {
        current.countryCodes.push(country.code);
      }
      languageMap.set(language.code, current);
    }
  }

  const policyLinks = backendConfig.legalDocuments?.length
    ? backendConfig.legalDocuments.map((document) => ({
        id: document.id,
        label: document.title,
        required: document.required,
        html: document.html,
        href: options.legalLinkBuilder
          ? options.legalLinkBuilder(options.apiUrl, options.country, options.language, document.id)
          : "#",
        target: "_blank" as const
      }))
    : options.fallbackPolicyLinks;

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
    })),
    policyVersion: backendConfig.privacyVersion,
    policyLinks,
    starterTopics: backendConfig.starterTopics,
    contextualTopics: backendConfig.contextualTopics,
    metadata: {
      kbMetadata: backendConfig.kbMetadata,
      limits: backendConfig.limits
    }
  };
}
