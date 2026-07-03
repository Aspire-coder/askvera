import { BackendChatDemo } from "../../src/generic-widget/examples/BackendChatDemo";
import { useEffect, useState } from "react";

const apiBaseUrl = new URLSearchParams(window.location.search).get("api") || "https://api.vera-api.xyz";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: { message: string };
};

type LegalDocument = {
  id: string;
  title: string;
  html: string;
};

type PrivacyResponseData = {
  version: string;
  documents: LegalDocument[];
};

const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

function LegalDocumentPage() {
  const params = new URLSearchParams(window.location.search);
  const api = params.get("api") || apiBaseUrl;
  const country = params.get("country") || "US";
  const lang = params.get("lang") || "en";
  const documentId = params.get("doc") || "privacy";
  const [state, setState] = useState<{ loading: boolean; error?: string; data?: PrivacyResponseData }>({ loading: true });

  useEffect(() => {
    let active = true;
    const path = `/api/privacy?country=${encodeURIComponent(country)}&lang=${encodeURIComponent(lang)}`;

    fetch(joinUrl(api, path))
      .then(async (response) => {
        const envelope = (await response.json()) as ApiEnvelope<PrivacyResponseData>;
        if (!response.ok || !envelope.success || !envelope.data) {
          throw new Error(envelope.error?.message || `Request failed with status ${response.status}`);
        }
        if (active) setState({ loading: false, data: envelope.data });
      })
      .catch((error) => {
        if (active) {
          setState({ loading: false, error: error instanceof Error ? error.message : "Could not load legal document." });
        }
      });

    return () => {
      active = false;
    };
  }, [api, country, documentId, lang]);

  const selectedDocument = state.data?.documents.find((document) => document.id === documentId) || state.data?.documents[0];

  return (
    <main className="legal-page">
      <a className="legal-back-link" href={`/?api=${encodeURIComponent(api)}`}>Back to widget demo</a>
      {state.loading ? <p className="legal-status">Loading legal document...</p> : null}
      {state.error ? <p className="legal-error">{state.error}</p> : null}
      {selectedDocument ? (
        <article className="legal-document">
          <header>
            <p className="legal-eyebrow">{country} / {lang.toUpperCase()} / Version {state.data?.version}</p>
            <h1>{selectedDocument.title}</h1>
          </header>
          <div className="legal-html" dangerouslySetInnerHTML={{ __html: selectedDocument.html }} />
        </article>
      ) : null}
    </main>
  );
}

export function App() {
  if (window.location.pathname === "/legal") {
    return <LegalDocumentPage />;
  }

  return (
    <main className="demo-page">
      <section className="demo-layout">
        <div className="demo-copy">
          <p className="demo-eyebrow">AWS-connected demo</p>
          <h1>ASK Vera widget connected to the Python API</h1>
          <p>
            Review the market selector, privacy acceptance, and chat flow locally while messages are sent to the
            AWS-backed FastAPI service.
          </p>
          <div className="demo-actions" aria-label="Demo status">
            <span>Local widget</span>
            <span>AWS backend</span>
            <span>Consent-first</span>
          </div>
        </div>

        <aside className="demo-preview" aria-label="Integration preview">
          <div className="demo-preview-header">
            <span className="demo-status-dot" />
            <span>Widget shell preview</span>
          </div>
          <div className="demo-preview-body">
            <div>
              <span className="demo-metric-label">Provider</span>
              <strong>ASK Vera API</strong>
            </div>
            <div>
              <span className="demo-metric-label">Mode</span>
              <strong>Consent-first</strong>
            </div>
            <div>
              <span className="demo-metric-label">API</span>
              <strong>{apiBaseUrl}</strong>
            </div>
          </div>
        </aside>
      </section>
      <BackendChatDemo apiBaseUrl={apiBaseUrl} />
    </main>
  );
}
