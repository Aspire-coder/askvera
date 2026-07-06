import type { WidgetFeatureFlags } from "./featureFlags";
import type { ThemeConfig } from "./themeConfig";

export type LauncherPosition = "bottom-right" | "bottom-left";

export type RuntimeEventCallbacks = {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Error) => void;
};

export type RuntimeConfig = {
  apiUrl: string;
  companyName?: string;
  logoUrl?: string;
  accentColor?: string;
  theme?: ThemeConfig;
  launcherPosition?: LauncherPosition;
  width?: number | string;
  height?: number | string;
  welcomeMessage?: string;
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
