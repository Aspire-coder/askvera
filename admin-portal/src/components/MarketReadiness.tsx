import { useEffect, useMemo, useState } from "react";
import { AdminApi, withDemoFallback, type AdminCredentials } from "../api";
import type { AdminConfig, MarketReadiness, ReadinessCheckStatus } from "../types";

type Props = { credentials: AdminCredentials; config: AdminConfig };
type Filter = "all" | ReadinessCheckStatus;

function demoReadiness(config: AdminConfig): MarketReadiness {
  return {
    checked_at: new Date().toISOString(),
    summary: {
      total: config.countries.length,
      ready: 0,
      needs_review: config.countries.length,
      not_configured: 0,
    },
    markets: config.countries.map((market) => ({
      code: market.code,
      name: market.name,
      overall: "warning",
      languages: market.languages.map((language) => ({
        ...language,
        policy_published: false,
      })),
      checks: [
        {
          key: "market_config",
          label: "Market configuration",
          status: "pass",
          detail: "Market data is available in this demo.",
        },
        {
          key: "policy_locales",
          label: "Policy locales",
          status: "not_configured",
          detail: "Connect live data to verify published policy coverage.",
        },
        {
          key: "legal",
          label: "Legal version",
          status: "pass",
          detail: "Consent configuration is represented by demo data.",
        },
        {
          key: "support",
          label: "Support routing",
          status: "not_configured",
          detail: "Connect live data to verify the handoff route.",
        },
        {
          key: "widget",
          label: "Widget coverage",
          status: "not_configured",
          detail: "Connect live data to verify active widgets.",
        },
        {
          key: "retrieval",
          label: "Retrieval validation",
          status: "not_verified",
          detail: "Run the market evaluation before production use.",
        },
      ],
    })),
  };
}

function statusLabel(status: ReadinessCheckStatus) {
  return {
    pass: "Ready",
    warning: "Needs review",
    not_configured: "Not configured",
    not_verified: "Not verified",
  }[status];
}

export function MarketReadiness({ credentials, config }: Props) {
  const [data, setData] = useState<MarketReadiness>(() => demoReadiness(config));
  const [mode, setMode] = useState<"live" | "demo">("demo");
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    void withDemoFallback(
      () => new AdminApi(credentials).marketReadiness(),
      demoReadiness(config),
    )
      .then((result) => {
        setData(result.data);
        setMode(result.mode);
      })
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to load market readiness.",
        ),
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [credentials.accessToken, credentials.apiKey]);

  const markets = useMemo(() => data.markets.filter((market) => {
    const matchesFilter = filter === "all"
      || market.overall === filter
      || market.checks.some((check) => check.status === filter);
    const needle = query.trim().toLowerCase();
    return matchesFilter && (!needle || `${market.code} ${market.name}`.toLowerCase().includes(needle));
  }), [data.markets, filter, query]);

  return (
    <section className="page-section">
    <div className="page-heading">
      <div>
        <span className="eyebrow">Market onboarding</span>
        <h1>Market readiness</h1>
        <p>Check each market before enabling its documents, support route, or widget.</p>
      </div>
      <button className="button secondary" onClick={load} disabled={loading}>
        {loading ? "Checking..." : "Refresh checks"}
      </button>
    </div>
    {error ? <div className="admin-toast error" role="alert">{error}</div> : null}
    <div className="readiness-summary">
      <div className="readiness-summary-card">
        <small>Total markets</small><strong>{data.summary.total}</strong>
        <span>Enabled in configuration</span>
      </div>
      <div className="readiness-summary-card">
        <small>Ready</small><strong>{data.summary.ready}</strong>
        <span>Required setup complete</span>
      </div>
      <div className="readiness-summary-card">
        <small>Needs review</small><strong>{data.summary.needs_review}</strong>
        <span>Configuration needs attention</span>
      </div>
      <div className="readiness-summary-card">
        <small>Not configured</small><strong>{data.summary.not_configured}</strong>
        <span>Not ready for use</span>
      </div>
    </div>
    <div className="readiness-toolbar surface">
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search market" aria-label="Search market" />
      <select value={filter} onChange={(event) => setFilter(event.target.value as Filter)} aria-label="Filter readiness">
        <option value="all">All statuses</option><option value="pass">Ready</option><option value="warning">Needs review</option><option value="not_configured">Not configured</option><option value="not_verified">Not verified</option>
      </select>
      <span className="mode-note">
        {mode === "live"
          ? `Live check - ${new Date(data.checked_at).toLocaleString()}`
          : "Demo data - connect live operational data to verify"}
      </span>
    </div>
    <div className="readiness-list">
      {markets.map((market) => (
        <article className="readiness-market surface" key={market.code}>
          <div className="readiness-market-header">
            <div><span className="eyebrow">{market.code}</span><h2>{market.name}</h2></div>
            <span className={`readiness-status ${market.overall}`}>
              {statusLabel(market.overall)}
            </span>
          </div>
          <div className="readiness-language-list">
            <strong>Languages</strong>
            {market.languages.map((language) => (
              <span
                className={`readiness-language ${language.policy_published ? "published" : "missing"}`}
                key={language.code}
              >
                {language.name} {language.policy_published ? "- policy ready" : "- policy missing"}
              </span>
            ))}
          </div>
          <div className="readiness-check-grid">
            {market.checks.map((check) => (
              <div className="readiness-check" key={check.key}>
                <div className="readiness-check-head">
                  <strong>{check.label}</strong>
                  <span className={`readiness-status ${check.status}`}>
                    {statusLabel(check.status)}
                  </span>
                </div>
                <p>{check.detail}</p>
              </div>
            ))}
          </div>
        </article>
      ))}
      {!markets.length ? <div className="empty-state surface">No markets match this filter.</div> : null}
    </div>
    </section>
  );
}
