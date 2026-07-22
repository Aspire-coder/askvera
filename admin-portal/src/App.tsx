import { useEffect, useState } from "react";
import { type AdminCredentials } from "./api";
import { beginSignIn, cognitoConfigured, completeSignIn, demoAllowed, signOut, type AuthSession } from "./auth";
import { ChartIcon, FlowIcon, KeyIcon, UploadIcon } from "./icons";
import { FlowVisualizer } from "./components/FlowVisualizer";
import { InsightsDashboard } from "./components/InsightsDashboard";
import { KnowledgeUploader } from "./components/KnowledgeUploader";
import type { View } from "./types";

const nav = [
  { id: "flow" as const, label: "Live flow", detail: "Follow an answer", icon: <FlowIcon /> },
  { id: "knowledge" as const, label: "Knowledge", detail: "Manage approved content", icon: <UploadIcon /> },
  { id: "insights" as const, label: "Insights", detail: "Measure and improve", icon: <ChartIcon /> },
];

export function App() {
  const [view, setView] = useState<View>("flow");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = useState(!cognitoConfigured);
  const [authError, setAuthError] = useState("");
  const [apiKey, setApiKey] = useState(() => window.sessionStorage.getItem("askvera_admin_key") || "");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftKey, setDraftKey] = useState(apiKey);

  useEffect(() => {
    if (!cognitoConfigured) return;
    void completeSignIn()
      .then((nextSession) => setSession(nextSession))
      .catch((error) => setAuthError(error instanceof Error ? error.message : "Sign-in failed."))
      .finally(() => setAuthReady(true));
  }, []);

  const connect = () => {
    const key = draftKey.trim();
    if (key) window.sessionStorage.setItem("askvera_admin_key", key);
    else window.sessionStorage.removeItem("askvera_admin_key");
    setApiKey(key);
    setSettingsOpen(false);
  };

  if (!authReady) {
    return <main className="auth-page"><section className="auth-card"><div className="brand-mark">V</div><span className="eyebrow">AskVera Operations</span><h1>Signing you in</h1><p>Verifying your administrator session.</p></section></main>;
  }

  if (cognitoConfigured && !session) {
    return <main className="auth-page"><section className="auth-card">
      <div className="brand-mark">V</div><span className="eyebrow">AskVera Operations</span><h1>Operational clarity, in one place.</h1><p>Review answer quality, follow live requests, and manage approved knowledge through your company account.</p>
      {authError ? <div className="auth-error" role="alert">{authError}</div> : null}
      <button className="button primary auth-button" onClick={() => void beginSignIn()}>Sign in securely</button>
      <small>Access is limited to approved AskVera administrators.</small>
    </section></main>;
  }

  const credentials: AdminCredentials = session ? { accessToken: session.accessToken } : { apiKey };
  const connectionLabel = session ? session.username : apiKey ? "Admin connected" : "Demo mode";
  const connectionDetail = session || apiKey ? "Live operational data" : "Presentation data";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">V</div><div><strong>AskVera</strong><span>Operations</span></div></div>
        <nav aria-label="Admin sections">{nav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>{item.icon}<span><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}</nav>
        <div className="sidebar-bottom">
          <button className="connection-button" onClick={() => session ? signOut() : setSettingsOpen(true)}><KeyIcon /><span><strong>{connectionLabel}</strong><small>{session ? "Select to sign out" : connectionDetail}</small></span><i className={session || apiKey ? "online" : ""} /></button>
          <div className="environment"><span>Production</span><strong>Operations</strong></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="mobile-header"><div className="brand"><div className="brand-mark">V</div><strong>AskVera Operations</strong></div><button onClick={() => session ? signOut() : setSettingsOpen(true)}><KeyIcon /></button></header>
        {view === "flow" ? <FlowVisualizer credentials={credentials} /> : null}
        {view === "knowledge" ? <KnowledgeUploader credentials={credentials} /> : null}
        {view === "insights" ? <InsightsDashboard credentials={credentials} /> : null}
        <nav className="mobile-nav" aria-label="Admin sections">{nav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>{item.icon}<span>{item.label}</span></button>)}</nav>
      </main>

      {settingsOpen && demoAllowed ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}><section className="connection-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title">
        <button className="drawer-close" onClick={() => setSettingsOpen(false)} aria-label="Close">x</button>
        <div className="connection-icon"><KeyIcon /></div><span className="eyebrow">Local connection</span><h2 id="connect-title">Connect operational data</h2><p>Enter the development admin key. Production uses company sign-in and never places an API key in the website bundle.</p>
        <label><span>Admin API key</span><input type="password" value={draftKey} onChange={(event) => setDraftKey(event.target.value)} placeholder="Enter admin key" autoFocus /></label>
        <div className="modal-actions"><button className="button secondary" onClick={() => { setDraftKey(""); setApiKey(""); window.sessionStorage.removeItem("askvera_admin_key"); setSettingsOpen(false); }}>Use demo data</button><button className="button primary" onClick={connect}>Connect</button></div>
      </section></div> : null}
    </div>
  );
}
