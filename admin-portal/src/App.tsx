import { useState } from "react";
import { ChartIcon, FlowIcon, KeyIcon } from "./icons";
import { FlowVisualizer } from "./components/FlowVisualizer";
import { InsightsDashboard } from "./components/InsightsDashboard";
import type { View } from "./types";

const nav = [
  { id: "flow" as const, label: "Live flow", detail: "Follow an answer", icon: <FlowIcon /> },
  { id: "insights" as const, label: "Insights", detail: "Measure and improve", icon: <ChartIcon /> }
];

export function App() {
  const [view, setView] = useState<View>("flow");
  const [apiKey, setApiKey] = useState(() => window.sessionStorage.getItem("askvera_admin_key") || "");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftKey, setDraftKey] = useState(apiKey);

  const connect = () => {
    const key = draftKey.trim();
    if (key) window.sessionStorage.setItem("askvera_admin_key", key);
    else window.sessionStorage.removeItem("askvera_admin_key");
    setApiKey(key);
    setSettingsOpen(false);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">V</div><div><strong>AskVera</strong><span>Operations</span></div></div>
        <nav aria-label="Admin sections">{nav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>{item.icon}<span><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}</nav>
        <div className="sidebar-bottom">
          <button className="connection-button" onClick={() => { setDraftKey(apiKey); setSettingsOpen(true); }}><KeyIcon /><span><strong>{apiKey ? "Admin connected" : "Demo mode"}</strong><small>{apiKey ? "Live operational data" : "Add an API key"}</small></span><i className={apiKey ? "online" : ""} /></button>
          <div className="environment"><span>Production</span><strong>v1.0</strong></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="mobile-header"><div className="brand"><div className="brand-mark">V</div><strong>AskVera Operations</strong></div><button onClick={() => setSettingsOpen(true)}><KeyIcon /></button></header>
        {view === "flow" ? <FlowVisualizer apiKey={apiKey} /> : null}
        {view === "insights" ? <InsightsDashboard apiKey={apiKey} /> : null}
        <nav className="mobile-nav" aria-label="Admin sections">{nav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>{item.icon}<span>{item.label}</span></button>)}</nav>
      </main>

      {settingsOpen ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}><section className="connection-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title">
        <button className="drawer-close" onClick={() => setSettingsOpen(false)} aria-label="Close">×</button>
        <div className="connection-icon"><KeyIcon /></div><span className="eyebrow">Secure connection</span><h2 id="connect-title">Connect operational data</h2><p>Enter the admin key configured on the AskVera API. It remains in this browser tab and is never written to the portal bundle.</p>
        <label><span>Admin API key</span><input type="password" value={draftKey} onChange={(event) => setDraftKey(event.target.value)} placeholder="Enter admin key" autoFocus /></label>
        <div className="modal-actions"><button className="button secondary" onClick={() => { setDraftKey(""); setApiKey(""); window.sessionStorage.removeItem("askvera_admin_key"); setSettingsOpen(false); }}>Use demo data</button><button className="button primary" onClick={connect}>Connect</button></div>
        <small>For production, manage this key in AWS Systems Manager Parameter Store and rotate it regularly.</small>
      </section></div> : null}
    </div>
  );
}
