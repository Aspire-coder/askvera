import { KeyboardEvent, useEffect, useRef, useState } from "react";
import type { GenericWidgetConfig } from "./types";
import { sanitizeLegalHtml } from "./legalHtml";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

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

  const downloadDocument = (documentId: string) => {
    // Previously opened a blank window with window.open("", "_blank") and
    // wrote content into it after the fact, then called print() 250ms
    // later. That blank-popup-before-content pattern is what left a stuck
    // about:blank tab showing the browser's print UI, which in turn left
    // the host site unresponsive if the user navigated back to it before
    // the popup resolved (TRB-19161). A direct Blob download never opens
    // a second window at all.
    const documentToDownload = config.policyLinks.find((link) => link.id === documentId);
    if (!documentToDownload?.html) return;
    const safeHtml = sanitizeLegalHtml(documentToDownload.html);
    const escapedTitle = documentToDownload.label.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const documentHtml = `<!doctype html><html><head><meta charset="utf-8"><title>${escapedTitle}</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;max-width:760px;margin:48px auto;padding:0 28px;color:#1d1d1f;line-height:1.55}h1,h2,h3{line-height:1.25}table{width:100%;border-collapse:collapse}th,td{border:1px solid #d9ddd9;padding:8px;text-align:left}</style></head><body>${safeHtml}</body></html>`;

    const blobUrl = URL.createObjectURL(new Blob([documentHtml], { type: "text/html" }));
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.download = `${documentToDownload.label.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "document"}.html`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(blobUrl);
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
        <div className="gw-legal-title">{config.labels.legalReviewTitle || "Review required documents"}</div>
        {config.policyLinks.map((link) => (
          <div key={link.id} className="gw-legal-item">
            <span aria-hidden="true">{"\u2713"}</span>
            {link.html ? (
              <div className="gw-legal-document-actions">
                <button type="button" className="gw-legal-link-button" onClick={() => openDocument(link.id)} aria-haspopup="dialog">{link.label}</button>
                <button type="button" className="gw-legal-print-button" onClick={() => downloadDocument(link.id)} aria-label={`${config.labels.saveDocumentLabel || "Save as PDF"}: ${link.label}`} title={config.labels.saveDocumentLabel || "Save as PDF"}>
                  <DownloadIcon />
                </button>
              </div>
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
              <button ref={closeButtonRef} type="button" className="gw-icon-button" onClick={closeDocument} aria-label={config.labels.closeLegalDocumentLabel || "Close legal document"}>
                <span aria-hidden="true">{"\u00d7"}</span>
              </button>
            </header>
            <div id={modalBodyId} className="gw-legal-modal-body" dangerouslySetInnerHTML={{ __html: sanitizeLegalHtml(activeDocument.html) }} />
          </section>
        </div>
      ) : null}
    </>
  );
}
