import { useEffect, useMemo, useState } from "react";
import { AdminApi, type AdminCredentials } from "../api";
import type { AdminConfig, WidgetConfig } from "../types";
import { useDialogFocus } from "../useDialogFocus";

type Draft = Omit<WidgetConfig, "id" | "public_key" | "previous_public_key" | "previous_key_expires_at" | "key_version" | "status" | "embed_code" | "created_at" | "updated_at" | "has_draft">;
const blank = (): Draft => ({
  name: "", customer: "", allowed_origins: [], markets: [], languages: [],
  default_market: "", default_language: "", display_name: "AskVera",
  greeting: "Hello. How can I help?", logo_url: "", accent_color: "#2F7D4E",
  position: "bottom-right", legal_version: "2026.1", rate_limit_tier: "standard", usage_cap: null
});

function validateOrigins(value: string) {
  const origins = value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
  if (!origins.length) return "Add at least one approved website origin.";
  if (new Set(origins.map((origin) => origin.toLowerCase().replace(/\/$/, ""))).size !== origins.length) {
    return "Each approved origin must be unique.";
  }
  for (const origin of origins) {
    try {
      const parsed = new URL(origin);
      if (!["http:", "https:"].includes(parsed.protocol)
        || parsed.username
        || parsed.password
        || !parsed.hostname
        || parsed.pathname !== "/"
        || parsed.search
        || parsed.hash) {
        return `${origin} is not an exact http or https origin.`;
      }
    } catch {
      return `${origin} is not a valid website origin.`;
    }
  }
  return "";
}

