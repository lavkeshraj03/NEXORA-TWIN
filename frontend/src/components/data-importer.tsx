"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Business } from "@/lib/api";
import { cellText, type DataCatalog, type DataRecord, type ImportPreview } from "@/lib/data-types";

function PreviewTable({rows}: {rows:DataRecord[]}){
  if(!rows.length)return null;
  const columns=Object.keys(rows[0]);
  return <div className="table-scroll"><table><thead><tr>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(column=><td key={column}>{cellText(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

export function DataImporter({business,csrf}: {business:Business;csrf:string}){
  const [catalog,setCatalog]=useState<DataCatalog|null>(null);
  const [resource,setResource]=useState("customers");
  const [file,setFile]=useState<File|null>(null);
  const [batch,setBatch]=useState<ImportPreview|null>(null);
  const [mapping,setMapping]=useState<Record<string,string>>({});
  const [history,setHistory]=useState<ImportPreview[]>([]);
  const [pending,setPending]=useState(false);
  const [error,setError]=useState("");
  const [dirty,setDirty]=useState(false);
  const [confirmed,setConfirmed]=useState(false);
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>{
    const c=new AbortController();
    Promise.all([api<DataCatalog>(`businesses/${business.id}/data-schema`,{signal:c.signal}),api<ImportPreview[]>(`businesses/${business.id}/imports?limit=20`,{signal:c.signal})]).then(([schema,list])=>{if(!c.signal.aborted){setCatalog(schema);setHistory(list);}}).catch(failure=>{if(!c.signal.aborted)setError(failure instanceof Error?failure.message:"Import setup unavailable");});
    return()=>{c.abort();controller.current?.abort();};
  },[business.id]);
  function show(item:ImportPreview){setResource(item.resource);setBatch(item);setMapping(item.mapping);setDirty(false);setConfirmed(false);setHistory(list=>[item,...list.filter(row=>row.id!==item.id)].slice(0,20));}
  async function upload(){
    if(!file)return;
    if(file.size>(catalog?.max_upload_bytes??2097152)){setError("Choose a file no larger than 2 MiB");return;}
    const c=new AbortController();controller.current=c;setPending(true);setError("");
    try{
      const query=new URLSearchParams({resource,filename:file.name});
      const response=await fetch(`/api/backend/businesses/${business.id}/imports?${query}`,{method:"POST",headers:{"Content-Type":"application/octet-stream","X-CSRF-Token":csrf},body:file,credentials:"same-origin",signal:c.signal});
      const result:unknown=await response.json();
      if(!response.ok){let message="Could not read the uploaded file";if(result&&typeof result==="object"&&"error"in result&&result.error&&typeof result.error==="object"&&"message"in result.error&&typeof result.error.message==="string")message=result.error.message;throw new Error(message);}
      show(result as ImportPreview);
    }catch(failure){setError(c.signal.aborted?"Upload cancelled. No business records were committed.":failure instanceof Error?failure.message:"Upload failed");}
    finally{setPending(false);controller.current=null;}
  }
  async function validate(){if(!batch)return;setPending(true);setError("");try{show(await api<ImportPreview>(`businesses/${business.id}/imports/${batch.id}/validate`,{method:"POST",csrf,body:{mapping}}));}catch(failure){setError(failure instanceof Error?failure.message:"Validation failed");}finally{setPending(false);}}
  async function commit(){if(!batch||!confirmed||dirty)return;setPending(true);setError("");try{show(await api<ImportPreview>(`businesses/${business.id}/imports/${batch.id}/commit`,{method:"POST",csrf,body:{confirmed:true,preview_updated_at:batch.updated_at}}));}catch(failure){setError(failure instanceof Error?failure.message:"Import was not completed" );}finally{setPending(false);}}
  async function reopen(id:string){setPending(true);setError("");try{show(await api<ImportPreview>(`businesses/${business.id}/imports/${id}`));}catch(failure){setError(failure instanceof Error?failure.message:"Preview unavailable");}finally{setPending(false);}}
  return <div className="data-importer"><section className="panel"><span className="eyebrow">IMPORT WITH CONFIDENCE</span><h2>Preview. Map. Validate. Confirm.</h2><p className="section-description">CSV, single-sheet XLSX, or a JSON array of flat objects. Maximum 2 MiB and 1000 rows. Import suppliers/customers, then products, then orders or stock movements. Dates use YYYY-MM-DD in {business.timezone}; amounts use {business.currency}.</p>{error&&<p role="alert" className="notice error">{error}</p>}<div className="data-toolbar"><label>Import record type<select aria-label="Import record type" disabled={pending} value={resource} onChange={event=>{setResource(event.target.value);setBatch(null);setConfirmed(false);}}>{Object.entries(catalog?.resources??{customers:{label:"Customers"}}).map(([key,value])=><option key={key} value={key}>{value.label}</option>)}</select></label><label>Choose data file<input aria-label="Choose data file" disabled={pending} type="file" accept=".csv,.xlsx,.json" onChange={event=>{setFile(event.target.files?.[0]??null);setBatch(null);}}/></label><button className="button submit-button" disabled={!file||pending||!catalog} onClick={()=>void upload()}>{pending?"Processing…":"Upload & preview"}</button>{pending&&controller.current&&<button className="button secondary" onClick={()=>controller.current?.abort()}>Cancel upload</button>}</div><p className="fine-print">Uploading creates an isolated preview. It does not add business records. Monetary values are parsed as decimals; synthetic data must include is_demo=true.</p></section>
    {batch&&<section className="panel"><div className="panel-heading"><h2>{batch.filename}</h2><span className="outline-badge">{batch.status.toUpperCase()}</span></div><p className="section-description">{batch.row_count} source rows · {batch.currency} · {batch.is_demo?"Contains demonstration data":"User-supplied data"}. First 10 records shown.</p><details open><summary>Source preview</summary><PreviewTable rows={batch.preview}/></details>{batch.status!=="committed"&&<><h3 className="import-heading">Map your columns</h3><div className="mapping-grid">{(catalog?.resources[resource]?.fields??[]).map(field=><label key={field.name}>{field.label}{field.required?" *":""}<select aria-label={`Column for ${field.name}`} value={mapping[field.name]??""} disabled={pending} onChange={event=>{const next={...mapping};if(event.target.value)next[field.name]=event.target.value;else delete next[field.name];setMapping(next);setDirty(true);setConfirmed(false);}}><option value="">{field.required?"Select a source column":"Use default / leave empty"}</option>{batch.columns.map(column=><option key={column}>{column}</option>)}</select></label>)}</div><button className="button secondary" disabled={pending} onClick={()=>void validate()}>{pending?"Validating…":"Validate mapping & rows"}</button></>}
    <h3 className="import-heading">Mapped preview</h3><PreviewTable rows={batch.transformed_preview}/><div className="import-counts"><span>{batch.valid_count} valid rows</span><span>{batch.error_count} validation errors</span><span>{batch.imported_count} imported rows</span></div>
    {batch.error_count>0&&<><p className="notice error">No rows can be imported until every error is resolved. Up to 200 messages are displayed.</p><a className="button secondary" href={`/api/backend/businesses/${business.id}/imports/${batch.id}/errors`}>Download error report</a><ul className="validation-errors">{batch.errors.map((item,index)=><li key={index}>Row {item.row} · {item.field}: {item.message}</li>)}</ul></>}
    {batch.status==="committed"?<p className="notice success" role="status">Import complete: {batch.imported_count} rows persisted. Re-uploading the same file or confirming again will not duplicate them. Open Overview to see recalculated metrics.</p>:<div className="confirmation"><label className="inline-check"><input type="checkbox" checked={confirmed} disabled={pending||dirty||batch.status!=="validated"||batch.error_count>0} onChange={event=>setConfirmed(event.target.checked)}/>I reviewed this preview and confirm importing {batch.row_count} rows into {business.name} using {batch.currency}.</label><button className="button submit-button" disabled={pending||!confirmed||dirty||batch.error_count>0||batch.status!=="validated"} onClick={()=>void commit()}>Confirm import</button></div>}
    </section>}
    <section className="panel"><h2>Recent imports</h2><p className="section-description">Saved previews and results for this business. Nothing is shared across businesses.</p>{history.length?<div className="table-scroll"><table><thead><tr><th>File</th><th>Records</th><th>Status</th><th>Imported</th><th>Review</th></tr></thead><tbody>{history.map(item=><tr key={item.id}><td>{item.filename}</td><td>{item.resource}</td><td>{item.status}</td><td>{item.imported_count}</td><td><button className="text-button" disabled={pending} onClick={()=>void reopen(item.id)}>Open preview</button></td></tr>)}</tbody></table></div>:<p className="section-description">No import previews yet.</p>}</section>
  </div>;
}
