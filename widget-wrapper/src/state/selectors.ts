import type { GenericWidgetRenderState, WidgetMessage } from "../generic-widget/types";
import type { WidgetState } from "./widgetState";

export const selectIsOpen = (state: WidgetState) => state.ui.open;
export const selectMenuOpen = (state: WidgetState) => state.ui.menuOpen;
export const selectLoading = (state: WidgetState) => state.ui.loading;
export const selectTyping = (state: WidgetState) => state.ui.typing;
export const selectDraftMessage = (state: WidgetState) => state.ui.draftMessage;
export const selectShowSuccess = (state: WidgetState) => state.ui.showSuccess;
export const selectConsentSubmitting = (state: WidgetState) => state.ui.consentSubmitting;
export const selectMessages = (state: WidgetState): WidgetMessage[] => state.conversation.messages;
export const selectCountry = (state: WidgetState) => state.locale.country;
export const selectLanguage = (state: WidgetState) => state.locale.language;
export const selectConsentAccepted = (state: WidgetState) => state.consent.accepted;
export const selectConsentError = (state: WidgetState) => state.consent.error;
export const selectConnection = (state: WidgetState) => state.connection;

export function selectRenderState(state: WidgetState): GenericWidgetRenderState {
  return {
    isOpen: state.ui.open,
    selectedCountry: state.locale.country,
    selectedLanguage: state.locale.language,
    consentAccepted: state.consent.accepted,
    visitorId: state.session.visitorId,
    sessionId: state.session.sessionId
  };
}
