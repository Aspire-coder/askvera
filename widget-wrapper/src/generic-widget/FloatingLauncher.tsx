import { forwardRef } from "react";
import type { GenericWidgetConfig } from "./types";

export const FloatingLauncher = forwardRef<HTMLButtonElement, { config: GenericWidgetConfig; onClick: () => void }>(
  function FloatingLauncher({ config, onClick }, ref) {
  const assistantName = config.assistantName || config.brandName;
  const mark = assistantName.trim().slice(0, 1) || config.brandName.slice(0, 1);
  const iconUrl = config.launcherIconUrl || config.logoUrl;

  return (
    <button
      ref={ref}
      type="button"
      className="gw-launcher"
      onClick={onClick}
      aria-label={config.labels.launcherAriaLabel}
      aria-haspopup="dialog"
      title={config.launcherTitle}
    >
      <span aria-hidden="true" className="gw-launcher-mark">
        {iconUrl ? <img src={iconUrl} alt="" /> : mark}
      </span>
    </button>
  );
  }
);
