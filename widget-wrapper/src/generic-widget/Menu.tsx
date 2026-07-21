import { useState } from "react";
import type { GenericWidgetConfig, LocaleChangePayload, SessionResetReason, SessionResetResult } from "./types";

export function Menu({
  config,
  payload,
  onNewChat,
  onEscalate,
  onDismiss
}: {
  config: GenericWidgetConfig;
  payload: LocaleChangePayload;
  onNewChat?: (payload: LocaleChangePayload, reason: SessionResetReason) => SessionResetResult | Promise<SessionResetResult>;
  onEscalate?: (payload: LocaleChangePayload) => void;
  onDismiss?: () => void;
}) {
  const [confirmingNewChat, setConfirmingNewChat] = useState(false);

  const resetChat = async (reason: SessionResetReason) => {
    onDismiss?.();
    await onNewChat?.(payload, reason);
  };

  return (
    <div className="gw-menu" role="menu">
      {confirmingNewChat ? (
        <div className="gw-menu-confirm" role="group" aria-label={config.menu.newChat}>
          <p className="gw-menu-confirm-message">{config.menu.newChatConfirmation}</p>
          <button type="button" className="gw-menu-confirm-primary" onClick={() => void resetChat("new_chat")}>
            {config.menu.confirmNewChat}
          </button>
          <button type="button" onClick={() => setConfirmingNewChat(false)}>
            {config.menu.cancelNewChat}
          </button>
        </div>
      ) : (
        <button type="button" className="gw-menu-item" role="menuitem" onClick={() => setConfirmingNewChat(true)}>
          <span className="gw-menu-icon" aria-hidden="true">+</span>
          <span>{config.menu.newChat}</span>
        </button>
      )}
      {onEscalate ? <button type="button" className="gw-menu-item" role="menuitem" onClick={() => { onDismiss?.(); onEscalate(payload); }}>
        <span className="gw-menu-icon" aria-hidden="true">?</span>
        <span>{config.menu.escalate}</span>
      </button> : null}
    </div>
  );
}
