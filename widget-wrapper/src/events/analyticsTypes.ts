import type { WidgetEventType } from "./eventTypes";

export type AnalyticsEventName =
  | WidgetEventType
  | "BUTTON_CLICKED"
  | "MENU_OPENED"
  | "MENU_CLOSED";

export type AnalyticsEvent = {
  name: AnalyticsEventName;
  timestamp: string;
  sessionId?: string;
  visitorId?: string;
  correlationId?: string;
  properties?: Record<string, unknown>;
};

export type AnalyticsIdentity = {
  visitorId: string;
  sessionId?: string;
  traits?: Record<string, unknown>;
};

export type AnalyticsContext = {
  widgetVersion?: string;
  companyName?: string;
  apiUrl?: string;
  country?: string;
  language?: string;
  metadata?: Record<string, unknown>;
};

export type AnalyticsProvider = {
  trackEvent(event: AnalyticsEvent): void | Promise<void>;
  identify?(identity: AnalyticsIdentity): void | Promise<void>;
  setContext?(context: AnalyticsContext): void | Promise<void>;
  flush?(): void | Promise<void>;
};
