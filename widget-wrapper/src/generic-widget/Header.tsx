import type { GenericWidgetConfig, WidgetCountryOption } from "./types";

export function Header({
  config,
  selectedCountry,
  menuOpen,
  onToggleMenu,
  onClose
}: {
  config: GenericWidgetConfig;
  selectedCountry?: WidgetCountryOption;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onClose: () => void;
}) {
  return (
    <header className="gw-header">
      <div>
        <div className="gw-title">{config.brandName}</div>
        {selectedCountry ? <div className="gw-subtitle">{selectedCountry.label}</div> : null}
      </div>
      <div className="gw-header-actions">
        <button type="button" className="gw-icon-button" onClick={onToggleMenu} aria-label={config.labels.menuAriaLabel} aria-expanded={menuOpen}>
          <span aria-hidden="true">⋮</span>
        </button>
        <button type="button" className="gw-icon-button" onClick={onClose} aria-label={config.labels.closeAriaLabel}>
          <span aria-hidden="true">×</span>
        </button>
      </div>
    </header>
  );
}
