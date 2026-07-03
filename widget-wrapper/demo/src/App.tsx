import { BackendChatDemo } from "../../src/generic-widget/examples/BackendChatDemo";

const apiBaseUrl = new URLSearchParams(window.location.search).get("api") || "https://api.vera-api.xyz";

export function App() {
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
