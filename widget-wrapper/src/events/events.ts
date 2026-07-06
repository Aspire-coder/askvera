import type { ConsentEventPayload, LocaleChangePayload, MessageEventPayload, WidgetMessage } from "../generic-widget/types";
import type { WidgetEventType } from "./eventTypes";

export type BaseWidgetEventPayload = {
  timestamp?: string;
  sessionId?: string;
  visitorId?: string;
  correlationId?: string;
  metadata?: Record<string, unknown>;
};

export type WidgetEventPayloadMap = {
  WIDGET_INITIALIZED: BaseWidgetEventPayload;
  WIDGET_OPENED: BaseWidgetEventPayload;
  WIDGET_CLOSED: BaseWidgetEventPayload;
  WIDGET_DESTROYED: BaseWidgetEventPayload;
  MESSAGE_SENT: BaseWidgetEventPayload & { message: MessageEventPayload };
  MESSAGE_RECEIVED: BaseWidgetEventPayload & { message: WidgetMessage };
  MESSAGE_FAILED: BaseWidgetEventPayload & { error: string };
  MESSAGE_RETRIED: BaseWidgetEventPayload & { message: MessageEventPayload };
  MESSAGE_COPIED: BaseWidgetEventPayload & { message: WidgetMessage };
  MESSAGE_HELPFUL: BaseWidgetEventPayload & { message: WidgetMessage; rating: number };
  MESSAGE_NOT_HELPFUL: BaseWidgetEventPayload & { message: WidgetMessage; rating: number };
  CONSENT_REQUIRED: BaseWidgetEventPayload & { reason?: string };
  CONSENT_ACCEPTED: BaseWidgetEventPayload & { consent: ConsentEventPayload };
  CONSENT_REJECTED: BaseWidgetEventPayload & { consent: ConsentEventPayload };
  COUNTRY_CHANGED: BaseWidgetEventPayload & { locale: LocaleChangePayload };
  LANGUAGE_CHANGED: BaseWidgetEventPayload & { locale: LocaleChangePayload };
  SESSION_CREATED: BaseWidgetEventPayload;
  SESSION_RESTORED: BaseWidgetEventPayload;
  SESSION_RESET: BaseWidgetEventPayload;
  SESSION_EXPIRED: BaseWidgetEventPayload;
  BACKEND_CONNECTED: BaseWidgetEventPayload;
  BACKEND_DISCONNECTED: BaseWidgetEventPayload & { error?: string };
  RECONNECT_STARTED: BaseWidgetEventPayload;
  RECONNECT_COMPLETED: BaseWidgetEventPayload;
  API_ERROR: BaseWidgetEventPayload & { error: string };
  NETWORK_ERROR: BaseWidgetEventPayload & { error: string };
  TIMEOUT_ERROR: BaseWidgetEventPayload & { error: string };
  VALIDATION_ERROR: BaseWidgetEventPayload & { error: string };
  UNKNOWN_ERROR: BaseWidgetEventPayload & { error: string };
  CHAT_STARTED: BaseWidgetEventPayload;
  FIRST_MESSAGE: BaseWidgetEventPayload & { message: MessageEventPayload };
  FEEDBACK_SUBMITTED: BaseWidgetEventPayload;
};

export type WidgetEvent<TType extends WidgetEventType = WidgetEventType> = {
  type: TType;
  timestamp: string;
  payload: WidgetEventPayloadMap[TType];
};
