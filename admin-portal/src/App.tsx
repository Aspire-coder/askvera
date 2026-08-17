import { useEffect, useState } from "react";
import { AdminApi, demo, type AdminCredentials } from "./api";
import { beginSignIn, cognitoConfigured, completeSignIn, demoAllowed, signOut, type AuthSession } from "./auth";
import { AskVeraMark, ChartIcon, FlowIcon, HomeIcon, KeyIcon, UploadIcon } from "./icons";
import { FlowVisualizer } from "./components/FlowVisualizer";
import { InsightsDashboard } from "./components/InsightsDashboard";
import { KnowledgeUploader } from "./components/KnowledgeUploader";
import { MarketReadiness } from "./components/MarketReadiness";
import { OperationsOverview } from "./components/OperationsOverview";
import { SupportRoutesManager } from "./components/SupportRoutesManager";
import { UsersManager } from "./components/UsersManager";
import { WidgetManager } from "./components/WidgetManager";
import type { AdminConfig, View } from "./types";
import { useDialogFocus } from "./useDialogFocus";

const nav = [
  { id: "overview" as const, label: "Overview", detail: "Run the operation", icon: <HomeIcon /> },
  { id: "flow" as const, label: "Live flow", detail: "Follow an answer", icon: <FlowIcon /> },
  { id: "knowledge" as const, label: "Knowledge", detail: "Manage approved content", icon: <UploadIcon /> },
  { id: "readiness" as const, label: "Market readiness", detail: "Prepare and verify markets", icon: <ChartIcon /> },
  { id: "insights" as const, label: "Insights", detail: "Measure and improve", icon: <ChartIcon /> },
  { id: "support" as const, label: "Support", detail: "Route customer requests", icon: <FlowIcon /> },
  { id: "users" as const, label: "Users", detail: "Manage access", icon: <KeyIcon /> },
  { id: "widget" as const, label: "Widget", detail: "Configure customer embeds", icon: <UploadIcon /> },
];

