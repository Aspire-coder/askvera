import type { WidgetEvent, WidgetEventPayloadMap } from "./events";
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

export type EmitWidgetEvent = <TType extends WidgetEventType>(
  type: TType,
  payload: WidgetEventPayloadMap[TType]
) => WidgetEvent<TType>;
