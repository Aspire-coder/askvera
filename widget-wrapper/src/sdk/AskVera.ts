import type { RuntimeConfig } from "../config";
import { widgetEventBus, widgetEventTypes } from "../events";
import { authenticateWidget } from "./auth";
import { mountWidget, type MountedWidget } from "./mount";

const SDK_VERSION = "1.0.0";

export type AskVeraRuntimeConfig = RuntimeConfig & {
  mountTarget?: string | HTMLElement;
};

export type AskVeraInitConfig = {
  widgetId: string;
  apiUrl: string;
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
  init(config: AskVeraInitConfig): Promise<void>;
};

class AskVeraSdkImpl implements AskVeraSdk {
  private mounted?: MountedWidget;
  private launcher?: HTMLButtonElement;
  private state: SdkRenderState = {
    config: {
      apiUrl: "",
      launcherPosition: "bottom-right",
      debug: false
    },
    ready: false,
    openSignal: 0,
    closeSignal: 0,
    resetSignal: 0,
    clearConversationSignal: 0
  };

  async init(config: AskVeraInitConfig) {
    if (!config.widgetId || !config.apiUrl) {
      throw new Error("AskVera.init requires widgetId and apiUrl.");
    }
    const nextConfig = {
      ...this.state.config,
      widgetId: config.widgetId,
      apiUrl: config.apiUrl
    };
    const auth = await authenticateWidget(nextConfig);
    this.state = {
      ...this.state,
      config: {
        ...nextConfig,
        widgetAuthToken: auth.token,
        widgetAuthExpiresAt: auth.expiresAt
      },
      ready: true
    };

    if (this.mounted) {
      this.render();
    } else {
      this.renderLauncher();
    }

    widgetEventBus.emit(widgetEventTypes.WIDGET_INITIALIZED, {
      metadata: {
        source: "sdk",
        version: SDK_VERSION
      }
    });
  }

  private renderLauncher() {
    if (this.launcher) return;
    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.className = "askvera-sdk-launcher";
    launcher.setAttribute("aria-label", "Open ASK Vera chat");
    launcher.textContent = "Ask Vera";
    launcher.addEventListener("click", () => {
      this.launcher?.remove();
      this.launcher = undefined;
      this.state = { ...this.state, openSignal: this.state.openSignal + 1 };
      this.mounted = mountWidget(this.state.config, this.state);
    });
    document.body.appendChild(launcher);
    this.launcher = launcher;
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
