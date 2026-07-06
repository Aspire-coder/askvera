import type { RuntimeConfig } from "../config";
import { defaultRuntimeConfig } from "../config";
import { widgetEventBus, widgetEventTypes, type WidgetEventListener, type WidgetEventSubscription, type WidgetEventType } from "../events";
import { createSessionManager, type WidgetSessionMetadata } from "../services";
import { authenticateWidget } from "./auth";
import { mountWidget, type MountedWidget } from "./mount";

const SDK_VERSION = "1.0.0";
const SDK_NAME = "@askvera/widget";
const SDK_SESSION_KEYS = {
  visitorStorageKey: "askvera_visitor_id",
  sessionStorageKey: "askvera_session_id",
  sessionMetadataStorageKey: "askvera_session_metadata",
  consentStorageKey: "forever-style-widget-demo-consent"
};

declare const __ASKVERA_SDK_NAME__: string | undefined;
declare const __ASKVERA_SDK_VERSION__: string | undefined;
declare const __ASKVERA_BUILD_DATE__: string | undefined;
declare const __ASKVERA_BUILD_COMMIT__: string | undefined;

export type AskVeraRuntimeConfig = RuntimeConfig & {
  mountTarget?: string | HTMLElement;
};

export type AskVeraPlugin = {
  name: string;
  install: (api: AskVeraSdk) => void | Promise<void>;
};

export type AskVeraBuildInfo = {
  sdk: string;
  version: string;
  buildDate: string;
  commit: string;
};

export type SdkRenderState = {
  config: AskVeraRuntimeConfig;
  ready: boolean;
  openSignal: number;
  closeSignal: number;
  resetSignal: number;
  clearConversationSignal: number;
  sdkMessage?: { id: string; text: string };
  country?: string;
  language?: string;
};

export type AskVeraSdk = {
  init(config?: Partial<AskVeraRuntimeConfig>): Promise<void>;
  open(): void;
  close(): void;
  destroy(): void;
  reset(): void;
  updateConfig(config: Partial<AskVeraRuntimeConfig>): void;
  getSession(): WidgetSessionMetadata;
  resetSession(): WidgetSessionMetadata;
  setCountry(country: string): void;
  setLanguage(language: string): void;
  setLocale(country: string, language: string): void;
  sendMessage(text: string): void;
  clearConversation(): void;
  on<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>): WidgetEventSubscription;
  off<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>): void;
  once<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>): WidgetEventSubscription;
  isOpen(): boolean;
  isReady(): boolean;
  getVersion(): string;
  getBuildInfo(): AskVeraBuildInfo;
  getConfig(): AskVeraRuntimeConfig;
  use(plugin: AskVeraPlugin): Promise<void>;
};

const createDefaultConfig = (): AskVeraRuntimeConfig => ({
  ...defaultRuntimeConfig,
  apiUrl: defaultRuntimeConfig.apiUrl
});

class AskVeraSdkImpl implements AskVeraSdk {
  private mounted?: MountedWidget;
  private plugins = new Map<string, AskVeraPlugin>();
  private sessionManager = createSessionManager({ keys: SDK_SESSION_KEYS });
  private state: SdkRenderState = {
    config: createDefaultConfig(),
    ready: false,
    openSignal: 0,
    closeSignal: 0,
    resetSignal: 0,
    clearConversationSignal: 0
  };

  async init(config: Partial<AskVeraRuntimeConfig> = {}) {
    const nextConfig = {
      ...this.state.config,
      ...config,
      apiUrl: config.apiUrl || this.state.config.apiUrl
    };
    const auth = await authenticateWidget(nextConfig);
    this.state = {
      ...this.state,
      config: {
        ...nextConfig,
        widgetAuthToken: auth.token,
        widgetAuthExpiresAt: auth.expiresAt
      },
      country: config.defaultCountry || this.state.country,
      language: config.defaultLanguage || this.state.language,
      ready: true
    };

    if (!this.mounted) {
      this.mounted = mountWidget(this.state.config, this.state);
    } else {
      this.render();
    }

    widgetEventBus.emit(widgetEventTypes.WIDGET_INITIALIZED, {
      metadata: {
        source: "sdk",
        version: SDK_VERSION
      }
    });
  }

