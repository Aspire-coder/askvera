import { useEffect, useMemo, useRef, useState } from "react";
import type { GenericWidgetRenderState } from "../types";

type ChatwootUser = {
  identifier: string;
  name?: string;
  email?: string;
  avatarUrl?: string;
  identifierHash?: string;
};

type ChatwootSettings = {
  position?: "left" | "right";
  type?: "standard" | "expanded_bubble";
  launcherTitle?: string;
  locale?: string;
  hideMessageBubble?: boolean;
  showPopoutButton?: boolean;
  [key: string]: unknown;
};

export type ChatwootWidgetAdapterProps = {
  baseUrl: string;
  websiteToken: string;
  state: GenericWidgetRenderState;
  settings?: ChatwootSettings;
  user?: ChatwootUser;
  customAttributes?: Record<string, unknown>;
  hideDefaultBubble?: boolean;
  openWhenWrapperOpens?: boolean;
  resetOnNewSession?: boolean;
  onReady?: () => void;
  onError?: (error: Error) => void;
};

type ChatwootSdk = {
  run: (options: { websiteToken: string; baseUrl: string }) => void;
};

type ChatwootApi = {
  toggle?: (state?: "open" | "close") => void;
  toggleBubbleVisibility?: (visibility: "show" | "hide") => void;
  setLocale?: (locale: string) => void;
  setUser?: (identifier: string, user: Record<string, unknown>) => void;
  setCustomAttributes?: (attributes: Record<string, unknown>) => void;
  reset?: () => void;
};

declare global {
  interface Window {
    chatwootSDK?: ChatwootSdk;
    chatwootSettings?: ChatwootSettings;
    $chatwoot?: ChatwootApi;
  }
}

const scriptId = "generic-widget-chatwoot-sdk";

const normalizeBaseUrl = (baseUrl: string) => baseUrl.replace(/\/$/, "");

const loadChatwootSdk = (baseUrl: string) =>
  new Promise<void>((resolve, reject) => {
    const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
    const existingScript = document.getElementById(scriptId) as HTMLScriptElement | null;

    if (window.chatwootSDK) {
      resolve();
      return;
    }

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Unable to load Chatwoot SDK.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `${normalizedBaseUrl}/packs/js/sdk.js`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Unable to load Chatwoot SDK."));
    document.head.appendChild(script);
  });

export function ChatwootWidgetAdapter({
  baseUrl,
  websiteToken,
  state,
  settings,
  user,
  customAttributes,
  hideDefaultBubble = true,
  openWhenWrapperOpens = true,
  resetOnNewSession = false,
  onReady,
  onError
}: ChatwootWidgetAdapterProps) {
  const [ready, setReady] = useState(false);
  const initializedRef = useRef(false);
  const normalizedBaseUrl = useMemo(() => normalizeBaseUrl(baseUrl), [baseUrl]);
  const locale = state.selectedLanguage?.code || settings?.locale;

  useEffect(() => {
    window.chatwootSettings = {
      ...(settings || {}),
      locale,
      hideMessageBubble: hideDefaultBubble
    };

    loadChatwootSdk(normalizedBaseUrl)
      .then(() => {
        if (!initializedRef.current) {
          window.chatwootSDK?.run({ websiteToken, baseUrl: normalizedBaseUrl });
          initializedRef.current = true;
        }
      })
      .catch((error: Error) => onError?.(error));
  }, [hideDefaultBubble, locale, normalizedBaseUrl, onError, settings, websiteToken]);

  useEffect(() => {
    const handleReady = () => {
      setReady(true);
      if (hideDefaultBubble) window.$chatwoot?.toggleBubbleVisibility?.("hide");
      onReady?.();
    };

    if (window.$chatwoot) handleReady();
    window.addEventListener("chatwoot:ready", handleReady);
    return () => window.removeEventListener("chatwoot:ready", handleReady);
  }, [hideDefaultBubble, onReady]);

  useEffect(() => {
    if (!ready || !locale) return;
    window.$chatwoot?.setLocale?.(locale);
  }, [locale, ready]);

  useEffect(() => {
    if (!ready || !user?.identifier) return;
    const { identifier, ...profile } = user;
    window.$chatwoot?.setUser?.(identifier, profile);
  }, [ready, user]);

  useEffect(() => {
    if (!ready) return;
    window.$chatwoot?.setCustomAttributes?.({
      ...(customAttributes || {}),
      wrapperVisitorId: state.visitorId,
      wrapperSessionId: state.sessionId,
      selectedCountry: state.selectedCountry?.code || "",
      selectedLanguage: state.selectedLanguage?.code || "",
      wrapperConsentAccepted: state.consentAccepted
    });
  }, [customAttributes, ready, state.consentAccepted, state.selectedCountry?.code, state.selectedLanguage?.code, state.sessionId, state.visitorId]);

  useEffect(() => {
    if (!ready || !openWhenWrapperOpens) return;
    window.$chatwoot?.toggle?.(state.isOpen ? "open" : "close");
  }, [openWhenWrapperOpens, ready, state.isOpen]);

  useEffect(() => {
    if (!ready || !resetOnNewSession) return;
    window.$chatwoot?.reset?.();
  }, [ready, resetOnNewSession, state.sessionId]);

  return null;
}
