import type { WidgetFeatureFlags } from "./featureFlags";
import type { ThemeConfig } from "./themeConfig";
import type { WidgetTopic } from "../generic-widget/types";

export type LauncherPosition = "bottom-right" | "bottom-left";

export type RuntimeEventCallbacks = {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Error) => void;
};

export type RuntimeConfig = {
  apiUrl: string;
  providerName?: string;
  companyName?: string;
  assistantName?: string;
  assistantSubtitle?: string;
  logoUrl?: string;
  launcherIconUrl?: string;
  launcherTitle?: string;
  launcherAriaLabel?: string;
  accentColor?: string;
  theme?: ThemeConfig;
  launcherPosition?: LauncherPosition;
  width?: number | string;
  height?: number | string;
  welcomeTitle?: string;
  welcomeMessage?: string;
  assistantPromise?: string;
  footerText?: string;
  starterTopics?: WidgetTopic[];
  contextualTopics?: WidgetTopic[];
  defaultCountry?: string;
  defaultLanguage?: string;
  fontFamily?: string;
  debug?: boolean;
  features?: Partial<WidgetFeatureFlags>;
  events?: RuntimeEventCallbacks;
};

export type NormalizedRuntimeConfig = RuntimeConfig & {
  launcherPosition: LauncherPosition;
  debug: boolean;
};
