import type { ThemeCssVariables, WidgetThemeTokens } from "./themeTypes";

export function themeToCssVariables(theme: WidgetThemeTokens): ThemeCssVariables {
  return {
    "--gw-accent": theme.accentColor,
    "--gw-accent-text": theme.accentTextColor,
    "--gw-secondary": theme.secondaryColor,
    "--gw-surface": theme.surfaceColor,
    "--gw-panel": theme.panelColor,
    "--gw-background": theme.backgroundColor,
    "--gw-text": theme.textColor,
    "--gw-muted": theme.mutedTextColor,
    "--gw-border": theme.borderColor,
    "--gw-launcher": theme.launcherColor,
    "--gw-launcher-text": theme.launcherTextColor,
    "--gw-success": theme.successColor,
    "--gw-warning": theme.warningColor,
    "--gw-danger": theme.dangerColor,
    "--gw-error": theme.errorColor,
    "--gw-header-bg": theme.headerBackgroundColor,
    "--gw-header-text": theme.headerTextColor,
    "--gw-field-bg": theme.fieldBackgroundColor,
    "--gw-field-text": theme.fieldTextColor,
    "--gw-focus-ring": theme.focusRingColor,
    "--gw-shadow": theme.shadow,
    "--gw-radius": theme.radius,
    "--gw-font": theme.fontFamily,
    "--gw-z": String(theme.zIndex),
    "--gw-panel-width": theme.panelWidth,
    "--gw-panel-height": theme.panelHeight,
    "--gw-launcher-size": theme.launcherSize,
    "--gw-motion-duration": theme.animationDuration,
    "--gw-motion-easing": theme.animationEasing,
    "--gw-space": theme.spacingUnit
  };
}
