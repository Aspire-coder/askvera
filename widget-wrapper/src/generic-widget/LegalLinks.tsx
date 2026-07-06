import { KeyboardEvent, useEffect, useRef, useState } from "react";
import type { GenericWidgetConfig } from "./types";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

export function LegalLinks({ config }: { config: GenericWidgetConfig }) {
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const modalPanelRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  const activeDocument = config.policyLinks.find((link) => link.id === activeDocumentId);
  const modalTitleId = activeDocument ? `gw-legal-modal-title-${activeDocument.id}` : undefined;
  const modalBodyId = activeDocument ? `gw-legal-modal-body-${activeDocument.id}` : undefined;

  const openDocument = (documentId: string) => {
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setActiveDocumentId(documentId);
  };

  const closeDocument = () => {
    setActiveDocumentId(null);
    window.setTimeout(() => returnFocusRef.current?.focus(), 0);
  };

  useEffect(() => {
    if (!activeDocument?.html) return;
    closeButtonRef.current?.focus();
  }, [activeDocument?.html]);

  const handleModalKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeDocument();
      return;
    }

    if (event.key !== "Tab") return;

    const panel = modalPanelRef.current;
    if (!panel) return;
    const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
      (element) => element.offsetParent !== null
    );
    if (!focusable.length) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!config.policyLinks.length) return null;

  return (
    <>
      <nav className="gw-legal" aria-label={config.labels.legalLinksLabel}>
        {config.policyLinks.map((link) => (
          <div key={link.id} className="gw-legal-item">
            <span aria-hidden="true">{"\u2022"}</span>
            {link.html ? (
              <button type="button" className="gw-legal-link-button" onClick={() => openDocument(link.id)} aria-haspopup="dialog">
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
        <div className="gw-legal-modal" role="presentation">
          <div className="gw-legal-modal-backdrop" onClick={closeDocument} />
          <section
            ref={modalPanelRef}
            className="gw-legal-modal-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby={modalTitleId}
            aria-describedby={modalBodyId}
            tabIndex={-1}
            onKeyDown={handleModalKeyDown}
          >
            <header className="gw-legal-modal-header">
              <h3 id={modalTitleId}>{activeDocument.label}</h3>
              <button ref={closeButtonRef} type="button" className="gw-icon-button" onClick={closeDocument} aria-label="Close legal document">
                <span aria-hidden="true">{"\u00d7"}</span>
              </button>
            </header>
            <div id={modalBodyId} className="gw-legal-modal-body" dangerouslySetInnerHTML={{ __html: activeDocument.html }} />
          </section>
        </div>
      ) : null}
    </>
  );
}
