import type { WidgetEvent } from "../events";
import { widgetEventBus } from "../events";
import { ConsoleAnalyticsProvider, NullAnalyticsProvider } from "../events/analytics";
import type { AnalyticsContext, AnalyticsEvent, AnalyticsIdentity, AnalyticsProvider } from "../events/analyticsTypes";
import type { WidgetEventSubscription } from "../events/eventListeners";
import { widgetEventTypes, type WidgetEventType } from "../events/eventTypes";

export type AnalyticsServiceOptions = {
  enabled?: boolean;
  debug?: boolean;
  provider?: AnalyticsProvider;
  context?: AnalyticsContext;
};

const trackedEvents: WidgetEventType[] = [
  widgetEventTypes.WIDGET_INITIALIZED,
  widgetEventTypes.WIDGET_OPENED,
  widgetEventTypes.WIDGET_CLOSED,
  widgetEventTypes.CHAT_STARTED,
  widgetEventTypes.FIRST_MESSAGE,
  widgetEventTypes.MESSAGE_SENT,
  widgetEventTypes.MESSAGE_RECEIVED,
  widgetEventTypes.MESSAGE_FAILED,
  widgetEventTypes.SESSION_CREATED,
  widgetEventTypes.SESSION_RESTORED,
  widgetEventTypes.SESSION_EXPIRED,
  widgetEventTypes.CONSENT_ACCEPTED,
  widgetEventTypes.CONSENT_REJECTED,
  widgetEventTypes.COUNTRY_CHANGED,
  widgetEventTypes.LANGUAGE_CHANGED,
  widgetEventTypes.API_ERROR,
  widgetEventTypes.NETWORK_ERROR,
  widgetEventTypes.TIMEOUT_ERROR
];

export class AnalyticsService {
  private enabled: boolean;
  private provider: AnalyticsProvider;
  private context?: AnalyticsContext;
  private subscriptions: WidgetEventSubscription[] = [];

  constructor(options: AnalyticsServiceOptions = {}) {
    this.enabled = options.enabled !== false;
    this.provider = options.provider || (this.enabled ? new ConsoleAnalyticsProvider({ debug: options.debug }) : new NullAnalyticsProvider());
    this.context = options.context;
  }

  attachToEventBus(eventBus = widgetEventBus) {
    this.detach();
    if (!this.enabled) return;

    this.subscriptions = trackedEvents.map((eventType) =>
      eventBus.subscribe(eventType, (event) => {
        void this.trackWidgetEvent(event);
      })
    );
  }

  detach() {
    this.subscriptions.forEach((subscription) => subscription.unsubscribe());
    this.subscriptions = [];
  }

  async trackEvent(event: AnalyticsEvent) {
    if (!this.enabled) return;
    await this.provider.trackEvent({
      ...event,
      properties: {
        ...(this.context || {}),
        ...(event.properties || {})
      }
    });
  }

  async identify(identity: AnalyticsIdentity) {
    if (!this.enabled || !this.provider.identify) return;
    await this.provider.identify(identity);
  }

  async setContext(context: AnalyticsContext) {
    this.context = {
      ...(this.context || {}),
      ...context
    };
    if (!this.enabled || !this.provider.setContext) return;
    await this.provider.setContext(this.context);
  }

  async flush() {
    if (!this.enabled || !this.provider.flush) return;
    await this.provider.flush();
  }

  private async trackWidgetEvent(event: WidgetEvent) {
    await this.trackEvent({
      name: event.type,
      timestamp: event.timestamp,
      sessionId: event.payload.sessionId,
      visitorId: event.payload.visitorId,
      correlationId: event.payload.correlationId,
      properties: event.payload.metadata
    });
  }
}

export function createAnalyticsService(options?: AnalyticsServiceOptions) {
  return new AnalyticsService(options);
}
