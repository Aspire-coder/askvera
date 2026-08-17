import { useEffect, useState } from "react";
import { AdminApi, demo, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import { ArrowIcon, CheckIcon, HomeIcon, RefreshIcon } from "../icons";
import type { AdminAuditEvent, AdminConfig, AnalyticsOverview, IngestionJob, OperationsStatus, View } from "../types";

type OperationsOverviewProps = {
  credentials: AdminCredentials;
  config: AdminConfig;
  onNavigate: (view: View) => void;
};

const formatNumber = (value: number) => new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export function OperationsOverview({ credentials, config, onNavigate }: OperationsOverviewProps) {
  const [overview, setOverview] = useState<AnalyticsOverview>(demo.overview);
  const [jobs, setJobs] = useState<IngestionJob[]>(demo.jobs);
  const [auditEvents, setAuditEvents] = useState<AdminAuditEvent[]>([]);
  const [operations, setOperations] = useState<OperationsStatus | null>(null);
  const [mode, setMode] = useState<DataMode>("demo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const canViewAudit = !config.rbacEnabled
    || config.principal?.role === "super_admin"
    || Boolean(config.principal?.scopes.some((scope) => scope.section === "audit"));

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const api = new AdminApi(credentials);
      const auditRequest = canViewAudit
        ? withDemoFallback(() => api.auditEvents(), [])
        : Promise.resolve({ data: [] as AdminAuditEvent[], mode: "live" as DataMode });
      const [overviewResult, jobsResult, auditResult, operationsResult] = await Promise.all([
        withDemoFallback(() => api.overview(new URLSearchParams({ days: "1" })), demo.overview),
        withDemoFallback(() => api.ingestions(), demo.jobs),
        auditRequest,
        withDemoFallback(() => api.operationsStatus(), null)
      ]);
      setOverview(overviewResult.data);
      setJobs(jobsResult.data);
      setAuditEvents(auditResult.data);
      setOperations(operationsResult.data);
      setMode(overviewResult.mode === "live" || jobsResult.mode === "live" || auditResult.mode === "live" ? "live" : "demo");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Operational data could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [credentials.accessToken, credentials.apiKey, canViewAudit]);

  const activeJobs = jobs.filter((job) => ["queued", "processing", "indexing", "staging"].includes(job.status));
  const failedJobs = jobs.filter((job) => ["failed", "error"].includes(job.status));
  const pendingJobs = jobs.filter((job) => ["queued", "processing", "indexing", "staging"].includes(job.status));
  const recentAudit = auditEvents.slice(0, 4);
  const coverageCount = config.countries.length;
  const widgetCoverageCount = config.widgetCountries?.length ?? coverageCount;
  const checks = [
    { label: "Review low-rated answers", detail: `${overview.totals.notHelpful} answers need attention`, view: "insights" as const, done: overview.totals.notHelpful === 0 },
    { label: "Check knowledge processing", detail: pendingJobs.length ? `${pendingJobs.length} document job${pendingJobs.length === 1 ? "" : "s"} in progress` : "No documents are processing", view: "knowledge" as const, done: pendingJobs.length === 0 },
    { label: "Confirm support routing", detail: "Market destinations are managed centrally", view: "support" as const, done: true }
  ];

  return <section className="page-section overview-page">
    <div className="page-heading">
      <div><span className="eyebrow">Operations command center</span><h1>Know what needs attention.</h1><p>A simple starting point for answer quality, approved knowledge, customer support, and widget operations.</p></div>
      <div className="heading-actions"><span className={`mode-pill ${mode}`}><span />{mode === "live" ? "Live data" : "Demo data"}</span><button className="button secondary" onClick={() => void load()} disabled={loading}><RefreshIcon />{loading ? "Refreshing" : "Refresh"}</button></div>
    </div>
    {error ? <div className="notice error" role="alert">{error}</div> : null}
    <div className="overview-metrics">
      <article className="overview-metric surface"><span>Questions today</span><strong>{formatNumber(overview.totals.questions)}</strong><small>{formatNumber(overview.totals.users)} unique users</small></article>
      <article className="overview-metric surface"><span>Live sessions</span><strong>{formatNumber(overview.totals.liveSessions)}</strong><small>Consent given and not expired</small></article>
      <article className="overview-metric surface"><span>Helpful answers</span><strong>{Math.round(overview.totals.helpfulRate * 100)}%</strong><small>{formatNumber(overview.totals.helpful + overview.totals.notHelpful)} ratings recorded</small></article>
      <article className="overview-metric surface"><span>Knowledge jobs</span><strong>{activeJobs.length}</strong><small>{failedJobs.length ? `${failedJobs.length} failed job${failedJobs.length === 1 ? "" : "s"} to review` : "No failed jobs"}</small></article>
    </div>
    <section className="surface operations-health" aria-labelledby="operations-health-title">
      <div className="section-heading"><div><span className="eyebrow">Production status</span><h2 id="operations-health-title">Service health and deployed versions</h2><p>Live dependency checks, knowledge synchronization and versions reported by the API.</p></div><span className={`status-label ${operations?.status || "unknown"}`}>{operations?.status || "Unavailable"}</span></div>
      {operations ? <>
        <div className="health-service-grid">{Object.entries(operations.services).map(([name, service]) => <article key={name}><span className={`attention-dot ${service.status === "healthy" || service.status === "configured" ? "good" : "warning"}`} /><div><strong>{name.replaceAll("_", " ")}</strong><small>{service.detail}</small></div><em>{service.status.replaceAll("_", " ")}</em></article>)}</div>
        <div className="operations-detail-grid">
          <div><span>Document synchronization</span><strong>{operations.knowledge_sync.status}</strong><small>{operations.knowledge_sync.active_jobs} active · {operations.knowledge_sync.failed_jobs} failed · {operations.knowledge_sync.expiring_documents} expiring{operations.knowledge_sync.last_change_at ? ` · changed ${new Date(operations.knowledge_sync.last_change_at).toLocaleString()}` : ""}</small></div>
          <div><span>Application</span><strong>{operations.versions.application}</strong><small>Knowledge {operations.versions.knowledge}</small></div>
          <div><span>Retrieval pipeline</span><strong>{operations.versions.retrieval_pipeline}</strong><small>Response {operations.versions.response_pipeline}</small></div>
          <div><span>Operational quality</span><strong>{Math.round(operations.metrics.retrieval_failure_rate * 100)}% retrieval failures</strong><small>{operations.metrics.validation_failures} validation failures · {operations.metrics.audit_queue_depth} audit events queued</small></div>
        </div>
      </> : <div className="empty-state compact">Operational status is unavailable.</div>}
      {operations?.assigned_actions.length ? <div className="assigned-actions"><h3>Assigned actions</h3>{operations.assigned_actions.map((action, index) => <div key={`${action.label}-${index}`}><strong>{action.label}</strong><span>{action.reason}</span><em>{action.owner}</em></div>)}</div> : null}
    </section>
    <div className="overview-grid">
      <section className="surface overview-panel"><div className="section-heading"><div><h2>Start here</h2><p>The three checks that keep the service healthy.</p></div><HomeIcon /></div><div className="overview-checklist">{checks.map((check) => <button key={check.label} onClick={() => onNavigate(check.view)}><span className={`check-icon ${check.done ? "done" : ""}`}>{check.done ? <CheckIcon /> : <span />}</span><span><strong>{check.label}</strong><small>{check.detail}</small></span><ArrowIcon /></button>)}</div></section>
      <section className="surface overview-panel"><div className="section-heading"><div><h2>Quick actions</h2><p>Jump directly to the task you need.</p></div></div><div className="quick-actions"><button onClick={() => onNavigate("knowledge")}><strong>Upload knowledge</strong><span>Add a policy or global directory document.</span><ArrowIcon /></button><button onClick={() => onNavigate("insights")}><strong>Review answers</strong><span>Inspect feedback, confidence, and retrieval signals.</span><ArrowIcon /></button><button onClick={() => onNavigate("support")}><strong>Manage support</strong><span>Update where customer requests are delivered.</span><ArrowIcon /></button><button onClick={() => onNavigate("widget")}><strong>Manage widgets</strong><span>Configure approved websites and embed code.</span><ArrowIcon /></button></div></section>
    </div>
    <div className="overview-grid overview-secondary-grid">
      <section className="surface overview-panel"><div className="section-heading"><div><span className="eyebrow">Operational signal</span><h2>What needs attention</h2><p>These signals are based on the current selected range.</p></div></div><div className="attention-list">
        <button onClick={() => onNavigate("insights")}><span className={`attention-dot ${overview.totals.notHelpful ? "warning" : "good"}`} /><span><strong>{overview.totals.notHelpful ? `${overview.totals.notHelpful} low-rated answers` : "No low-rated answers"}</strong><small>{overview.totals.notHelpful ? "Open Answer review to inspect them." : "Feedback is not waiting for review."}</small></span><ArrowIcon /></button>
        <button onClick={() => onNavigate("knowledge")}><span className={`attention-dot ${failedJobs.length ? "warning" : "good"}`} /><span><strong>{failedJobs.length ? `${failedJobs.length} failed knowledge jobs` : "Knowledge processing is healthy"}</strong><small>{failedJobs.length ? "Open Knowledge to see the error details." : "No failed jobs in the latest activity window."}</small></span><ArrowIcon /></button>
        <button onClick={() => onNavigate("users")}><span className="attention-dot neutral" /><span><strong>Access is centrally managed</strong><small>Review administrators and audit history in Users.</small></span><ArrowIcon /></button>
      </div></section>
      <section className="surface overview-panel"><div className="section-heading"><div><span className="eyebrow">Change history</span><h2>Recent admin activity</h2><p>Read-only visibility into configuration changes.</p></div></div><div className="activity-list">
        {recentAudit.map((event) => <div className="activity-row" key={event.event_id}><span className="activity-mark" /><span><strong>{event.action.replaceAll(".", " ")}</strong><small>{event.target_type} / {event.target_id}</small></span><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></div>)}
        {!recentAudit.length ? <div className="empty-state compact">No recent administrator changes are available.</div> : null}
      </div></section>
    </div>
    <section className="surface readiness-panel"><div><span className="eyebrow">Coverage and readiness</span><h2>One place to see what is connected.</h2><p>Markets and widget coverage are configured separately. This keeps a new market from appearing in a customer widget before its approved content and support destination are ready.</p></div><div className="readiness-grid"><div><strong>{coverageCount}</strong><span>approved markets</span></div><div><strong>{widgetCoverageCount}</strong><span>widget markets</span></div><div><strong>{config.documentTypes.length}</strong><span>content types</span></div><div><strong>{config.rbacEnabled ? "On" : "Off"}</strong><span>role-based access</span></div></div></section>
    <section className="surface overview-footer"><div><span className="eyebrow">Configured coverage</span><h2>{config.countries.length} approved markets available</h2><p>Keep market policy coverage, global directory content, and support routing aligned from the sections in the left navigation.</p></div><button className="button primary" onClick={() => onNavigate("flow")}>Follow a live answer <ArrowIcon /></button></section>
  </section>;
}
