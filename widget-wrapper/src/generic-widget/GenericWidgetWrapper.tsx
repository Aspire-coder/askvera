import { FormEvent, KeyboardEvent, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ConsentPanel } from "./ConsentPanel";
import { FloatingLauncher } from "./FloatingLauncher";
import { Header } from "./Header";
import { MessageFeed, type LoadingDisplayState } from "./MessageFeed";
import { RegionSelector } from "./RegionSelector";
import type { GenericWidgetRenderState, GenericWidgetWrapperProps, MessageEventPayload, WidgetMessage, WidgetTheme } from "./types";
import { WidgetEventBus, widgetEventBus, widgetEventTypes } from "../events";
import { createSessionManager } from "../services";
import { buildThemeVars } from "../themes";
import { LoadingTimingMs } from "../constants";
import {
  createWidgetInitialState,
  selectConsentAccepted,
  selectConsentError,
  selectConsentSubmitting,
  selectConnection,
  selectCountry,
  selectDraftMessage,
  selectIsOpen,
  selectLanguage,
  selectLoading,
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

const HealthCheckIntervalMs = 30000;

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
  onHealthCheck,
  onOpen,
  onClose,
  onAcceptConsent,
  onRejectConsent,
  onCountryChange,
  onLanguageChange,
  onSendMessage,
  onMessageCopied,
  onMessageFeedback,
  onDownloadSource,
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
  const initialConsentIsAccepted = Boolean(config.persistConsent ? restoredSession.consentAccepted : initialConsentAccepted);
  const initialState = useMemo(
    () =>
      createWidgetInitialState({
        openByDefault,
        loading,
        initialConsentAccepted: initialConsentIsAccepted,
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
      initialConsentIsAccepted
    ]
  );
  const [widgetState, dispatch] = useReducer(widgetReducer, initialState);
  const [consentDeclined, setConsentDeclined] = useState(false);
  const [localRequestPending, setLocalRequestPending] = useState(false);
  const isOpen = selectIsOpen(widgetState);
  const selectedCountry = selectCountry(widgetState);
  const selectedLanguage = selectLanguage(widgetState);
  const message = selectDraftMessage(widgetState);
  const showSuccess = selectShowSuccess(widgetState);
  const consentSubmitting = selectConsentSubmitting(widgetState);
  const consentError = selectConsentError(widgetState);
  const consentAccepted = selectConsentAccepted(widgetState);
  const connection = selectConnection(widgetState);
  const effectiveLoading = selectLoading(widgetState);
  const [loadingDisplayState, setLoadingDisplayState] = useState<LoadingDisplayState>("hidden");
  const launcherButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);
  const submitLockRef = useRef(false);
  const consentRequired = config.consent.requireConsentBeforeMessaging !== false && !consentAccepted;
  const requestBusy = effectiveLoading || localRequestPending;
  const composerDisabledReason = consentRequired
    ? "Accept the privacy agreement to begin."
    : !connection.online
      ? "ASK Vera is temporarily unavailable. Please try again in a moment."
    : requestBusy
      ? "Waiting for the current response to finish."
      : "";
  const composerDisabled = Boolean(composerDisabledReason);
  const canSendMessage = Boolean(message.trim()) && !composerDisabled;
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
    if (!isOpen || !onHealthCheck) return;

    let cancelled = false;
    let intervalId: number | undefined;

    const checkHealth = async () => {
      try {
        const healthy = await onHealthCheck();
        if (cancelled) return;
        dispatch({ type: "SET_CONNECTION", online: healthy, reconnecting: false, backendHealthy: healthy });
      } catch {
        if (cancelled) return;
        dispatch({ type: "SET_CONNECTION", online: false, reconnecting: false, backendHealthy: false });
      }
    };

    void checkHealth();
    intervalId = window.setInterval(() => void checkHealth(), HealthCheckIntervalMs);

    return () => {
      cancelled = true;
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [isOpen, onHealthCheck]);

  useEffect(() => {
    dispatch({ type: "SET_MESSAGES", messages });
  }, [messages]);

  useEffect(() => {
    dispatch({ type: "SET_LOADING", loading });
  }, [loading]);

  useEffect(() => {
    if (loading) return;
    submitLockRef.current = false;
    setLocalRequestPending(false);
  }, [loading]);

  useEffect(() => {
    if (!effectiveLoading) {
      setLoadingDisplayState("hidden");
      return;
    }

    setLoadingDisplayState("hidden");
    const typingTimer = window.setTimeout(() => setLoadingDisplayState("typing"), LoadingTimingMs.TYPING_INDICATOR_DELAY);
    const skeletonTimer = window.setTimeout(() => setLoadingDisplayState("skeleton"), LoadingTimingMs.SKELETON_DELAY);
    const slowTimer = window.setTimeout(() => setLoadingDisplayState("slow"), LoadingTimingMs.SLOW_RESPONSE_DELAY);

    return () => {
      window.clearTimeout(typingTimer);
      window.clearTimeout(skeletonTimer);
      window.clearTimeout(slowTimer);
    };
  }, [effectiveLoading]);

  useEffect(() => {
    if (!showSuccess) return;
    const successTimer = window.setTimeout(() => {
      dispatch({ type: "SET_SUCCESS_VISIBLE", visible: false });
    }, 2400);
    return () => window.clearTimeout(successTimer);
  }, [showSuccess]);

  useEffect(() => {
    if (!isOpen) return;
    const focusTimer = window.setTimeout(() => panelRef.current?.focus(), 0);
    return () => window.clearTimeout(focusTimer);
  }, [isOpen]);

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
    setConsentDeclined(false);
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
    window.setTimeout(() => launcherButtonRef.current?.focus(), 0);
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
      setConsentDeclined(true);
      events.emit(widgetEventTypes.CONSENT_REJECTED, { visitorId, sessionId, consent: payload });
      onRejectConsent?.(payload);
      return;
    }

    try {
      setConsentDeclined(false);
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
    event.stopPropagation();
    const trimmed = message.trim();
    if (!trimmed || composerDisabled || submitLockRef.current || !onSendMessage) return;
    submitLockRef.current = true;
    setLocalRequestPending(true);
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

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    event.stopPropagation();
    if (canSendMessage) event.currentTarget.form?.requestSubmit();
  };

  const messageCorrelationId = (message: WidgetMessage) =>
    typeof message.metadata?.correlationId === "string" ? message.metadata.correlationId : undefined;

  const handleMessageCopied = async (message: WidgetMessage, renderState: GenericWidgetRenderState) => {
    events.emit(widgetEventTypes.MESSAGE_COPIED, {
      visitorId,
      sessionId,
      correlationId: messageCorrelationId(message),
      message,
      metadata: { messageId: message.id }
    });
    await onMessageCopied?.(message, renderState);
  };

  const handleMessageFeedback = async (message: WidgetMessage, rating: number, renderState: GenericWidgetRenderState) => {
    const eventType = rating > 0 ? widgetEventTypes.MESSAGE_HELPFUL : widgetEventTypes.MESSAGE_NOT_HELPFUL;
    events.emit(eventType, {
      visitorId,
      sessionId,
      correlationId: messageCorrelationId(message),
      message,
      rating,
      metadata: { messageId: message.id }
    });
    await onMessageFeedback?.(message, rating, renderState);
  };

  useEffect(() => {
    const textarea = composerTextareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
  }, [message]);

  const effectiveLoadingDisplayState: LoadingDisplayState =
    effectiveLoading && connection.reconnecting ? "reconnecting" : loadingDisplayState;
  const loadingLabel =
    effectiveLoadingDisplayState === "reconnecting"
      ? config.loadingMessages?.reconnecting || config.loadingText
      : effectiveLoadingDisplayState === "slow"
        ? config.loadingMessages?.slowResponse || config.loadingText
        : effectiveLoadingDisplayState === "skeleton"
          ? config.loadingMessages?.generating || config.loadingText
          : effectiveLoadingDisplayState === "typing"
            ? config.loadingMessages?.thinking || config.loadingText
            : config.loadingText;
  const chatContentVisible = !consentRequired;
  const introAssistantName = config.assistantName || config.brandName;
  const introCompanyName = config.brandName && config.brandName !== introAssistantName ? config.brandName : "Forever Living";

  return (
    <div className={`gw-root ${className}`} style={{ ...buildThemeVars(config.theme), ...style }}>
      {!isOpen ? (
        <FloatingLauncher
          ref={launcherButtonRef}
          config={config}
          onClick={() => {
            dispatch({ type: "OPEN_WIDGET" });
            events.emit(widgetEventTypes.WIDGET_OPENED, { visitorId, sessionId });
            onOpen?.();
          }}
        />
      ) : null}

      {isOpen ? (
        <section
          ref={panelRef}
          className={`gw-panel ${showSuccess ? "gw-panel-has-success" : ""} ${consentAccepted ? "gw-panel-consented" : "gw-panel-needs-consent"}`}
          role="dialog"
          aria-modal="false"
          aria-label={`${config.brandName} assistant widget`}
          tabIndex={-1}
          onKeyDown={(event) => {
            if (event.key === "Escape") closeWidget();
          }}
        >
          <Header config={config} selectedCountry={selectedCountry} connection={connection} onClose={closeWidget} />
          {showSuccess ? (
            <div className="gw-success-banner" role="status">
              <span>{config.successText}</span>
              <button type="button" onClick={() => dispatch({ type: "SET_SUCCESS_VISIBLE", visible: false })} aria-label={config.labels.successDismissLabel}>{"\u00d7"}</button>
            </div>
          ) : null}
          <div className="gw-content">
            {consentRequired && !consentDeclined ? (
              <section className="gw-onboarding-intro" aria-label="Welcome">
                <div className="gw-onboarding-mark" aria-hidden="true">
                  {config.logoUrl ? <img src={config.logoUrl} alt="" /> : <span>{introAssistantName.trim().slice(0, 1) || "A"}</span>}
                </div>
                <div>
                  <p className="gw-onboarding-eyebrow">Welcome</p>
                  <h2>Hi, I&apos;m {introAssistantName}.</h2>
                  <p>
                    I can help you find approved answers about {introCompanyName} products, policies, and business
                    support.
                  </p>
                  <p className="gw-onboarding-next">Choose your market and language to begin.</p>
                </div>
              </section>
            ) : null}
            {showLocaleSelector && !consentAccepted && !consentDeclined ? (
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
            {config.consent.requireConsentBeforeMessaging !== false && !consentAccepted && !consentDeclined ? (
              <ConsentPanel
                config={config}
                accepting={consentSubmitting}
                error={consentError}
                onAccept={() => handleConsent("accepted")}
                onReject={() => handleConsent("rejected")}
              />
            ) : null}
            {config.consent.requireConsentBeforeMessaging !== false && !consentAccepted && consentDeclined ? (
              <section className="gw-section gw-consent-declined" role="status" aria-live="polite">
                <div className="gw-consent-declined-mark" aria-hidden="true">i</div>
                <div>
                  <h2>{config.consent.declineTitle}</h2>
                  <p>{config.consent.declineBody}</p>
                  <button type="button" className="gw-secondary-button" onClick={() => setConsentDeclined(false)}>
                    {config.consent.declineActionLabel || "Review privacy terms"}
                  </button>
                </div>
              </section>
            ) : null}
            {chatContentVisible ? (
              <MessageFeed
                config={config}
                messages={messages}
                state={state}
                renderMessages={renderMessages}
                loadingState={effectiveLoadingDisplayState}
                loadingLabel={loadingLabel}
                onCopyMessage={handleMessageCopied}
                onMessageFeedback={handleMessageFeedback}
                onDownloadSource={onDownloadSource}
              />
            ) : null}
            {chatContentVisible && suggestedTopics.length ? (
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
            {children ? <section className="gw-child-slot" aria-label={config.labels.childrenRegionLabel}>{typeof children === "function" ? children(state) : children}</section> : null}
            {config.footerText ? <footer className="gw-widget-footer">{config.footerText}</footer> : null}
          </div>
          <form className={`gw-composer ${composerDisabled ? "gw-composer-disabled" : ""}`} onSubmit={handleSubmit}>
            <label className="gw-sr-only" htmlFor="gw-message-input">{config.labels.messageInputLabel}</label>
            <div className="gw-composer-shell">
              <button type="button" className="gw-composer-tool" aria-label="Attach a file" disabled>
                <span aria-hidden="true">+</span>
              </button>
              <textarea
                ref={composerTextareaRef}
                id="gw-message-input"
                rows={1}
                value={message}
                onChange={(event) => dispatch({ type: "SET_DRAFT_MESSAGE", message: event.target.value })}
                onKeyDown={handleComposerKeyDown}
                placeholder={config.labels.messageInputPlaceholder}
                disabled={composerDisabled}
                aria-describedby={composerDisabledReason ? "gw-composer-status gw-composer-hint" : "gw-composer-hint"}
              />
              <button type="submit" className="gw-primary-button" disabled={!canSendMessage}>{config.labels.sendMessageLabel}</button>
            </div>
            {composerDisabledReason ? <div id="gw-composer-status" className="gw-composer-status">{composerDisabledReason}</div> : null}
            <div id="gw-composer-hint" className="gw-composer-hint">Enter to send. Shift + Enter for a new line.</div>
          </form>
        </section>
      ) : null}
    </div>
  );
}
