import { useEffect, useMemo, useState } from "react";
import { AdminApi, type AdminCredentials } from "../api";
import type { AdminAuditEvent, AdminConfig, SupportRoute } from "../types";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function SupportRoutesManager({ credentials, config }: { credentials: AdminCredentials; config: AdminConfig }) {
  const api = useMemo(() => new AdminApi(credentials), [credentials.accessToken, credentials.apiKey]);
  const [routes, setRoutes] = useState<SupportRoute[]>([]);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [bulkCountries, setBulkCountries] = useState<string[]>([]);
  const [history, setHistory] = useState<AdminAuditEvent[]>([]);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    try { setRoutes(await api.supportRoutes()); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Support routes could not be loaded."); }
  };
  useEffect(() => { void load(); }, [api]);

  const rows = useMemo(() => {
    const byCountry = new Map(routes.map((route) => [route.country, route]));
    return config.countries.map((country) => {
      const route = byCountry.get(country.code);
      return route ? { ...route, country_name: country.name } : {
        country: country.code, country_name: country.name, department: "", email: "", fallback_department: "", fallback_email: "",
        enabled: false, updated_at: null, updated_by: ""
      };
    });
  }, [config.countries, routes]);

  const selectedRoute = rows.find((route) => route.country === selectedCountry) || rows[0];
  useEffect(() => {
    if (selectedRoute?.country && selectedRoute.country !== selectedCountry) setSelectedCountry(selectedRoute.country);
  }, [selectedRoute?.country, selectedCountry]);

  const change = (country: string, field: keyof SupportRoute, value: string | boolean) => {
    setRoutes((current) => {
      const existing = current.find((route) => route.country === country);
      const base = existing || rows.find((route) => route.country === country);
      if (!base) return current;
      const next = { ...base, [field]: value };
      return existing ? current.map((route) => route.country === country ? next : route) : [...current, next];
    });
  };

  const save = async (route: SupportRoute) => {
    const email = route.email.trim().toLowerCase();
    const department = route.department.trim();
    if (route.enabled && !department) {
      setError(`Enter a department for ${route.country_name} before enabling this route.`);
      return;
    }
    if (route.enabled && !EMAIL_PATTERN.test(email)) {
      setError(`Enter a valid destination email for ${route.country_name}.`);
      return;
    }
    setSaving(route.country);
    setError("");
    try {
      await api.updateSupportRoute(route.country, {
        department, email, fallback_department: route.fallback_department.trim(), fallback_email: route.fallback_email.trim().toLowerCase(), enabled: route.enabled
      });
      setNotice(`${route.country_name} routing saved.`);
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "The support route could not be saved.");
    } finally { setSaving(""); }
  };

  const testRoute = async (route: SupportRoute) => {
    setTesting(true); setError("");
    try { await api.testSupportRoute(route.country); setNotice(`A test message was submitted for ${route.country_name}.`); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "The test could not be submitted."); }
    finally { setTesting(false); }
  };
  const loadHistory = async (country: string) => {
    try { setHistory(await api.supportRouteHistory(country)); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Route history could not be loaded."); }
  };
  const bulkSave = async () => {
    if (!selectedRoute || !bulkCountries.length) return;
    setSaving("bulk");
    try {
      await api.bulkUpdateSupportRoutes(bulkCountries, { department: selectedRoute.department, email: selectedRoute.email, fallback_department: selectedRoute.fallback_department, fallback_email: selectedRoute.fallback_email, enabled: selectedRoute.enabled });
      setNotice(`Routing updated for ${bulkCountries.length} markets.`); setBulkCountries([]); await load();
    } catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Bulk routing could not be saved."); }
    finally { setSaving(""); }
  };

  return <section className="page-section">
    <div className="page-heading"><div><span className="eyebrow">Customer handoff</span><h1>Support routing</h1><p>Choose where each market's support requests are delivered. Changes take effect without a code deployment.</p></div></div>
    {notice ? <div className="admin-toast success" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss">x</button></div> : null}
    {error ? <div className="admin-toast error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss">x</button></div> : null}
    <div className="user-toolbar surface"><label className="toolbar-field"><span>Market</span><select aria-label="Select support market" value={selectedRoute?.country || ""} onChange={(event) => { setSelectedCountry(event.target.value); setHistory([]); }}>{rows.map((route) => <option key={route.country} value={route.country}>{route.country_name} ({route.country})</option>)}</select></label><label className="toolbar-field"><span>Apply same route to</span><select multiple value={bulkCountries} onChange={(event) => setBulkCountries(Array.from(event.currentTarget.selectedOptions).map((option) => option.value))}>{rows.filter((route) => route.country !== selectedRoute?.country).map((route) => <option key={route.country} value={route.country}>{route.country_name}</option>)}</select></label><button className="button secondary" disabled={!bulkCountries.length || saving === "bulk"} onClick={() => void bulkSave()}>Apply to selected</button></div>
    <div className="support-route-list surface">
      <div className="support-route-head"><span>Market</span><span>Department</span><span>Destination email</span><span>Active</span><span /></div>
      {selectedRoute ? [selectedRoute].map((route) => <div className="support-route-row" key={route.country}>
        <div><strong>{route.country_name}</strong><small>{route.country}</small></div>
        <input aria-label={`${route.country_name} department`} value={route.department} onChange={(event) => change(route.country, "department", event.target.value)} />
        <input type="email" aria-label={`${route.country_name} support email`} value={route.email} onChange={(event) => change(route.country, "email", event.target.value)} />
        <label className="route-toggle"><input type="checkbox" checked={route.enabled} onChange={(event) => change(route.country, "enabled", event.target.checked)} /><span>{route.enabled ? "On" : "Off"}</span></label>
        <button className="button primary" disabled={saving === route.country} onClick={() => void save(route)}>{saving === route.country ? "Saving..." : "Save"}</button>
        <div className="support-fallback"><label><span>Fallback department</span><input value={route.fallback_department} onChange={(event) => change(route.country, "fallback_department", event.target.value)} /></label><label><span>Fallback email</span><input type="email" value={route.fallback_email} onChange={(event) => change(route.country, "fallback_email", event.target.value)} /></label><div><button className="button secondary" disabled={testing || !route.enabled} onClick={() => void testRoute(route)}>{testing ? "Testing..." : "Test delivery"}</button><button className="button secondary" onClick={() => void loadHistory(route.country)}>View history</button></div></div>
      </div>) : null}
      {!selectedRoute ? <div className="empty-state">No markets are available.</div> : null}
    </div>
    {history.length ? <section className="surface route-history"><div className="section-heading"><div><span className="eyebrow">Route history</span><h2>{selectedRoute?.country_name}</h2></div></div>{history.map((event) => <div className="audit-row" key={event.event_id}><strong>{event.action.replaceAll(".", " ")}</strong><span>{event.actor_sub}</span><time>{new Date(event.created_at).toLocaleString()}</time></div>)}</section> : null}
  </section>;
}
