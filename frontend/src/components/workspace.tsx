"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type AuditEvent, type Business, type Member, type Profiles, type Role, type SessionInfo } from "@/lib/api";
import { BusinessForm } from "@/components/business-form";
import { OperationalDashboard } from "@/components/operational-dashboard";
import { DataExplorer } from "@/components/data-explorer";
import { DataImporter } from "@/components/data-importer";
import { DocumentLibrary } from "@/components/document-library";
import { ForecastWorkspace } from "@/components/forecast-workspace";
import { TwinWorkspace } from "@/components/twin-workspace";
import { SimulationWorkspace } from "@/components/simulation-workspace";
import { AnalystWorkspace } from "@/components/analyst-workspace";
import { KnowledgeWorkspace } from "@/components/knowledge-workspace";
import { ReportsWorkspace } from "@/components/reports-workspace";

type Tab = "overview" | "twin" | "simulations" | "analyst" | "graph" | "reports" | "forecasts" | "documents" | "data" | "imports" | "settings" | "team" | "activity";
const roleLabels: Record<Role,string> = {owner: "Owner", administrator: "Administrator", analyst: "Analyst", viewer: "Viewer"};

function MemberRow({ member, actor, pending, change, remove }: { member: Member; actor: Role; pending: boolean; change: (id: string, role: Role) => void; remove: (id: string) => void }) {
  const [role, setRole] = useState<Role>(member.role);
  const canManage = actor === "owner" || (actor === "administrator" && ["analyst","viewer"].includes(member.role));
  const roles: Role[] = actor === "owner" ? ["owner","administrator","analyst","viewer"] : ["analyst","viewer"];
  return <tr><td><strong>{member.name}</strong><small>{member.email}</small></td><td>{canManage ? <select aria-label={`Role for ${member.name}`} value={role} disabled={pending} onChange={event => setRole(event.target.value as Role)}>{roles.map(item => <option key={item} value={item}>{roleLabels[item]}</option>)}</select> : roleLabels[member.role]}</td><td>{canManage && <div className="row-actions"><button className="button secondary" disabled={pending || role === member.role} onClick={() => change(member.user_id, role)}>Save role</button><button className="text-button danger" disabled={pending} onClick={() => {if (window.confirm(`Remove ${member.name} from this business?`)) remove(member.user_id);}}>Remove</button></div>}</td></tr>;
}

