import { useState, type ReactNode } from "react";
import { LoadingTimingMs } from "../constants";
import { CitationRenderer, MarkdownRenderer } from "../renderers";
import type { GenericWidgetConfig, GenericWidgetRenderState, WidgetMessage } from "./types";

type MessageRole = WidgetMessage["role"];
export type LoadingDisplayState = "hidden" | "typing" | "skeleton" | "slow" | "reconnecting";

function formatMessageTimestamp(timestamp?: string): string {
  if (!timestamp) return "Now";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function roleLabel(role: MessageRole, config: GenericWidgetConfig): string {
  if (role === "assistant") return config.assistantName || config.brandName;
  if (role === "user") return "You";
  return "System";
}

function assistantMark(config: GenericWidgetConfig): string {
  const label = config.assistantName || config.brandName;
  return label.trim().slice(0, 1) || "A";
}

function messageCopyText(message: WidgetMessage): string {
  if (typeof message.content === "string") return message.content;
  const copyText = message.metadata?.copyText;
  return typeof copyText === "string" ? copyText : "";
}

async function copyTextToClipboard(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function MessageActions({
  message,
  state,
  onCopyMessage,
  onMessageFeedback
}: {
  message: WidgetMessage;
  state: GenericWidgetRenderState;
  onCopyMessage?: (message: WidgetMessage, state: GenericWidgetRenderState) => void | Promise<void>;
  onMessageFeedback?: (message: WidgetMessage, rating: number, state: GenericWidgetRenderState) => void | Promise<void>;
}) {
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState<number | null>(null);
  const copyText = messageCopyText(message);

  const handleCopy = async () => {
    if (!copyText) return;
    await copyTextToClipboard(copyText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), LoadingTimingMs.COPY_FEEDBACK_DURATION);
    await onCopyMessage?.(message, state);
  };

  const handleFeedback = async (nextRating: number) => {
    setRating(nextRating);
    await onMessageFeedback?.(message, nextRating, state);
  };

  return (
    <div className="gw-message-actions" aria-label="Message actions">
      <button type="button" className="gw-message-action" onClick={handleCopy} disabled={!copyText} aria-label="Copy assistant response">
        {copied ? "Copied" : "Copy"}
      </button>
      <button
        type="button"
        className={`gw-message-action ${rating === 1 ? "gw-message-action-active" : ""}`}
        onClick={() => void handleFeedback(1)}
        aria-label="Mark response as helpful"
        aria-pressed={rating === 1}
      >
        Helpful
      </button>
      <button
        type="button"
        className={`gw-message-action ${rating === -1 ? "gw-message-action-active" : ""}`}
        onClick={() => void handleFeedback(-1)}
        aria-label="Mark response as not helpful"
        aria-pressed={rating === -1}
      >
        Not helpful
      </button>
      {copied ? <span className="gw-sr-only" role="status">Response copied.</span> : null}
    </div>
  );
}

function MessageCard({
  message,
  config,
  state,
  onCopyMessage,
  onMessageFeedback
}: {
  message: WidgetMessage;
  config: GenericWidgetConfig;
  state: GenericWidgetRenderState;
  onCopyMessage?: (message: WidgetMessage, state: GenericWidgetRenderState) => void | Promise<void>;
  onMessageFeedback?: (message: WidgetMessage, rating: number, state: GenericWidgetRenderState) => void | Promise<void>;
}) {
  const isAssistant = message.role === "assistant";
  const isSystem = message.role === "system";
  const label = roleLabel(message.role, config);
  const content =
    typeof message.content === "string" && (isAssistant || isSystem)
      ? <MarkdownRenderer content={message.content} />
      : message.content;

  return (
    <article className={`gw-message gw-message-${message.role}`}>
      <div className="gw-message-avatar" aria-hidden="true">
        {isAssistant ? assistantMark(config) : message.role === "user" ? "Y" : "i"}
      </div>
      <div className="gw-message-card">
        <header className="gw-message-meta">
          <span className="gw-message-author">{label}</span>
          <time>{formatMessageTimestamp(message.timestamp)}</time>
        </header>
        <div className="gw-message-body">{content}</div>
        {isAssistant ? <CitationRenderer sources={message.metadata?.sources} /> : null}
        {isAssistant ? (
          <MessageActions
            message={message}
            state={state}
            onCopyMessage={onCopyMessage}
            onMessageFeedback={onMessageFeedback}
          />
        ) : null}
      </div>
    </article>
  );
}

function LoadingMessage({
  config,
  state,
  label
}: {
  config: GenericWidgetConfig;
  state: Exclude<LoadingDisplayState, "hidden">;
  label: ReactNode;
}) {
  const showSkeleton = state === "skeleton" || state === "slow";

  return (
    <article className={`gw-message gw-message-assistant gw-message-loading gw-message-loading-${state}`}>
      <div className="gw-message-avatar" aria-hidden="true">{assistantMark(config)}</div>
      <div className="gw-message-card">
        <header className="gw-message-meta">
          <span className="gw-message-author">{config.assistantName || config.brandName}</span>
          <time>{formatMessageTimestamp()}</time>
        </header>
        <div className="gw-loading-body" role="status" aria-live="polite">
          <div className="gw-typing-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div className="gw-loading-label">{label}</div>
          {showSkeleton ? (
            <div className="gw-skeleton-lines" aria-hidden="true">
              <span className="gw-skeleton-line gw-skeleton-line-wide" />
              <span className="gw-skeleton-line gw-skeleton-line-medium" />
              <span className="gw-skeleton-line gw-skeleton-line-long" />
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function MessageFeed({
  config,
  messages,
  state,
  renderMessages,
  loadingState = "hidden",
  loadingLabel,
  onCopyMessage,
  onMessageFeedback
}: {
  config: GenericWidgetConfig;
  messages: WidgetMessage[];
  state: GenericWidgetRenderState;
  renderMessages?: (messages: WidgetMessage[], state: GenericWidgetRenderState) => ReactNode;
  loadingState?: LoadingDisplayState;
  loadingLabel?: ReactNode;
  onCopyMessage?: (message: WidgetMessage, state: GenericWidgetRenderState) => void | Promise<void>;
  onMessageFeedback?: (message: WidgetMessage, rating: number, state: GenericWidgetRenderState) => void | Promise<void>;
}) {
  if (renderMessages) return <div className="gw-message-feed">{renderMessages(messages, state)}</div>;

  return (
    <div className="gw-message-feed" role="log" aria-live="polite" aria-busy={loadingState !== "hidden"}>
      {config.welcomeText ? (
        <MessageCard
          message={{ id: "gw-welcome-message", role: "system", content: config.welcomeText }}
          config={config}
          state={state}
          onCopyMessage={onCopyMessage}
          onMessageFeedback={onMessageFeedback}
        />
      ) : null}
      {messages.map((message) => (
        <MessageCard
          key={message.id}
          message={message}
          config={config}
          state={state}
          onCopyMessage={onCopyMessage}
          onMessageFeedback={onMessageFeedback}
        />
      ))}
      {loadingState !== "hidden" ? <LoadingMessage config={config} state={loadingState} label={loadingLabel || config.loadingText} /> : null}
    </div>
  );
}
