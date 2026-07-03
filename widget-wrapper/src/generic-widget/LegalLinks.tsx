import type { GenericWidgetConfig } from "./types";

export function LegalLinks({ config }: { config: GenericWidgetConfig }) {
  if (!config.policyLinks.length) return null;

  return (
    <nav className="gw-legal" aria-label={config.labels.legalLinksLabel}>
      {config.policyLinks.map((link) => (
        <div key={link.id} className="gw-legal-item">
          <span aria-hidden="true">{"\u2022"}</span>
          <a href={link.href} target={link.target || "_blank"} rel="noreferrer">
            {link.label}
          </a>
        </div>
      ))}
    </nav>
  );
}
