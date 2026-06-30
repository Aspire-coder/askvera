import type { GenericWidgetConfig } from "./types";

export function FloatingLauncher({ config, onClick }: { config: GenericWidgetConfig; onClick: () => void }) {
  return (
    <button type="button" className="gw-launcher" onClick={onClick} aria-label={config.labels.launcherAriaLabel}>
      <span aria-hidden="true" className="gw-launcher-mark">
        {config.brandName.slice(0, 1)}
      </span>
    </button>
  );
}
