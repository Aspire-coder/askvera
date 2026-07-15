import type { AnalyticsEvent, AnalyticsProvider } from "./analyticsTypes";

export class ConsoleAnalyticsProvider implements AnalyticsProvider {
  private debug: boolean;

  constructor({ debug = false }: { debug?: boolean } = {}) {
    this.debug = debug;
  }

  trackEvent(event: AnalyticsEvent) {
    if (!this.debug) return;
    console.info("[AskVera Analytics]", event.name, event);
  }
}

export class NullAnalyticsProvider implements AnalyticsProvider {
  trackEvent() {
    return;
  }
}
