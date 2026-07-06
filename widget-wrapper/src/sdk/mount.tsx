import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { BackendChatDemo } from "../generic-widget/examples/BackendChatDemo";
import type { AskVeraRuntimeConfig, SdkRenderState } from "./AskVera";

export type MountedWidget = {
  root: Root;
  element: HTMLElement;
  render: (state: SdkRenderState) => void;
  destroy: () => void;
};

const createMountElement = (target?: string | HTMLElement) => {
  if (target instanceof HTMLElement) return target;
  if (typeof target === "string") {
    const existing = document.querySelector<HTMLElement>(target);
    if (existing) return existing;
  }

  const element = document.createElement("div");
  element.id = "askvera-widget-root";
  document.body.appendChild(element);
  return element;
};

export function mountWidget(config: AskVeraRuntimeConfig, state: SdkRenderState): MountedWidget {
  const element = createMountElement(config.mountTarget);
  const root = createRoot(element);

  const render = (nextState: SdkRenderState) => {
    root.render(
      <React.StrictMode>
        <BackendChatDemo
          apiBaseUrl={nextState.config.apiUrl}
          openSignal={nextState.openSignal}
          closeSignal={nextState.closeSignal}
          resetSignal={nextState.resetSignal}
          clearConversationSignal={nextState.clearConversationSignal}
          sdkMessage={nextState.sdkMessage}
          country={nextState.country}
          language={nextState.language}
        />
      </React.StrictMode>
    );
  };

  render(state);

  return {
    root,
    element,
    render,
    destroy: () => root.unmount()
  };
}
