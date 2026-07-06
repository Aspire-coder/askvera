import type {
  ConsentActionType,
  GenericWidgetConfig,
  WidgetCountryOption,
  WidgetLanguageOption
} from "./types";

export const filterLanguagesByCountry = (
  languages: WidgetLanguageOption[],
  countryCode?: string,
  countries: WidgetCountryOption[] = []
) => {
  if (!countryCode) return languages;
  const country = countries.find((option) => option.code === countryCode);
  if (country?.languageCodes?.length) {
    return languages.filter((language) => country.languageCodes?.includes(language.code));
  }

  return languages.filter((language) => !language.countryCodes?.length || language.countryCodes.includes(countryCode));
};

export const ensureLanguageForCountry = (
  languages: WidgetLanguageOption[],
  countryCode: string,
  currentLanguageCode?: string,
  countries: WidgetCountryOption[] = []
) => {
  const available = filterLanguagesByCountry(languages, countryCode, countries);
  return available.find((language) => language.code === currentLanguageCode) || available[0] || languages[0];
};

export const detectInitialLocale = (
  countries: WidgetCountryOption[],
  languages: WidgetLanguageOption[],
  defaultCountryCode?: string,
  defaultLanguageCode?: string
) => {
  const browserLanguage = typeof navigator !== "undefined" ? navigator.language : "";
  const [browserLanguageCode, browserCountryCode] = browserLanguage.split("-");
  const countryCode = defaultCountryCode || browserCountryCode?.toUpperCase() || countries[0]?.code || "";
  const country = countries.find((option) => option.code === countryCode) || countries[0];
  const languageOptions = filterLanguagesByCountry(languages, country?.code, countries);
  const languageCode = defaultLanguageCode || browserLanguageCode || languageOptions[0]?.code || "";
  const language = languageOptions.find((option) => option.code === languageCode) || languageOptions[0] || languages[0];

  return { country, language };
};

export const createConsentRecord = ({
  actionType,
  config,
  selectedCountry,
  selectedLanguage,
  visitorId,
  sessionId,
  metadata
}: {
  actionType: ConsentActionType;
  config: GenericWidgetConfig;
  selectedCountry: string;
  selectedLanguage: string;
  visitorId: string;
  sessionId: string;
  metadata?: Record<string, unknown>;
}) => ({
  visitorId,
  sessionId,
  timestamp: new Date().toISOString(),
  selectedCountry,
  selectedLanguage,
  policyVersion: config.consent.policyVersion,
  acceptedCategories: actionType === "accepted" ? config.consent.categories : [],
  widgetProviderName: config.provider.name,
  widgetProviderType: config.provider.type,
  actionType,
  metadata
});

export const createLocalePayload = ({
  visitorId,
  sessionId,
  selectedCountry,
  selectedLanguage,
  metadata
}: {
  visitorId: string;
  sessionId: string;
  selectedCountry: string;
  selectedLanguage: string;
  metadata?: Record<string, unknown>;
}) => ({ visitorId, sessionId, selectedCountry, selectedLanguage, metadata });
