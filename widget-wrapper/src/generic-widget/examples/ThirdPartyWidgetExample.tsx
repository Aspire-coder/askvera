import { useEffect, useRef, useState } from "react";
import { GenericWidgetWrapper } from "../GenericWidgetWrapper";
import { PlainStateGenericWidgetWrapper } from "../PlainStateGenericWidgetWrapper";
import { exampleWidgetConfig } from "../config/exampleWidgetConfig";
import type { MessageEventPayload, WidgetMessage } from "../types";

export function MockChatbotExample() {
  const [messages, setMessages] = useState<WidgetMessage[]>([]);

  const handleMessage = (payload: MessageEventPayload) => {
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: payload.message },
      { id: `assistant-${Date.now()}`, role: "assistant", content: "This is a mock response supplied by the demo chat engine." }
    ]);
  };

  return <GenericWidgetWrapper config={exampleWidgetConfig} messages={messages} onSendMessage={handleMessage} />;
}

export function IframeWidgetExample() {
  return (
    <GenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Iframe provider", type: "iframe" } }}>
      <iframe title="Embedded assistant" src="https://example.com/embed" style={{ width: "100%", height: 360, border: 0, borderRadius: 12 }} />
    </GenericWidgetWrapper>
  );
}

function ScriptMount({ src }: { src: string }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    ref.current.appendChild(script);

    return () => script.remove();
  }, [src]);

  return <div ref={ref} />;
}

export function ScriptWidgetExample() {
  return (
    <PlainStateGenericWidgetWrapper config={{ ...exampleWidgetConfig, provider: { name: "Script provider", type: "script" } }}>
      <ScriptMount src="https://example.com/widget.js" />
    </PlainStateGenericWidgetWrapper>
  );
}
