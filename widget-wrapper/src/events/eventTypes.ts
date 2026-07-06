import { WidgetEventNames } from "../constants";

export const widgetEventTypes = WidgetEventNames;

export type WidgetEventType = (typeof widgetEventTypes)[keyof typeof widgetEventTypes];
