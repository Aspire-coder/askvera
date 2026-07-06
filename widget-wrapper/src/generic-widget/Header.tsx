import type { WidgetState } from "../state";
import type { GenericWidgetConfig, WidgetCountryOption } from "./types";

type HeaderIconName = "menu" | "close";

function HeaderIcon({ name }: { name: HeaderIconName }) {
  const commonProps = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true
  };

  if (name === "menu") {
    return (
      <svg {...commonProps}>
        <circle cx="12" cy="12" r="1" />
        <circle cx="12" cy="5" r="1" />
        <circle cx="12" cy="19" r="1" />
      </svg>
    );
  }

  return (
    <svg {...commonProps}>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

export function Header({
  config,
  selectedCountry,
  connection,
  menuOpen,
  onToggleMenu,
  onClose
}: {
  config: GenericWidgetConfig;
  selectedCountry?: WidgetCountryOption;
  connection: WidgetState["connection"];
  menuOpen: boolean;
  onToggleMenu: () => void;
  onClose: () => void;
}) {
  const assistantName = config.assistantName || config.brandName;
  const assistantSubtitle = config.assistantSubtitle || "AI Assistant";
  const statusType = connection.reconnecting ? "reconnecting" : connection.online ? "online" : "offline";
  const statusLabel =
    statusType === "reconnecting"
      ? config.statusLabels?.reconnecting || "Reconnecting"
      : statusType === "online"
        ? config.statusLabels?.online || "Online"
        : config.statusLabels?.offline || "Offline";
  const mark = assistantName.trim().slice(0, 1) || config.brandName.slice(0, 1);

  return (
    <header className="gw-header">
      <div className="gw-header-identity">
        <div className="gw-header-mark" aria-hidden="true">
          {config.logoUrl ? <img src={config.logoUrl} alt="" /> : <span>{mark}</span>}
        </div>
        <div className="gw-header-copy">
          <div className="gw-title">{assistantName}</div>
          <div className="gw-subtitle">{assistantSubtitle}</div>
          <div className={`gw-status gw-status-${statusType}`}>
            <span className="gw-status-dot" aria-hidden="true" />
            <span>{statusLabel}</span>
            {selectedCountry ? <span className="gw-status-region">{selectedCountry.label}</span> : null}
          </div>
        </div>
      </div>
      <div className="gw-header-actions">
        <button type="button" className="gw-icon-button" onClick={onToggleMenu} aria-label={config.labels.menuAriaLabel} aria-expanded={menuOpen}>
          <HeaderIcon name="menu" />
        </button>
        <button type="button" className="gw-icon-button" onClick={onClose} aria-label={config.labels.closeAriaLabel}>
          <HeaderIcon name="close" />
        </button>
      </div>
    </header>
  );
}
