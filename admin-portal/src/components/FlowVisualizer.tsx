import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { AdminApi, demo, withDemoFallback, type DataMode } from "../api";
import { CheckIcon, RefreshIcon } from "../icons";
import type { PipelineTrace, TraceStage } from "../types";

const stations = [
  { id: "request_received", label: "Question", detail: "Widget sends market, language and session context." },
  { id: "governance", label: "Safety", detail: "Policy guardrails classify and approve the request." },
  { id: "retrieval", label: "Knowledge", detail: "Hybrid search finds approved, market-matched passages." },
  { id: "prompt_build", label: "Context", detail: "Evidence and conversation history become a grounded prompt." },
  { id: "model_generate", label: "Answer", detail: "The language model writes only from approved evidence." },
  { id: "validation", label: "Verify", detail: "Language, numbers, claims and citations are checked." },
  { id: "response_build", label: "Package", detail: "The answer, sources and confidence are assembled." },
  { id: "response_delivered", label: "Delivered", detail: "The verified response returns to the user." }
];

const displayTime = (value: string) => value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "In progress";
const stageFor = (trace: PipelineTrace, id: string) => trace.stages.find((stage) => stage.stage === id);

export function FlowVisualizer({ apiKey }: { apiKey: string }) {
  const [traces, setTraces] = useState<PipelineTrace[]>(demo.traces);
  const [selectedId, setSelectedId] = useState(demo.traces[0].correlation_id);
  const [selectedStage, setSelectedStage] = useState(stations[0].id);
  const [mode, setMode] = useState<DataMode>("demo");
  const [playing, setPlaying] = useState(true);
  const [playKey, setPlayKey] = useState(0);

  const refresh = async () => {
    const result = await withDemoFallback(() => new AdminApi(apiKey).traces(), demo.traces);
    setTraces(result.data.length ? result.data : demo.traces);
    setMode(result.mode);
    if (result.data.length && !result.data.some((trace) => trace.correlation_id === selectedId)) {
      setSelectedId(result.data[0].correlation_id);
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [apiKey]);

  const trace = useMemo(
    () => traces.find((item) => item.correlation_id === selectedId) || traces[0] || demo.traces[0],
    [selectedId, traces]
  );
  const detail = stations.find((station) => station.id === selectedStage) || stations[0];
  const activeStage = stageFor(trace, selectedStage);
  const totalDuration = trace.stages.reduce((sum, stage) => sum + stage.duration_ms, 0);

  const replay = () => {
    setPlaying(false);
    window.requestAnimationFrame(() => {
      setPlayKey((value) => value + 1);
      setPlaying(true);
    });
  };

  return (
    <section className="page-section" aria-labelledby="flow-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Live architecture</span>
          <h1 id="flow-title">See every answer take shape.</h1>
          <p>Follow one question through AskVera, from the widget to a verified response.</p>
        </div>
        <div className="heading-actions">
          <span className={`mode-pill ${mode}`}><span />{mode === "live" ? "Live data" : "Demo data"}</span>
          <button className="button secondary" onClick={() => void refresh()}><RefreshIcon /> Refresh</button>
        </div>
      </div>

      <div className="trace-toolbar surface">
        <label>
          <span>Recent question</span>
          <select value={trace.correlation_id} onChange={(event) => setSelectedId(event.target.value)}>
            {traces.map((item) => <option key={item.correlation_id} value={item.correlation_id}>{item.question_preview || item.correlation_id}</option>)}
          </select>
        </label>
        <div className="trace-context">
          <span>{trace.country || "—"}</span><span>{trace.language?.toUpperCase() || "—"}</span><span>{displayTime(trace.started_at)}</span>
        </div>
        <button className="button primary" onClick={replay}>Replay journey</button>
      </div>

      <div className="flow-stage surface">
        <div className="question-quote">“{trace.question_preview || "A user asks AskVera a question."}”</div>
        <div className={`metro-line ${playing ? "is-playing" : ""}`} key={playKey} role="list" aria-label="AskVera answer pipeline">
          <div className="metro-track" />
          <div className="metro-progress" />
          <div className="metro-train" aria-hidden="true"><span /></div>
          {stations.map((station, index) => {
            const result = stageFor(trace, station.id);
            const status = result?.status || "waiting";
            return (
              <button
                key={station.id}
                type="button"
                role="listitem"
                className={`station ${selectedStage === station.id ? "selected" : ""} ${status}`}
                style={{ "--station-index": index } as CSSProperties}
                onClick={() => setSelectedStage(station.id)}
                aria-label={`${station.label}: ${status}`}
              >
                <span className="station-node">{status === "complete" ? <CheckIcon /> : index + 1}</span>
                <strong>{station.label}</strong>
                <small>{result ? `${Math.round(result.duration_ms)} ms` : "Waiting"}</small>
              </button>
            );
          })}
        </div>

        <div className="station-detail" aria-live="polite">
          <div>
            <span className="detail-number">{String(stations.findIndex((station) => station.id === selectedStage) + 1).padStart(2, "0")}</span>
            <div><strong>{detail.label}</strong><p>{detail.detail}</p></div>
          </div>
          <dl>
            <div><dt>Status</dt><dd className={activeStage?.status === "error" ? "bad" : "good"}>{activeStage?.status || "Waiting"}</dd></div>
            <div><dt>This stop</dt><dd>{activeStage ? `${Math.round(activeStage.duration_ms)} ms` : "—"}</dd></div>
            <div><dt>Total journey</dt><dd>{Math.round(totalDuration)} ms</dd></div>
          </dl>
        </div>
      </div>

      <div className="architecture-note">
        <span>Privacy boundary</span>
        <p>The admin trace shows operational metadata and a short question preview—not retrieved document content, prompts, or private user details.</p>
      </div>
    </section>
  );
}
