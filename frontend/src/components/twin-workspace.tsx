"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, type Business } from "@/lib/api";

type Period = {start:string; end:string; days:number};
type Value = string | number | null;
type Snapshot = {id:string; name:string; created_at:string; content_hash:string; implementation_version:string; period:Period; currency:string; demo_records:number};
type Provenance = {kind:string; recorded_at:string; definition:string; sources:Record<string,unknown>};
type State = {
  captured_at:string; period:Period; business:{name:string;currency:string;timezone:string}; metrics:Record<string,Value>; metric_provenance:Record<string,Provenance>;
  demo_records:number; counts:Record<string,number>; data_updated_at:string|null; inventory_value:string|null;
  inventory:{sku:string;name:string;quantity:string;value:string|null;days_cover:string|null;below_seven_days_cover:boolean;is_demo:boolean}[]|null;
  customers:{total:number;active_in_period:number;eligible_retention:number;retained:number;retention_pct:string|null}; orders:Record<string,number>;
  suppliers:{total:number;linked_products:number;purchasing_state:string}; health:{key:string;status:string;detail:string}[]; assumptions:string[];
  source_versions:Record<string,{records:number;sha256:string}>;
  forecasts:{run_id:string;task:string;algorithm:string;data_scope:string;created_at:string;config:Record<string,unknown>;result:Record<string,unknown>}[];
};
type Detail = {state:State; integrity?:string};
type Comparison = {same_period:boolean;equal_period_length:boolean;definition:string;source_changes:string[];metrics:Record<string,{before:Value;after:Value;absolute_change:Value;percentage_change:Value;unit:string}>};
type Sources = {items:Record<string,unknown>[];total:number;source_hash:string;definition:string};
const label = (value:string) => value.replaceAll("_"," ");
const show = (value:unknown) => value === null || value === undefined ? "Incomplete / undefined" : typeof value === "object" ? JSON.stringify(value) : String(value);

