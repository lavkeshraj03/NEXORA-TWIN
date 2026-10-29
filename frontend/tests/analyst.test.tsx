import React from "react";
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { AnalystWorkspace } from "../src/components/analyst-workspace";
import type { Business } from "../src/lib/api";

const business:Business={id:"one",name:"Nexa",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:["inventory"],role:"owner",permissions:["analyst:read","analyst:ask"],data_status:"has_data",created_at:"2026-10-01",updated_at:"2026-10-01"};
const fact={id:"E1.F1",evidence_id:"E1",text:"Recorded revenue was INR 123456789012345.99; operating profit is incomplete.",kind:"calculated_historical",citation:null};
const result={id:"investigation-one",question:"How did recorded profit change?",status:"partial",created_at:"2026-10-29",chat_model:"local-model",captured_at:"2026-10-29",input_hash:"source-hash",parameters:{start:"2026-09-29",end:"2026-10-28"},executions:[{id:"E1",tool:"get_business_metrics",permission:"data:read",status:"completed",duration_ms:10,started_at:"2026-10-29",arguments:{},output:{revenue:"123456789012345.99"},facts:[fact]},{id:"E2",tool:"run_sales_forecast",permission:"ml:read",status:"failed",duration_ms:1,started_at:"2026-10-29",arguments:{},error:"No active model selected",facts:[]}],response:{answer:fact.text+" [E1]",findings:[fact],recommendations:["Review expense coverage."],insufficient:false,limitations:["Recorded changes do not establish a cause."],evidence_hash:"evidence-hash",chat_model:"local-model",usage:[]}};
const response=(value:unknown,status=200)=>({ok:status<400,status,json:async()=>value}) as Response;

describe("AI analyst",()=>{
  it("runs only on explicit submission with dates, scope and CSRF and renders exact evidence",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(url,options)=>{
      const path=String(url);
      if(path.includes("/sources?"))return response({items:[{id:"order-one",status:"paid"}],total:1,source_hash:"hash",definition:"Frozen source values"});
      if(path.endsWith("/investigations")&&options?.method==="POST")return response(result);
      return response([]);
    });
    render(<AnalystWorkspace business={business} csrf="csrf-token"/>);
    await screen.findByText(/No saved investigations yet/);
    expect(fetch.mock.calls.filter(([,options])=>options?.method==="POST")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Business question"),{target:{value:"How did recorded profit change?"}});
    fireEvent.change(screen.getByLabelText("Analyst reporting starts"),{target:{value:"2026-09-29"}});
    fireEvent.change(screen.getByLabelText("Analyst reporting ends"),{target:{value:"2026-10-28"}});
    fireEvent.change(screen.getByLabelText("Analyst model data scope"),{target:{value:"demo"}});
    fireEvent.submit(screen.getByRole("button",{name:"Investigate question"}).closest("form")!);
    expect(await screen.findByText(fact.text+" [E1]")).toBeInTheDocument();
    expect(await screen.findByText("order-one")).toBeInTheDocument();
    expect(screen.getByText("No active model selected")).toBeInTheDocument();
    const request=fetch.mock.calls.find(([,options])=>options?.method==="POST");
    expect(JSON.parse(String(request?.[1]?.body))).toEqual(expect.objectContaining({start:"2026-09-29",end:"2026-10-28",model_data_scope:"demo",document_ids:[],scenario_run_ids:[]}));
    expect(request?.[1]?.headers).toEqual(expect.objectContaining({"X-CSRF-Token":"csrf-token"}));
    expect(screen.getByRole("link",{name:/Download investigation CSV/})).toHaveAttribute("href","/api/backend/businesses/one/analyst/investigations/investigation-one/export");
  });

  it("shows document version citations and insufficient-evidence limitations from saved history",async()=>{
    const citation={document_id:"doc-one",chunk_id:"chunk-one",title:"Demo policy",version:2,page:1,excerpt:"Returns require the original receipt."};
    const docFact={...fact,id:"E2.F1",evidence_id:"E2",kind:"document_excerpt",text:"Demo policy states the receipt requirement.",citation};
    const saved={...result,response:{...result.response,answer:"The document requires a receipt. [E2]",findings:[docFact]}};
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>{
      const path=String(url);
      return response(path.includes("/sources?")?{items:[],total:0,definition:"Frozen values"}:path.endsWith("/investigations")?[result]:path.endsWith("/investigation-one")?saved:[]);
    });
    render(<AnalystWorkspace business={business} csrf="csrf"/>);
    await screen.findByRole("option",{name:/partial · How did recorded profit change/});
    fireEvent.change(screen.getByLabelText("Saved investigation"),{target:{value:"investigation-one"}});
    expect(await screen.findByText("Demo policy · version 2 · page 1")).toBeInTheDocument();
    expect(screen.getByText("Returns require the original receipt.")).toBeInTheDocument();
    expect(screen.getByText("Recorded changes do not establish a cause.")).toBeInTheDocument();
  });

  it("reports actual provider errors and reloads history without a fabricated answer",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(_,options)=>options?.method==="POST"?response({error:{message:"Local provider unavailable"}},503):response([]));
    render(<AnalystWorkspace business={business} csrf="csrf"/>);
    await screen.findByText(/No saved investigations yet/);
    fireEvent.change(screen.getByLabelText("Business question"),{target:{value:"What changed?"}});
    fireEvent.submit(screen.getByRole("button",{name:"Investigate question"}).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Local provider unavailable");
    expect(screen.queryByText(/Evidence-backed findings/)).not.toBeInTheDocument();
    await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>String(url).endsWith("/investigations")).length).toBeGreaterThan(2));
  });

  it("keeps execution controls hidden from viewers",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response([]));
    render(<AnalystWorkspace business={{...business,role:"viewer",permissions:["analyst:read"]}} csrf="csrf"/>);
    await screen.findByText(/No saved investigations yet/);
    expect(screen.queryByRole("button",{name:"Investigate question"})).not.toBeInTheDocument();
    expect(screen.getByText(/Your role can inspect its saved history/)).toBeInTheDocument();
  });
});
