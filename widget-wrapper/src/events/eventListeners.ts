import type { WidgetEvent } from "./events";
import type { WidgetEventType } from "./eventTypes";

export type WidgetEventListener<TType extends WidgetEventType = WidgetEventType> = (
  event: WidgetEvent<TType>
) => void;

export type WidgetEventSubscription = {
  unsubscribe: () => void;
};

export type WidgetEventListenerMap = {
  [TType in WidgetEventType]?: Set<WidgetEventListener<TType>>;
};
