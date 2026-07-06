import { FormEvent, useEffect, useMemo, useReducer } from "react";
import { ConsentPanel } from "./ConsentPanel";
import { FloatingLauncher } from "./FloatingLauncher";
import { Header } from "./Header";
import { Menu } from "./Menu";
import { MessageFeed } from "./MessageFeed";
import { RegionSelector } from "./RegionSelector";
import type { GenericWidgetRenderState, GenericWidgetWrapperProps, MessageEventPayload, WidgetTheme } from "./types";
import { WidgetEventBus, widgetEventBus, widgetEventTypes } from "../events";
import { createSessionManager } from "../services";
import { buildThemeVars } from "../themes";
import {
  createWidgetInitialState,
  selectConsentAccepted,
  selectConsentError,
  selectConsentSubmitting,
  selectCountry,
  selectDraftMessage,
  selectIsOpen,
  selectLanguage,
  selectLoading,
  selectMenuOpen,
  selectRenderState,
  selectShowSuccess,
  widgetReducer
} from "../state";
import {
  createConsentRecord,
  createLocalePayload,
  detectInitialLocale,
  ensureLanguageForCountry,
  filterLanguagesByCountry
} from "./utils";
import "./generic-widget.css";

export function GenericWidgetWrapper({
  config,
  children,
  messages = [],
  loading = false,
  openByDefault = false,
  initialConsentAccepted = false,
  initialShowSuccess = false,
  consentRequiredSignal = 0,
  openSignal = 0,
  closeSignal = 0,
  resetSignal = 0,
  outboundMessage,
  showLocaleSelector = true,
  visitorId: providedVisitorId,
  sessionId: providedSessionId,
  className = "",
  style,
  eventBus,
  debugEvents = false,
  renderMessages,
  onOpen,
  onClose,
  onAcceptConsent,
  onRejectConsent,
  onCountryChange,
  onLanguageChange,
  onSendMessage,
  onEscalate,
  onNewChat
}: GenericWidgetWrapperProps) {
  const events = useMemo(
    () => eventBus || (debugEvents ? new WidgetEventBus({ debug: debugEvents }) : widgetEventBus),
    [debugEvents, eventBus]
  );
  const initialLocale = useMemo(
    () => detectInitialLocale(config.countries, config.languages, config.defaultCountryCode, config.defaultLanguageCode),
    [config.countries, config.defaultCountryCode, config.defaultLanguageCode, config.languages]
  );
  const sessionManager = useMemo(
    () =>
      createSessionManager({
        keys: {
          visitorStorageKey: config.visitorStorageKey,
          sessionStorageKey: config.sessionStorageKey,
          sessionMetadataStorageKey: config.sessionMetadataStorageKey,
          consentStorageKey: config.consent.storageKey
        }
      }),
    [config.consent.storageKey, config.sessionMetadataStorageKey, config.sessionStorageKey, config.visitorStorageKey]
  );
  const restoredSession = useMemo(
    () =>
      sessionManager.restore({
        providedVisitorId,
        providedSessionId,
        legalVersion: config.consent.policyVersion,
        country: initialLocale.country?.code,
        language: initialLocale.language?.code,
        consentAccepted: Boolean(initialConsentAccepted || (config.persistConsent && sessionManager.readConsentFlag()))
      }),
    [
      config.consent.policyVersion,
      config.persistConsent,
      initialConsentAccepted,
      initialLocale.country?.code,
      initialLocale.language?.code,
      providedSessionId,
      providedVisitorId,
      sessionManager
    ]
  );
  const visitorId = restoredSession.visitorId;
  const sessionId = restoredSession.sessionId;
  const storedLocale = useMemo(() => {
    const country = config.countries.find((option) => option.code === restoredSession.country);
    if (!country) return undefined;
    const languageOptions = filterLanguagesByCountry(config.languages, country.code, config.countries);
    const language = languageOptions.find((option) => option.code === restoredSession.language);
    return language ? { country, language } : undefined;
  }, [config.countries, config.languages, restoredSession.country, restoredSession.language]);
  const sessionCreatedAt = useMemo(
    () => restoredSession.createdAt,
    [restoredSession.createdAt]
  );
  const initialState = useMemo(
    () =>
      createWidgetInitialState({
        openByDefault,
        loading,
        initialConsentAccepted: Boolean(restoredSession.consentAccepted),
        initialShowSuccess,
        visitorId,
        sessionId,
        sessionCreatedAt,
        policyVersion: config.consent.policyVersion,
        selectedCountry: storedLocale?.country || initialLocale.country,
        selectedLanguage: storedLocale?.language || initialLocale.language,
        messages
      }),
    [
      config.consent.policyVersion,
      initialLocale.country,
      initialLocale.language,
      initialShowSuccess,
      loading,
      messages,
      openByDefault,
      sessionCreatedAt,
      sessionId,
      storedLocale?.country,
      storedLocale?.language,
      visitorId,
      restoredSession.consentAccepted
    ]
  );
  const [widgetState, dispatch] = useReducer(widgetReducer, initialState);
  const isOpen = selectIsOpen(widgetState);
  const menuOpen = selectMenuOpen(widgetState);
  const selectedCountry = selectCountry(widgetState);
  const selectedLanguage = selectLanguage(widgetState);
  const message = selectDraftMessage(widgetState);
  const showSuccess = selectShowSuccess(widgetState);
  const consentSubmitting = selectConsentSubmitting(widgetState);
  const consentError = selectConsentError(widgetState);
  const consentAccepted = selectConsentAccepted(widgetState);
  const effectiveLoading = selectLoading(widgetState);
  const availableLanguages = useMemo(
    () => filterLanguagesByCountry(config.languages, selectedCountry?.code, config.countries),
    [config.countries, config.languages, selectedCountry?.code]
  );
  const suggestedTopics = useMemo(
    () => [...(config.starterTopics || []), ...(config.contextualTopics || [])],
    [config.contextualTopics, config.starterTopics]
  );
  const state: GenericWidgetRenderState = selectRenderState(widgetState);
  const localePayload = createLocalePayload({
    visitorId,
    sessionId,
    selectedCountry: selectedCountry?.code || "",
    selectedLanguage: selectedLanguage?.code || ""
  });

  useEffect(() => {
    events.emit(widgetEventTypes.WIDGET_INITIALIZED, { visitorId, sessionId });
  }, [events, sessionId, visitorId]);

  useEffect(() => {
    dispatch({ type: "SET_MESSAGES", messages });
  }, [messages]);

  useEffect(() => {
    dispatch({ type: "SET_LOADING", loading });
  }, [loading]);

  useEffect(() => {
    const validation = sessionManager.validate(restoredSession, config.consent.policyVersion);
    const legalVersionChanged = Boolean(
      restoredSession.sessionId === sessionId &&
        restoredSession.legalVersion &&
        !validation.legalVersionMatches
    );
    if (legalVersionChanged) {
      dispatch({ type: "REQUIRE_CONSENT" });
      events.emit(widgetEventTypes.CONSENT_REQUIRED, {
        visitorId,
        sessionId,
        reason: "legal_version_changed"
      });
      if (config.persistConsent) sessionManager.updateConsent(restoredSession, false, config.consent.policyVersion);
    }
    sessionManager.persist(restoredSession, {
      legalVersion: config.consent.policyVersion,
      country: selectedCountry?.code,
      language: selectedLanguage?.code,
      consentAccepted
    });
  }, [
    config.consent.policyVersion,
    config.persistConsent,
    consentAccepted,
    events,
    restoredSession,
    sessionId,
    sessionManager,
    selectedCountry?.code,
    selectedLanguage?.code,
    visitorId
  ]);

  useEffect(() => {
    if (!consentRequiredSignal) return;
    dispatch({ type: "REQUIRE_CONSENT", error: "Please review and accept the legal documents before chatting." });
    events.emit(widgetEventTypes.CONSENT_REQUIRED, {
      visitorId,
      sessionId,
      reason: "backend_required_consent"
    });
    if (config.persistConsent) sessionManager.updateConsent(restoredSession, false, config.consent.policyVersion);
  }, [config.consent.policyVersion, config.persistConsent, consentRequiredSignal, events, restoredSession, sessionId, sessionManager, visitorId]);

  useEffect(() => {
    if (!openSignal) return;
    dispatch({ type: "OPEN_WIDGET" });
    events.emit(widgetEventTypes.WIDGET_OPENED, { visitorId, sessionId, metadata: { source: "sdk" } });
  }, [events, openSignal, sessionId, visitorId]);

  useEffect(() => {
    if (!closeSignal) return;
    dispatch({ type: "CLOSE_WIDGET" });
    events.emit(widgetEventTypes.WIDGET_CLOSED, { visitorId, sessionId, metadata: { source: "sdk" } });
  }, [closeSignal, events, sessionId, visitorId]);

  useEffect(() => {
    if (!resetSignal) return;
    const nextSession = sessionManager.reset({
      legalVersion: config.consent.policyVersion,
      country: selectedCountry?.code,
      language: selectedLanguage?.code
    });
    dispatch({ type: "RESET_SESSION", visitorId: nextSession.visitorId, sessionId: nextSession.sessionId, createdAt: nextSession.createdAt });
    events.emit(widgetEventTypes.SESSION_RESET, { visitorId: nextSession.visitorId, sessionId: nextSession.sessionId });
  }, [config.consent.policyVersion, events, resetSignal, selectedCountry?.code, selectedLanguage?.code, sessionManager]);

  useEffect(() => {
    if (!outboundMessage?.id || !outboundMessage.text.trim()) return;
    dispatch({ type: "OPEN_WIDGET" });

    if (config.consent.requireConsentBeforeMessaging !== false && !consentAccepted) {
      dispatch({ type: "SET_DRAFT_MESSAGE", message: outboundMessage.text });
      events.emit(widgetEventTypes.CONSENT_REQUIRED, {
        visitorId,
        sessionId,
        reason: "sdk_message_requires_consent"
      });
      return;
    }

    const payload: MessageEventPayload = {
      visitorId,
      sessionId,
      message: outboundMessage.text.trim(),
      selectedCountry: selectedCountry?.code || "",
      selectedLanguage: selectedLanguage?.code || "",
      widgetProviderName: config.provider.name,
      widgetProviderType: config.provider.type,
      metadata: { source: "sdk" }
    };
    events.emit(widgetEventTypes.MESSAGE_SENT, { visitorId, sessionId, message: payload });
    onSendMessage?.(payload);
  }, [
    config.consent.requireConsentBeforeMessaging,
    config.provider.name,
    config.provider.type,
    consentAccepted,
    events,
    onSendMessage,
    outboundMessage,
    selectedCountry?.code,
    selectedLanguage?.code,
    sessionId,
    visitorId
  ]);

  const closeWidget = () => {
    dispatch({ type: "CLOSE_WIDGET" });
    events.emit(widgetEventTypes.WIDGET_CLOSED, { visitorId, sessionId });
    onClose?.();
  };

  const handleCountryChange = (countryCode: string) => {
    const nextCountry = config.countries.find((country) => country.code === countryCode);
    if (!nextCountry) return;
    const nextLanguage = ensureLanguageForCountry(config.languages, nextCountry.code, selectedLanguage?.code, config.countries);
    dispatch({ type: "SET_COUNTRY", country: nextCountry, language: nextLanguage });
    const payload = createLocalePayload({ visitorId, sessionId, selectedCountry: nextCountry.code, selectedLanguage: nextLanguage?.code || "" });
    events.emit(widgetEventTypes.COUNTRY_CHANGED, { visitorId, sessionId, locale: payload });
    onCountryChange?.(payload);
  };

  const handleLanguageChange = (languageCode: string) => {
    const nextLanguage = availableLanguages.find((language) => language.code === languageCode);
    if (!nextLanguage) return;
    dispatch({ type: "SET_LANGUAGE", language: nextLanguage });
    const payload = createLocalePayload({ visitorId, sessionId, selectedCountry: selectedCountry?.code || "", selectedLanguage: nextLanguage.code });
    events.emit(widgetEventTypes.LANGUAGE_CHANGED, { visitorId, sessionId, locale: payload });
    onLanguageChange?.(payload);
  };

  const handleConsent = async (actionType: "accepted" | "rejected") => {
    const payload = createConsentRecord({
      actionType,
      config,
      selectedCountry: selectedCountry?.code || "",
      selectedLanguage: selectedLanguage?.code || "",
      visitorId,
      sessionId
    });
    const accepted = actionType === "accepted";
    dispatch({ type: "SET_CONSENT_ERROR", error: null });

    if (!accepted) {
      events.emit(widgetEventTypes.CONSENT_REJECTED, { visitorId, sessionId, consent: payload });
      onRejectConsent?.(payload);
      return;
    }

    try {
      dispatch({ type: "START_CONSENT_SUBMIT" });
      await onAcceptConsent?.(payload);
      dispatch({ type: "ACCEPT_CONSENT" });
      events.emit(widgetEventTypes.CONSENT_ACCEPTED, { visitorId, sessionId, consent: payload });
      if (config.persistConsent) sessionManager.updateConsent(restoredSession, true, config.consent.policyVersion);
    } catch {
      dispatch({ type: "REQUIRE_CONSENT", error: "Unable to record your consent. Please try again." });
    } finally {
      dispatch({ type: "STOP_CONSENT_SUBMIT" });
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || (config.consent.requireConsentBeforeMessaging !== false && !consentAccepted)) return;
    const payload: MessageEventPayload = {
      visitorId,
      sessionId,
      message: trimmed,
      selectedCountry: selectedCountry?.code || "",
      selectedLanguage: selectedLanguage?.code || "",
      widgetProviderName: config.provider.name,
      widgetProviderType: config.provider.type
    };
    dispatch({ type: "CLEAR_DRAFT_MESSAGE" });
    events.emit(widgetEventTypes.MESSAGE_SENT, { visitorId, sessionId, message: payload });
    onSendMessage?.(payload);
  };

  return (
    <div className={`gw-root ${className}`} style={{ ...buildThemeVars(config.theme), ...style }}>
      {!isOpen ? (
        <FloatingLauncher
          config={config}
          onClick={() => {
            dispatch({ type: "OPEN_WIDGET" });
            events.emit(widgetEventTypes.WIDGET_OPENED, { visitorId, sessionId });
            onOpen?.();
          }}
        />
      ) : null}

      {isOpen ? (
        <section className={`gw-panel ${showSuccess ? "gw-panel-has-success" : ""} ${consentAccepted ? "gw-panel-consented" : "gw-panel-needs-consent"}`} aria-label={config.brandName}>
          <Header config={config} selectedCountry={selectedCountry} menuOpen={menuOpen} onToggleMenu={() => dispatch({ type: "TOGGLE_MENU" })} onClose={closeWidget} />
          {menuOpen ? <Menu config={config} payload={localePayload} onEscalate={onEscalate} onNewChat={onNewChat} /> : null}
          {showSuccess ? (
            <div className="gw-success-banner" role="status">
              <span>{config.successText}</span>
              <button type="button" onClick={() => dispatch({ type: "SET_SUCCESS_VISIBLE", visible: false })} aria-label={config.labels.successDismissLabel}>{"\u00d7"}</button>
            </div>
          ) : null}
          <div className="gw-content">
            {showLocaleSelector ? (
              <RegionSelector
                config={config}
                countries={config.countries}
                languages={availableLanguages}
                selectedCountryCode={selectedCountry?.code}
                selectedLanguageCode={selectedLanguage?.code}
                onCountryChange={handleCountryChange}
                onLanguageChange={handleLanguageChange}
              />
            ) : null}
            {config.consent.requireConsentBeforeMessaging !== false && !consentAccepted ? (
              <ConsentPanel
                config={config}
                accepting={consentSubmitting}
                error={consentError}
                onAccept={() => handleConsent("accepted")}
                onReject={() => handleConsent("rejected")}
              />
            ) : null}
            <MessageFeed config={config} messages={messages} state={state} renderMessages={renderMessages} />
            {suggestedTopics.length ? (
              <section className="gw-section">
                <div className="gw-section-title">{config.labels.suggestedTopicsLabel}</div>
                <div className="gw-topic-list">
                  {suggestedTopics.map((topic) => (
                    <button key={topic.id} type="button" className="gw-topic" onClick={() => dispatch({ type: "SET_DRAFT_MESSAGE", message: topic.prompt || topic.label })}>
                      {topic.label}
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            {effectiveLoading ? <div className="gw-loading" role="status"><span className="gw-spinner" aria-hidden="true" /><span>{config.loadingText}</span></div> : null}
            {children ? <section className="gw-child-slot" aria-label={config.labels.childrenRegionLabel}>{typeof children === "function" ? children(state) : children}</section> : null}
          </div>
          <form className="gw-composer" onSubmit={handleSubmit}>
            <label className="gw-sr-only" htmlFor="gw-message-input">{config.labels.messageInputLabel}</label>
            <input
              id="gw-message-input"
              value={message}
              onChange={(event) => dispatch({ type: "SET_DRAFT_MESSAGE", message: event.target.value })}
              placeholder={config.labels.messageInputPlaceholder}
              disabled={effectiveLoading || (config.consent.requireConsentBeforeMessaging !== false && !consentAccepted)}
            />
            <button type="submit" className="gw-primary-button" disabled={!message.trim() || effectiveLoading}>{config.labels.sendMessageLabel}</button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
