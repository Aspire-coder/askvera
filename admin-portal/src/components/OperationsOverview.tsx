import { useEffect, useState } from "react";
import { AdminApi, demo, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import { ArrowIcon, RefreshIcon } from "../icons";
import type { AdminAuditEvent, AdminConfig, AnalyticsOverview, CacheResetResult, IngestionJob, ModelRoutingReport, OperationsStatus, RetrievalProfileStatus, View } from "../types";
import { useDialogFocus } from "../useDialogFocus";

type OperationsOverviewProps = {
  credentials: AdminCredentials;
  config: AdminConfig;
  onNavigate: (view: View) => void;
};

const formatNumber = (value: number) => new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
const modelName = (value: string) => {
  const normalized = value.toLowerCase();
  if (normalized.includes("haiku-4-5")) return "Claude Haiku 4.5";
  if (normalized.includes("sonnet-5")) return "Claude Sonnet 5";
  return value || "Not configured";
};

export function OperationsOverview({ credentials, config, onNavigate }: OperationsOverviewProps) {
  const [overview, setOverview] = useState<AnalyticsOverview>(demo.overview);
  const [routing, setRouting] = useState<ModelRoutingReport>(demo.modelRouting);
  const [routingDays, setRoutingDays] = useState("7");
  const [routingCountry, setRoutingCountry] = useState("");
  const [jobs, setJobs] = useState<IngestionJob[]>(demo.jobs);
  const [auditEvents, setAuditEvents] = useState<AdminAuditEvent[]>([]);
  const [operations, setOperations] = useState<OperationsStatus | null>(null);
  const [retrievalProfile, setRetrievalProfile] = useState<RetrievalProfileStatus | null>(null);
  const [mode, setMode] = useState<DataMode>("demo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cacheDialogOpen, setCacheDialogOpen] = useState(false);
  const [cacheCountry, setCacheCountry] = useState(config.widgetCountries?.[0]?.code || config.countries[0]?.code || "");
  const [cacheMode, setCacheMode] = useState<"exact" | "exact_and_semantic">("exact_and_semantic");
  const [cacheReason, setCacheReason] = useState("");
  const [cacheConfirmation, setCacheConfirmation] = useState("");
  const [cacheResetting, setCacheResetting] = useState(false);
  const [cacheError, setCacheError] = useState("");
  const [cacheResult, setCacheResult] = useState<CacheResetResult | null>(null);
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);
  const [profileMode, setProfileMode] = useState<"current" | "shadow">("current");
  const [profileSampleRate, setProfileSampleRate] = useState("0.1");
  const [profileReason, setProfileReason] = useState("");
  const [profileConfirmation, setProfileConfirmation] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");

  const closeCacheDialog = () => { if (!cacheResetting) setCacheDialogOpen(false); };
  const cacheDialogRef = useDialogFocus<HTMLElement>(cacheDialogOpen, closeCacheDialog);
  const closeProfileDialog = () => { if (!profileSaving) setProfileDialogOpen(false); };
  const profileDialogRef = useDialogFocus<HTMLElement>(profileDialogOpen, closeProfileDialog);

  const canViewAudit = !config.rbacEnabled
    || config.principal?.role === "super_admin"
    || Boolean(config.principal?.scopes.some((scope) => scope.section === "audit"));
  const canResetCache = config.principal?.role === "super_admin";
  const requiredConfirmation = `RESET ${cacheCountry}`;
  const profileRequiredConfirmation = profileMode === "shadow" ? "ENABLE SHADOW" : "USE CURRENT";

  const openProfileDialog = () => {
    const selectedMode = retrievalProfile?.control.mode || "current";
    setProfileMode(selectedMode);
    setProfileSampleRate(String(retrievalProfile?.control.sample_rate || 0.1));
    setProfileReason("");
    setProfileConfirmation("");
    setProfileError("");
    setProfileDialogOpen(true);
  };

  const saveRetrievalProfile = async () => {
    setProfileSaving(true);
    setProfileError("");
    try {
      const result = await new AdminApi(credentials).updateRetrievalProfile({
        mode: profileMode,
        sample_rate: profileMode === "shadow" ? Number(profileSampleRate) : 0,
        reason: profileReason.trim(),
        confirmation: profileConfirmation.trim()
      });
      setRetrievalProfile(result);
      setProfileDialogOpen(false);
      await load();
    } catch (saveError) {
      setProfileError(saveError instanceof Error ? saveError.message : "The retrieval profile could not be updated.");
    } finally {
      setProfileSaving(false);
    }
  };

  const resetCache = async () => {
    setCacheResetting(true);
    setCacheError("");
    try {
      const result = await new AdminApi(credentials).resetAnswerCache({
        country: cacheCountry,
        mode: cacheMode,
        reason: cacheReason.trim(),
        confirmation: cacheConfirmation.trim()
      });
      setCacheResult(result);
      setCacheDialogOpen(false);
      setCacheReason("");
      setCacheConfirmation("");
      await load();
    } catch (resetError) {
      setCacheError(resetError instanceof Error ? resetError.message : "The answer cache could not be reset.");
    } finally {
      setCacheResetting(false);
    }
  };

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const api = new AdminApi(credentials);
      const auditRequest = canViewAudit
        ? withDemoFallback(() => api.auditEvents(), [])
        : Promise.resolve({ data: [] as AdminAuditEvent[], mode: "live" as DataMode });
      const routingFilters = new URLSearchParams({ days: routingDays });
      if (routingCountry) routingFilters.set("country", routingCountry);
      const [overviewResult, routingResult, jobsResult, auditResult, operationsResult, retrievalProfileResult] = await Promise.all([
        withDemoFallback(() => api.overview(new URLSearchParams({ days: "1" })), demo.overview),
        withDemoFallback(() => api.modelRouting(routingFilters), demo.modelRouting),
        withDemoFallback(() => api.ingestions(), demo.jobs),
        auditRequest,
        withDemoFallback(() => api.operationsStatus(), null),
        api.retrievalProfile()
      ]);
      setOverview(overviewResult.data);
      setRouting(routingResult.data);
      setJobs(jobsResult.data);
      setAuditEvents(auditResult.data);
      setOperations(operationsResult.data);
      setRetrievalProfile(retrievalProfileResult);
      setMode(overviewResult.mode === "live" || routingResult.mode === "live" || jobsResult.mode === "live" || auditResult.mode === "live" ? "live" : "demo");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Operational data could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [credentials.accessToken, credentials.apiKey, canViewAudit, routingDays, routingCountry]);

  const activeJobs = jobs.filter((job) => ["queued", "processing", "indexing", "staging"].includes(job.status));
  const failedJobs = jobs.filter((job) => ["failed", "error"].includes(job.status));
  const recentAudit = auditEvents.slice(0, 4);
  const routingModeLabel = routing.mode === "shadow" ? "Shadow observation" : routing.mode === "live" ? "Live routing" : "Routing off";
  const actualModel = modelName(routing.actualModels[0]?.label || routing.models.primary);
  const fastPercent = Math.round(routing.totals.fastShare * 100);
  const projectedDelta = routing.cost.projectedDeltaUsd;

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
    <section className="surface routing-dashboard" aria-labelledby="routing-dashboard-title">
      <div className="section-heading routing-heading">
        <div><span className="eyebrow">Model routing</span><h2 id="routing-dashboard-title">Measure where Sonnet adds value.</h2><p>Haiku serves customers today. Shadow routing identifies answers that may benefit from Sonnet.</p></div>
        <div className="routing-filters">
          <label><span>Market</span><select value={routingCountry} onChange={(event) => setRoutingCountry(event.target.value)}><option value="">All markets</option>{config.countries.map((market) => <option key={market.code} value={market.code}>{market.name} ({market.code})</option>)}</select></label>
          <label><span>Period</span><select value={routingDays} onChange={(event) => setRoutingDays(event.target.value)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label>
        </div>
      </div>
      <div className={`routing-mode-banner ${routing.mode}`}><strong>{routingModeLabel}</strong><span>{routing.mode === "shadow" ? `${modelName(routing.models.primary)} is serving customer answers now. Shadow mode only measures which complex answers would move to Sonnet.` : routing.mode === "live" ? "Customer answers are being routed between Haiku and Sonnet." : `${modelName(routing.models.primary)} is serving customer answers without dynamic routing.`}</span></div>
      <div className="routing-metrics">
        <article><span>Fresh answers evaluated</span><strong>{formatNumber(routing.totals.evaluated)}</strong><small>{formatNumber(routing.totals.cached)} cache hits skipped model generation</small></article>
        <article><span>Remain on Haiku</span><strong>{fastPercent}%</strong><small>{formatNumber(routing.totals.proposedFast)} lower-complexity answers</small></article>
        <article><span>Would move to Sonnet</span><strong>{formatNumber(routing.totals.proposedComplex)}</strong><small>Complex or higher-risk answers in live mode</small></article>
        <article><span>Projected cost change</span><strong>{projectedDelta >= 0 ? "+" : "−"}${Math.abs(projectedDelta).toFixed(2)}</strong><small>{projectedDelta >= 0 ? "Additional cost for Sonnet-protected answers" : "Lower cost than the current model baseline"}</small></article>
      </div>
      <div className="routing-detail-grid">
        <div className="routing-split-panel"><div className="routing-split-label"><strong>Proposed answer split</strong><span>{routing.totals.evaluated ? `${fastPercent}% Haiku · ${100 - fastPercent}% Sonnet` : "Waiting for fresh answers"}</span></div><div className="routing-split" role="img" aria-label={`${fastPercent}% Haiku eligible and ${100 - fastPercent}% Sonnet protected`}><span style={{ width: `${fastPercent}%` }} /></div><small>Average generation time: {routing.totals.averageGenerationLatencyMs ? `${Math.round(routing.totals.averageGenerationLatencyMs).toLocaleString()} ms` : "not available"}</small></div>
        <div className="routing-reasons"><strong>Why Sonnet or Haiku was chosen</strong>{routing.reasons.length ? routing.reasons.slice(0, 4).map((reason) => <div key={reason.label}><span>{reason.label.replaceAll("_", " ")}</span><em>{formatNumber(reason.value)}</em></div>) : <small>No routing reasons recorded yet.</small>}</div>
        <div className="routing-actual"><strong>Actual production model</strong><span>{actualModel}</span><small>{routing.mode === "shadow" ? "All shadow recommendations leave the current production model unchanged." : "Based on generated answers in this period."}</small><button className="text-button" onClick={() => onNavigate("flow")}>Inspect individual answers <ArrowIcon /></button></div>
      </div>
      <p className="routing-pricing-note">Projection only · {routing.cost.pricingLabel}. Current {modelName(routing.models.primary)} cost ${routing.cost.currentUsd.toFixed(2)} → proposed routed cost ${routing.cost.projectedUsd.toFixed(2)}.</p>
    </section>
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
      {retrievalProfile ? <div className="retrieval-profile-panel">
        <div className="retrieval-profile-heading"><div><strong>Retrieval comparison control</strong><span>Customer answers always use Current. Shadow evaluates the isolated candidate in the background and records comparison metrics only.</span></div><span className={`status-label ${retrievalProfile.control.mode === "shadow" ? "configured" : "healthy"}`}>{retrievalProfile.control.mode === "shadow" ? `Shadow ${Math.round(retrievalProfile.control.sample_rate * 100)}%` : "Current only"}</span></div>
        <div className="retrieval-profile-grid">
          <div><span>Customer serving</span><strong>Current</strong><small>{retrievalProfile.primary.pipeline_version}</small></div>
          <div><span>Candidate readiness</span><strong>{retrievalProfile.candidate.ready ? "Ready" : "Not ready"}</strong><small>{retrievalProfile.candidate.ready ? retrievalProfile.candidate.pipeline_version : retrievalProfile.candidate.readiness_error}</small></div>
          <div><span>Current index</span><strong>{retrievalProfile.primary.index || "Not configured"}</strong><small>Chunk profile: {retrievalProfile.primary.chunk_profile}</small></div>
          <div><span>Candidate index</span><strong>{retrievalProfile.candidate.index || "Not configured"}</strong><small>Chunk profile: {retrievalProfile.candidate.chunk_profile}</small></div>
        </div>
        <div className="retrieval-profile-footer"><span>This control does not reparse, rechunk, publish or delete documents.</span>{canResetCache ? <button className="button secondary" onClick={openProfileDialog}>Change comparison mode</button> : null}</div>
      </div> : null}
      {canResetCache ? <div className="cache-control-panel">
        <div><strong>Answer cache controls</strong><span>Clear stale generated answers for one market or all markets. Login, security, rate limits, widget settings and session data are never affected.</span></div>
        <button className="button danger" onClick={() => { setCacheError(""); setCacheDialogOpen(true); }}>Reset answer cache</button>
      </div> : null}
      {cacheResult ? <div className="notice cache-result" role="status"><strong>Cache reset completed.</strong> Removed {cacheResult.total_deleted} answer cache {cacheResult.total_deleted === 1 ? "entry" : "entries"} for {cacheResult.country === "ALL" ? "all markets" : cacheResult.country} ({cacheResult.exact_deleted} exact, {cacheResult.semantic_deleted} semantic) at {new Date(cacheResult.completed_at).toLocaleString()}.</div> : null}
    </section>
    <div className="overview-grid">
      <section className="surface overview-panel"><div className="section-heading"><div><h2>Quick actions</h2><p>Jump directly to the task you need.</p></div></div><div className="quick-actions"><button onClick={() => onNavigate("knowledge")}><strong>Upload knowledge</strong><span>Add a policy or global directory document.</span><ArrowIcon /></button><button onClick={() => onNavigate("insights")}><strong>Review answers</strong><span>Inspect feedback, confidence, and retrieval signals.</span><ArrowIcon /></button><button onClick={() => onNavigate("support")}><strong>Manage support</strong><span>Update where customer requests are delivered.</span><ArrowIcon /></button><button onClick={() => onNavigate("widget")}><strong>Manage widgets</strong><span>Configure approved websites and embed code.</span><ArrowIcon /></button></div></section>
      <section className="surface overview-panel"><div className="section-heading"><div><span className="eyebrow">Operational signal</span><h2>What needs attention</h2><p>These signals are based on the current selected range.</p></div></div><div className="attention-list">
        <button onClick={() => onNavigate("insights")}><span className={`attention-dot ${overview.totals.notHelpful ? "warning" : "good"}`} /><span><strong>{overview.totals.notHelpful ? `${overview.totals.notHelpful} low-rated answers` : "No low-rated answers"}</strong><small>{overview.totals.notHelpful ? "Open Answer review to inspect them." : "Feedback is not waiting for review."}</small></span><ArrowIcon /></button>
        <button onClick={() => onNavigate("knowledge")}><span className={`attention-dot ${failedJobs.length ? "warning" : "good"}`} /><span><strong>{failedJobs.length ? `${failedJobs.length} failed knowledge jobs` : "Knowledge processing is healthy"}</strong><small>{failedJobs.length ? "Open Knowledge to see the error details." : "No failed jobs in the latest activity window."}</small></span><ArrowIcon /></button>
        <button onClick={() => onNavigate("users")}><span className="attention-dot neutral" /><span><strong>Access is centrally managed</strong><small>Review administrators and audit history in Users.</small></span><ArrowIcon /></button>
      </div></section>
    </div>
    <section className="surface overview-panel overview-activity"><div className="section-heading"><div><span className="eyebrow">Change history</span><h2>Recent admin activity</h2><p>Read-only visibility into configuration changes.</p></div></div><div className="activity-list">
        {recentAudit.map((event) => <div className="activity-row" key={event.event_id}><span className="activity-mark" /><span><strong>{event.action.replaceAll(".", " ")}</strong><small>{event.target_type} / {event.target_id}</small></span><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></div>)}
        {!recentAudit.length ? <div className="empty-state compact">No recent administrator changes are available.</div> : null}
      </div></section>
    {cacheDialogOpen ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeCacheDialog(); }}>
      <section ref={cacheDialogRef} className="connection-modal cache-reset-modal" role="dialog" aria-modal="true" aria-labelledby="cache-reset-title" tabIndex={-1}>
        <span className="eyebrow">Super Admin only</span>
        <h2 id="cache-reset-title">Reset answer cache</h2>
        <p>Use this after a policy or retrieval correction when an older generated answer may still be cached. New questions will rebuild fresh answers automatically.</p>
        <div className="cache-reset-fields">
          <label><span>Scope</span><select value={cacheCountry} onChange={(event) => { setCacheCountry(event.target.value); setCacheConfirmation(""); }} autoFocus>
            {(config.widgetCountries?.length ? config.widgetCountries : config.countries).map((market) => <option key={market.code} value={market.code}>{market.name} ({market.code})</option>)}
            <option value="ALL">All markets</option>
          </select></label>
          <label><span>Cache type</span><select value={cacheMode} onChange={(event) => setCacheMode(event.target.value as "exact" | "exact_and_semantic")}>
            <option value="exact_and_semantic">Exact and semantic answers</option>
            <option value="exact">Exact answers only</option>
          </select></label>
          <label><span>Reason</span><textarea value={cacheReason} onChange={(event) => setCacheReason(event.target.value)} maxLength={500} placeholder="Explain why cached answers must be refreshed" /></label>
          <label><span>Confirmation</span><input value={cacheConfirmation} onChange={(event) => setCacheConfirmation(event.target.value)} placeholder={requiredConfirmation} autoComplete="off" /><small>Type <strong>{requiredConfirmation}</strong> exactly.</small></label>
        </div>
        {cacheError ? <div className="notice error" role="alert">{cacheError}</div> : null}
        <div className="modal-actions"><button className="button secondary" onClick={closeCacheDialog} disabled={cacheResetting}>Cancel</button><button className="button danger" onClick={() => void resetCache()} disabled={cacheResetting || cacheReason.trim().length < 8 || cacheConfirmation.trim().toUpperCase() !== requiredConfirmation}>{cacheResetting ? "Resetting" : "Reset answer cache"}</button></div>
        <small>This action does not delete documents or change the Bedrock knowledge index. It only removes generated answer entries from Redis/Valkey.</small>
      </section>
    </div> : null}
    {profileDialogOpen ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeProfileDialog(); }}>
      <section ref={profileDialogRef} className="connection-modal retrieval-profile-modal" role="dialog" aria-modal="true" aria-labelledby="retrieval-profile-title" tabIndex={-1}>
        <span className="eyebrow">Super Admin only</span>
        <h2 id="retrieval-profile-title">Retrieval comparison mode</h2>
        <p>Current always serves customers. Shadow sends a sampled copy to the isolated candidate and stores only comparison telemetry.</p>
        <div className="cache-reset-fields">
          <label><span>Mode</span><select value={profileMode} onChange={(event) => { setProfileMode(event.target.value as "current" | "shadow"); setProfileConfirmation(""); }} autoFocus><option value="current">Current only</option><option value="shadow" disabled={!retrievalProfile?.candidate.ready}>Shadow comparison</option></select></label>
          {profileMode === "shadow" ? <label><span>Traffic sample</span><select value={profileSampleRate} onChange={(event) => setProfileSampleRate(event.target.value)}><option value="0.05">5%</option><option value="0.1">10%</option><option value="0.25">25%</option><option value="1">100%</option></select></label> : null}
          <label><span>Reason</span><textarea value={profileReason} onChange={(event) => setProfileReason(event.target.value)} maxLength={500} placeholder="Explain why this comparison mode is changing" /></label>
          <label><span>Confirmation</span><input value={profileConfirmation} onChange={(event) => setProfileConfirmation(event.target.value)} placeholder={profileRequiredConfirmation} autoComplete="off" /><small>Type <strong>{profileRequiredConfirmation}</strong> exactly.</small></label>
        </div>
        {profileMode === "shadow" && !retrievalProfile?.candidate.ready ? <div className="notice error" role="alert">{retrievalProfile?.candidate.readiness_error || "The isolated candidate is not ready."}</div> : null}
        {profileError ? <div className="notice error" role="alert">{profileError}</div> : null}
        <div className="modal-actions"><button className="button secondary" onClick={closeProfileDialog} disabled={profileSaving}>Cancel</button><button className="button" onClick={() => void saveRetrievalProfile()} disabled={profileSaving || profileReason.trim().length < 8 || profileConfirmation.trim().toUpperCase() !== profileRequiredConfirmation || (profileMode === "shadow" && !retrievalProfile?.candidate.ready)}>{profileSaving ? "Saving" : "Apply mode"}</button></div>
        <small>No candidate answer is returned to a customer in Shadow mode. Live candidate serving is intentionally unavailable.</small>
      </section>
    </div> : null}
  </section>;
}
