import { useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import type { MessageEventPayload, WidgetMessage } from "../types";
import { foreverDemoConfig } from "./foreverDemoConfig";

const localChatwootConfig = {
  ...foreverDemoConfig,
  provider: { name: "Local Chatwoot simulator", type: "script" }
};

export function LocalChatwootDemo() {
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: "local-chatwoot-welcome",
      role: "assistant",
      content: "After privacy acceptance, this local provider simulates the connected widget response."
    }
  ]);

  const handleMessage = (payload: MessageEventPayload) => {
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: payload.message },
      {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: `Demo reply from ${localChatwootConfig.provider.name}. Country: ${payload.selectedCountry || "none"}, language: ${payload.selectedLanguage || "none"}.`
      }
    ]);
  };

  return (
    <GenericWidgetWrapper
      config={localChatwootConfig}
      messages={messages}
      openByDefault
      onSendMessage={handleMessage}
    />
  );
}
