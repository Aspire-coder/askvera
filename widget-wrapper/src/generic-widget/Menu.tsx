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
  const [resetting, setResetting] = useState(false);
  const [confirmingEnd, setConfirmingEnd] = useState(false);
  const resetChat = async (reason: SessionResetReason) => {
    if (resetting) return;
    setResetting(true);
    onDismiss?.();
    try {
      await onNewChat?.(payload, reason);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="gw-menu" role="menu">
      <button type="button" className="gw-menu-item" role="menuitem" disabled={resetting} onClick={() => void resetChat("new_chat")}>
        <span className="gw-menu-icon" aria-hidden="true">+</span>
        <span>{config.menu.newChat}</span>
      </button>
      {confirmingEnd ? (
        <div className="gw-menu-confirm" role="group" aria-label={config.menu.endChat}>
          <button type="button" className="gw-menu-confirm-end" disabled={resetting} onClick={() => void resetChat("user_ended")}>{config.menu.confirmEndChat}</button>
          <button type="button" disabled={resetting} onClick={() => setConfirmingEnd(false)}>{config.menu.cancelEndChat}</button>
        </div>
      ) : (
        <button type="button" className="gw-menu-item" role="menuitem" disabled={resetting} onClick={() => setConfirmingEnd(true)}>
          <span className="gw-menu-icon" aria-hidden="true">{String.fromCharCode(215)}</span>
          <span>{config.menu.endChat}</span>
        </button>
      )}
      {onEscalate ? <button type="button" className="gw-menu-item" role="menuitem" onClick={() => { onDismiss?.(); onEscalate(payload); }}>
        <span className="gw-menu-icon" aria-hidden="true">?</span>
        <span>{config.menu.escalate}</span>
      </button> : null}
    </div>
  );
}
