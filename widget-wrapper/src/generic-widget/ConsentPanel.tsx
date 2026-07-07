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
  const managedLegalLinks = config.policyLinks.filter((link) => link.required !== undefined);
  const legalDocumentsReady = managedLegalLinks.length
    ? managedLegalLinks.every((link) => link.required === false || Boolean(link.html))
    : config.policyLinks.length > 0;
  const acceptDisabled = !acknowledged || accepting || !legalDocumentsReady;

  return (
    <section className="gw-section gw-consent">
      <div className="gw-consent-heading">
        <p>One quick privacy step</p>
        <h2>{config.consent.title}</h2>
      </div>
      <div className="gw-consent-body">{config.consent.body}</div>
      <LegalLinks config={config} />
      {!legalDocumentsReady ? (
        <p className="gw-consent-loading" role="status">Loading legal documents before consent can be recorded.</p>
      ) : null}
      <label className="gw-consent-ack">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
          disabled={!legalDocumentsReady || accepting}
        />
        <span>I have read and agree to all of the above documents.</span>
      </label>
      {error ? <p className="gw-consent-error" role="alert">{error}</p> : null}
      <div className="gw-consent-actions">
        <button type="button" className="gw-consent-skip" onClick={onReject} disabled={accepting}>{config.labels.rejectConsentLabel}</button>
        <button type="button" className="gw-primary-button" onClick={onAccept} disabled={acceptDisabled}>
          {accepting ? "Saving..." : config.labels.acceptConsentLabel}
        </button>
      </div>
    </section>
  );
}
