export const WidgetFeatures = {
  analytics: true,
  attachments: false,
  citations: false,
  darkMode: true,
  debugMode: false,
  feedback: true,
  localization: true,
  markdown: true,
  plugins: true,
  richRendering: true,
  streaming: false,
  typingIndicator: true
} as const;

export type WidgetFeatureKey = keyof typeof WidgetFeatures;
