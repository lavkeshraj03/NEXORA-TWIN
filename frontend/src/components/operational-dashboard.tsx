"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, type Business } from "@/lib/api";
import { displayMoney, type DashboardData } from "@/lib/data-types";

export function OperationalDashboard({business,csrf}: {business:Business;csrf:string}) {
  const [data,setData]=useState<DashboardData|null>(null);
  const [query,setQuery]=useState("");
  const [start,setStart]=useState("");
  const [end,setEnd]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [reload,setReload]=useState(0);
  const [confirm,setConfirm]=useState(false);
  const [pending,setPending]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);setData(null);setError("");setConfirm(false);
    api<DashboardData>(`businesses/${business.id}/dashboard${query}`,{signal:controller.signal}).then(result=>{if(!controller.signal.aborted){setData(result);setStart(result.start_date);setEnd(result.end_date);}}).catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"Dashboard unavailable");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[business.id,query,reload]);
  function changePeriod(event:FormEvent<HTMLFormElement>){event.preventDefault();setQuery(`?start=${start}&end=${end}`);}
  async function coverage(){
    if(!data)return;
    setPending(true);setError("");
    try{await api(`businesses/${business.id}/expense-coverage`,{method:"PUT",csrf,body:{start_date:data.start_date,end_date:data.end_date,complete:!data.expenses_complete}});setReload(value=>value+1);}
    catch(failure){setError(failure instanceof Error?failure.message:"Could not save coverage");}
    finally{setPending(false);}
  }
  if(loading)return <section className="panel loading-state" role="status">Calculating business metrics…</section>;
  if(!data)return <section className="panel"><p role="alert" className="notice error">{error}</p><button className="button secondary" onClick={()=>setReload(value=>value+1)}>Retry dashboard</button></section>;
  const cards=[
    ["Revenue",displayMoney(data.metrics.revenue,data.currency),"Paid net sales · tax excluded"],
    ["Gross profit",displayMoney(data.metrics.gross_profit,data.currency),data.missing_cost_lines?`${data.missing_cost_lines} sale lines have unknown costs`:"Revenue less recorded cost of goods sold"],
    ["Recorded operating expenses",displayMoney(data.metrics.recorded_expenses,data.currency),data.expenses_complete?"Period coverage confirmed":"Coverage is not yet confirmed"],
    ["Operating profit",displayMoney(data.metrics.operating_profit,data.currency),"Requires complete costs and expense coverage"],
    ["Average order value",data.metrics.average_order_value===null?"No paid orders":displayMoney(data.metrics.average_order_value,data.currency),`${data.metrics.paid_orders} paid orders`],
    ["Gross margin",data.metrics.gross_margin_pct===null?"Not available":data.metrics.gross_margin_pct+"%","Gross profit / revenue"],
  ];
  const max=Math.max(1,...data.trend.flatMap(point=>[Number(point.revenue),Number(point.expenses)]));
  const path=(key:"revenue"|"expenses")=>data.trend.map((point,index)=>`${15+index/Math.max(1,data.trend.length-1)*810},${165-Number(point[key])/max*145}`).join(" ");
  return <div className="operational-dashboard"><div className="report-toolbar"><div><span className="outline-badge">CALCULATED HISTORICAL RESULTS</span><p>{data.timezone} · {data.data_updated_at?`Data updated ${new Date(data.data_updated_at).toLocaleString()}`:"No operational records yet"}</p></div><form onSubmit={changePeriod}><label>From<input aria-label="Report start" type="date" required value={start} onChange={event=>setStart(event.target.value)}/></label><label>To<input aria-label="Report end" type="date" required min={start} value={end} onChange={event=>setEnd(event.target.value)}/></label><button className="button secondary">Apply dates</button></form></div>
    {data.demo_records>0&&<p className="notice">This business contains {data.demo_records} explicitly labelled demonstration records. These results do not represent validated real-world performance.</p>}
    {error&&<p className="notice error" role="alert">{error}</p>}
    {!Object.values(data.counts).some(value=>value>0)&&<section className="panel empty-state"><span className="empty-symbol">▥</span><h2>Your business is ready for its data.</h2><p>Add records in Data explorer or import a CSV, XLSX, or JSON file. No demo data is added automatically.</p></section>}
    <div className="metric-grid">{cards.map(([label,value,definition])=><article className="panel metric-card" key={label}><span className="eyebrow">{label}</span><strong>{value}</strong><small>{definition}</small></article>)}</div>
    <section className="panel"><div className="panel-heading"><h2>Revenue & recorded expenses</h2><span className="chart-legend"><i/>Revenue <i/>Expenses</span></div>{data.metrics.paid_orders||Number(data.metrics.recorded_expenses)>0?<svg viewBox="0 0 840 180" role="img" aria-label="Historical revenue and recorded expense trends"><path d="M15 165H825" stroke="#dce5da"/><polyline points={path("revenue")} fill="none" stroke="#167e68" strokeWidth="3"/><polyline points={path("expenses")} fill="none" stroke="#c39b5d" strokeWidth="2"/></svg>:<p className="section-description">No qualifying sales or expenses in this reporting period.</p>}<div className="chart-dates"><span>{data.start_date}</span><span>{data.end_date}</span></div><details><summary>Inspect daily source totals</summary><div className="table-scroll"><table><thead><tr><th>Business date</th><th>Revenue</th><th>Recorded expenses</th></tr></thead><tbody>{data.trend.map(point=><tr key={point.date}><td>{point.date}</td><td>{displayMoney(point.revenue,data.currency)}</td><td>{displayMoney(point.expenses,data.currency)}</td></tr>)}</tbody></table></div></details></section>
    <div className="business-facts"><article className="panel"><span className="eyebrow">Active {data.labels.customers.toLowerCase()}</span><strong>{data.active_customers}</strong><p className="section-description">Customers with a paid order in this period.</p></article><article className="panel"><span className="eyebrow">Customer retention</span><strong>{data.retention.percentage===null?"Insufficient history":data.retention.percentage+"%"}</strong><p className="section-description">{data.retention.retained} retained / {data.retention.eligible} eligible prior purchasers.</p></article>{data.inventory&&<article className="panel"><span className="eyebrow">Current inventory value</span><strong>{displayMoney(data.inventory.value,data.currency)}</strong><p className="section-description">Current unit cost · {data.inventory.stocked_products} stocked products · {data.inventory.zero_stock_products} at zero stock. Independent of report dates.</p></article>}</div>
    <section className="panel"><h2>Expense coverage</h2><p className="section-description">{data.expenses_complete?"An authorized member confirmed that all operating expenses for this exact reporting period have been recorded.":"Recorded expenses may be partial. Operating profit is intentionally incomplete until the period is confirmed."}</p>{business.permissions.includes("data:write")&&<><label className="inline-check">{!data.expenses_complete&&<><input type="checkbox" checked={confirm} onChange={event=>setConfirm(event.target.checked)}/>I confirm that every operating expense from {data.start_date} through {data.end_date} is recorded, including a genuinely zero-expense period.</>}</label><button className="button secondary" disabled={pending||(!data.expenses_complete&&!confirm)} onClick={()=>void coverage()}>{pending?"Saving…":data.expenses_complete?"Mark expense coverage incomplete":"Confirm period coverage"}</button></>}</section>
    <details className="panel"><summary>Metric definitions & limitations</summary><ul>{data.methodology.map(item=><li key={item}>{item}</li>)}</ul></details>
  </div>;
}