export function Workspace({ session }: { session: SessionInfo }) {
  const router = useRouter();
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [profiles, setProfiles] = useState<Profiles>({});
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Business | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const [reload, setReload] = useState(0);
  const business = detail?.id === selected ? detail : null;

  function handleError(failure: unknown) {
    if (failure instanceof ApiError && failure.status === 401) { router.replace("/login"); router.refresh(); }
    else setError(failure instanceof Error ? failure.message : "The request failed. Try again.");
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    Promise.all([api<Business[]>("businesses", {signal: controller.signal}), api<Profiles>("businesses/profiles", {signal: controller.signal})]).then(([list, configs]) => {
      if (!controller.signal.aborted) {setBusinesses(list); setProfiles(configs); setSelected(current => list.some(item => item.id === current) ? current : list[0]?.id ?? "");}
    }).catch(failure => {if (!controller.signal.aborted) handleError(failure);}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
    // The initial authenticated identity is fixed for this mounted workspace.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setMembers([]); setEvents([]); setError("");
    if (!selected) return () => controller.abort();
    setSwitching(true);
    async function load() {
      try {
        const item = await api<Business>(`businesses/${selected}`, {signal: controller.signal});
        const [team, logs] = await Promise.all([
          item.permissions.includes("team:read") ? api<Member[]>(`businesses/${selected}/members`, {signal: controller.signal}) : Promise.resolve([]),
          item.permissions.includes("audit:read") ? api<AuditEvent[]>(`businesses/${selected}/audit-logs?limit=25`, {signal: controller.signal}) : Promise.resolve([]),
        ]);
        if (!controller.signal.aborted) {setDetail(item); setMembers(team); setEvents(logs);}
      } catch (failure) {if (!controller.signal.aborted) handleError(failure);}
      finally {if (!controller.signal.aborted) setSwitching(false);}
    }
    void load();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, revision]);

  async function mutate(action: () => Promise<unknown>, message: string) {
    setPending(true); setError(""); setNotice("");
    try { await action(); setNotice(message); setRevision(value => value+1); }
    catch (failure) {handleError(failure);}
    finally {setPending(false);}
  }
  function saved(item: Business) {
    setBusinesses(current => [...current.filter(entry => entry.id !== item.id), item]);
    setSelected(item.id); setCreating(false); setTab("overview"); setNotice("Business settings saved."); setRevision(value => value+1);
  }
  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await mutate(() => api(`businesses/${selected}/members`, {method:"POST", csrf: session.csrf_token, body:{email:values.get("email"),role:values.get("role")}}), "Teammate added.");
  }
  async function logout() {
    setPending(true); setError("");
    try {await api("auth/logout", {method:"POST", csrf:session.csrf_token}); router.replace("/login"); router.refresh();}
    catch (failure) {handleError(failure); setPending(false);}
  }
  const tabs: {key:Tab; label:string; allowed:boolean}[] = [
    {key:"twin",label:"Digital twin",allowed:!!business?.permissions.includes("twin:read")},
    {key:"simulations",label:"What-If Lab",allowed:!!business?.permissions.includes("simulation:read")},
    {key:"analyst",label:"AI analyst",allowed:!!business?.permissions.includes("analyst:read")},
    {key:"graph",label:"Knowledge graph",allowed:!!business?.permissions.includes("graph:read")},
    {key:"reports",label:"Reports & exports",allowed:!!business?.permissions.includes("reports:read")},
    {key:"overview",label:"Overview",allowed:true}, {key:"forecasts",label:"Forecasts & risk",allowed:!!business?.permissions.includes("ml:read")}, {key:"documents",label:"Documents & answers",allowed:!!business?.permissions.includes("documents:read")}, {key:"data",label:"Data explorer",allowed:!!business?.permissions.includes("data:read")}, {key:"imports",label:"Import data",allowed:!!business?.permissions.includes("data:write")}, {key:"settings",label:"Business settings",allowed:!!business?.permissions.includes("business:write")},
    {key:"team",label:"Team",allowed:!!business?.permissions.includes("team:read")}, {key:"activity",label:"Audit history",allowed:!!business?.permissions.includes("audit:read")},
  ];
  return <div className="app-shell business-shell"><aside className="sidebar"><a className="brand" href="/"><span className="brand-mark">N</span>NEXORA <span className="brand-light">TWIN</span></a><div className="workspace-label">BUSINESS WORKSPACE</div><label className="tenant-select">Switch business<select aria-label="Switch business" value={selected} disabled={loading || pending} onChange={event => {setSelected(event.target.value); setTab("overview"); setCreating(false); setNotice("");}}>{businesses.length === 0 && <option value="">No businesses yet</option>}{businesses.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><nav aria-label="Business navigation">{tabs.filter(item => item.allowed).map(item => <button key={item.key} aria-current={tab === item.key && !creating ? "page" : undefined} className={`nav-link nav-button ${tab === item.key && !creating ? "active" : ""}`} onClick={() => {setTab(item.key); setCreating(false); setNotice("");}}>{item.label}</button>)}<a className="nav-link" href="/#system-health">System health ↗</a></nav><div className="sidebar-bottom"><div className="profile"><span className="avatar">{session.user.name.slice(0,2).toUpperCase()}</span><div><strong>{session.user.name}</strong><small>{session.user.email}</small></div></div><button className="sign-out" disabled={pending} onClick={() => void logout()}>Sign out →</button></div></aside><div className="main-shell"><header className="topbar"><span>Workspace / {business?.name ?? "Choose a business"}</span><span className="environment">{business ? roleLabels[business.role] : "Account"}</span></header><main id="main-content" tabIndex={-1}>
    <div className="page-title"><div><span className="eyebrow">YOUR CONNECTED BUSINESS</span><h1>{creating ? "Create a business." : business?.name ?? "Your workspace."}</h1><p>{creating ? "Configure an independent workspace for your business." : "A clear foundation for your next decision."}</p></div><button className="button submit-button" disabled={loading || pending || !Object.keys(profiles).length} onClick={() => {setCreating(true); setNotice("");}}>+ New business</button></div>
    {error && <div role="alert" className="notice error">{error} <button className="text-button" onClick={() => {setReload(value => value+1); setRevision(value => value+1);}}>Retry loading</button></div>}{notice && <p className="notice success" role="status">{notice}</p>}
    {loading ? <section className="panel loading-state" role="status">Loading your businesses…</section> : creating ? <section className="panel"><h2>Make it yours.</h2><p className="section-description">Select your profile and relevant modules. After creating the business, add records or open Import data.</p><BusinessForm profiles={profiles} csrf={session.csrf_token} onSaved={saved} onCancel={() => setCreating(false)}/></section> : businesses.length === 0 ? <section className="panel empty-state"><span className="empty-symbol">◇</span><h2>Every business starts somewhere.</h2><p>Create your first business to configure its workspace and team.</p><button className="button submit-button" disabled={!Object.keys(profiles).length} onClick={() => setCreating(true)}>Create your first business →</button></section> : switching || !business ? <section className="panel loading-state" role="status">Loading the selected business…</section> : <div key={business.id}>
    {tab === "overview" && <><div className="business-facts"><article className="panel"><span className="eyebrow">BUSINESS PROFILE</span><strong>{business.business_type === "services" ? "Professional services" : business.business_type}</strong></article><article className="panel"><span className="eyebrow">REPORTING CURRENCY</span><strong>{business.currency}</strong></article><article className="panel"><span className="eyebrow">TIMEZONE</span><strong>{business.timezone}</strong></article></div>{business.permissions.includes("data:read") ? <OperationalDashboard business={business} csrf={session.csrf_token}/> : <section className="panel empty-state"><h2>Your business workspace</h2><p>Operational data is unavailable for this role.</p></section>}</>}
    {tab === "data" && business.permissions.includes("data:read") && <DataExplorer business={business} csrf={session.csrf_token}/>}
    {tab === "imports" && business.permissions.includes("data:write") && <DataImporter business={business} csrf={session.csrf_token}/>}
    {tab === "forecasts" && business.permissions.includes("ml:read") && <ForecastWorkspace business={business} csrf={session.csrf_token}/>}
    {tab === "twin" && business.permissions.includes("twin:read") && <TwinWorkspace business={business} csrf={session.csrf_token}/>}
    {tab === "simulations" && business.permissions.includes("simulation:read") && <SimulationWorkspace business={business} csrf={session.csrf_token}/>}
    {tab === "analyst" && business.permissions.includes("analyst:read") && <AnalystWorkspace business={business} csrf={session.csrf_token}/>}
    {tab === "graph" && business.permissions.includes("graph:read") && <KnowledgeWorkspace business={business} csrf={session.csrf_token}/>}
    {tab === "reports" && business.permissions.includes("reports:read") && <ReportsWorkspace business={business} csrf={session.csrf_token}/>}
    {tab === "documents" && business.permissions.includes("documents:read") && <DocumentLibrary business={business} csrf={session.csrf_token}/>}
    {tab === "settings" && business.permissions.includes("business:write") && <section className="panel"><h2>Business settings</h2><p className="section-description">Changes apply only to this business.</p><BusinessForm initial={business} profiles={profiles} csrf={session.csrf_token} onSaved={saved}/></section>}
    {tab === "team" && business.permissions.includes("team:read") && <section className="panel"><h2>Your team</h2><p className="section-description">Each person can have a different role in every business.</p><div className="table-scroll"><table><thead><tr><th>Teammate</th><th>Business role</th><th>Access management</th></tr></thead><tbody>{members.map(member => <MemberRow key={`${member.user_id}-${member.role}`} member={member} actor={business.role} pending={pending} change={(id,role) => void mutate(() => api(`businesses/${selected}/members/${id}`, {method:"PATCH",csrf:session.csrf_token,body:{role}}), "Role updated.")} remove={id => void mutate(() => api(`businesses/${selected}/members/${id}`, {method:"DELETE",csrf:session.csrf_token}), "Member removed.")}/>)}</tbody></table></div>{business.permissions.includes("team:write") && <form className="team-form" onSubmit={event => void addMember(event)}><h3>Add an existing account</h3><p>The teammate must register first. No invitation email is sent.</p><fieldset disabled={pending}><label>Teammate email<input name="email" type="email" required maxLength={254}/></label><label>Role<select name="role" defaultValue="viewer">{(business.role === "owner" ? ["viewer","analyst","administrator","owner"] as Role[] : ["viewer","analyst"] as Role[]).map(role => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label><button className="button submit-button" type="submit">{pending ? "Saving…" : "Add teammate"}</button></fieldset></form>}</section>}
    {tab === "activity" && business.permissions.includes("audit:read") && <section className="panel"><h2>Audit history</h2><p className="section-description">The 25 most recent events for this business.</p>{events.length ? <ol className="audit-list">{events.map(event => <li key={event.id}><span className="dot green"/><div><strong>{event.event.replaceAll("."," · ").replaceAll("_"," ")}</strong><small>Actor: {event.user_id ?? "System"}{event.target_id && ` · Target: ${event.target_id}`}</small></div><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></li>)}</ol> : <p className="section-description">No audit events are available.</p>}</section>}
    </div>}<footer className="footer"><span>NEXORA TWIN</span><span>Business data & evaluated models</span></footer></main></div></div>;
}
