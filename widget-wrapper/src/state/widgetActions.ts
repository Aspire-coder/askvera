import type { WidgetCountryOption, WidgetLanguageOption, WidgetMessage } from "../generic-widget/types";

export type WidgetAction =
  | { type: "OPEN_WIDGET" }
  | { type: "CLOSE_WIDGET" }
  | { type: "TOGGLE_MENU" }
  | { type: "SET_MENU_OPEN"; open: boolean }
  | { type: "START_LOADING" }
  | { type: "STOP_LOADING" }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_DRAFT_MESSAGE"; message: string }
  | { type: "CLEAR_DRAFT_MESSAGE" }
  | { type: "SET_COUNTRY"; country: WidgetCountryOption; language?: WidgetLanguageOption }
  | { type: "SET_LANGUAGE"; language: WidgetLanguageOption }
  | { type: "ACCEPT_CONSENT" }
  | { type: "REQUIRE_CONSENT"; error?: string }
  | { type: "START_CONSENT_SUBMIT" }
  | { type: "STOP_CONSENT_SUBMIT" }
  | { type: "SET_CONSENT_ERROR"; error: string | null }
  | { type: "SET_SUCCESS_VISIBLE"; visible: boolean }
  | { type: "SET_MESSAGES"; messages: WidgetMessage[] }
  | { type: "ADD_MESSAGE"; message: WidgetMessage }
  | { type: "UPDATE_MESSAGE"; message: WidgetMessage }
  | { type: "SET_REQUEST_IN_FLIGHT"; requestInFlight: boolean }
  | { type: "SET_CONNECTION"; online: boolean; reconnecting?: boolean; backendHealthy?: boolean }
  | { type: "RESET_SESSION"; visitorId: string; sessionId: string; createdAt: string }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "ADD_WARNING"; warning: string };
