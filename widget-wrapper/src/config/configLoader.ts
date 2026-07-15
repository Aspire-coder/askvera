import type { GenericWidgetConfig } from "../generic-widget/types";
import { normalizeBackendConfig, type BackendConfig } from "./backendConfig";
import { defaultRuntimeConfig } from "./defaults";
import { mergeFeatureFlags, type WidgetFeatureFlags } from "./featureFlags";
import type { RuntimeConfig } from "./runtimeConfig";
import { buildThemeConfig, type ThemeConfig } from "./themeConfig";
import { validateBackendConfig, validateRuntimeConfig, validateThemeConfig, type ConfigValidationResult } from "./configValidator";

export type WidgetConfig = Readonly<{
  runtime: RuntimeConfig;
  backend?: BackendConfig;
  theme: ThemeConfig;
  features: WidgetFeatureFlags;
  genericConfig: GenericWidgetConfig;
  validation: ConfigValidationResult;
}>;

export type BuildWidgetConfigOptions = {
  baseConfig: GenericWidgetConfig;
  runtimeConfig?: Partial<RuntimeConfig>;
  backendConfig?: BackendConfig;
  themeConfig?: ThemeConfig;
  selectedCountry: string;
  selectedLanguage: string;
  legalLinkBuilder?: (apiUrl: string, country: string, language: string, documentId: string) => string;
};

function combineValidation(...results: ConfigValidationResult[]): ConfigValidationResult {
  const errors = results.flatMap((result) => result.errors);
  const warnings = results.flatMap((result) => result.warnings);
  return { valid: errors.length === 0, errors, warnings };
}

function freezeConfig<T extends Record<string, unknown>>(value: T): Readonly<T> {
  return Object.freeze(value);
}

function buildRuntimeWelcomeText(runtime: RuntimeConfig, fallback: GenericWidgetConfig["welcomeText"]) {
  const parts = [runtime.welcomeTitle, runtime.welcomeMessage, runtime.assistantPromise].filter(Boolean);
  return parts.length ? parts.join("\n\n") : fallback;
}

export function buildWidgetConfig({
  baseConfig,
  runtimeConfig,
  backendConfig,
  themeConfig,
  selectedCountry,
  selectedLanguage,
  legalLinkBuilder
}: BuildWidgetConfigOptions): WidgetConfig {
  const runtime: RuntimeConfig = {
    ...defaultRuntimeConfig,
    ...runtimeConfig,
    apiUrl: runtimeConfig?.apiUrl || defaultRuntimeConfig.apiUrl
  };
  const theme = buildThemeConfig(themeConfig || runtime.theme, runtime.accentColor, runtime.fontFamily);
  const features = mergeFeatureFlags(runtime.features);
  const fallbackPolicyLinks = baseConfig.policyLinks.map((link) => ({
    ...link,
    href: legalLinkBuilder
      ? legalLinkBuilder(runtime.apiUrl, selectedCountry, selectedLanguage, link.id === "terms" ? "privacy" : link.id)
      : link.href,
    target: "_blank" as const
  }));
  const normalizedBackend = normalizeBackendConfig(backendConfig, {
    apiUrl: runtime.apiUrl,
    country: selectedCountry,
    language: selectedLanguage,
    legalLinkBuilder,
    fallbackPolicyLinks
  });
  const validation = combineValidation(
    validateRuntimeConfig(runtime),
    validateBackendConfig(backendConfig),
    validateThemeConfig(theme)
  );
  const copy = backendConfig?.copy || {};
  const genericConfig: GenericWidgetConfig = {
    ...baseConfig,
    brandName: runtime.companyName || baseConfig.brandName,
    assistantName: runtime.assistantName || baseConfig.assistantName,
    assistantSubtitle: copy.assistantSubtitle || runtime.assistantSubtitle || baseConfig.assistantSubtitle,
    logoUrl: runtime.logoUrl || baseConfig.logoUrl,
    launcherIconUrl: runtime.launcherIconUrl || runtime.logoUrl || baseConfig.launcherIconUrl,
    launcherTitle: runtime.launcherTitle || baseConfig.launcherTitle,
    footerText: copy.footerText || runtime.footerText || baseConfig.footerText,
    welcomeText: copy.welcomeText || buildRuntimeWelcomeText(runtime, baseConfig.welcomeText),
    loadingText: copy.loadingText || baseConfig.loadingText,
    successText: copy.successText || baseConfig.successText,
    provider: { name: runtime.providerName || baseConfig.provider.name, type: "custom-react" },
    labels: {
      ...baseConfig.labels,
      ...(copy.acceptConsentLabel ? { acceptConsentLabel: copy.acceptConsentLabel } : {}),
      ...(copy.rejectConsentLabel ? { rejectConsentLabel: copy.rejectConsentLabel } : {}),
      ...(copy.messageInputPlaceholder ? { messageInputPlaceholder: copy.messageInputPlaceholder } : {}),
      ...(runtime.launcherAriaLabel ? { launcherAriaLabel: runtime.launcherAriaLabel } : {})
    },
    theme: {
      ...baseConfig.theme,
      ...theme
    },
    consent: {
      ...baseConfig.consent,
      ...(copy.consentEyebrow ? { eyebrow: copy.consentEyebrow } : {}),
      ...(copy.consentTitle ? { title: copy.consentTitle } : {}),
      ...(copy.consentBody ? { body: copy.consentBody } : {}),
      ...(copy.consentAcknowledgmentLabel ? { acknowledgmentLabel: copy.consentAcknowledgmentLabel } : {}),
      ...(copy.consentLoadingText ? { loadingText: copy.consentLoadingText } : {}),
      ...(copy.consentDeclineTitle ? { declineTitle: copy.consentDeclineTitle } : {}),
      ...(copy.consentDeclineBody ? { declineBody: copy.consentDeclineBody } : {}),
      ...(copy.consentDeclineActionLabel ? { declineActionLabel: copy.consentDeclineActionLabel } : {}),
      policyVersion: normalizedBackend?.policyVersion || baseConfig.consent.policyVersion
    },
    countries: normalizedBackend?.countries || baseConfig.countries,
    languages: normalizedBackend?.languages || baseConfig.languages,
    defaultCountryCode: runtime.defaultCountry || selectedCountry || baseConfig.defaultCountryCode,
    defaultLanguageCode: runtime.defaultLanguage || selectedLanguage || baseConfig.defaultLanguageCode,
    policyLinks: normalizedBackend?.policyLinks || fallbackPolicyLinks,
    starterTopics: runtime.starterTopics || normalizedBackend?.starterTopics || baseConfig.starterTopics,
    contextualTopics: runtime.contextualTopics || normalizedBackend?.contextualTopics || baseConfig.contextualTopics
  };

  if (runtime.debug) {
    for (const warning of validation.warnings) console.warn(`[AskVera config] ${warning}`);
    for (const error of validation.errors) console.error(`[AskVera config] ${error}`);
  }

  return freezeConfig({
    runtime: freezeConfig(runtime as Record<string, unknown>) as RuntimeConfig,
    backend: backendConfig,
    theme: freezeConfig(theme as Record<string, unknown>) as ThemeConfig,
    features: freezeConfig(features as unknown as Record<string, unknown>) as WidgetFeatureFlags,
    genericConfig: freezeConfig(genericConfig as unknown as Record<string, unknown>) as GenericWidgetConfig,
    validation
  });
}
