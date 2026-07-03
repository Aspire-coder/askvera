import { FormEvent, type CSSProperties, useEffect, useMemo, useState } from "react";
import { ConsentPanel } from "./ConsentPanel";
import { FloatingLauncher } from "./FloatingLauncher";
import { Header } from "./Header";
import { Menu } from "./Menu";
import { MessageFeed } from "./MessageFeed";
import { RegionSelector } from "./RegionSelector";
import { defaultTheme } from "./config/defaultTheme";
import type { GenericWidgetRenderState, GenericWidgetWrapperProps, MessageEventPayload, WidgetTheme } from "./types";
import {
  createConsentRecord,
  createLocalePayload,
  createSessionId,
  createVisitorId,
  detectInitialLocale,
  ensureLanguageForCountry,
  filterLanguagesByCountry,
  readConsentFlag,
  readSessionMetadata,
  readStoredId,
  writeSessionMetadata,
  writeStoredId,
  writeConsentFlag
} from "./utils";
import "./generic-widget.css";

const buildThemeVars = (theme?: WidgetTheme) => {
  const merged = { ...defaultTheme, ...theme };
  return {
    "--gw-accent": merged.accentColor,
    "--gw-accent-text": merged.accentTextColor,
    "--gw-surface": merged.surfaceColor,
    "--gw-panel": merged.panelColor,
    "--gw-text": merged.textColor,
    "--gw-muted": merged.mutedTextColor,
    "--gw-border": merged.borderColor,
    "--gw-launcher": merged.launcherColor,
    "--gw-launcher-text": merged.launcherTextColor,
    "--gw-success": merged.successColor,
    "--gw-shadow": merged.shadow,
    "--gw-radius": merged.radius,
    "--gw-font": merged.fontFamily,
    "--gw-z": String(merged.zIndex)
  } as CSSProperties;
};

