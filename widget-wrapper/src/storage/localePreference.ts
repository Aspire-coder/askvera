const LOCALE_PREFERENCE_SCHEMA_VERSION = 1;
const LOCALE_PREFERENCE_STORAGE_PREFIX = "askvera_locale_preference";

type LocaleStorage = Pick<Storage, "getItem" | "setItem">;

export type LocalePreference = {
  country: string;
  language: string;
};

type StoredLocalePreference = LocalePreference & {
  schemaVersion: number;
  updatedAt: string;
};

export function localePreferenceStorageKey(widgetId?: string): string {
  const normalizedWidgetId = (widgetId || "default").trim() || "default";
  return `${LOCALE_PREFERENCE_STORAGE_PREFIX}:${normalizedWidgetId}`;
}

export function readLocalePreference(storage: LocaleStorage, widgetId?: string): LocalePreference | undefined {
  try {
    const raw = storage.getItem(localePreferenceStorageKey(widgetId));
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as Partial<StoredLocalePreference>;
    const country = typeof parsed.country === "string" ? parsed.country.trim() : "";
    const language = typeof parsed.language === "string" ? parsed.language.trim() : "";
    if (!country || !language) return undefined;
    return { country, language };
  } catch {
    return undefined;
  }
}

export function writeLocalePreference(
  storage: LocaleStorage,
  preference: LocalePreference,
  widgetId?: string
): void {
  const country = preference.country.trim();
  const language = preference.language.trim();
  if (!country || !language) return;
  const stored: StoredLocalePreference = {
    schemaVersion: LOCALE_PREFERENCE_SCHEMA_VERSION,
    country,
    language,
    updatedAt: new Date().toISOString()
  };
  try {
    storage.setItem(localePreferenceStorageKey(widgetId), JSON.stringify(stored));
  } catch {
    // Storage can be unavailable because of browser privacy settings or quota.
    // The in-memory selection remains usable for the current page.
  }
}
