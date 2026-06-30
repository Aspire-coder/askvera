import type { GenericWidgetConfig } from "./types";

export function LegalLinks({ config }: { config: GenericWidgetConfig }) {
  if (!config.policyLinks.length) return null;

  return (
    <nav className="gw-legal" aria-label={config.labels.legalLinksLabel}>
      {config.policyLinks.map((link) => (
        <a key={link.id} href={link.href} target={link.target || "_blank"} rel="noreferrer">
          {link.label}
        </a>
      ))}
    </nav>
  );
}
