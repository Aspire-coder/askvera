import { useEffect, useMemo, useState } from "react";
import { AdminApi, type AdminCredentials } from "../api";
import type { AdminConfig, SupportRoute } from "../types";

export function SupportRoutesManager({ credentials, config }: { credentials: AdminCredentials; config: AdminConfig }) {
  const api = useMemo(() => new AdminApi(credentials), [credentials.accessToken, credentials.apiKey]);
  const [routes, setRoutes] = useState<SupportRoute[]>([]);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

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
        country: country.code, country_name: country.name, department: "", email: "",
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
    setSaving(route.country);
    setError("");
    try {
      await api.updateSupportRoute(route.country, {
        department: route.department.trim(), email: route.email.trim(), enabled: route.enabled
      });
      setNotice(`${route.country_name} routing saved.`);
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "The support route could not be saved.");
    } finally { setSaving(""); }
  };

  return <section className="page-section">
    <div className="page-heading"><div><span className="eyebrow">Customer handoff</span><h1>Support routing</h1><p>Choose where each market's support requests are delivered. Changes take effect without a code deployment.</p></div></div>
    {notice ? <div className="admin-toast success" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss">x</button></div> : null}
    {error ? <div className="admin-toast error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss">x</button></div> : null}
    <div className="user-toolbar surface"><label className="toolbar-field"><span>Market</span><select aria-label="Select support market" value={selectedRoute?.country || ""} onChange={(event) => setSelectedCountry(event.target.value)}>{rows.map((route) => <option key={route.country} value={route.country}>{route.country_name} ({route.country})</option>)}</select></label><span className="mode-note">Choose a market to edit its handoff route.</span></div>
    <div className="support-route-list surface">
      <div className="support-route-head"><span>Market</span><span>Department</span><span>Destination email</span><span>Active</span><span /></div>
      {selectedRoute ? [selectedRoute].map((route) => <div className="support-route-row" key={route.country}>
        <div><strong>{route.country_name}</strong><small>{route.country}</small></div>
        <input aria-label={`${route.country_name} department`} value={route.department} onChange={(event) => change(route.country, "department", event.target.value)} />
        <input type="email" aria-label={`${route.country_name} support email`} value={route.email} onChange={(event) => change(route.country, "email", event.target.value)} />
        <label className="route-toggle"><input type="checkbox" checked={route.enabled} onChange={(event) => change(route.country, "enabled", event.target.checked)} /><span>{route.enabled ? "On" : "Off"}</span></label>
        <button className="button primary" disabled={saving === route.country} onClick={() => void save(route)}>{saving === route.country ? "Saving..." : "Save"}</button>
      </div>) : null}
      {!selectedRoute ? <div className="empty-state">No markets are available.</div> : null}
    </div>
  </section>;
}
