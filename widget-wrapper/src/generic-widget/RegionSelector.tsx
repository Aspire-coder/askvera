import type { GenericWidgetConfig, WidgetCountryOption, WidgetLanguageOption } from "./types";

function displayName(type: "region" | "language", code: string, locale: string, fallback: string): string {
  try {
    return new Intl.DisplayNames([locale], { type }).of(code) || fallback;
  } catch {
    return fallback;
  }
}

export function RegionSelector({
  config,
  countries,
  languages,
  selectedCountryCode,
  selectedLanguageCode,
  onCountryChange,
  onLanguageChange
}: {
  config: GenericWidgetConfig;
  countries: WidgetCountryOption[];
  languages: WidgetLanguageOption[];
  selectedCountryCode?: string;
  selectedLanguageCode?: string;
  onCountryChange: (countryCode: string) => void;
  onLanguageChange: (languageCode: string) => void;
}) {
  const displayLocale = selectedLanguageCode || config.defaultLanguageCode || "en";
  return (
    <section className="gw-section gw-region-selector">
      <label className="gw-field">
        <span>{config.labels.countryLabel}</span>
        <select value={selectedCountryCode || ""} onChange={(event) => onCountryChange(event.target.value)}>
          {config.labels.countryPlaceholder ? <option value="">{config.labels.countryPlaceholder}</option> : null}
          {countries.map((country) => (
            <option key={country.code} value={country.code}>
              {displayName("region", country.code, displayLocale, country.label)}
            </option>
          ))}
        </select>
      </label>
      <label className="gw-field">
        <span>{config.labels.languageLabel}</span>
        <select
          value={selectedLanguageCode || ""}
          onChange={(event) => onLanguageChange(event.target.value)}
          disabled={!selectedCountryCode}
        >
          {config.labels.languagePlaceholder ? <option value="">{config.labels.languagePlaceholder}</option> : null}
          {languages.map((language) => (
            <option key={language.code} value={language.code}>
              {displayName("language", language.code, displayLocale, language.label)}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
