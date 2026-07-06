import type { WidgetTheme } from "../generic-widget/types";

export type ThemeMode = "light" | "dark" | "custom";

export type ThemeConfig = WidgetTheme & {
  mode?: ThemeMode;
  spacingScale?: "compact" | "comfortable";
  animationEnabled?: boolean;
};

export function buildThemeConfig(theme?: ThemeConfig, accentColor?: string, fontFamily?: string): ThemeConfig {
  return {
    ...(theme || {}),
    ...(accentColor ? { accentColor, launcherTextColor: accentColor } : {}),
    ...(fontFamily ? { fontFamily } : {})
  };
}
