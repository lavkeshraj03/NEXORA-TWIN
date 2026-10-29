"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, type Business } from "@/lib/api";

type Saved={id:string;question:string;status:string;created_at:string;chat_model:string};
type Fact={id:string;evidence_id:string;text:string;kind:string;citation:null|{document_id:string;chunk_id:string;title:string;version:number;page:number|null;excerpt:string}};
type Execution={id:string;tool:string;permission:string;status:string;duration_ms:number;started_at:string;arguments:Record<string,unknown>;output?:Record<string,unknown>;error?:string;facts:Fact[]};
type Answer={answer:string;findings:Fact[];recommendations:string[];insufficient:boolean;demo_records:number;data_updated_at:string|null;limitations:string[];evidence_hash:string;chat_model:string;usage:unknown[]};
type Detail=Saved&{response:Answer|null;executions:Execution[];input_hash:string;captured_at:string;parameters:Record<string,unknown>;error?:string};
type Model={id:string;task:string;data_scope:string;algorithm:string;config:{end:string}};
type Scenario={id:string;name:string};
type Document={id:string;title:string;active_version:number};
type Sources={items:Record<string,unknown>[];total:number;source_hash:string;definition:string};
const resources=["orders","order_items","products","inventory","balances","customers","suppliers","expenses","expense_coverage"];
const label=(text:string)=>text.replaceAll("_"," ");
function dates(timezone:string){const today=new Intl.DateTimeFormat("en-CA",{timeZone:timezone,year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());const end=new Date(`${today}T12:00:00Z`);end.setUTCDate(end.getUTCDate()-1);const start=new Date(end);start.setUTCDate(start.getUTCDate()-29);return{start:start.toISOString().slice(0,10),end:end.toISOString().slice(0,10)};}

export function AnalystWorkspace({business,csrf}:{business:Business;csrf:string}){
  const initial=dates(business.timezone);
  const [question,setQuestion]=useState(""),[start,setStart]=useState(initial.start),[end,setEnd]=useState(initial.end),[sku,setSku]=useState("");
  const [scope,setScope]=useState("real"),[forecast,setForecast]=useState(""),[churn,setChurn]=useState(""),[scenario,setScenario]=useState(""),[secondScenario,setSecondScenario]=useState(""),[document,setDocument]=useState("");
  const [history,setHistory]=useState<Saved[]>([]),[models,setModels]=useState<Model[]>([]),[scenarios,setScenarios]=useState<Scenario[]>([]),[documents,setDocuments]=useState<Document[]>([]);
  const [selected,setSelected]=useState(""),[detail,setDetail]=useState<Detail|null>(null),[loading,setLoading]=useState(true),[pending,setPending]=useState(false),[error,setError]=useState("");
  const [resource,setResource]=useState("orders"),[offset,setOffset]=useState(0),[sources,setSources]=useState<Sources|null>(null),[sourceLoading,setSourceLoading]=useState(false);
  const path=`businesses/${business.id}/analyst`;
  const canAsk=business.permissions.includes("analyst:ask");
  useEffect(()=>{
    const controller=new AbortController();
    Promise.all([api<Saved[]>(`${path}/investigations`,{signal:controller.signal}),api<Model[]>(`businesses/${business.id}/ml/runs`,{signal:controller.signal}),api<Scenario[]>(`businesses/${business.id}/simulations/runs`,{signal:controller.signal}),api<Document[]>(`businesses/${business.id}/documents`,{signal:controller.signal})])
      .then(([saved,versions,whatifs,docs])=>{if(!controller.signal.aborted){setHistory(saved);setModels(versions);setScenarios(whatifs);setDocuments(docs.filter(row=>row.active_version>0));}})
      .catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"Analyst unavailable");})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[business.id,path]);
  useEffect(()=>{
    setSources(null);if(!selected||!detail)return;
    const controller=new AbortController();setSourceLoading(true);
    api<Sources>(`${path}/investigations/${selected}/sources?resource=${resource}&offset=${offset}`,{signal:controller.signal})
      .then(value=>{if(!controller.signal.aborted)setSources(value);})
      .catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"Sources unavailable");})
      .finally(()=>{if(!controller.signal.aborted)setSourceLoading(false);});
    return()=>controller.abort();
  },[path,selected,detail,resource,offset]);
  async function refresh(){setHistory(await api<Saved[]>(`${path}/investigations`));}
  async function action(operation:()=>Promise<void>){setPending(true);setError("");try{await operation();}catch(failure){setError(failure instanceof Error?failure.message:"Investigation failed");try{await refresh();}catch{}}finally{setPending(false);}}
  async function investigate(event:FormEvent){event.preventDefault();await action(async()=>{
    setDetail(null);setSelected("");setOffset(0);
    const body={question,start,end,product_sku:sku.trim()||null,model_data_scope:scope,forecast_run_id:forecast||null,churn_run_id:churn||null,scenario_run_ids:[scenario,secondScenario].filter(Boolean),document_ids:document?[document]:[]};
    const result=await api<Detail>(`${path}/investigations`,{method:"POST",csrf,body});setDetail(result);setSelected(result.id);await refresh();
  });}
  return <div className="analyst-workspace twin-workspace">
    <section className="panel"><span className="eyebrow">QUESTIONS WITH TRACEABLE EVIDENCE</span><h2>AI business analyst</h2><p className="section-description">Investigate recorded changes with a bounded set of tools. The analyst selects calculated facts and exact document excerpts; it does not change your business records.</p>
      {error&&<p className="notice error" role="alert">{error}</p>}{loading&&<p role="status">Loading analyst history and available evidence…</p>}
      {canAsk&&<form className="analyst-form" onSubmit={event=>void investigate(event)}><fieldset disabled={pending||loading}>
        <label className="analyst-question">Business question<textarea aria-label="Business question" required minLength={5} maxLength={1500} value={question} onChange={event=>setQuestion(event.target.value)} placeholder="How did recorded revenue, costs and profit change from the previous period?"/></label>
        <label>Reporting starts<input aria-label="Analyst reporting starts" type="date" required value={start} onChange={event=>setStart(event.target.value)}/></label><label>Reporting ends<input aria-label="Analyst reporting ends" type="date" required value={end} onChange={event=>setEnd(event.target.value)}/></label>
        <p className="analyst-explanation">These explicit dates control the analysis, including questions that say “this month”. Financial tools compare the preceding period of the same length and include labelled demo records.</p>
        <details className="analyst-options"><summary>Optional product, model, document and scenario scope</summary><div className="analyst-option-grid">
          <label>Product SKU<input aria-label="Analyst product SKU" maxLength={80} value={sku} onChange={event=>setSku(event.target.value)} placeholder="NX-PEN-01"/></label>
          <label>Saved model data<select aria-label="Analyst model data scope" value={scope} onChange={event=>{setScope(event.target.value);setForecast("");setChurn("");}}><option value="real">Real records only</option><option value="demo">Labelled demonstration records only</option></select></label>
          <label>Sales model<select aria-label="Analyst sales model" value={forecast} onChange={event=>setForecast(event.target.value)}><option value="">Use explicitly active model if available</option>{models.filter(row=>row.task==="sales"&&row.data_scope===scope).map(row=><option key={row.id} value={row.id}>{row.algorithm} · {row.config.end}</option>)}</select></label>
          <label>Customer inactivity model<select aria-label="Analyst inactivity model" value={churn} onChange={event=>setChurn(event.target.value)}><option value="">Use explicitly active model if available</option>{models.filter(row=>row.task==="churn"&&row.data_scope===scope).map(row=><option key={row.id} value={row.id}>{row.algorithm} · {row.config.end}</option>)}</select></label>
          <label>Document scope<select aria-label="Analyst document scope" value={document} onChange={event=>setDocument(event.target.value)}><option value="">All visible indexed documents</option>{documents.map(row=><option key={row.id} value={row.id}>{row.title}</option>)}</select></label>
          <label>Reviewed scenario<select aria-label="Analyst reviewed scenario" value={scenario} onChange={event=>{setScenario(event.target.value);setSecondScenario("");}}><option value="">No scenario selected</option>{scenarios.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label>Second scenario for comparison<select aria-label="Analyst comparison scenario" value={secondScenario} onChange={event=>setSecondScenario(event.target.value)} disabled={!scenario}><option value="">No second scenario selected</option>{scenarios.filter(row=>row.id!==scenario).map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        </div><p>Model estimates retain their original cutoff. Scenarios must already be reviewed and saved in What-If Lab; the analyst reproduces their assumptions without creating new ones.</p></details>
        <button className="button submit-button" type="submit">{pending?"Investigating…":"Investigate question"}</button>
      </fieldset></form>}
      {pending&&<p className="notice" role="status">Collecting evidence and checking findings. The local model may take a few minutes; operational records stay unchanged.</p>}
      <div className="data-toolbar"><label>Your saved investigations<select aria-label="Saved investigation" disabled={pending||loading} value={selected} onChange={event=>{const id=event.target.value;if(!id){setSelected("");setDetail(null);return;}void action(async()=>{setDetail(null);const value=await api<Detail>(`${path}/investigations/${id}`);setDetail(value);setSelected(id);setOffset(0);});}}><option value="">Choose an investigation</option>{history.map(row=><option key={row.id} value={row.id}>{row.status} · {row.question.slice(0,80)}</option>)}</select></label><button className="button secondary" disabled={pending||loading} onClick={()=>void action(refresh)}>Refresh investigation history</button></div>
      {!loading&&!history.length&&<p>No saved investigations yet. History is private to your account within this business.</p>}{!canAsk&&<p>Your role can inspect its saved history. An owner, administrator or analyst can start investigations.</p>}
    </section>
    {detail&&<>
      {detail.status==="partial"&&<p className="notice" role="status">Some tools failed. Findings use only the available evidence; inspect the execution trail.</p>}
      <section className="panel"><h2>{detail.question}</h2><p>Status: {detail.status} · Model: {detail.chat_model} · Operational values captured {detail.captured_at}</p>{detail.error&&<p className="notice error" role="alert">{detail.error}</p>}
        {detail.response&&<><p className="notice">{detail.response.insufficient?"Insufficient evidence for this question":"Evidence-backed findings; review the source context"}</p>{detail.response.demo_records>0&&<p className="notice">Includes {detail.response.demo_records} labelled demonstration records. These are synthetic examples.</p>}<div className="analyst-answer">{detail.response.answer}</div>
          <h3>Evidence references</h3>{detail.response.findings.map(fact=><article key={fact.id} className="analyst-finding"><span className="eyebrow">{fact.evidence_id} · {label(fact.kind)}</span><p>{fact.text}</p>{fact.citation&&<blockquote><strong>{fact.citation.title} · version {fact.citation.version}{fact.citation.page&&` · page ${fact.citation.page}`}</strong><p>{fact.citation.excerpt}</p><small>Document {fact.citation.document_id} · Chunk {fact.citation.chunk_id}</small></blockquote>}</article>)}
          {detail.response.recommendations.length>0&&<><h3>Review steps</h3><ul>{detail.response.recommendations.map(value=><li key={value}>{value}</li>)}</ul></>}
          <details><summary>Method, assumptions & limits</summary><ul>{detail.response.limitations.map(value=><li key={value}>{value}</li>)}</ul><p>Source SHA-256: <code className="twin-hash">{detail.input_hash}</code></p><p>Evidence SHA-256: <code className="twin-hash">{detail.response.evidence_hash}</code></p><pre className="twin-evidence">{JSON.stringify({parameters:detail.parameters,provider_usage:detail.response.usage},null,2)}</pre></details>
          <a className="button secondary" href={`/api/backend/${path}/investigations/${detail.id}/export`}>Download investigation CSV ↗</a>
        </>}{!detail.response&&<p>No generated answer was saved for this investigation. Inspect the execution status below.</p>}
      </section>
      <section className="panel"><h2>Tool execution trail</h2><p>At most four predefined tools. Dates, parameters, results and durations are recorded; no arbitrary SQL or operational actions are available.</p>{detail.executions.map(execution=><details key={execution.id}><summary>{execution.id} · {label(execution.tool)} · {execution.status} · {execution.duration_ms} ms</summary><p>Permission: {execution.permission} · Started {execution.started_at}</p>{execution.error&&<p className="notice error">{execution.error}</p>}<pre className="twin-evidence">{JSON.stringify({arguments:execution.arguments,result:execution.output},null,2)}</pre></details>)}</section>
      <section className="panel"><h2>Captured operational sources</h2><label>Source resource<select aria-label="Analyst source resource" value={resource} onChange={event=>{setResource(event.target.value);setOffset(0);}}>{resources.map(value=><option key={value} value={value}>{label(value)}</option>)}</select></label>{sourceLoading?<p role="status">Loading captured sources…</p>:sources&&<><p>{sources.definition} · {sources.total} records</p><div className="table-scroll"><table><thead><tr>{Object.keys(sources.items[0]??{}).map(key=><th key={key}>{label(key)}</th>)}</tr></thead><tbody>{sources.items.map((row,index)=><tr key={index}>{Object.values(row).map((value,column)=><td key={column}>{value===null?"Unknown":String(value)}</td>)}</tr>)}</tbody></table></div>{!sources.total&&<p>No records in this source.</p>}<div className="row-actions"><button className="button secondary" disabled={offset===0} onClick={()=>setOffset(value=>Math.max(0,value-25))}>Previous source records</button><button className="button secondary" disabled={offset+25>=sources.total} onClick={()=>setOffset(value=>value+25)}>Next source records</button></div></>}</section>
    </>}
  </div>;
}
