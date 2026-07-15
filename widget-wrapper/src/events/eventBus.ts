import type { WidgetEvent, WidgetEventPayloadMap } from "./events";
import type { WidgetEventListener, WidgetEventListenerMap, WidgetEventSubscription } from "./eventListeners";
import type { WidgetEventType } from "./eventTypes";

export type WidgetEventBusOptions = {
  debug?: boolean;
  logger?: Pick<Console, "info" | "warn">;
};

export class WidgetEventBus {
  private listeners: WidgetEventListenerMap = {};
  private debug: boolean;
  private logger: Pick<Console, "info" | "warn">;

  constructor(options: WidgetEventBusOptions = {}) {
    this.debug = Boolean(options.debug);
    this.logger = options.logger || console;
  }

  emit<TType extends WidgetEventType>(type: TType, payload: WidgetEventPayloadMap[TType]): WidgetEvent<TType> {
    const event: WidgetEvent<TType> = {
      type,
      timestamp: new Date().toISOString(),
      payload: {
        ...payload,
        timestamp: payload.timestamp || new Date().toISOString()
      }
    };

    if (this.debug) {
      this.logger.info("[AskVera Event]", event.type, event);
    }

    const listeners = this.listeners[type] as Set<WidgetEventListener<TType>> | undefined;
    listeners?.forEach((listener) => {
      try {
        listener(event);
      } catch (error) {
        this.logger.warn("[AskVera Event] listener failed", error);
      }
    });

    return event;
  }

  subscribe<TType extends WidgetEventType>(
    type: TType,
    listener: WidgetEventListener<TType>
  ): WidgetEventSubscription {
    const current = (this.listeners[type] || new Set()) as Set<WidgetEventListener<TType>>;
    current.add(listener);
    this.listeners[type] = current as WidgetEventListenerMap[TType];

    return {
      unsubscribe: () => this.unsubscribe(type, listener)
    };
  }

  unsubscribe<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>) {
    const listeners = this.listeners[type] as Set<WidgetEventListener<TType>> | undefined;
    listeners?.delete(listener);
  }

  once<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>): WidgetEventSubscription {
    const subscription = this.subscribe(type, (event) => {
      subscription.unsubscribe();
      listener(event);
    });
    return subscription;
  }

  clear() {
    this.listeners = {};
  }
}

export const widgetEventBus = new WidgetEventBus();
