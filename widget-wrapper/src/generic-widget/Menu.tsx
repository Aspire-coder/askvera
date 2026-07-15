import type { GenericWidgetConfig, LocaleChangePayload } from "./types";

export function Menu({
  config,
  payload,
  onNewChat,
  onEscalate,
  onDismiss
}: {
  config: GenericWidgetConfig;
  payload: LocaleChangePayload;
  onNewChat?: (payload: LocaleChangePayload) => void;
  onEscalate?: (payload: LocaleChangePayload) => void;
  onDismiss?: () => void;
}) {
  const startNewChat = () => {
    onDismiss?.();
    onNewChat?.(payload);
  };

  return (
    <div className="gw-menu" role="menu">
      <button type="button" className="gw-menu-item" role="menuitem" onClick={startNewChat}>
        <span className="gw-menu-icon" aria-hidden="true">+</span>
        <span>{config.menu.newChat}</span>
      </button>
      {onEscalate ? <button type="button" className="gw-menu-item" role="menuitem" onClick={() => { onDismiss?.(); onEscalate(payload); }}>
        <span className="gw-menu-icon" aria-hidden="true">?</span>
        <span>{config.menu.escalate}</span>
      </button> : null}
    </div>
  );
}
