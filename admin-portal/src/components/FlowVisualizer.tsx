import { useEffect, useMemo, useState } from "react";
import { AdminApi, demo, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import { CheckIcon, RefreshIcon } from "../icons";
import type { PipelineTrace, TraceStage } from "../types";

type StationDefinition = {
  id: string;
  label: string;
  service: string;
  family: string;
  detail: string;
  entered: string;
  process: string;
  produced: string;
};

const stations: StationDefinition[] = [
  { id: "request_received", label: "Request", service: "Widget + FastAPI", family: "ingress", detail: "The authenticated widget request enters AskVera.", entered: "Question, session, selected market, language and role.", process: "Create a correlation ID and privacy-safe operational trace.", produced: "A validated request envelope for policy processing." },
  { id: "governance", label: "Guardrails", service: "Amazon Bedrock Guardrails", family: "safety", detail: "Safety policy decides whether processing may continue.", entered: "PII-scrubbed question and market context.", process: "Evaluate denied topics, compliance intent and configured rules.", produced: "Allow, block or review decision with risk classification." },
  { id: "cache_lookup", label: "Cache", service: "ElastiCache for Valkey", family: "cache", detail: "AskVera checks whether an approved answer can be reused.", entered: "Versioned question, market, language and role key.", process: "Look up a validated response without exposing the question in the cache key.", produced: "A cache hit that skips AI work, or a miss that continues to retrieval." },
  { id: "retrieval", label: "Knowledge", service: "OpenSearch Serverless", family: "knowledge", detail: "Hybrid search finds approved, locale-compatible evidence.", entered: "Governed query and country/language access filters.", process: "Combine keyword, vector and structured-section ranking.", produced: "Ranked evidence, source metadata and retrieval confidence." },
  { id: "prompt_build", label: "Grounding", service: "AskVera Prompt Builder", family: "context", detail: "Approved evidence is assembled into a grounded model request.", entered: "Question, evidence and limited conversation history.", process: "Apply persona, compliance, role and evidence instructions.", produced: "A constrained prompt ready for model inference." },
  { id: "model_generate", label: "Generate", service: "Amazon Bedrock + Claude", family: "model", detail: "Claude writes an answer using only supplied evidence.", entered: "Grounded prompt and evidence - the input token payload.", process: "Model inference generates the answer and usage telemetry.", produced: "Draft response, finish reason and output token count." },
  { id: "validation", label: "Validate", service: "AskVera Validators", family: "validation", detail: "Independent validators check safety and grounding.", entered: "Draft answer, citations, evidence and locale expectations.", process: "Check language, citations, numbers, claims and response metadata.", produced: "Pass, repaired claim, or a safe blocked response." },
  { id: "response_build", label: "Package", service: "AskVera Response Builder", family: "package", detail: "The verified answer becomes the widget response contract.", entered: "Validated answer, approved sources and diagnostics.", process: "Remove unresolved placeholders and assemble public metadata.", produced: "Stable API response with answer, sources and confidence." },
  { id: "response_delivered", label: "Deliver", service: "HTTPS + Widget", family: "delivery", detail: "The completed response returns to the user and analytics layer.", entered: "Final response and operational measurements.", process: "Return HTTPS response and record redacted quality telemetry.", produced: "Answer displayed with outcome, token usage and savings." }
];

const stationById = new Map(stations.map((station) => [station.id, station]));
const displayTime = (value: string) => value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "In progress";
const stageFor = (trace: PipelineTrace, id: string) => trace.stages.find((stage) => stage.stage === id);
const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("en");
const numberValue = (value: unknown) => { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; };
const booleanValue = (value: unknown) => value === true || String(value).toLowerCase() === "true";
const titleCase = (value: string) => value.replace(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const formatMetadata = (value: unknown): string => {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? integer.format(value) : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  if (typeof value === "string") return value || "Not reported";
  if (value && typeof value === "object") return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${titleCase(key)}: ${formatMetadata(item)}`).join(" · ");
  return "Not reported";
};
const metadataNumber = (stages: Array<TraceStage | undefined>, ...keys: string[]) => {
  for (const stage of stages) for (const key of keys) { const value = numberValue(stage?.metadata?.[key]); if (value) return value; }
  return 0;
};

export function FlowVisualizer({ credentials }: { credentials: AdminCredentials }) {
  const [traces, setTraces] = useState<PipelineTrace[]>(demo.traces);
  const [selectedId, setSelectedId] = useState(demo.traces[0].correlation_id);
  const [selectedStage, setSelectedStage] = useState("request_received");
  const [mode, setMode] = useState<DataMode>("demo");
  const [replayKey, setReplayKey] = useState(0);

  const refresh = async () => {
    const result = await withDemoFallback(() => new AdminApi(credentials).traces(), demo.traces);
    setTraces(result.data.length ? result.data : demo.traces);
    setMode(result.mode);
    if (result.data.length && !result.data.some((trace) => trace.correlation_id === selectedId)) setSelectedId(result.data[0].correlation_id);
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [credentials.accessToken, credentials.apiKey]);

  const trace = useMemo(() => traces.find((item) => item.correlation_id === selectedId) || traces[0] || demo.traces[0], [selectedId, traces]);
  const detail = stationById.get(selectedStage) || stations[0];
  const activeStage = stageFor(trace, selectedStage);
  const deliveredStage = stageFor(trace, "response_delivered");
  const modelStage = stageFor(trace, "model_generate");
  const retrievalStage = stageFor(trace, "retrieval");
  const responseStage = stageFor(trace, "response_build");
  const cacheStage = stageFor(trace, "cache_lookup");
  const cacheHit = booleanValue(cacheStage?.metadata?.cacheHit) || booleanValue(deliveredStage?.metadata?.cacheHit);
  const inputTokens = metadataNumber([deliveredStage, modelStage], "inputTokens", "input_tokens");
  const outputTokens = metadataNumber([deliveredStage, modelStage], "outputTokens", "output_tokens");
  const tokensSaved = metadataNumber([deliveredStage, cacheStage], "tokensSaved", "cache_token_savings");
  const sourceCount = metadataNumber([deliveredStage, responseStage, retrievalStage], "source_count", "sourceCount", "citationCount");
  const confidence = metadataNumber([deliveredStage, responseStage, retrievalStage], "confidence");
  const totalDuration = trace.stages.reduce((sum, stage) => sum + stage.duration_ms, 0);
  const metadataEntries = Object.entries(activeStage?.metadata || {}).filter(([, value]) => value !== "" && value !== null && value !== undefined);
  const slowestStage = trace.stages.reduce<TraceStage | undefined>((slowest, stage) => !slowest || stage.duration_ms > slowest.duration_ms ? stage : slowest, undefined);
  const servicesTouched = new Set(trace.stages.map((stage) => stationById.get(stage.stage)?.service).filter(Boolean)).size;

  const replay = () => setReplayKey((value) => value + 1);
  const resetView = () => {
    setSelectedStage("request_received");
    setSelectedId(traces[0]?.correlation_id || demo.traces[0].correlation_id);
    setReplayKey((value) => value + 1);
    void refresh();
  };

  const renderNode = (id: string, className = "") => {
    const definition = stationById.get(id) || stations[0];
    const result = stageFor(trace, id);
    const status = result?.status || "waiting";
    return <button type="button" className={`service-node ${definition.family} ${status} ${selectedStage === id ? "selected" : ""} ${className}`} onClick={() => setSelectedStage(id)} aria-label={`${definition.label}, ${definition.service}: ${status}`}>
      <span className="service-node-icon">{status === "complete" ? <CheckIcon /> : definition.label.slice(0, 1)}</span>
      <span><small>{definition.service}</small><strong>{definition.label}</strong><em>{result ? `${Math.round(result.duration_ms)} ms` : "Not used"}</em></span>
    </button>;
  };

  return (
    <section className="page-section" aria-labelledby="flow-title">
      <div className="page-heading">
        <div><span className="eyebrow">Live service trace</span><h1 id="flow-title">See every answer take shape.</h1><p>Follow the AWS services, decisions, latency, token usage and cache savings behind one response.</p></div>
        <div className="heading-actions"><span className={`mode-pill ${mode}`}><span />{mode === "live" ? "Live data" : "Demo data"}</span><button className="button secondary" onClick={resetView}>Reset view</button><button className="button secondary" onClick={() => void refresh()}><RefreshIcon /> Refresh</button></div>
      </div>

      <div className="trace-toolbar surface">
        <label><span>Recent question</span><select value={trace.correlation_id} onChange={(event) => setSelectedId(event.target.value)}>{traces.map((item) => <option key={item.correlation_id} value={item.correlation_id}>{item.question_preview || item.correlation_id}</option>)}</select></label>
        <div className="trace-context"><span>{trace.country || "-"}</span><span>{trace.language?.toUpperCase() || "-"}</span><span>{displayTime(trace.started_at)}</span></div>
        <button className="button primary" onClick={replay}>Replay journey</button>
      </div>

      <div className="journey-metrics">
        <article className="journey-metric surface"><span>End-to-end work</span><strong>{integer.format(Math.round(totalDuration))}<small> ms</small></strong><p>{slowestStage ? `${titleCase(slowestStage.stage)} was the longest stop` : "Waiting for the journey"}</p></article>
        <article className="journey-metric surface"><span>Services touched</span><strong>{servicesTouched}</strong><p>{sourceCount} approved source{sourceCount === 1 ? "" : "s"} · {confidence ? `${Math.round(confidence * 100)}% confidence` : "confidence pending"}</p></article>
        <article className="journey-metric token-card surface"><span>Input tokens consumed</span><strong>{inputTokens ? compact.format(inputTokens) : cacheHit ? "0" : "-"}</strong><p>{cacheHit ? "Skipped because Valkey returned a validated answer" : "Instructions, question and evidence sent to Claude"}</p></article>
        <article className="journey-metric token-card returned surface"><span>Output tokens returned</span><strong>{outputTokens ? compact.format(outputTokens) : cacheHit ? "0" : "-"}</strong><p>{cacheHit ? "No generation call was required" : "Generated answer returned by Claude"}</p></article>
        <article className={`journey-metric savings-card surface ${tokensSaved ? "has-savings" : ""}`}><span>Tokens saved by cache</span><strong>{tokensSaved ? compact.format(tokensSaved) : "0"}</strong><p>{cacheHit ? "Estimated tokens avoided on this request" : "This request used the regular AI path"}</p></article>
      </div>

      <div className="flow-stage service-map surface" key={replayKey}>
        <div className="question-quote">“{trace.question_preview || "A user asks AskVera a question."}”</div>
        <div className="service-tree" role="tree" aria-label="AskVera service trace">
          <div className="tree-trunk">{renderNode("request_received")}<span className="tree-link" />{renderNode("governance")}<span className="tree-link" />{renderNode("cache_lookup")}</div>
          <div className="branch-split"><span /><strong>Decision</strong><span /></div>
          <div className="tree-branches">
            <section className={`tree-branch cache-branch ${cacheHit ? "active-path" : "inactive-path"}`} aria-label="Cached answer path">
              <header><span>Cache hit</span><strong>{cacheHit ? "Fast path used" : "Not used"}</strong></header>
              <div className="branch-summary cache"><span>Valkey response</span><strong>{cacheHit ? `${compact.format(tokensSaved)} tokens avoided` : "Waiting for a reusable answer"}</strong></div>
              <span className="tree-link" />{renderNode("validation")}<span className="tree-link" />{renderNode("response_delivered", "cache-delivery")}
            </section>
            <section className={`tree-branch model-branch ${cacheHit ? "inactive-path" : "active-path"}`} aria-label="Generated answer path">
              <header><span>Cache miss</span><strong>{cacheHit ? "Skipped" : "Grounded AI path used"}</strong></header>
              <div className="model-lane">{renderNode("retrieval")}<span className="lane-link" />{renderNode("prompt_build")}<span className="lane-link" />{renderNode("model_generate")}<span className="lane-link" />{renderNode("validation")}<span className="lane-link" />{renderNode("response_build")}<span className="lane-link" />{renderNode("response_delivered")}</div>
            </section>
          </div>
        </div>

        <div className="stage-inspector" aria-live="polite">
          <div className="stage-inspector-heading"><div><span className="detail-number">{String(stations.findIndex((station) => station.id === selectedStage) + 1).padStart(2, "0")}</span><div><span className={`service-chip ${detail.family}`}>{detail.service}</span><strong>{detail.label}</strong><p>{detail.detail}</p></div></div><dl><div><dt>Status</dt><dd className={activeStage?.status === "error" ? "bad" : "good"}>{activeStage?.status || "Not used"}</dd></div><div><dt>Stage time</dt><dd>{activeStage ? `${Math.round(activeStage.duration_ms)} ms` : "-"}</dd></div><div><dt>Journey share</dt><dd>{activeStage && totalDuration ? `${Math.round(activeStage.duration_ms / totalDuration * 100)}%` : "-"}</dd></div></dl></div>
          <div className="stage-story"><article><span>01 · Entered</span><p>{detail.entered}</p></article><article><span>02 · Processing</span><p>{detail.process}</p></article><article><span>03 · Produced</span><p>{detail.produced}</p></article></div>
          {metadataEntries.length ? <div className="stage-metadata"><div><strong>Operational signals</strong><span>Safe metadata captured from this service</span></div><dl>{metadataEntries.map(([key, value]) => <div key={key}><dt>{titleCase(key)}</dt><dd>{formatMetadata(value)}</dd></div>)}</dl></div> : null}
        </div>
      </div>
    </section>
  );
}
