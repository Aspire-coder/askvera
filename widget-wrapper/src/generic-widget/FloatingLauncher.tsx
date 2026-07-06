import { forwardRef } from "react";
import type { GenericWidgetConfig } from "./types";

export const FloatingLauncher = forwardRef<HTMLButtonElement, { config: GenericWidgetConfig; onClick: () => void }>(
  function FloatingLauncher({ config, onClick }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      className="gw-launcher"
      onClick={onClick}
      aria-label={config.labels.launcherAriaLabel}
      aria-haspopup="dialog"
    >
      <span aria-hidden="true" className="gw-launcher-mark">
        {config.brandName.slice(0, 1)}
      </span>
    </button>
  );
  }
);
