export type WidgetFeatureFlags = {
  streaming: boolean;
  markdown: boolean;
  feedback: boolean;
  typingIndicator: boolean;
  darkMode: boolean;
  citations: boolean;
  attachments: boolean;
  analytics: boolean;
};

export const defaultFeatureFlags: Readonly<WidgetFeatureFlags> = Object.freeze({
  streaming: false,
  markdown: true,
  feedback: true,
  typingIndicator: true,
  darkMode: true,
  citations: false,
  attachments: false,
  analytics: true
});

export function mergeFeatureFlags(overrides?: Partial<WidgetFeatureFlags>): WidgetFeatureFlags {
  return {
    ...defaultFeatureFlags,
    ...(overrides || {})
  };
}
