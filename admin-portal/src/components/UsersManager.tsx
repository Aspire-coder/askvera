import { useEffect, useMemo, useState } from "react";
import { AdminApi, type AdminCredentials } from "../api";
import type { AdminAuditEvent, AdminConfig, AdminScope, AdminUser } from "../types";

const sections = [
  { id: "knowledge", label: "Knowledge", permissions: ["view", "stage", "publish"] },
  { id: "insights", label: "Insights", permissions: ["view"] },
  { id: "flow", label: "Live flow", permissions: ["view"] },
  { id: "widget", label: "Widget config", permissions: ["view", "manage"] },
  { id: "users", label: "Users", permissions: ["view", "manage"] },
  { id: "audit", label: "Audit log", permissions: ["view"] }
];

function summary(role: string, scopes: AdminScope[]) {
  if (role === "super_admin") return "This user will have full access to every market and admin section.";
  if (role === "auditor") return "This user will have read-only access to the user list and audit history.";
  if (!scopes.length) return "Choose at least one market and section permission.";
  const markets = [...new Set(scopes.map((scope) => scope.market))].join(", ");
  const access = [...new Set(scopes.map((scope) => `${scope.section} (${scope.permission})`))].join(", ");
  return `This user will have ${access} access for ${markets}.`;
}