const viewIds = new Set<View>(nav.map((item) => item.id));
const initialView = (): View => {
  const candidate = window.location.hash.replace(/^#/, "") as View;
  return viewIds.has(candidate) ? candidate : "overview";
};

export function App() {
  const [view, setView] = useState<View>(initialView);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = useState(!cognitoConfigured);
  const [authError, setAuthError] = useState("");
  const [apiKey, setApiKey] = useState(() => window.sessionStorage.getItem("askvera_admin_key") || "");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftKey, setDraftKey] = useState(apiKey);
  const [adminConfig, setAdminConfig] = useState<AdminConfig>(demo.config);
  const [configLoading, setConfigLoading] = useState(false);
  const [configError, setConfigError] = useState("");
  const [configAttempt, setConfigAttempt] = useState(0);
  const closeSettings = () => setSettingsOpen(false);
  const settingsDialogRef = useDialogFocus<HTMLElement>(settingsOpen && demoAllowed, closeSettings);

  useEffect(() => {
    if (!cognitoConfigured) return;
    void completeSignIn()
      .then((nextSession) => setSession(nextSession))
      .catch((error) => setAuthError(error instanceof Error ? error.message : "Sign-in failed."))
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    if (!session) return;
    const expire = () => signOut();
    const remaining = Math.max(0, session.expiresAt - Date.now() - 15_000);
    const timer = window.setTimeout(expire, remaining);
    window.addEventListener("askvera:auth-expired", expire);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("askvera:auth-expired", expire);
    };
  }, [session?.expiresAt]);

  useEffect(() => {
    const syncFromLocation = () => {
      const candidate = window.location.hash.replace(/^#/, "") as View;
      if (viewIds.has(candidate)) setView(candidate);
    };
    window.addEventListener("hashchange", syncFromLocation);
    return () => window.removeEventListener("hashchange", syncFromLocation);
  }, []);

  const connect = () => {
    const key = draftKey.trim();
    if (key) window.sessionStorage.setItem("askvera_admin_key", key);
    else window.sessionStorage.removeItem("askvera_admin_key");
    setApiKey(key);
    setSettingsOpen(false);
  };

  const credentials: AdminCredentials = session ? { accessToken: session.accessToken } : { apiKey };
  const navigate = (nextView: View) => {
    setView(nextView);
    if (window.location.hash !== `#${nextView}`) window.location.hash = nextView;
  };
  const canView = (section: View) => {
    if (section === "overview") return true;
    if (section === "users" && !adminConfig.userManagementEnabled) return false;
    if (section === "widget" && !adminConfig.widgetConfigEnabled) return false;
    if (section === "readiness") return canView("knowledge");
    if (!adminConfig.rbacEnabled || adminConfig.principal?.role === "super_admin") return true;
    return Boolean(adminConfig.principal?.scopes.some((scope) => scope.section === section));
  };
  const visibleNav = nav.filter((item) => canView(item.id));
  const connectionLabel = session ? session.username : apiKey ? "Admin connected" : "Demo mode";
  const connectionDetail = session || apiKey ? "Live operational data" : "Presentation data";

  useEffect(() => {
    if (!session && !apiKey) return;
    setConfigLoading(true);
    setConfigError("");
    void new AdminApi(credentials).config()
      .then((nextConfig) => {
        setAdminConfig(nextConfig);
      })
      .catch((error) => {
        if (demoAllowed) setAdminConfig(demo.config);
        else setConfigError(error instanceof Error ? error.message : "Your administrator access could not be loaded.");
      })
      .finally(() => setConfigLoading(false));
  }, [session?.accessToken, apiKey, configAttempt]);
  useEffect(() => {
    if (visibleNav.length && !visibleNav.some((item) => item.id === view)) {
      setView(visibleNav[0].id);
    }
  }, [adminConfig, view]);

  if (!authReady) {
    return <main className="auth-page"><section className="auth-card"><div className="brand-mark"><AskVeraMark /></div><span className="eyebrow">AskVera Operations</span><h1>Signing you in</h1><p>Verifying your administrator session.</p></section></main>;
  }

  if (cognitoConfigured && !session) {
    return <main className="auth-page"><section className="auth-card">
      <div className="brand-mark"><AskVeraMark /></div><span className="eyebrow">AskVera Operations</span><h1>Operational clarity, in one place.</h1><p>Review answer quality, follow live requests, and manage approved knowledge through your company account.</p>
      {authError ? <div className="auth-error" role="alert">{authError}</div> : null}
      <button className="button primary auth-button" onClick={() => void beginSignIn()}>Sign in securely</button>
      <small>Access is limited to approved AskVera administrators.</small>
    </section></main>;
  }

  if (configLoading) {
    return <main className="auth-page"><section className="auth-card"><div className="brand-mark"><AskVeraMark /></div><span className="eyebrow">AskVera Operations</span><h1>Loading your access</h1><p>Checking your assigned markets and permissions.</p></section></main>;
  }

  if (configError) {
    return <main className="auth-page"><section className="auth-card"><div className="brand-mark"><AskVeraMark /></div><span className="eyebrow">Connection problem</span><h1>We could not load your access.</h1><p>{configError}</p><div className="modal-actions"><button className="button secondary" onClick={() => signOut()}>Sign out</button><button className="button primary" onClick={() => setConfigAttempt((value) => value + 1)}>Try again</button></div></section></main>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><AskVeraMark /></div><div><strong>AskVera</strong><span>Operations</span></div></div>
        <nav aria-label="Admin sections">{visibleNav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => navigate(item.id)}>{item.icon}<span><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}</nav>
        <div className="sidebar-bottom">
          <button className="connection-button" onClick={() => session ? signOut() : setSettingsOpen(true)}><KeyIcon /><span><strong>{connectionLabel}</strong><small>{session ? "Select to sign out" : connectionDetail}</small></span><i className={session || apiKey ? "online" : ""} /></button>
          <div className="environment"><span>Production</span><strong>Operations</strong></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="mobile-header"><div className="brand"><div className="brand-mark"><AskVeraMark /></div><strong>AskVera Operations</strong></div><button onClick={() => session ? signOut() : setSettingsOpen(true)}><KeyIcon /></button></header>
        {view === "overview" ? <OperationsOverview credentials={credentials} config={adminConfig} onNavigate={navigate} /> : null}
        {view === "flow" ? <FlowVisualizer credentials={credentials} /> : null}
        {view === "knowledge" ? <KnowledgeUploader credentials={credentials} /> : null}
        {view === "readiness" ? <MarketReadiness credentials={credentials} config={adminConfig} onNavigate={navigate} /> : null}
        {view === "insights" ? <InsightsDashboard credentials={credentials} /> : null}
        {view === "support" ? <SupportRoutesManager credentials={credentials} config={adminConfig} /> : null}
        {view === "users" ? <UsersManager credentials={credentials} config={adminConfig} /> : null}
        {view === "widget" ? <WidgetManager credentials={credentials} config={adminConfig} /> : null}
        {!visibleNav.length ? <section className="page-section"><div className="empty-state surface">Your account does not currently have access to an operations section.</div></section> : null}
        <nav className="mobile-nav" aria-label="Admin sections">{visibleNav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => navigate(item.id)}>{item.icon}<span>{item.label}</span></button>)}</nav>
      </main>

      {settingsOpen && demoAllowed ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeSettings(); }}><section ref={settingsDialogRef} className="connection-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title" tabIndex={-1}>
        <button className="drawer-close" onClick={() => setSettingsOpen(false)} aria-label="Close">x</button>
        <div className="connection-icon"><KeyIcon /></div><span className="eyebrow">Local connection</span><h2 id="connect-title">Connect operational data</h2><p>Enter the development admin key. Production uses company sign-in and never places an API key in the website bundle.</p>
        <label><span>Admin API key</span><input type="password" value={draftKey} onChange={(event) => setDraftKey(event.target.value)} placeholder="Enter admin key" autoFocus /></label>
        <div className="modal-actions"><button className="button secondary" onClick={() => { setDraftKey(""); setApiKey(""); window.sessionStorage.removeItem("askvera_admin_key"); setSettingsOpen(false); }}>Use demo data</button><button className="button primary" onClick={connect}>Connect</button></div>
      </section></div> : null}
    </div>
  );
}
