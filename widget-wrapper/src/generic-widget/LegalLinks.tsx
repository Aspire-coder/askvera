import { useState } from "react";
import type { GenericWidgetConfig } from "./types";

export function LegalLinks({ config }: { config: GenericWidgetConfig }) {
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  if (!config.policyLinks.length) return null;

  const activeDocument = config.policyLinks.find((link) => link.id === activeDocumentId);

  return (
    <>
      <nav className="gw-legal" aria-label={config.labels.legalLinksLabel}>
        {config.policyLinks.map((link) => (
          <div key={link.id} className="gw-legal-item">
            <span aria-hidden="true">{"\u2022"}</span>
            {link.html ? (
              <button type="button" className="gw-legal-link-button" onClick={() => setActiveDocumentId(link.id)}>
                {link.label}
              </button>
            ) : (
              <a href={link.href} target={link.target || "_blank"} rel="noreferrer">
                {link.label}
              </a>
            )}
          </div>
        ))}
      </nav>
      {activeDocument?.html ? (
        <div className="gw-legal-modal" role="dialog" aria-modal="true" aria-labelledby="gw-legal-modal-title">
          <div className="gw-legal-modal-backdrop" onClick={() => setActiveDocumentId(null)} />
          <section className="gw-legal-modal-panel">
            <header className="gw-legal-modal-header">
              <h3 id="gw-legal-modal-title">{activeDocument.label}</h3>
              <button type="button" className="gw-icon-button" onClick={() => setActiveDocumentId(null)} aria-label="Close legal document">
                <span aria-hidden="true">{"\u00d7"}</span>
              </button>
            </header>
            <div className="gw-legal-modal-body" dangerouslySetInnerHTML={{ __html: activeDocument.html }} />
          </section>
        </div>
      ) : null}
    </>
  );
}
