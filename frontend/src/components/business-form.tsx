"use client";
import { useState, type FormEvent } from "react";
import { api, type Business, type BusinessInput, type Profiles } from "@/lib/api";

export function BusinessForm({ initial, profiles, csrf, onSaved, onCancel }: { initial?: Business; profiles: Profiles; csrf: string; onSaved: (business: Business) => void; onCancel?: () => void }) {
  const [type, setType] = useState(initial?.business_type ?? "retail");
  const [modules, setModules] = useState(initial?.modules ?? profiles.retail ?? []);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: BusinessInput = {name: String(form.get("name")), business_type: type, country: String(form.get("country")), currency: String(form.get("currency")), timezone: String(form.get("timezone")), reporting_month: Number(form.get("reporting_month")), modules};
    setPending(true); setError("");
    try { const business = await api<Business>(initial ? `businesses/${initial.id}` : "businesses", {method: initial ? "PUT" : "POST", body, csrf}); onSaved(business); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not save the business"); }
    finally { setPending(false); }
  }
  return <form className="business-form" onSubmit={event => void submit(event)}><fieldset disabled={pending}><div className="form-grid"><label>Business name<input name="name" required maxLength={100} defaultValue={initial?.name}/></label><label>Business type<select name="business_type" value={type} onChange={event => {setType(event.target.value); setModules(profiles[event.target.value] ?? []);}}>{Object.keys(profiles).map(key => <option value={key} key={key}>{key === "services" ? "Professional services" : key[0].toUpperCase()+key.slice(1)}</option>)}</select></label><label>Country code<input name="country" required pattern="[A-Z]{2}" maxLength={2} defaultValue={initial?.country ?? "IN"} aria-describedby="country-help"/><small id="country-help">Two letters, e.g. IN, US or GB</small></label><label>Currency<input name="currency" required pattern="[A-Z]{3}" maxLength={3} defaultValue={initial?.currency ?? "INR"}/></label><label>Timezone<input name="timezone" required defaultValue={initial?.timezone ?? "Asia/Kolkata"} maxLength={80}/></label><label>Reporting year starts<select name="reporting_month" defaultValue={initial?.reporting_month ?? 1}>{Array.from({length: 12}, (_, index) => <option key={index} value={index+1}>{new Date(2026,index,1).toLocaleString("en", {month:"long"})}</option>)}</select></label></div><span className="field-label">Business modules</span><div className="module-options">{(profiles[type] ?? []).map(module => <label key={module}><input type="checkbox" checked={modules.includes(module)} onChange={event => setModules(event.target.checked ? [...modules,module] : modules.filter(item => item !== module))}/>{module}</label>)}</div><div className="form-actions"><button type="submit" className="button submit-button" disabled={!modules.length}>{pending ? "Saving…" : initial ? "Save business settings" : "Create empty workspace"}</button>{onCancel && <button type="button" className="button secondary" onClick={onCancel}>Cancel</button>}</div></fieldset>{error && <p className="notice error" role="alert">{error}</p>}</form>;
}
