import type { ReactNode } from "react";
import type { GenericWidgetConfig, GenericWidgetRenderState, WidgetMessage } from "./types";

export function MessageFeed({
  config,
  messages,
  state,
  renderMessages
}: {
  config: GenericWidgetConfig;
  messages: WidgetMessage[];
  state: GenericWidgetRenderState;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
}) {
  if (renderMessages) return <div className="gw-message-feed">{renderMessages(messages, state)}</div>;

  return (
    <div className="gw-message-feed" role="log" aria-live="polite">
      {config.welcomeText ? <article className="gw-message gw-message-system"><div>{config.welcomeText}</div></article> : null}
      {messages.map((message) => (
        <article key={message.id} className={`gw-message gw-message-${message.role}`}>
          <div>{message.content}</div>
        </article>
      ))}
    </div>
  );
}
