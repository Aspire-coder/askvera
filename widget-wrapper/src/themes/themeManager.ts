import type { WidgetTheme } from "../generic-widget/types";
import { themeToCssVariables } from "./cssVariables";
import { darkTheme, lightTheme } from "./themeTokens";
import type { ThemeCssVariables, ThemeInput, WidgetThemeMode, WidgetThemeTokens } from "./themeTypes";

export function resolveTheme(theme?: ThemeInput | WidgetTheme, mode: WidgetThemeMode = "light"): WidgetThemeTokens {
  const requestedMode = (theme as ThemeInput | undefined)?.mode || mode;
  const base = requestedMode === "dark" ? darkTheme : lightTheme;

  return {
    ...base,
    ...(theme || {}),
    mode: requestedMode
  };
}

export function buildThemeVars(theme?: ThemeInput | WidgetTheme, mode?: WidgetThemeMode): ThemeCssVariables {
  return themeToCssVariables(resolveTheme(theme, mode));
}

export class ThemeManager {
  private theme: WidgetThemeTokens;

  constructor(theme?: ThemeInput | WidgetTheme, mode?: WidgetThemeMode) {
    this.theme = resolveTheme(theme, mode);
  }

  getTheme() {
    return this.theme;
  }

  update(theme?: ThemeInput | WidgetTheme, mode?: WidgetThemeMode) {
    this.theme = resolveTheme(theme, mode || this.theme.mode);
    return this.theme;
  }

  toCssVariables() {
    return themeToCssVariables(this.theme);
  }
}

export function createThemeManager(theme?: ThemeInput | WidgetTheme, mode?: WidgetThemeMode) {
  return new ThemeManager(theme, mode);
}
