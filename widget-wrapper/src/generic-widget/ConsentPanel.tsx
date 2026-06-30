import type { GenericWidgetConfig } from "./types";
import { LegalLinks } from "./LegalLinks";

export function ConsentPanel({
  config,
  onAccept,
  onReject
}: {
  config: GenericWidgetConfig;
  onAccept: () => void;
  onReject: () => void;
}) {
  return (
    <section className="gw-section gw-consent">
      <h2>{config.consent.title}</h2>
      <div className="gw-consent-body">{config.consent.body}</div>
      <LegalLinks config={config} />
      <div className="gw-consent-actions">
        <button type="button" className="gw-secondary-button" onClick={onReject}>{config.labels.rejectConsentLabel}</button>
        <button type="button" className="gw-primary-button" onClick={onAccept}>{config.labels.acceptConsentLabel}</button>
      </div>
    </section>
  );
}
