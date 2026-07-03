import type {
  ConsentActionType,
  GenericWidgetConfig,
  WidgetCountryOption,
  WidgetLanguageOption
} from "./types";

const createId = (prefix: string) =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `${prefix}_${crypto.randomUUID()}`
    : `${prefix}_${Math.random().toString(36).slice(2)}_${Date.now().toString(36)}`;

export const createVisitorId = () => createId("visitor");

export const createSessionId = () => createId("session");

export const readStoredId = (storageKey?: string) =>
  storageKey && typeof localStorage !== "undefined" ? localStorage.getItem(storageKey) || undefined : undefined;

export const writeStoredId = (storageKey: string | undefined, value: string) => {
  if (!storageKey || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, value);
};

export type StoredSessionMetadata = {
  sessionId: string;
  createdAt: string;
  legalVersion: string;
  market?: string;
  language?: string;
};

export const readSessionMetadata = (storageKey?: string): StoredSessionMetadata | undefined => {
  if (!storageKey || typeof localStorage === "undefined") return undefined;
  const raw = localStorage.getItem(storageKey);
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredSessionMetadata>;
    if (!parsed.sessionId || !parsed.createdAt || !parsed.legalVersion) return undefined;
    return {
      sessionId: parsed.sessionId,
      createdAt: parsed.createdAt,
      legalVersion: parsed.legalVersion,
      market: parsed.market,
      language: parsed.language
    };
  } catch {
    return undefined;
  }
};

export const writeSessionMetadata = (storageKey: string | undefined, metadata: StoredSessionMetadata) => {
  if (!storageKey || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, JSON.stringify(metadata));
};

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

export const readConsentFlag = (storageKey?: string) =>
  Boolean(storageKey && typeof localStorage !== "undefined" && localStorage.getItem(storageKey) === "true");

export const writeConsentFlag = (storageKey: string | undefined, accepted: boolean) => {
  if (!storageKey || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, accepted ? "true" : "false");
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
