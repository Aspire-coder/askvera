import { WidgetFeatures } from "../constants";

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
  streaming: WidgetFeatures.streaming,
  markdown: WidgetFeatures.markdown,
  feedback: WidgetFeatures.feedback,
  typingIndicator: WidgetFeatures.typingIndicator,
  darkMode: WidgetFeatures.darkMode,
  citations: WidgetFeatures.citations,
  attachments: WidgetFeatures.attachments,
  analytics: WidgetFeatures.analytics
});

export function mergeFeatureFlags(overrides?: Partial<WidgetFeatureFlags>): WidgetFeatureFlags {
  return {
    ...defaultFeatureFlags,
    ...(overrides || {})
  };
}
