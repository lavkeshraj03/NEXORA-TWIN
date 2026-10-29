"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, type Business } from "@/lib/api";

type Change={baseline:string|null;scenario:string|null;absolute_change:string|null;percentage_change:string|null;unit:string};
type Result={kind:string;currency:string;demo_records_present:boolean;baseline_period:{start:string;end:string};baseline_captured_at:string;metrics:Record<string,string|null>;changes:Record<string,Change>;demand_units:string;replenishment_cash_outlay:string;warnings:string[];methodology:string[];inventory:Record<string,unknown>[]|null;sensitivity:{elasticity:string;metrics:Record<string,string|null>;demand_units:string}[];sensitivity_extremes:{best_operating_profit:string|null;worst_operating_profit:string|null;definition:string}};
type Run={id:string;name:string;baseline_snapshot_id:string;created_at:string;content_hash:string};
type Detail=Run&{result:Result;parameters:Record<string,unknown>;integrity:string};
type Snapshot={id:string;name:string;period:{start:string;end:string}};
type Preview={preview_hash:string;parameters:Record<string,unknown>;result:Result};
const numericFields=[
  ["price_change_pct","Product price change (%)",-90,200], ["demand_change_pct","Additional demand change (%)",-100,200],
  ["unit_cost_change_pct","Supplier / unit-cost change (%)",-100,200], ["marketing_change_pct","Marketing expense change (%)",-100,300],
  ["employee_cost_change_pct","Payroll expense change (%)",-100,200], ["customer_loss_pct","Additional demand lost to customer inactivity (%)",0,100],
] as const;
const initial=Object.fromEntries(numericFields.map(([key])=>[key,"0"]));
const label=(value:string)=>value.replaceAll("_"," ");
const show=(value:unknown)=>value===null||value===undefined?"Incomplete / undefined":String(value);

function Changes({changes,left="Historical baseline",right="Hypothetical scenario"}:{changes:Record<string,Change>;left?:string;right?:string}){
  return <div className="table-scroll"><table><thead><tr><th>Metric</th><th>{left}</th><th>{right}</th><th>Change</th><th>% change</th></tr></thead><tbody>{Object.entries(changes).map(([key,row])=><tr key={key}><td>{label(key)}</td><td>{show(row.baseline)}</td><td>{show(row.scenario)}</td><td>{show(row.absolute_change)} {row.unit==="percentage_points"?"percentage points":""}</td><td>{row.percentage_change===null?"Undefined":`${row.percentage_change}%`}</td></tr>)}</tbody></table></div>;
}

