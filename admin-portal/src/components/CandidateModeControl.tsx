import { useEffect, useState } from "react";
import { AdminApi, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import type { AdminConfig, CandidateModeFlags } from "../types";

type CandidateModeControlProps = {
  credentials: AdminCredentials;
  config: AdminConfig;
};

const TOGGLES: Array<{ key: keyof CandidateModeFlags; label: string; description: string }> = [
  {
    key: "narrowingFallback",
    label: "Narrowing fallback",
    description: "On a retrieval miss, ask a short clarifying question instead of the flat \"I don't have that\" refusal."
  },
  {
    key: "inVoiceGuardrail",
    label: "In-voice guardrail phrasing",
    description: "Phrase medical/income/off-topic declines in the model's own words. EXPERIMENTAL PLACEHOLDER WORDING, not reviewed by Legal - keep this off anywhere real users could see it."
  },
  {
    key: "widerTypoTolerance",
    label: "Wider typo tolerance",
    description: "Extend typo forgiveness beyond greeting/thanks/farewell to capability phrases, with a longer word/character span."
  }
];

const REQUIRED_CONFIRMATION = "UPDATE CANDIDATE MODE";
const DEMO_FLAGS: CandidateModeFlags = { narrowingFallback: false, inVoiceGuardrail: false, widerTypoTolerance: false };

export function CandidateModeControl({ credentials, config }: CandidateModeControlProps) {
  const [flags, setFlags] = useState<CandidateModeFlags>(DEMO_FLAGS);
  const [draft, setDraft] = useState<CandidateModeFlags>(DEMO_FLAGS);
  const [mode, setMode] = useState<DataMode>("demo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const isSuperAdmin = config.principal?.role === "super_admin";

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const api = new AdminApi(credentials);
      const result = await withDemoFallback(() => api.candidateMode(), DEMO_FLAGS);
      setFlags(result.data);
      setDraft(result.data);
      setMode(result.mode);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Candidate mode could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [credentials.accessToken, credentials.apiKey]);

  const dirty = draft.narrowingFallback !== flags.narrowingFallback
    || draft.inVoiceGuardrail !== flags.inVoiceGuardrail
    || draft.widerTypoTolerance !== flags.widerTypoTolerance;

  const apply = async () => {
    setSaving(true);
    setSaveError("");
    try {
      const result = await new AdminApi(credentials).updateCandidateMode({
        ...draft,
        reason: reason.trim(),
        confirmation: confirmation.trim()
      });
      setFlags(result);
      setDraft(result);
      setReason("");
      setConfirmation("");
    } catch (applyError) {
      setSaveError(applyError instanceof Error ? applyError.message : "Candidate mode could not be updated.");
    } finally {
      setSaving(false);
    }
  };

  if (!isSuperAdmin) return null;

  return (
    <section className="page-section candidate-mode-page">
    <div className="surface overview-panel candidate-mode-panel" aria-labelledby="candidate-mode-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Super Admin only · Test environment</span>
          <h2 id="candidate-mode-title">Current vs experimental chat behavior</h2>
          <p>
            Toggles the live test-environment widget between today's behavior and Taia-inspired candidate
            behaviors. This changes what every current tester sees immediately - it is not a per-session preview.
          </p>
        </div>
        <span className={`mode-pill ${mode}`}><span />{mode === "live" ? "Live control" : "Demo data"}</span>
      </div>
      {error ? <div className="notice error" role="alert">{error}</div> : null}
      {loading ? <div className="empty-state compact">Loading candidate mode…</div> : <>
        <div className="candidate-mode-status">
          <strong>
            {TOGGLES.some((toggle) => flags[toggle.key])
              ? `Active now: ${TOGGLES.filter((toggle) => flags[toggle.key]).map((toggle) => toggle.label).join(", ")}`
              : "All experimental behaviors are off - the widget matches today's production behavior."}
          </strong>
        </div>
        <div className="candidate-mode-toggles">
          {TOGGLES.map((toggle) => (
            <label key={toggle.key} className="candidate-mode-toggle">
              <input
                type="checkbox"
                checked={draft[toggle.key]}
                onChange={(event) => setDraft({ ...draft, [toggle.key]: event.target.checked })}
              />
              <span>
                <strong>{toggle.label}</strong>
                <small>{toggle.description}</small>
              </span>
            </label>
          ))}
        </div>
        {dirty ? <div className="candidate-mode-apply">
          <label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} placeholder="Explain why you are changing candidate mode" /></label>
          <label><span>Confirmation</span><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder={REQUIRED_CONFIRMATION} autoComplete="off" /><small>Type <strong>{REQUIRED_CONFIRMATION}</strong> exactly.</small></label>
          {saveError ? <div className="notice error" role="alert">{saveError}</div> : null}
          <div className="modal-actions">
            <button className="button secondary" onClick={() => { setDraft(flags); setReason(""); setConfirmation(""); setSaveError(""); }} disabled={saving}>Discard changes</button>
            <button
              className="button primary"
              onClick={() => void apply()}
              disabled={saving || reason.trim().length < 8 || confirmation.trim().toUpperCase() !== REQUIRED_CONFIRMATION}
            >
              {saving ? "Applying" : "Apply to test environment"}
            </button>
          </div>
        </div> : null}
      </>}
    </div>
    </section>
  );
}