export function WidgetManager({ credentials, config }: { credentials: AdminCredentials; config: AdminConfig }) {
  const api = useMemo(() => new AdminApi(credentials), [credentials.accessToken, credentials.apiKey]);
  const [items, setItems] = useState<WidgetConfig[]>([]);
  const [draft, setDraft] = useState<Draft>(() => blank());
  const [editing, setEditing] = useState<WidgetConfig | null>(null);
  const [originText, setOriginText] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [previewMode, setPreviewMode] = useState<"desktop" | "mobile">("desktop");
  const originIssue = originText ? validateOrigins(originText) : "";

  const load = async () => {
    setLoading(true);
    try { setItems(await api.widgetConfigs()); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Widget instances could not be loaded."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [api]);

  const widgetCountries = config.widgetCountries || config.countries;
  const allowedLanguages = useMemo(() => {
    const selected = widgetCountries.filter((country) => draft.markets.includes(country.code));
    return [...new Map(selected.flatMap((country) => country.languages).map((language) => [language.code, language])).values()];
  }, [widgetCountries, draft.markets]);

  const openEdit = (item?: WidgetConfig) => {
    setEditing(item || null);
    const next = item ? {
      name: item.name, customer: item.customer, allowed_origins: item.allowed_origins,
      markets: item.markets, languages: item.languages, default_market: item.default_market,
      default_language: item.default_language, display_name: item.display_name, greeting: item.greeting,
      logo_url: item.logo_url, accent_color: item.accent_color, position: item.position, legal_version: item.legal_version,
      rate_limit_tier: item.rate_limit_tier, usage_cap: item.usage_cap
    } : blank();
    setDraft(next);
    setOriginText(next.allowed_origins.join("\n"));
    setShowForm(true);
    setError("");
  };
  const close = () => { setShowForm(false); setEditing(null); };
  const formDialogRef = useDialogFocus<HTMLElement>(showForm, close);

  const save = async () => {
    const origins = originText.split(/\r?\n|,/).map((value) => value.trim()).filter(Boolean);
    const validationError = validateOrigins(originText);
    if (!draft.name.trim() || validationError) { setError(!draft.name.trim() ? "Enter a widget name." : validationError); return; }
    if (!draft.markets.length) { setError("Select at least one market."); return; }
    if (!draft.languages.length) { setError("Select at least one language."); return; }
    if (draft.default_market && !draft.markets.includes(draft.default_market)) {
      setError("Choose a default market that is enabled for this widget.");
      return;
    }
    if (draft.default_language && !draft.languages.includes(draft.default_language)) {
      setError("Choose a default language that is enabled for this widget.");
      return;
    }
    setSaving(true); setError("");
    try {
      const body = { ...draft, allowed_origins: origins };
      if (editing) await api.stageWidgetConfig(editing.id, body);
      else await api.createWidgetConfig(body);
      setNotice(editing ? "Widget changes saved as a draft. Publish after reviewing the preview." : "Widget instance created.");
      close(); await load();
    } catch (nextError) { setError(nextError instanceof Error ? nextError.message : "The widget configuration could not be saved."); }
    finally { setSaving(false); }
  };

  const copy = async (item: WidgetConfig) => {
    try {
      await navigator.clipboard.writeText(item.embed_code);
      setNotice("Embed code copied.");
    } catch {
      setError("The embed code could not be copied. Open How to install and copy it manually.");
    }
  };

  const uploadLogo = async (file?: File) => {
    if (!file) return;
    if (file.size > 1024 * 1024) { setError("Logo must be 1 MB or smaller."); return; }
    setSaving(true);
    setError("");
    try {
      const result = await api.uploadWidgetLogo(file);
      setDraft((current) => ({ ...current, logo_url: result.url }));
      setNotice("Logo uploaded. Save the widget to publish it.");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "The logo could not be uploaded.");
    } finally { setSaving(false); }
  };

  return <section className="page-section">
    <div className="page-heading"><div><span className="eyebrow">Plug-and-play delivery</span><h1>Widget</h1><p>Configure approved markets and websites, then hand the customer a ready-to-paste installation snippet.</p></div><button className="button primary" onClick={() => openEdit()}>Create widget</button></div>
    {notice ? <div className="admin-toast success" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss">x</button></div> : null}
    {error ? <div className="admin-toast error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss">x</button></div> : null}
    <div className="widget-config-grid">
      {loading ? <div className="empty-state surface">Loading widget instances...</div> : items.map((item) => <article className="widget-config-card surface" key={item.id}>
        <div><span className={`status-pill ${item.status}`}>{item.status}</span><h2>{item.name}</h2><p>{item.customer || "No customer label"}</p></div>
        <dl><div><dt>Websites</dt><dd>{item.allowed_origins.join(", ")}</dd></div><div><dt>Markets</dt><dd>{item.markets.join(", ")}</dd></div><div><dt>Languages</dt><dd>{item.languages.join(", ")}</dd></div><div><dt>Public instance ID</dt><dd><code>{item.public_key}</code></dd></div></dl>
        <div className="card-actions"><button className="button secondary" onClick={() => openEdit(item)}>Edit draft</button>{item.has_draft ? <button className="button primary" onClick={() => void api.publishWidgetConfig(item.id).then(() => { setNotice("Widget draft published."); return load(); }).catch((nextError) => setError(nextError instanceof Error ? nextError.message : "The draft could not be published."))}>Publish draft</button> : null}<button className="button secondary" onClick={() => void copy(item)}>Copy embed code</button><button className="button secondary" onClick={() => { if (window.confirm("Rotate this public instance ID? The old ID will remain valid during the grace period.")) void api.rotateWidgetKey(item.id).then(() => { setNotice("Public instance ID rotated with a grace period."); return load(); }).catch((nextError) => setError(nextError instanceof Error ? nextError.message : "The key could not be rotated.")); }}>Rotate ID</button>{item.status === "active" ? <button className="button secondary" onClick={() => { if (window.confirm("Disable this widget? Existing embeds will stop working immediately.")) void api.disableWidgetConfig(item.id).then(() => { setNotice("Widget disabled."); return load(); }).catch((nextError) => setError(nextError instanceof Error ? nextError.message : "The widget could not be disabled.")); }}>Disable</button> : null}</div>
        {item.previous_key_expires_at ? <small>Previous instance ID remains valid until {new Date(item.previous_key_expires_at).toLocaleString()}.</small> : null}
        <details className="install-details"><summary>How to install</summary><p>Paste this snippet before the closing body tag on an approved website.</p><pre>{item.embed_code}</pre><button className="button secondary" onClick={() => void copy(item)}>Copy code</button></details>
      </article>)}
      {!loading && !items.length ? <div className="empty-state surface">No widget instances yet. Create one when a customer site is ready.</div> : null}
    </div>
    {showForm ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section ref={formDialogRef} className="admin-form-modal widget-form-modal" role="dialog" aria-modal="true" aria-labelledby="widget-form-title" tabIndex={-1}>
      <button className="drawer-close" onClick={close} aria-label="Close">x</button><span className="eyebrow">{editing ? "Edit instance" : "New instance"}</span><h2 id="widget-form-title">{editing ? editing.name : "Create a widget"}</h2>
      <div className="form-grid"><label><span>Name</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} autoFocus /></label><label><span>Customer</span><input value={draft.customer} onChange={(event) => setDraft({ ...draft, customer: event.target.value })} /></label></div>
      <label><span>Approved website origins</span><textarea aria-describedby="origin-help origin-error" aria-invalid={Boolean(originIssue)} value={originText} onChange={(event) => setOriginText(event.target.value)} placeholder={"https://www.example.com\nhttps://portal.example.com"} /><small id="origin-help">One exact http or https origin per line. Paths are not accepted.</small>{originIssue ? <small id="origin-error" className="inline-error" role="alert">{originIssue}</small> : null}</label>
      <fieldset><legend>Markets</legend><div className="choice-grid">{widgetCountries.map((market) => <label key={market.code}><input type="checkbox" checked={draft.markets.includes(market.code)} onChange={() => setDraft({ ...draft, markets: draft.markets.includes(market.code) ? draft.markets.filter((item) => item !== market.code) : [...draft.markets, market.code] })} />{market.name}</label>)}</div></fieldset>
      <fieldset><legend>Languages</legend><div className="choice-grid">{allowedLanguages.map((language) => <label key={language.code}><input type="checkbox" checked={draft.languages.includes(language.code)} onChange={() => setDraft({ ...draft, languages: draft.languages.includes(language.code) ? draft.languages.filter((item) => item !== language.code) : [...draft.languages, language.code] })} />{language.name}</label>)}</div></fieldset>
      <div className="form-grid"><label><span>Default market</span><select value={draft.default_market} onChange={(event) => setDraft({ ...draft, default_market: event.target.value })}><option value="">Select</option>{draft.markets.map((market) => <option key={market}>{market}</option>)}</select></label><label><span>Default language</span><select value={draft.default_language} onChange={(event) => setDraft({ ...draft, default_language: event.target.value })}><option value="">Select</option>{draft.languages.map((language) => <option key={language}>{language}</option>)}</select></label></div>
      <div className="form-grid"><label><span>Display name</span><input value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} /></label><label><span>Accent</span><input type="color" value={draft.accent_color} onChange={(event) => setDraft({ ...draft, accent_color: event.target.value })} /></label></div>
      <label className="logo-upload"><span>Widget logo</span><div>{draft.logo_url ? <img src={draft.logo_url} alt="Current widget logo preview" /> : <span className="logo-placeholder">No logo</span>}<div><input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => void uploadLogo(event.target.files?.[0])} /><small>PNG, JPEG or WebP. Maximum 1 MB.</small>{draft.logo_url ? <button type="button" className="text-button" onClick={() => setDraft({ ...draft, logo_url: "" })}>Remove logo</button> : null}</div></div></label>
      <label><span>Greeting</span><textarea value={draft.greeting} onChange={(event) => setDraft({ ...draft, greeting: event.target.value })} /></label>
      <div className="form-grid"><label><span>Position</span><select value={draft.position} onChange={(event) => setDraft({ ...draft, position: event.target.value as Draft["position"] })}><option value="bottom-right">Bottom right</option><option value="bottom-left">Bottom left</option></select></label><label><span>Legal version</span><input value={draft.legal_version} onChange={(event) => setDraft({ ...draft, legal_version: event.target.value })} /></label><label><span>Rate-limit tier</span><select value={draft.rate_limit_tier} onChange={(event) => setDraft({ ...draft, rate_limit_tier: event.target.value })}><option>standard</option><option>low</option><option>high</option></select></label><label><span>Monthly usage cap</span><input type="number" min="1" value={draft.usage_cap || ""} onChange={(event) => setDraft({ ...draft, usage_cap: event.target.value ? Number(event.target.value) : null })} /></label></div>
      <div className="preview-mode"><button className={previewMode === "desktop" ? "selected" : ""} onClick={() => setPreviewMode("desktop")}>Desktop</button><button className={previewMode === "mobile" ? "selected" : ""} onClick={() => setPreviewMode("mobile")}>Mobile</button></div><div className={`widget-preview-frame ${previewMode}`}><div className={`widget-mini-preview ${draft.position}`} style={{ borderColor: draft.accent_color }}>{draft.logo_url ? <img src={draft.logo_url} alt="" /> : null}<strong>{draft.display_name || "AskVera"}</strong><p>{draft.greeting || "Hello. How can I help?"}</p><span style={{ background: draft.accent_color }}>Ask a question</span></div></div>
      <div className="modal-actions"><button className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={saving || Boolean(originIssue)} onClick={() => void save()}>{saving ? "Saving..." : editing ? "Save draft" : "Create widget"}</button></div>
    </section></div> : null}
  </section>;
}