export function SimulationWorkspace({business,csrf}:{business:Business;csrf:string}){
  const [snapshots,setSnapshots]=useState<Snapshot[]>([]),[runs,setRuns]=useState<Run[]>([]),[baseline,setBaseline]=useState("");
  const [name,setName]=useState(""),[sku,setSku]=useState(""),[supplier,setSupplier]=useState(""),[values,setValues]=useState(initial);
  const [elasticity,setElasticity]=useState(""),[cases,setCases]=useState("-0.5,-1,-2"),[incoming,setIncoming]=useState("0"),[purchaseCost,setPurchaseCost]=useState(""),[stock,setStock]=useState(false);
  const [preview,setPreview]=useState<Preview|null>(null),[confirmed,setConfirmed]=useState(false),[detail,setDetail]=useState<Detail|null>(null),[selected,setSelected]=useState("");
  const [left,setLeft]=useState(""),[right,setRight]=useState(""),[comparison,setComparison]=useState<{changes:Record<string,Change>;definition:string}|null>(null);
  const [loading,setLoading]=useState(true),[pending,setPending]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const path=`businesses/${business.id}/simulations`;
  const canRun=business.permissions.includes("simulation:run");
  useEffect(()=>{
    const controller=new AbortController();
    Promise.all([api<Snapshot[]>(`businesses/${business.id}/twin/snapshots`,{signal:controller.signal}),api<Run[]>(`${path}/runs`,{signal:controller.signal})])
      .then(([saved,history])=>{if(!controller.signal.aborted){setSnapshots(saved);setRuns(history);setBaseline(saved[0]?.id??"");}})
      .catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"What-If Lab unavailable");})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[business.id,path]);
  function invalidate(){setPreview(null);setConfirmed(false);}
  async function action(operation:()=>Promise<void>){setPending(true);setError("");setNotice("");try{await operation();}catch(failure){setError(failure instanceof Error?failure.message:"Request failed");}finally{setPending(false);}}
  async function inspect(event:FormEvent){event.preventDefault();await action(async()=>{
    const body={name,baseline_snapshot_id:baseline,product_sku:sku.trim()||null,supplier_external_id:supplier.trim()||null,...values,price_elasticity:elasticity||null,replenishment_units:incoming,replenishment_unit_cost:purchaseCost||null,stock_constrained:stock,sensitivity_elasticities:values.price_change_pct!=="0"?cases.split(",").map(value=>value.trim()).filter(Boolean):[]};
    setPreview(await api<Preview>(`${path}/preview`,{method:"POST",csrf,body}));setConfirmed(false);
  });}
  async function save(){if(!preview)return;await action(async()=>{
    const saved=await api<Detail>(`${path}/runs`,{method:"POST",csrf,body:{...preview.parameters,preview_hash:preview.preview_hash,assumptions_confirmed:confirmed}});
    setDetail(saved);setSelected(saved.id);setRuns(await api<Run[]>(`${path}/runs`));setNotice("Hypothetical scenario saved. Operational records were not changed.");setPreview(null);setConfirmed(false);
  });}
  const sameBaseline=runs.filter(row=>!left||row.baseline_snapshot_id===runs.find(item=>item.id===left)?.baseline_snapshot_id);
  return <div className="simulation-workspace twin-workspace">
    <section className="panel"><span className="eyebrow">TEST YOUR ASSUMPTIONS</span><h2>What-If Lab</h2><p className="section-description">Calculate hypothetical outcomes from a saved twin baseline. Scenarios preserve assumptions and never change your orders, expenses or stock.</p>
      {error&&<p className="notice error" role="alert">{error}</p>}{notice&&<p className="notice success" role="status">{notice}</p>}{loading&&<p role="status">Loading baselines and scenarios…</p>}
      {!loading&&!snapshots.length&&<p>Save a snapshot in Digital twin first, then reopen What-If Lab.</p>}
      {canRun&&snapshots.length>0&&<form className="scenario-form" onSubmit={event=>void inspect(event)} onChange={invalidate}><fieldset disabled={loading||pending}>
        <label>Scenario name<input aria-label="Scenario name" required maxLength={100} value={name} onChange={event=>setName(event.target.value)}/></label>
        <label>Baseline snapshot<select aria-label="Scenario baseline" value={baseline} onChange={event=>setBaseline(event.target.value)}>{snapshots.map(row=><option key={row.id} value={row.id}>{row.name} · {row.period.start} – {row.period.end}</option>)}</select></label>
        <label>Product SKU — blank applies to all products<input aria-label="Scenario product SKU" value={sku} maxLength={80} onChange={event=>setSku(event.target.value)} placeholder="NX-PEN-01"/></label>
        <label>Supplier reference — optional cost scope<input aria-label="Scenario supplier reference" value={supplier} maxLength={80} onChange={event=>setSupplier(event.target.value)} placeholder="NX-SUP-01"/></label>
        {numericFields.map(([key,title,min,max])=><label key={key}>{title}<input aria-label={title} type="number" min={min} max={max} step="0.01" required value={values[key]} onChange={event=>setValues(current=>({...current,[key]:event.target.value}))}/></label>)}
        <label>Price elasticity assumption<input aria-label="Price elasticity assumption" type="number" min={-5} max={0} step="0.001" required={Number(values.price_change_pct)!==0} value={elasticity} onChange={event=>setElasticity(event.target.value)} placeholder="Required for price changes; e.g. -1"/></label>
        <label>Sensitivity elasticities — comma separated<input aria-label="Sensitivity elasticities" value={cases} onChange={event=>setCases(event.target.value)} placeholder="-0.5,-1,-2"/></label>
        <label>Incoming units — requires a product SKU<input aria-label="Scenario incoming units" type="number" min={0} max={1000000} step="0.001" required value={incoming} onChange={event=>setIncoming(event.target.value)}/></label>
        <label>Replenishment unit cost — blank uses saved current cost<input aria-label="Scenario replenishment unit cost" type="number" min={0} max={1000000000} step="0.0001" value={purchaseCost} onChange={event=>setPurchaseCost(event.target.value)}/></label>
        <label className="inline-check scenario-stock"><input type="checkbox" checked={stock} onChange={event=>setStock(event.target.checked)}/>Limit hypothetical sales to captured stock plus incoming units</label>
        <p className="scenario-explanation">Elasticity and customer loss are explicit assumptions. Marketing and payroll changes adjust recorded costs; demand benefits must be supplied separately. Replenishment cash is reported separately from profit.</p>
        <button className="button submit-button" type="submit">{pending?"Working…":"Preview assumptions"}</button>
      </fieldset></form>}
      {preview&&<div className="scenario-preview"><h3>Review before saving</h3><p className="notice">Hypothetical preview · {preview.result.currency} · {preview.result.baseline_period.start} – {preview.result.baseline_period.end}</p><pre className="twin-evidence">{JSON.stringify(preview.parameters,null,2)}</pre><ul>{preview.result.methodology.map(value=><li key={value}>{value}</li>)}{preview.result.warnings.map(value=><li key={value}>{value}</li>)}</ul>
        <label className="inline-check"><input aria-label="Confirm scenario assumptions" type="checkbox" checked={confirmed} disabled={pending} onChange={event=>setConfirmed(event.target.checked)}/>I reviewed these assumptions and understand this is a hypothetical calculation.</label><button className="button submit-button" disabled={pending||!confirmed} onClick={()=>void save()}>Run & save scenario</button>
      </div>}
      <label>Saved scenario<select aria-label="Saved scenario" value={selected} disabled={pending||loading} onChange={event=>{const id=event.target.value;if(!id){setSelected("");setDetail(null);return;}void action(async()=>{setDetail(await api<Detail>(`${path}/runs/${id}`));setSelected(id);});}}><option value="">Choose a saved scenario</option>{runs.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>{!loading&&!runs.length&&<p>No saved scenarios yet.</p>}
    </section>
    {detail&&<section className="panel"><h2>{detail.name}</h2><p className="notice">HYPOTHETICAL SIMULATION · {detail.result.currency} · Integrity verified and result reproduced</p>{detail.result.demo_records_present&&<p className="notice">Baseline includes labelled demonstration records.</p>}<p>Historical baseline: {detail.result.baseline_period.start} – {detail.result.baseline_period.end} · Captured {detail.result.baseline_captured_at}</p><Changes changes={detail.result.changes}/><p>Planned demand: {detail.result.demand_units} units. Replenishment cash outlay: {detail.result.replenishment_cash_outlay} {detail.result.currency}, separate from operating profit.</p>{detail.result.warnings.map(value=><p key={value} className="notice">{value}</p>)}
      {detail.result.inventory&&<><h3>Hypothetical inventory</h3><div className="table-scroll"><table><thead><tr><th>SKU</th><th>Starting stock</th><th>Incoming</th><th>Demand</th><th>Fulfilled</th><th>Unfulfilled</th><th>Closing stock</th><th>Additional supply needed</th></tr></thead><tbody>{detail.result.inventory.map(row=><tr key={String(row.sku)}>{["sku","current_stock","incoming_units","planned_demand","fulfilled_units","unfulfilled_units","projected_closing_units","additional_units_needed"].map(key=><td key={key}>{show(row[key])}</td>)}</tr>)}</tbody></table></div></>}
      <h3>Elasticity sensitivity</h3>{!detail.result.sensitivity.length?<p>No elasticity sensitivity cases were requested for a price change.</p>:<><div className="table-scroll"><table><thead><tr><th>Assumed elasticity</th><th>Demand units</th><th>Revenue</th><th>Operating profit</th></tr></thead><tbody>{detail.result.sensitivity.map(row=><tr key={row.elasticity}><td>{row.elasticity}</td><td>{row.demand_units}</td><td>{show(row.metrics.revenue)}</td><td>{show(row.metrics.operating_profit)}</td></tr>)}</tbody></table></div><p>{detail.result.sensitivity_extremes.definition} Best: {show(detail.result.sensitivity_extremes.best_operating_profit)}. Worst: {show(detail.result.sensitivity_extremes.worst_operating_profit)}.</p></>}
      <details><summary>Saved assumptions, method & evidence</summary><p>Baseline snapshot {detail.baseline_snapshot_id} · Simulation SHA-256 {detail.content_hash}</p><pre className="twin-evidence">{JSON.stringify(detail.parameters,null,2)}</pre><ul>{detail.result.methodology.map(value=><li key={value}>{value}</li>)}</ul></details>
      <a className="button secondary" href={`/api/backend/${path}/runs/${detail.id}/export`}>Download scenario CSV ↗</a>
    </section>}
    <section className="panel"><h2>Compare scenarios</h2><p>Choose two scenarios using the same saved baseline.</p>{runs.length<2?<p>Save at least two scenarios to compare.</p>:<><div className="data-toolbar"><label>Left scenario<select aria-label="Left scenario" value={left} disabled={pending} onChange={event=>{setLeft(event.target.value);setRight("");setComparison(null);}}><option value="">Choose a scenario</option>{runs.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Right scenario<select aria-label="Right scenario" value={right} disabled={pending} onChange={event=>{setRight(event.target.value);setComparison(null);}}><option value="">Choose a scenario</option>{sameBaseline.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label><button className="button secondary" disabled={pending||!left||!right||left===right} onClick={()=>void action(async()=>setComparison(await api(`${path}/compare?left=${left}&right=${right}`)))}>Compare scenarios</button></div>{comparison&&<><p>{comparison.definition}</p><Changes changes={comparison.changes} left="Left scenario" right="Right scenario"/></>}</>}
    </section>
  </div>;
}
