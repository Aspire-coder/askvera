import type { BackendConfig } from "./backendConfig";
import type { RuntimeConfig } from "./runtimeConfig";
import type { ThemeConfig } from "./themeConfig";

export type ConfigValidationResult = {
  valid: boolean;
  warnings: string[];
  errors: string[];
};

const isValidUrl = (value: string) => {
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
};

export function validateRuntimeConfig(config: RuntimeConfig): ConfigValidationResult {
  const warnings: string[] = [];
  const errors: string[] = [];

  if (!config.apiUrl || !isValidUrl(config.apiUrl)) {
    errors.push("Runtime configuration requires a valid apiUrl.");
  }

  if (config.width !== undefined && typeof config.width !== "number" && typeof config.width !== "string") {
    warnings.push("Widget width should be a number or CSS string.");
  }

  if (config.height !== undefined && typeof config.height !== "number" && typeof config.height !== "string") {
    warnings.push("Widget height should be a number or CSS string.");
  }

  return { valid: errors.length === 0, warnings, errors };
}

export function validateBackendConfig(config?: BackendConfig): ConfigValidationResult {
  const warnings: string[] = [];
  const errors: string[] = [];

  if (!config) return { valid: true, warnings, errors };

  const countryCodes = new Set<string>();
  for (const country of config.countries) {
    if (!country.code) errors.push("Backend configuration contains a country without a code.");
    if (countryCodes.has(country.code)) errors.push(`Backend configuration contains duplicate country code ${country.code}.`);
    countryCodes.add(country.code);

    const languageCodes = new Set<string>();
    for (const language of country.languages) {
      if (!language.code) errors.push(`Country ${country.code} contains a language without a code.`);
      if (languageCodes.has(language.code)) {
        errors.push(`Country ${country.code} contains duplicate language code ${language.code}.`);
      }
      languageCodes.add(language.code);
    }
  }

  if (!config.privacyVersion) {
    warnings.push("Backend configuration did not include a privacyVersion.");
  }

  return { valid: errors.length === 0, warnings, errors };
}

export function validateThemeConfig(config?: ThemeConfig): ConfigValidationResult {
  const warnings: string[] = [];
  const errors: string[] = [];

  if (config?.mode && !["light", "dark", "custom"].includes(config.mode)) {
    errors.push(`Unsupported theme mode ${config.mode}.`);
  }

  return { valid: errors.length === 0, warnings, errors };
}