  open() {
    this.state = { ...this.state, openSignal: this.state.openSignal + 1 };
    this.render();
  }

  close() {
    this.state = { ...this.state, closeSignal: this.state.closeSignal + 1 };
    this.render();
  }

  destroy() {
    this.mounted?.destroy();
    this.mounted = undefined;
    this.state = { ...this.state, ready: false };
    widgetEventBus.emit(widgetEventTypes.WIDGET_DESTROYED, { metadata: { source: "sdk" } });
  }

  reset() {
    this.resetSession();
    this.clearConversation();
  }

  updateConfig(config: Partial<AskVeraRuntimeConfig>) {
    this.state = {
      ...this.state,
      config: {
        ...this.state.config,
        ...config,
        apiUrl: config.apiUrl || this.state.config.apiUrl
      },
      country: config.defaultCountry || this.state.country,
      language: config.defaultLanguage || this.state.language
    };
    this.render();
  }

  getSession() {
    return this.sessionManager.restore({
      legalVersion: "unknown",
      country: this.state.country,
      language: this.state.language
    });
  }

  resetSession() {
    const session = this.sessionManager.reset({
      legalVersion: "unknown",
      country: this.state.country,
      language: this.state.language
    });
    this.state = { ...this.state, resetSignal: this.state.resetSignal + 1 };
    this.render();
    return session;
  }

  setCountry(country: string) {
    this.setLocale(country, this.state.language || this.state.config.defaultLanguage || "en");
  }

  setLanguage(language: string) {
    this.setLocale(this.state.country || this.state.config.defaultCountry || "US", language);
  }

  setLocale(country: string, language: string) {
    this.state = { ...this.state, country, language };
    this.render();
  }

  sendMessage(text: string) {
    this.state = {
      ...this.state,
      openSignal: this.state.openSignal + 1,
      sdkMessage: {
        id: `sdk-message-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        text
      }
    };
    this.render();
  }

  clearConversation() {
    this.state = { ...this.state, clearConversationSignal: this.state.clearConversationSignal + 1 };
    this.render();
  }

  on<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>) {
    return widgetEventBus.subscribe(type, listener);
  }

  off<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>) {
    widgetEventBus.unsubscribe(type, listener);
  }

  once<TType extends WidgetEventType>(type: TType, listener: WidgetEventListener<TType>) {
    return widgetEventBus.once(type, listener);
  }

  isOpen() {
    return this.state.openSignal > this.state.closeSignal;
  }

  isReady() {
    return this.state.ready;
  }

  getVersion() {
    return SDK_VERSION;
  }

  getBuildInfo() {
    return {
      sdk: typeof __ASKVERA_SDK_NAME__ === "string" ? __ASKVERA_SDK_NAME__ : SDK_NAME,
      version: typeof __ASKVERA_SDK_VERSION__ === "string" ? __ASKVERA_SDK_VERSION__ : SDK_VERSION,
      buildDate: typeof __ASKVERA_BUILD_DATE__ === "string" ? __ASKVERA_BUILD_DATE__ : "development",
      commit: typeof __ASKVERA_BUILD_COMMIT__ === "string" ? __ASKVERA_BUILD_COMMIT__ : "unknown"
    };
  }

  getConfig() {
    return { ...this.state.config };
  }

  async use(plugin: AskVeraPlugin) {
    if (this.plugins.has(plugin.name)) return;
    await plugin.install(this);
    this.plugins.set(plugin.name, plugin);
  }

  private render() {
    this.mounted?.render(this.state);
  }
}

export const AskVera: AskVeraSdk = new AskVeraSdkImpl();

declare global {
  interface Window {
    AskVera?: AskVeraSdk;
  }
}

if (typeof window !== "undefined") {
  window.AskVera = AskVera;
}
