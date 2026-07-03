import { useState } from "react";
import type { GenericWidgetConfig } from "./types";
import { LegalLinks } from "./LegalLinks";

export function ConsentPanel({
  config,
  onAccept,
  onReject,
  accepting = false,
  error
}: {
  config: GenericWidgetConfig;
  onAccept: () => void;
  onReject: () => void;
  accepting?: boolean;
  error?: string | null;
}) {
  const [acknowledged, setAcknowledged] = useState(false);

  return (
    <section className="gw-section gw-consent">
      <h2>{config.consent.title}</h2>
      <div className="gw-consent-body">{config.consent.body}</div>
      <LegalLinks config={config} />
      <label className="gw-consent-ack">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
        />
        <span>I have read and agree to all of the above documents.</span>
      </label>
      {error ? <p className="gw-consent-error" role="alert">{error}</p> : null}
      <div className="gw-consent-actions">
        <button type="button" className="gw-secondary-button" onClick={onReject} disabled={accepting}>{config.labels.rejectConsentLabel}</button>
        <button type="button" className="gw-primary-button" onClick={onAccept} disabled={!acknowledged || accepting}>
          {accepting ? "Saving..." : config.labels.acceptConsentLabel}
        </button>
      </div>
    </section>
  );
}
