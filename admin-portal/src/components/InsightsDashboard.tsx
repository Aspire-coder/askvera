import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { AdminApi, demo, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import { ArrowIcon, SearchIcon } from "../icons";
import type { AnalyticsOverview, Interaction, InteractionPage, Market, ShadowReport } from "../types";
import { useDialogFocus } from "../useDialogFocus";
import "../tokenSplit.css";

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const percent = (value: number) => `${Math.round(value * 100)}%`;
const dateLabel = (value: string) => new Date(value).toLocaleDateString([], { month: "short", day: "numeric" });
const interactionDateLabel = (value: string) => new Date(value).toLocaleString([], {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit"
});
const demoInteractionPage: InteractionPage = {
  items: demo.interactions,
  total: demo.interactions.length,
  page: 1,
  pageSize: 50,
  totalPages: 1
};

function TrendChart({ overview }: { overview: AnalyticsOverview }) {
  const data = overview.trend;
  const width = 760;
  const height = 250;
  const inset = { top: 22, right: 24, bottom: 34, left: 36 };
  const max = Math.max(...data.map((point) => point.questions), 1);
  const x = (index: number) => inset.left + (index / Math.max(data.length - 1, 1)) * (width - inset.left - inset.right);
  const y = (value: number) => height - inset.bottom - (value / max) * (height - inset.top - inset.bottom);
  const line = data.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.questions).toFixed(1)}`).join(" ");
  const area = data.length ? `${line} L${x(data.length - 1)},${height - inset.bottom} L${x(0)},${height - inset.bottom} Z` : "";
  const tickIndexes = data.length <= 4 ? data.map((_, index) => index) : [0, Math.floor((data.length - 1) / 2), data.length - 1];
  return (
    <svg className="trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily question volume">
      <defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="currentColor" stopOpacity=".18"/><stop offset="1" stopColor="currentColor" stopOpacity=".01"/></linearGradient></defs>
      {[0, .5, 1].map((ratio) => <g key={ratio}><line x1={inset.left} x2={width - inset.right} y1={y(max * ratio)} y2={y(max * ratio)} className="grid-line"/><text x={inset.left - 10} y={y(max * ratio) + 4} textAnchor="end">{Math.round(max * ratio)}</text></g>)}
      {area ? <path d={area} fill="url(#area-fill)" /> : null}
      {line ? <path d={line} className="trend-line" /> : null}
      {data.map((point, index) => <circle key={point.date} cx={x(index)} cy={y(point.questions)} r="4" className="trend-point"><title>{dateLabel(point.date)}: {point.questions} questions</title></circle>)}
      {tickIndexes.map((index) => data[index] ? <text key={index} x={x(index)} y={height - 10} textAnchor="middle">{dateLabel(data[index].date)}</text> : null)}
    </svg>
  );
}

function RankedBars({ data }: { data: Array<{ label: string; value: number }> }) {
  const max = Math.max(...data.map((item) => Number(item.value)), 1);
  return <div className="ranked-bars">{data.map((item) => <div className="ranked-row" key={item.label}><div><span>{item.label}</span><strong>{compact.format(Number(item.value))}</strong></div><div className="bar-track"><i style={{ width: `${Number(item.value) / max * 100}%` }} /></div></div>)}</div>;
}

export function InsightsDashboard({ credentials }: { credentials: AdminCredentials }) {
  const [overview, setOverview] = useState<AnalyticsOverview>(demo.overview);
  const [shadowReport, setShadowReport] = useState<ShadowReport>(demo.shadowReport);
  const [interactions, setInteractions] = useState<Interaction[]>(demo.interactions);
  const [interactionTotal, setInteractionTotal] = useState(demo.interactions.length);
  const [interactionTotalPages, setInteractionTotalPages] = useState(1);
  const [markets, setMarkets] = useState<Market[]>(demo.config.countries);
  const [mode, setMode] = useState<DataMode>("demo");
  const [days, setDays] = useState("30");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [country, setCountry] = useState("");
  const [language, setLanguage] = useState("");
  const [trafficSource, setTrafficSource] = useState("");
  const [feedback, setFeedback] = useState("all");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [reviewPage, setReviewPage] = useState(1);
  const [reviewPageSize, setReviewPageSize] = useState("50");
  const [reviewSort, setReviewSort] = useState("newest");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = selectedId
    ? interactions.find((item) => item.correlation_id === selectedId) || null
    : null;
  const closeReview = () => setSelectedId(null);
  const reviewDialogRef = useDialogFocus<HTMLElement>(Boolean(selected), closeReview);

  const refresh = async () => {
    setLoadError("");
    const overviewFilters = new URLSearchParams({ days });
    const interactionFilters = new URLSearchParams({ days, feedback, search: debouncedQuery, sort: reviewSort, page: String(reviewPage), page_size: reviewPageSize });
    const shadowFilters = new URLSearchParams({ days });
    if (startAt) {
      const start = new Date(startAt).toISOString();
      overviewFilters.set("start", start);
      interactionFilters.set("start", start);
      shadowFilters.set("start", start);
    }
    if (endAt) {
      const end = new Date(endAt).toISOString();
      overviewFilters.set("end", end);
      interactionFilters.set("end", end);
      shadowFilters.set("end", end);
    }
    if (country) {
      overviewFilters.set("country", country);
      interactionFilters.set("country", country);
      shadowFilters.set("country", country);
    }
    if (language) {
      overviewFilters.set("language", language);
      interactionFilters.set("language", language);
      shadowFilters.set("language", language);
    }
    if (trafficSource) { overviewFilters.set("traffic_source", trafficSource); interactionFilters.set("traffic_source", trafficSource); }
    const api = new AdminApi(credentials);
    try {
      const [overviewResult, interactionResult, shadowResult, configResult] = await Promise.all([
        withDemoFallback(() => api.overview(overviewFilters), demo.overview),
        withDemoFallback(() => api.interactions(interactionFilters), demoInteractionPage),
        withDemoFallback(() => api.retrievalShadow(shadowFilters), demo.shadowReport),
        withDemoFallback(() => api.config(), demo.config)
      ]);
      setOverview(overviewResult.data);
      setInteractions(interactionResult.data.items);
      setInteractionTotal(interactionResult.data.total);
      setInteractionTotalPages(interactionResult.data.totalPages);
      setShadowReport(shadowResult.data);
      setMarkets(configResult.data.countries);
      setMode(
        overviewResult.mode === "live"
        && interactionResult.mode === "live"
        && shadowResult.mode === "live"
        && configResult.mode === "live"
          ? "live"
          : "demo"
      );
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Insights data could not be loaded.");
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 350);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => { void refresh(); }, [credentials.accessToken, credentials.apiKey, days, startAt, endAt, country, language, trafficSource, feedback, debouncedQuery, reviewPage, reviewPageSize, reviewSort]);

  const resetDashboard = () => {
    setDays("30");
    setStartAt("");
    setEndAt("");
    setCountry("");
    setLanguage("");
    setTrafficSource("");
    setFeedback("all");
    setQuery("");
    setReviewPage(1);
    setReviewPageSize("50");
    setReviewSort("newest");
    setSelectedId(null);
    if (days === "30" && !startAt && !endAt && !country && !language && !trafficSource && feedback === "all") void refresh();
  };

  const availableLanguages = useMemo(() => {
    const source = country ? markets.filter((market) => market.code === country) : markets;
    const unique = new Map<string, string>();
    source.flatMap((market) => market.languages).forEach((item) => unique.set(item.code, item.name));
    return [...unique].map(([code, name]) => ({ code, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [country, markets]);

  const filteredInteractions = interactions;
  const firstReviewResult = interactionTotal ? (reviewPage - 1) * Number(reviewPageSize) + 1 : 0;
  const lastReviewResult = Math.min(reviewPage * Number(reviewPageSize), interactionTotal);

  const exportInteractions = async () => {
    setExporting(true);
    setExportError("");
    try {
      const filters = new URLSearchParams({ days, feedback, search: debouncedQuery, limit: "5000", sort: reviewSort });
      if (startAt) filters.set("start", new Date(startAt).toISOString());
      if (endAt) filters.set("end", new Date(endAt).toISOString());
      if (country) filters.set("country", country);
      if (language) filters.set("language", language);
      if (trafficSource) filters.set("traffic_source", trafficSource);
      const blob = await new AdminApi(credentials).exportInteractionsXlsx(filters);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `askvera-feedback-${new Date().toISOString().slice(0, 10)}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const feedbackTotal = overview.totals.helpful + overview.totals.notHelpful;
  const unansweredRate = overview.totals.questions ? overview.totals.unanswered / overview.totals.questions : 0;
  const inputTokens = Number(overview.totals.inputTokens || 0);
  const outputTokens = Number(overview.totals.outputTokens || 0);
  const measuredTokens = inputTokens + outputTokens;
  const inputTokenShare = measuredTokens ? inputTokens / measuredTokens : 0;
  const outputTokenShare = measuredTokens ? outputTokens / measuredTokens : 0;

  return (
    <section className="page-section" aria-labelledby="insights-title">
      <div className="page-heading dashboard-heading">
        <div><span className="eyebrow">Experience intelligence</span><h1 id="insights-title">Know what users need next.</h1><p>Measure adoption, answer quality, knowledge gaps and AI usage across every market.</p></div>
        <div className="heading-actions"><span className={`mode-pill ${mode}`}><span />{mode === "live" ? "Live data" : "Demo data"}</span><button className="button secondary" onClick={resetDashboard}>Reset dashboard</button></div>
      </div>
      {loadError ? <div className="admin-toast error" role="alert">{loadError}</div> : null}

      <div className="filter-bar surface">
        <label><span>Quick range</span><select value={days} onChange={(event) => { setDays(event.target.value); setStartAt(""); setEndAt(""); setReviewPage(1); }}><option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label>
        <label><span>From date and hour</span><input type="datetime-local" value={startAt} max={endAt || undefined} onChange={(event) => { setStartAt(event.target.value); setReviewPage(1); }} /></label>
        <label><span>To date and hour</span><input type="datetime-local" value={endAt} min={startAt || undefined} onChange={(event) => { setEndAt(event.target.value); setReviewPage(1); }} /></label>
        <label><span>Country</span><select value={country} onChange={(event) => { setCountry(event.target.value); setLanguage(""); setReviewPage(1); }}><option value="">All countries</option>{markets.map((market) => <option key={market.code} value={market.code}>{market.name}</option>)}</select></label>
        <label><span>Language</span><select value={language} onChange={(event) => { setLanguage(event.target.value); setReviewPage(1); }}><option value="">All languages</option>{availableLanguages.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
        <label><span>Traffic source</span><select value={trafficSource} onChange={(event) => { setTrafficSource(event.target.value); setReviewPage(1); }}><option value="">All traffic</option><option value="widget">Widget users</option><option value="evaluation">Evaluation runs</option><option value="backend_test">Backend tests</option><option value="admin_test">Admin tests</option><option value="legacy">Legacy / unclassified</option></select></label>
        <button className="button primary" onClick={() => void refresh()}>Apply filters</button>
        <small className="filter-note">Date and hour use your local timezone: {Intl.DateTimeFormat().resolvedOptions().timeZone}</small>
      </div>

      <div className="metric-grid">
        <article className="metric-card surface"><span>Live sessions now</span><strong>{compact.format(overview.totals.liveSessions || 0)}</strong><small>Consented, open and not expired</small></article>
        <article className="metric-card surface"><span>Unique sessions</span><strong>{compact.format(overview.totals.users)}</strong><small>Sessions with questions in this range</small></article>
        <article className="metric-card surface"><span>Questions asked</span><strong>{compact.format(overview.totals.questions)}</strong><small>{(overview.totals.questions / Math.max(overview.totals.users, 1)).toFixed(1)} per session</small></article>
        <article className="metric-card surface"><span>Helpful answers</span><strong>{percent(overview.totals.helpfulRate)}</strong><small>{compact.format(feedbackTotal)} rated answers</small></article>
        <article className="metric-card token-metric surface">
          <span>AI tokens</span><strong>{compact.format(overview.totals.tokens)}</strong>
          <div className="token-split" role="img" aria-label={`Input tokens ${percent(inputTokenShare)}; output tokens ${percent(outputTokenShare)}`}>
            <i className="token-input" style={{ width: `${inputTokenShare * 100}%` }} />
            <i className="token-output" style={{ width: `${outputTokenShare * 100}%` }} />
          </div>
          <div className="token-split-labels">
            <span><i className="token-input" /><b>Input {percent(inputTokenShare)}</b><small>{compact.format(inputTokens)}</small></span>
            <span><i className="token-output" /><b>Output {percent(outputTokenShare)}</b><small>{compact.format(outputTokens)}</small></span>
          </div>
        </article>
      </div>

      <div className="dashboard-grid">
        <article className="chart-card surface span-2"><div className="card-heading"><div><span>Question volume</span><strong>{compact.format(overview.totals.questions)}</strong></div><small>Daily questions</small></div><TrendChart overview={overview} /></article>
        <article className="quality-card surface"><div className="card-heading"><div><span>Answer quality</span><strong>{percent(overview.totals.helpfulRate)}</strong></div><small>Helpful rate</small></div>
          <div className="quality-ring" style={{ "--quality": `${overview.totals.helpfulRate * 360}deg` } as CSSProperties}><div><strong>{overview.totals.notHelpful}</strong><span>not helpful</span></div></div>
          <dl><div><dt>Average confidence</dt><dd>{percent(overview.totals.averageConfidence)}</dd></div><div><dt>Unanswered</dt><dd>{percent(unansweredRate)}</dd></div></dl>
        </article>
        <article className="chart-card surface"><div className="card-heading"><div><span>Top question themes</span></div><small>Volume</small></div><RankedBars data={overview.topics} /></article>
        <article className="chart-card surface"><div className="card-heading"><div><span>Country mix</span></div><small>Questions</small></div><RankedBars data={overview.countries} /></article>
        <article className="chart-card surface"><div className="card-heading"><div><span>Language mix</span></div><small>Questions</small></div><RankedBars data={overview.languages} /></article>
      </div>

      <div className="shadow-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Retrieval vNext</span>
            <h2>Shadow comparison</h2>
            <p>Compare vNext with the live retriever. These checks never change the answer sent to users.</p>
          </div>
          <span className="shadow-sample-note">5% background sample</span>
        </div>
        <div className="shadow-metrics">
          <article className="shadow-metric surface">
            <span>Comparisons</span>
            <strong>{compact.format(shadowReport.totals.comparisons)}</strong>
            <small>Completed in this range</small>
          </article>
          <article className="shadow-metric surface">
            <span>Same top section</span>
            <strong>{percent(shadowReport.totals.topMatchRate)}</strong>
            <small>{compact.format(shadowReport.totals.topMatches)} exact matches</small>
          </article>
          <article className="shadow-metric surface">
            <span>Evidence overlap</span>
            <strong>{percent(shadowReport.totals.averageOverlap)}</strong>
            <small>Shared results across both pipelines</small>
          </article>
          <article className="shadow-metric surface">
            <span>vNext confidence wins</span>
            <strong>{percent(shadowReport.totals.vnextConfidenceWinRate)}</strong>
            <small>{shadowReport.totals.primaryConfidence.toFixed(2)} live vs {shadowReport.totals.vnextConfidence.toFixed(2)} vNext</small>
          </article>
          <article className="shadow-metric surface">
            <span>Shadow latency</span>
            <strong>{Math.round(shadowReport.totals.averageDurationMs)} ms</strong>
            <small>Background only, outside user response time</small>
          </article>
        </div>
        <div className="shadow-detail-grid">
          <article className="shadow-locale-card surface">
            <div className="card-heading"><div><span>Country consistency</span></div><small>Top-section match</small></div>
            <div className="shadow-locale-list">
              {shadowReport.countries.map((item) => <div key={item.label}>
                <span>{item.label}</span>
                <i><b style={{ width: `${item.matchRate * 100}%` }} /></i>
                <strong>{percent(item.matchRate)}</strong>
                <small>{item.comparisons}</small>
              </div>)}
              {!shadowReport.countries.length ? <p className="shadow-empty">Waiting for comparisons.</p> : null}
            </div>
          </article>
          <article className="shadow-locale-card surface">
            <div className="card-heading"><div><span>Language consistency</span></div><small>Top-section match</small></div>
            <div className="shadow-locale-list">
              {shadowReport.languages.map((item) => <div key={item.label}>
                <span>{item.label.toUpperCase()}</span>
                <i><b style={{ width: `${item.matchRate * 100}%` }} /></i>
                <strong>{percent(item.matchRate)}</strong>
                <small>{item.comparisons}</small>
              </div>)}
              {!shadowReport.languages.length ? <p className="shadow-empty">Waiting for comparisons.</p> : null}
            </div>
          </article>
        </div>
        <div className="shadow-disagreements surface">
          <div className="card-heading">
            <div><span>Recent top-section differences</span></div>
            <small>Review these before promotion</small>
          </div>
          {shadowReport.disagreements.map((item) => <div className="shadow-difference" key={item.correlation_id}>
            <div>
              <strong>{item.country}/{item.language.toUpperCase()}</strong>
              <small>{interactionDateLabel(item.created_at)} · {percent(item.result_overlap)} evidence overlap</small>
            </div>
            <dl>
              <div><dt>Live</dt><dd>{item.primary_top_id || "No result"}</dd></div>
              <div><dt>vNext</dt><dd>{item.vnext_top_id || "No result"}</dd></div>
            </dl>
          </div>)}
          {!shadowReport.disagreements.length ? (
            <div className="shadow-empty success">No top-section differences in this range.</div>
          ) : null}
        </div>
      </div>

      <div className="review-section">
        <div className="section-heading"><div><h2>Answer review</h2><p>Review every captured answer and see where retrieval or content can improve.</p></div><div className="review-controls"><label className="search-field"><SearchIcon /><input value={query} onChange={(event) => { setQuery(event.target.value); setReviewPage(1); }} placeholder="Search questions" /></label><select value={feedback} onChange={(event) => { setFeedback(event.target.value); setReviewPage(1); }} aria-label="Feedback filter"><option value="all">All answers</option><option value="not_helpful">Not helpful</option><option value="helpful">Helpful</option><option value="unrated">Unrated</option></select><select value={reviewSort} onChange={(event) => { setReviewSort(event.target.value); setReviewPage(1); }} aria-label="Sort answers"><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="lowest_confidence">Lowest confidence</option><option value="highest_confidence">Highest confidence</option><option value="not_helpful_first">Not helpful first</option><option value="helpful_first">Helpful first</option></select><span className="review-count">Showing {firstReviewResult}–{lastReviewResult} of {interactionTotal}</span><button className="button secondary" disabled={exporting} onClick={() => void exportInteractions()}>{exporting ? "Preparing..." : "Export Excel"}</button></div></div>
        {exportError ? <div className="notice error export-error" role="alert">{exportError}</div> : null}
        <div className="review-list surface">
          {filteredInteractions.map((item) => <button className="review-row" key={item.correlation_id} onClick={() => setSelectedId(item.correlation_id)}>
            <span className={`feedback-mark ${item.rating === null || item.rating === undefined ? "neutral" : item.rating > 0 ? "positive" : "negative"}`}>{item.rating === null || item.rating === undefined ? "-" : item.rating > 0 ? "↑" : "↓"}</span>
            <span className="review-question"><strong>{item.question}</strong><small>{item.topic} · {item.country}/{item.language.toUpperCase()} · {item.traffic_source.replaceAll("_", " ")} · {interactionDateLabel(item.created_at)}</small></span>
            {item.expected_answer_present ? <span className="suggestion-badge">Suggestion</span> : null}
            <span className="confidence">{percent(item.confidence)}</span>{item.rating === -1 ? <ArrowIcon /> : <span className="review-label">Review</span>}
          </button>)}
          {!filteredInteractions.length ? <div className="empty-state">No answers match these filters.</div> : null}
        </div>
        {interactionTotalPages > 1 ? <div className="review-pagination"><button className="button secondary" disabled={reviewPage <= 1} onClick={() => setReviewPage((value) => Math.max(1, value - 1))}>Previous</button><span>Page {reviewPage} of {interactionTotalPages}</span><label>Rows <select value={reviewPageSize} onChange={(event) => { setReviewPageSize(event.target.value); setReviewPage(1); }}><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><button className="button secondary" disabled={reviewPage >= interactionTotalPages} onClick={() => setReviewPage((value) => Math.min(interactionTotalPages, value + 1))}>Next</button></div> : null}
      </div>

      {selected ? <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeReview(); }}><aside ref={reviewDialogRef} className="review-drawer" role="dialog" aria-modal="true" aria-labelledby="review-title" tabIndex={-1}>
        <button className="drawer-close" onClick={() => setSelectedId(null)} aria-label="Close review">x</button>
        <span className="eyebrow">Answer review</span><h2 id="review-title">{selected.question}</h2>
        <div className="drawer-meta"><span>{selected.country}</span><span>{selected.language.toUpperCase()}</span><span>{selected.traffic_source.replaceAll("_", " ")}</span><span>{percent(selected.confidence)} confidence</span><span>{selected.tokens} tokens</span></div>
        <section><h3>AskVera answered</h3><p>{selected.answer}</p></section>
        <section className="feedback-section"><h3>User feedback</h3><p>{selected.comment || selected.expected_answer || "No written comment was provided."}</p></section>
        {selected.comment && selected.expected_answer_present && selected.expected_answer !== selected.comment ? <section className="feedback-section"><h3>User suggestion</h3><p>{selected.expected_answer}</p></section> : null}
        <section><h3>Diagnostic signal</h3><dl><div><dt>Topic</dt><dd>{selected.topic}</dd></div><div><dt>Sources</dt><dd>{selected.source_count}</dd></div><div><dt>Failure layer</dt><dd>{selected.failure_layer || "None"}</dd></div><div><dt>Fallback</dt><dd>{selected.fallback ? "Yes" : "No"}</dd></div></dl></section>
        <div className="recommended-action"><strong>Recommended next step</strong><p>{selected.failure_layer.includes("retrieval") || selected.source_count === 0 ? "Check whether the answer exists in the approved source, then review its chunking and index metadata." : "Compare the answer with its cited passage and add the missed exception or wording to the evaluation set."}</p></div>
      </aside></div> : null}
    </section>
  );
}