export function GenericWidgetWrapper({
  config,
  children,
  messages = [],
  loading = false,
  openByDefault = false,
  initialConsentAccepted = false,
  initialShowSuccess = false,
  consentRequiredSignal = 0,
  showLocaleSelector = true,
  visitorId: providedVisitorId,
  sessionId: providedSessionId,
  className = "",
  style,
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
  const initialLocale = useMemo(
    () => detectInitialLocale(config.countries, config.languages, config.defaultCountryCode, config.defaultLanguageCode),
    [config.countries, config.defaultCountryCode, config.defaultLanguageCode, config.languages]
  );
  const [storedSessionMetadata] = useState(() => readSessionMetadata(config.sessionMetadataStorageKey));
  const [visitorId] = useState(() => providedVisitorId || readStoredId(config.visitorStorageKey) || createVisitorId());
  const [sessionId] = useState(() => providedSessionId || readStoredId(config.sessionStorageKey) || createSessionId());
  const storedLocale = useMemo(() => {
    if (!storedSessionMetadata || storedSessionMetadata.sessionId !== sessionId) return undefined;
    const country = config.countries.find((option) => option.code === storedSessionMetadata.market);
    if (!country) return undefined;
    const languageOptions = filterLanguagesByCountry(config.languages, country.code, config.countries);
    const language = languageOptions.find((option) => option.code === storedSessionMetadata.language);
    return language ? { country, language } : undefined;
  }, [config.countries, config.languages, sessionId, storedSessionMetadata]);
  const [isOpen, setIsOpen] = useState(openByDefault);
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState(storedLocale?.country || initialLocale.country);
  const [selectedLanguage, setSelectedLanguage] = useState(storedLocale?.language || initialLocale.language);
  const [message, setMessage] = useState("");
  const [showSuccess, setShowSuccess] = useState(initialShowSuccess);
  const [consentSubmitting, setConsentSubmitting] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [sessionCreatedAt] = useState(
    () => storedSessionMetadata?.createdAt || new Date().toISOString()
  );
  const [consentAccepted, setConsentAccepted] = useState(
    Boolean(initialConsentAccepted || (config.persistConsent && readConsentFlag(config.consent.storageKey)))
  );
  const availableLanguages = useMemo(
    () => filterLanguagesByCountry(config.languages, selectedCountry?.code, config.countries),
    [config.countries, config.languages, selectedCountry?.code]
  );
  const suggestedTopics = useMemo(
    () => [...(config.starterTopics || []), ...(config.contextualTopics || [])],
    [config.contextualTopics, config.starterTopics]
  );
  const state: GenericWidgetRenderState = { isOpen, selectedCountry, selectedLanguage, consentAccepted, visitorId, sessionId };
  const localePayload = createLocalePayload({
    visitorId,
    sessionId,
    selectedCountry: selectedCountry?.code || "",
    selectedLanguage: selectedLanguage?.code || ""
  });

  useEffect(() => {
    writeStoredId(config.visitorStorageKey, visitorId);
    writeStoredId(config.sessionStorageKey, sessionId);
    const storedSession = readSessionMetadata(config.sessionMetadataStorageKey);
    const legalVersionChanged = Boolean(
      storedSession &&
        storedSession.sessionId === sessionId &&
        storedSession.legalVersion &&
        storedSession.legalVersion !== config.consent.policyVersion
    );
    if (legalVersionChanged) {
      setConsentAccepted(false);
      setShowSuccess(false);
      if (config.persistConsent) writeConsentFlag(config.consent.storageKey, false);
    }
    writeSessionMetadata(config.sessionMetadataStorageKey, {
      sessionId,
      createdAt: storedSession?.sessionId === sessionId ? storedSession.createdAt : sessionCreatedAt,
      legalVersion: config.consent.policyVersion,
      market: selectedCountry?.code,
      language: selectedLanguage?.code
    });
  }, [
    config.consent.policyVersion,
    config.consent.storageKey,
    config.persistConsent,
    config.sessionMetadataStorageKey,
    config.sessionStorageKey,
    config.visitorStorageKey,
    sessionCreatedAt,
    sessionId,
    selectedCountry?.code,
    selectedLanguage?.code,
    visitorId
  ]);

  useEffect(() => {
    if (!consentRequiredSignal) return;
    setConsentAccepted(false);
    setShowSuccess(false);
    setConsentError("Please review and accept the legal documents before chatting.");
    if (config.persistConsent) writeConsentFlag(config.consent.storageKey, false);
  }, [config.consent.storageKey, config.persistConsent, consentRequiredSignal]);

  const closeWidget = () => {
    setIsOpen(false);
    setMenuOpen(false);
    onClose?.();
  };

  const handleCountryChange = (countryCode: string) => {
    const nextCountry = config.countries.find((country) => country.code === countryCode);
    if (!nextCountry) return;
    const nextLanguage = ensureLanguageForCountry(config.languages, nextCountry.code, selectedLanguage?.code, config.countries);
    setSelectedCountry(nextCountry);
    setSelectedLanguage(nextLanguage);
    onCountryChange?.(
      createLocalePayload({ visitorId, sessionId, selectedCountry: nextCountry.code, selectedLanguage: nextLanguage?.code || "" })
    );
  };

  const handleLanguageChange = (languageCode: string) => {
    const nextLanguage = availableLanguages.find((language) => language.code === languageCode);
    if (!nextLanguage) return;
    setSelectedLanguage(nextLanguage);
    onLanguageChange?.(
      createLocalePayload({ visitorId, sessionId, selectedCountry: selectedCountry?.code || "", selectedLanguage: nextLanguage.code })
    );
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
    setConsentError(null);

    if (!accepted) {
      onRejectConsent?.(payload);
      return;
    }

    try {
      setConsentSubmitting(true);
      await onAcceptConsent?.(payload);
      setConsentAccepted(true);
      setShowSuccess(true);
      if (config.persistConsent) writeConsentFlag(config.consent.storageKey, true);
    } catch {
      setConsentAccepted(false);
      setShowSuccess(false);
      setConsentError("Unable to record your consent. Please try again.");
    } finally {
      setConsentSubmitting(false);
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
    setMessage("");
    onSendMessage?.(payload);
  };

  return (
    <div className={`gw-root ${className}`} style={{ ...buildThemeVars(config.theme), ...style }}>
      {!isOpen ? (
        <FloatingLauncher
          config={config}
          onClick={() => {
            setIsOpen(true);
            onOpen?.();
          }}
        />
      ) : null}

      {isOpen ? (
        <section className={`gw-panel ${showSuccess ? "gw-panel-has-success" : ""} ${consentAccepted ? "gw-panel-consented" : "gw-panel-needs-consent"}`} aria-label={config.brandName}>
          <Header config={config} selectedCountry={selectedCountry} menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((value) => !value)} onClose={closeWidget} />
          {menuOpen ? <Menu config={config} payload={localePayload} onEscalate={onEscalate} onNewChat={onNewChat} /> : null}
          {showSuccess ? (
            <div className="gw-success-banner" role="status">
              <span>{config.successText}</span>
              <button type="button" onClick={() => setShowSuccess(false)} aria-label={config.labels.successDismissLabel}>{"\u00d7"}</button>
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
                    <button key={topic.id} type="button" className="gw-topic" onClick={() => setMessage(topic.prompt || topic.label)}>
                      {topic.label}
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            {loading ? <div className="gw-loading" role="status"><span className="gw-spinner" aria-hidden="true" /><span>{config.loadingText}</span></div> : null}
            {children ? <section className="gw-child-slot" aria-label={config.labels.childrenRegionLabel}>{typeof children === "function" ? children(state) : children}</section> : null}
          </div>
          <form className="gw-composer" onSubmit={handleSubmit}>
            <label className="gw-sr-only" htmlFor="gw-message-input">{config.labels.messageInputLabel}</label>
            <input
              id="gw-message-input"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={config.labels.messageInputPlaceholder}
              disabled={loading || (config.consent.requireConsentBeforeMessaging !== false && !consentAccepted)}
            />
            <button type="submit" className="gw-primary-button" disabled={!message.trim() || loading}>{config.labels.sendMessageLabel}</button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
