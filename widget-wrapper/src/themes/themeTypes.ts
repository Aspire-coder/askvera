import type { CSSProperties } from "react";
import type { WidgetTheme } from "../generic-widget/types";

export type WidgetThemeMode = "light" | "dark" | "custom";

export type WidgetThemeTokens = Required<WidgetTheme> & {
  mode: WidgetThemeMode;
  secondaryColor: string;
  warningColor: string;
  errorColor: string;
  backgroundColor: string;
  headerBackgroundColor: string;
  headerTextColor: string;
  fieldBackgroundColor: string;
  fieldTextColor: string;
  focusRingColor: string;
  panelWidth: string;
  panelHeight: string;
  launcherSize: string;
  animationDuration: string;
  animationEasing: string;
  spacingUnit: string;
};

export type ThemeInput = WidgetTheme & Partial<Omit<WidgetThemeTokens, keyof WidgetTheme>>;

export type ThemeCssVariables = CSSProperties & Record<`--gw-${string}`, string>;