export function UsersManager({ credentials, config }: { credentials: AdminCredentials; config: AdminConfig }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [marketFilter, setMarketFilter] = useState("");
  const [auditEvents, setAuditEvents] = useState<AdminAuditEvent[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("country_admin");
  const [markets, setMarkets] = useState<string[]>([]);
  const [sectionPermissions, setSectionPermissions] = useState<Record<string, string>>({ knowledge: "view" });
  const api = useMemo(() => new AdminApi(credentials), [credentials.accessToken, credentials.apiKey]);
  const canViewAudit = !config.rbacEnabled
    || config.principal?.role === "super_admin"
    || Boolean(config.principal?.scopes.some((scope) => scope.section === "audit"));

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setUsers(await api.users());
      if (canViewAudit) setAuditEvents(await api.auditEvents());
    }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Users could not be loaded."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [api, canViewAudit]);

  const scopes = useMemo<AdminScope[]>(() => {
    if (role === "super_admin") return [];
    if (role === "auditor") return [
      { market: "*", section: "users", permission: "view" },
      { market: "*", section: "audit", permission: "view" }
    ];
    const allowedSections = role === "country_admin"
      ? new Set(["knowledge", "insights", "flow"])
      : new Set(["knowledge", "insights", "flow", "widget"]);
    return markets.flatMap((market) => Object.entries(sectionPermissions)
      .filter(([section, permission]) => allowedSections.has(section) && Boolean(permission))
      .map(([section, permission]) => ({ market, section, permission })));
  }, [markets, role, sectionPermissions]);

  const filtered = users.filter((user) => {
    const matchesSearch = !query || user.email.toLowerCase().includes(query.toLowerCase());
    const matchesMarket = !marketFilter || user.scopes.some((scope) => scope.market === marketFilter || scope.market === "*");
    return matchesSearch && matchesMarket && (!roleFilter || user.role === roleFilter);
  });

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
    setEmail("");
    setRole("country_admin");
    setMarkets([]);
    setSectionPermissions({ knowledge: "view" });
  };
  useEffect(() => {
    if (!showForm) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") closeForm(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showForm]);

  const edit = (user: AdminUser) => {
    setEditing(user);
    setEmail(user.email);
    setRole(user.role);
    setMarkets([...new Set(user.scopes.map((scope) => scope.market).filter((market) => market !== "*"))]);
    setSectionPermissions(Object.fromEntries(user.scopes.map((scope) => [scope.section, scope.permission])));
    setShowForm(true);
  };

  const save = async () => {
    if (!editing && !email.trim()) { setError("Enter an email address."); return; }
    if (role !== "super_admin" && !scopes.length) { setError("Choose at least one market and permission."); return; }
    setSaving(true);
    setError("");
    try {
      if (editing) {
        await api.updateUser(editing.id, { role, scopes });
        setNotice("Access updated.");
      } else {
        await api.createUser({ email: email.trim(), role, scopes });
        setNotice(`Invite sent. ${email.trim()} will receive a temporary password by email.`);
      }
      closeForm();
      await load();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "The user could not be saved.");
    } finally { setSaving(false); }
  };

  const toggle = async (user: AdminUser) => {
    const enabling = user.status === "disabled";
    if (!enabling && !window.confirm(`Terminate access for ${user.email}? They will be unable to sign in immediately.`)) return;
    try {
      await api.setUserEnabled(user.id, enabling);
      setNotice(enabling ? "Access restored." : "Access terminated.");
      await load();
    } catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Access could not be updated."); }
  };

  return <section className="page-section">
    <div className="page-heading"><div><span className="eyebrow">Access control</span><h1>Users</h1><p>Invite administrators and give each person only the markets and tools they need.</p></div><button className="button primary" onClick={() => setShowForm(true)}>Add user</button></div>
    {notice ? <div className="admin-toast success" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss">x</button></div> : null}
    {error ? <div className="admin-toast error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss">x</button></div> : null}
    <div className="user-toolbar surface"><input aria-label="Search users" placeholder="Search by email" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="Filter by role" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option value="">All roles</option><option value="super_admin">Super Admin</option><option value="country_admin">Country Admin</option><option value="section_scoped">Section-scoped</option><option value="auditor">Auditor</option></select><select aria-label="Filter by market" value={marketFilter} onChange={(event) => setMarketFilter(event.target.value)}><option value="">All markets</option>{config.countries.map((market) => <option key={market.code} value={market.code}>{market.name}</option>)}</select></div>
    <div className="user-list surface">
      {loading ? <div className="empty-state">Loading users...</div> : filtered.map((user) => <article className="user-row" key={user.id}>
        <div><strong>{user.email}</strong><small>{user.role.replaceAll("_", " ")} / {user.scopes.map((scope) => scope.market).filter((value, index, all) => all.indexOf(value) === index).join(", ") || "All markets"}</small></div>
        <span className={`status-pill ${user.status}`}>{user.status}</span>
        <small>{user.last_login ? `Last sign-in ${new Date(user.last_login).toLocaleString()}` : "Not signed in yet"}</small>
        <div><button className="button secondary" onClick={() => edit(user)}>Edit</button>{user.status === "invited" ? <button className="button secondary" onClick={() => void api.resendInvite(user.id).then(() => setNotice("Invitation resent.")).catch((nextError) => setError(nextError instanceof Error ? nextError.message : "Invitation could not be resent."))}>Resend invite</button> : null}<button className="button secondary" onClick={() => void toggle(user)}>{user.status === "disabled" ? "Enable" : "Terminate access"}</button></div>
      </article>)}
      {!loading && !filtered.length ? <div className="empty-state">No users match these filters.</div> : null}
    </div>
    {canViewAudit ? <section className="audit-list surface" aria-labelledby="audit-title"><div className="section-heading"><div><span className="eyebrow">Read-only history</span><h2 id="audit-title">Recent access changes</h2></div></div>{auditEvents.map((event) => <div className="audit-row" key={event.event_id}><strong>{event.action.replaceAll(".", " ")}</strong><span>{event.target_type}</span><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></div>)}{!loading && !auditEvents.length ? <div className="empty-state">No access changes have been recorded yet.</div> : null}</section> : null}
    {showForm ? <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeForm(); }}><section className="admin-form-modal" role="dialog" aria-modal="true" aria-labelledby="user-form-title">
      <button className="drawer-close" onClick={closeForm} aria-label="Close">x</button><span className="eyebrow">{editing ? "Edit access" : "New administrator"}</span><h2 id="user-form-title">{editing ? editing.email : "Invite a user"}</h2>
      {!editing ? <label><span>Email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoFocus /></label> : null}
      <label><span>Role template</span><select value={role} onChange={(event) => setRole(event.target.value)}><option value="super_admin">Super Admin</option><option value="country_admin">Country Admin</option><option value="section_scoped">Section-scoped user</option><option value="auditor">Auditor</option></select></label>
      {role !== "super_admin" && role !== "auditor" ? <><fieldset><legend>Markets</legend><div className="choice-grid">{config.countries.map((market) => <label key={market.code}><input type="checkbox" checked={markets.includes(market.code)} onChange={() => setMarkets((current) => current.includes(market.code) ? current.filter((item) => item !== market.code) : [...current, market.code])} />{market.name}</label>)}</div></fieldset><fieldset><legend>Section permissions</legend>{sections.filter((section) => role === "country_admin" ? ["knowledge", "insights", "flow"].includes(section.id) : !["users", "audit"].includes(section.id)).map((section) => <label className="permission-row" key={section.id}><span>{section.label}</span><select value={sectionPermissions[section.id] || ""} onChange={(event) => setSectionPermissions((current) => ({ ...current, [section.id]: event.target.value }))}><option value="">No access</option>{section.permissions.map((permission) => <option key={permission}>{permission}</option>)}</select></label>)}</fieldset></> : null}
      <div className="access-summary">{summary(role, scopes)}</div>
      <div className="modal-actions"><button className="button secondary" onClick={closeForm}>Cancel</button><button className="button primary" disabled={saving} onClick={() => void save()}>{saving ? "Saving..." : editing ? "Save access" : "Send invite"}</button></div>
    </section></div> : null}
  </section>;
}
