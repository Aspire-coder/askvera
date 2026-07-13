import type { WidgetAction } from "./widgetActions";
import type { WidgetState } from "./widgetState";

const eventTimestamp = () => new Date().toISOString();

export function widgetReducer(state: WidgetState, action: WidgetAction): WidgetState {
  const lastEventAt = eventTimestamp();

  switch (action.type) {
    case "OPEN_WIDGET":
      return {
        ...state,
        ui: { ...state.ui, open: true },
        analytics: { ...state.analytics, openedAt: state.analytics.openedAt || lastEventAt, lastEventAt }
      };
    case "CLOSE_WIDGET":
      return {
        ...state,
        ui: { ...state.ui, open: false, menuOpen: false },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "TOGGLE_MENU":
      return {
        ...state,
        ui: { ...state.ui, menuOpen: !state.ui.menuOpen },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "SET_MENU_OPEN":
      return { ...state, ui: { ...state.ui, menuOpen: action.open }, analytics: { ...state.analytics, lastEventAt } };
    case "START_LOADING":
      return { ...state, ui: { ...state.ui, loading: true }, analytics: { ...state.analytics, lastEventAt } };
    case "STOP_LOADING":
      return { ...state, ui: { ...state.ui, loading: false }, analytics: { ...state.analytics, lastEventAt } };
    case "SET_LOADING":
      return { ...state, ui: { ...state.ui, loading: action.loading }, analytics: { ...state.analytics, lastEventAt } };
    case "SET_DRAFT_MESSAGE":
      return { ...state, ui: { ...state.ui, draftMessage: action.message }, analytics: { ...state.analytics, lastEventAt } };
    case "CLEAR_DRAFT_MESSAGE":
      return { ...state, ui: { ...state.ui, draftMessage: "" }, analytics: { ...state.analytics, lastEventAt } };
    case "SET_COUNTRY":
      return {
        ...state,
        locale: { country: action.country, language: action.language || state.locale.language },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "SET_LANGUAGE":
      return { ...state, locale: { ...state.locale, language: action.language }, analytics: { ...state.analytics, lastEventAt } };
    case "ACCEPT_CONSENT":
      return {
        ...state,
        consent: { ...state.consent, accepted: true, error: null, pendingRetry: false },
        ui: { ...state.ui, showSuccess: true, consentSubmitting: false, activePanel: "chat" },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "REQUIRE_CONSENT":
      return {
        ...state,
        consent: { ...state.consent, accepted: false, error: action.error || state.consent.error, pendingRetry: true },
        ui: { ...state.ui, showSuccess: false, activePanel: "consent" },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "START_CONSENT_SUBMIT":
      return { ...state, ui: { ...state.ui, consentSubmitting: true }, analytics: { ...state.analytics, lastEventAt } };
    case "STOP_CONSENT_SUBMIT":
      return { ...state, ui: { ...state.ui, consentSubmitting: false }, analytics: { ...state.analytics, lastEventAt } };
    case "SET_CONSENT_ERROR":
      return {
        ...state,
        consent: { ...state.consent, error: action.error },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "SET_SUCCESS_VISIBLE":
      return { ...state, ui: { ...state.ui, showSuccess: action.visible }, analytics: { ...state.analytics, lastEventAt } };
    case "SET_MESSAGES":
      return { ...state, conversation: { ...state.conversation, messages: action.messages }, analytics: { ...state.analytics, lastEventAt } };
    case "ADD_MESSAGE":
      return {
        ...state,
        conversation: { ...state.conversation, messages: [...state.conversation.messages, action.message] },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "UPDATE_MESSAGE":
      return {
        ...state,
        conversation: {
          ...state.conversation,
          messages: state.conversation.messages.map((message) => (message.id === action.message.id ? action.message : message))
        },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "SET_REQUEST_IN_FLIGHT":
      return {
        ...state,
        conversation: { ...state.conversation, requestInFlight: action.requestInFlight },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "SET_CONNECTION":
      return {
        ...state,
        connection: {
          online: action.online,
          reconnecting: Boolean(action.reconnecting),
          backendHealthy: action.backendHealthy ?? action.online
        },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "RESET_SESSION":
      return {
        ...state,
        session: { visitorId: action.visitorId, sessionId: action.sessionId, createdAt: action.createdAt },
        consent: { ...state.consent, accepted: false, pendingRetry: false },
        conversation: { messages: [], requestInFlight: false },
        ui: { ...state.ui, showSuccess: false, draftMessage: "", activePanel: "consent" },
        analytics: { ...state.analytics, lastEventAt }
      };
    case "SET_ERROR":
      return { ...state, errors: { ...state.errors, lastError: action.error }, analytics: { ...state.analytics, lastEventAt } };
    case "ADD_WARNING":
      return {
        ...state,
        errors: { ...state.errors, warnings: [...state.errors.warnings, action.warning] },
        analytics: { ...state.analytics, lastEventAt }
      };
    default:
      return state;
  }
}