function dates(timezone:string) {
  const today = new Intl.DateTimeFormat("en-CA",{timeZone:timezone,year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
  const end=new Date(`${today}T12:00:00Z`); end.setUTCDate(end.getUTCDate()-1);
  const start=new Date(end); start.setUTCDate(start.getUTCDate()-29);
  return {start:start.toISOString().slice(0,10),end:end.toISOString().slice(0,10)};
}

export function TwinWorkspace({business,csrf}:{business:Business;csrf:string}) {
  const defaults=dates(business.timezone);
  const [start,setStart]=useState(defaults.start), [end,setEnd]=useState(defaults.end), [name,setName]=useState("");
  const [list,setList]=useState<Snapshot[]>([]), [selected,setSelected]=useState("current"), [detail,setDetail]=useState<Detail|null>(null);
  const [left,setLeft]=useState(""), [right,setRight]=useState(""), [comparison,setComparison]=useState<Comparison|null>(null);
  const [resource,setResource]=useState("orders"), [offset,setOffset]=useState(0), [sources,setSources]=useState<Sources|null>(null);
  const [pending,setPending]=useState(false), [loading,setLoading]=useState(true), [sourceLoading,setSourceLoading]=useState(false), [error,setError]=useState(""), [notice,setNotice]=useState("");
  const path=`businesses/${business.id}/twin`;
  const canWrite=business.permissions.includes("twin:write");

  useEffect(()=>{
    const controller=new AbortController();
    async function load() {
      try {
        const [saved,current]=await Promise.all([api<Snapshot[]>(`${path}/snapshots`,{signal:controller.signal}),api<Detail>(`${path}/current?start=${defaults.start}&end=${defaults.end}`,{signal:controller.signal})]);
        if(!controller.signal.aborted){setList(saved);setDetail(current);}
      } catch(failure){if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"Twin unavailable");}
      finally{if(!controller.signal.aborted)setLoading(false);}
    }
    void load(); return ()=>controller.abort();
    // Workspace remounts this component when its business changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[path]);

  useEffect(()=>{
    setSources(null); if(selected==="current")return;
    const controller=new AbortController(); setSourceLoading(true);
    api<Sources>(`${path}/snapshots/${selected}/sources?resource=${resource}&offset=${offset}`,{signal:controller.signal})
      .then(value=>{if(!controller.signal.aborted)setSources(value);})
      .catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"Sources unavailable");})
      .finally(()=>{if(!controller.signal.aborted)setSourceLoading(false);});
    return ()=>controller.abort();
  },[path,selected,resource,offset]);

  async function run(action:()=>Promise<void>) {
    setPending(true);setError("");setNotice("");
    try{await action();}catch(failure){setError(failure instanceof Error?failure.message:"Request failed");}finally{setPending(false);}
  }
  async function current(event:FormEvent){event.preventDefault();await run(async()=>{const [value,saved]=await Promise.all([api<Detail>(`${path}/current?start=${start}&end=${end}`),api<Snapshot[]>(`${path}/snapshots`)]);setDetail(value);setList(saved);setSelected("current");setOffset(0);});}
  async function save(){await run(async()=>{const value=await api<Snapshot&Detail>(`${path}/snapshots`,{method:"POST",csrf,body:{name,start,end}});setList(await api<Snapshot[]>(`${path}/snapshots`));setDetail(value);setSelected(value.id);setOffset(0);setNotice("Snapshot saved with source values. Later edits will not change it.");});}
  async function open(id:string){await run(async()=>{const value=await api<Detail>(id==="current"?`${path}/current?start=${start}&end=${end}`:`${path}/snapshots/${id}`);setDetail(value);setSelected(id);setOffset(0);});}
  const state=detail?.state;
  return <div className="twin-workspace">
    <section className="panel"><span className="eyebrow">BUSINESS STATE & HISTORY</span><h2>Digital twin</h2><p className="section-description">Capture the state of your business, trace its calculations and compare saved history.</p>
      {error&&<p className="notice error" role="alert">{error}</p>}{notice&&<p className="notice success" role="status">{notice}</p>}
      <form className="data-toolbar" onSubmit={event=>void current(event)}><fieldset disabled={pending||loading}><label>Reporting starts<input aria-label="Twin reporting starts" type="date" required value={start} onChange={event=>setStart(event.target.value)}/></label><label>Reporting ends<input aria-label="Twin reporting ends" type="date" required value={end} onChange={event=>setEnd(event.target.value)}/></label><button className="button secondary" type="submit">Refresh current state</button></fieldset></form>
      {canWrite&&<div className="data-toolbar"><label>Snapshot name<input aria-label="Snapshot name" maxLength={100} value={name} onChange={event=>setName(event.target.value)} placeholder="October review" disabled={pending}/></label><button className="button submit-button" disabled={pending||loading||!name.trim()||!start||!end} onClick={()=>void save()}>{pending?"Working…":"Save snapshot"}</button><small>Saves the latest source records for the dates above. Up to 50 snapshots.</small></div>}
      <label>State to inspect<select aria-label="State to inspect" disabled={pending||loading} value={selected} onChange={event=>void open(event.target.value)}><option value="current">Current preview</option>{list.map(row=><option key={row.id} value={row.id}>{row.name} · {row.period.start} – {row.period.end}</option>)}</select></label>
      {!loading&&!list.length&&<p className="section-description">No saved snapshots yet. The current preview is calculated from your recorded data.</p>}
    </section>
    {loading&&<section className="panel" role="status">Loading business state…</section>}
    {state&&<>
      <section className="panel"><h2>{selected==="current"?"Current business state":list.find(row=>row.id===selected)?.name??"Saved business state"}</h2><p>{state.period.start} – {state.period.end} · {state.business.currency} · {state.business.timezone}</p><p>Captured {state.captured_at} · Latest source update: {state.data_updated_at??"No records"}</p>{selected!=="current"&&<p className="notice">Saved evidence · {detail?.integrity==="verified_and_reproduced"?"Integrity verified and state reproduced":"Captured from stored source values"}</p>}{state.demo_records>0&&<p className="notice">Includes {state.demo_records} labelled demonstration records.</p>}
        <div className="business-facts">{Object.entries(state.metrics).map(([key,value])=><article key={key} className="panel"><span className="eyebrow">{label(key)}</span><strong>{show(value)}</strong></article>)}</div>
        <h3>Health indicators</h3><ul>{state.health.map(item=><li key={item.key}><strong>{label(item.key)} — {item.status}</strong><p>{item.detail}</p></li>)}</ul>
        <details><summary>Metric definitions & provenance</summary>{Object.entries(state.metric_provenance).map(([key,value])=><details key={key}><summary>{label(key)} · {value.kind}</summary><p>{value.definition}</p><p>Recorded at {value.recorded_at}</p><pre className="twin-evidence">{JSON.stringify(value.sources,null,2)}</pre></details>)}</details>
      </section>
      <section className="panel"><h2>Operations at capture</h2><p>Customers: {state.customers.total} · Active in period: {state.customers.active_in_period} · Retained: {state.customers.retained} of {state.customers.eligible_retention} eligible ({state.customers.retention_pct??"undefined"}%)</p><p>Orders in period: {Object.entries(state.orders).map(([key,value])=>`${key}: ${value}`).join(" · ")}</p><p>Suppliers: {state.suppliers.total} · Linked products: {state.suppliers.linked_products}</p><p>{state.suppliers.purchasing_state}</p>
        <h3>Current inventory at capture</h3><p>Value at current unit cost: {show(state.inventory_value)} {state.business.currency}. Stock belongs to the capture time, independently of the reporting-period end.</p>
        {state.inventory===null?<p>Inventory module disabled.</p>:!state.inventory.length?<p>No products recorded.</p>:<div className="table-scroll"><table><thead><tr><th>SKU</th><th>Product</th><th>Units</th><th>Value</th><th>Days cover</th></tr></thead><tbody>{state.inventory.map(row=><tr key={row.sku}><td>{row.sku}</td><td>{row.name}{row.is_demo&&" · Demo"}</td><td>{row.quantity}</td><td>{show(row.value)}</td><td>{row.days_cover??"No recorded demand"}{row.below_seven_days_cover&&" · Below 7 days"}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="panel"><h2>Forecasts at their saved cutoff</h2>{!state.forecasts.length?<p>No active model was selected at capture. Review and activate an evaluated model in Forecasts & risk, then capture a new state.</p>:state.forecasts.map(row=><details key={row.run_id}><summary>{label(row.task)} · {row.algorithm} · {row.data_scope} records</summary><p>Run {row.run_id} · Saved {row.created_at}. Forecast values are estimates at the original cutoff.</p><pre className="twin-evidence">{JSON.stringify({configuration:row.config,result:row.result},null,2)}</pre></details>)}<details><summary>Assumptions & limits</summary><ul>{state.assumptions.map(value=><li key={value}>{value}</li>)}</ul></details></section>
      <section className="panel"><h2>Source versions</h2><div className="table-scroll"><table><thead><tr><th>Source</th><th>Records</th><th>SHA-256 version</th></tr></thead><tbody>{Object.entries(state.source_versions).map(([key,value])=><tr key={key}><td>{label(key)}</td><td>{value.records}</td><td><code className="twin-hash">{value.sha256}</code></td></tr>)}</tbody></table></div>
        {selected!=="current"&&<><h3>Inspect saved source values</h3><label>Source resource<select aria-label="Snapshot source resource" value={resource} onChange={event=>{setResource(event.target.value);setOffset(0);}}>{Object.keys(state.source_versions).map(key=><option key={key} value={key}>{label(key)}</option>)}</select></label>{sourceLoading?<p role="status">Loading saved sources…</p>:sources&&<><p>{sources.definition} · {sources.total} records</p><div className="table-scroll"><table><thead><tr>{Object.keys(sources.items[0]??{}).map(key=><th key={key}>{label(key)}</th>)}</tr></thead><tbody>{sources.items.map((row,index)=><tr key={index}>{Object.values(row).map((value,column)=><td key={column}>{show(value)}</td>)}</tr>)}</tbody></table></div>{!sources.total&&<p>No records in this source.</p>}<div className="row-actions"><button className="button secondary" disabled={offset===0} onClick={()=>setOffset(value=>Math.max(0,value-25))}>Previous sources</button><button className="button secondary" disabled={offset+25>=sources.total} onClick={()=>setOffset(value=>value+25)}>Next sources</button></div></>}</>}
      </section>
    </>}
    <section className="panel"><h2>Compare saved snapshots</h2><p className="section-description">Compare reporting periods or see how corrections changed the same period. Differences use the right snapshot minus the left.</p>{list.length<2?<p>Save at least two snapshots to compare.</p>:<><div className="data-toolbar"><label>Left snapshot<select aria-label="Left snapshot" value={left} disabled={pending} onChange={event=>{setLeft(event.target.value);setComparison(null);}}><option value="">Choose a snapshot</option>{list.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Right snapshot<select aria-label="Right snapshot" value={right} disabled={pending} onChange={event=>{setRight(event.target.value);setComparison(null);}}><option value="">Choose a snapshot</option>{list.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label><button className="button secondary" disabled={pending||!left||!right||left===right} onClick={()=>void run(async()=>setComparison(await api<Comparison>(`${path}/compare?left=${left}&right=${right}`)))}>Compare snapshots</button></div>{comparison&&<><p>{comparison.definition}</p>{!comparison.equal_period_length&&<p className="notice">These periods have different lengths. Totals are not normalized.</p>}<p>{comparison.same_period?"Same reporting period":"Different reporting periods"} · Changed sources: {comparison.source_changes.join(", ")||"None"}</p><div className="table-scroll"><table><thead><tr><th>Metric</th><th>Left</th><th>Right</th><th>Change</th><th>% change</th></tr></thead><tbody>{Object.entries(comparison.metrics).map(([key,row])=><tr key={key}><td>{label(key)}</td><td>{show(row.before)}</td><td>{show(row.after)}</td><td>{show(row.absolute_change)} {row.unit}</td><td>{row.percentage_change===null?"Undefined":`${row.percentage_change}%`}</td></tr>)}</tbody></table></div></>}</>}
    </section>
  </div>;
}
