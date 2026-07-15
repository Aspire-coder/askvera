import type { GenericWidgetConfig, WidgetCountryOption, WidgetLanguageOption } from "./types";

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
  return (
    <section className="gw-section gw-region-selector">
      <label className="gw-field">
        <span>{config.labels.countryLabel}</span>
        <select value={selectedCountryCode || ""} onChange={(event) => onCountryChange(event.target.value)}>
          {config.labels.countryPlaceholder ? <option value="">{config.labels.countryPlaceholder}</option> : null}
          {countries.map((country) => <option key={country.code} value={country.code}>{country.label}</option>)}
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
          {languages.map((language) => <option key={language.code} value={language.code}>{language.label}</option>)}
        </select>
      </label>
    </section>
  );
}
