import type { GenericWidgetConfig, LocaleChangePayload } from "./types";

export function Menu({
  config,
  payload,
  onNewChat,
  onEscalate
}: {
  config: GenericWidgetConfig;
  payload: LocaleChangePayload;
  onNewChat?: (payload: LocaleChangePayload) => void;
  onEscalate?: (payload: LocaleChangePayload) => void;
}) {
  return (
    <div className="gw-menu" role="menu">
      <button type="button" className="gw-menu-item" role="menuitem">{config.menu.settings}</button>
      <button type="button" className="gw-menu-item" role="menuitem">{config.menu.history}</button>
      <button type="button" className="gw-menu-item" role="menuitem" onClick={() => onNewChat?.(payload)}>{config.menu.newChat}</button>
      <button type="button" className="gw-menu-item" role="menuitem" onClick={() => onEscalate?.(payload)}>{config.menu.escalate}</button>
    </div>
  );
}
