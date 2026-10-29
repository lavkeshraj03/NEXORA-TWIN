import React from "react";
import { fireEvent,render,screen,waitFor } from "@testing-library/react";
import { describe,expect,it,vi } from "vitest";
import { KnowledgeWorkspace } from "../src/components/knowledge-workspace";
import { ReportsWorkspace } from "../src/components/reports-workspace";
import type { Business } from "../src/lib/api";
const business:Business={id:"one",name:"Nexa",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:["inventory"],role:"owner",permissions:["graph:read","graph:build","reports:read","reports:create"],data_status:"has_data",created_at:"2026-10-01",updated_at:"2026-10-01"};
const response=(value:unknown,status=200)=>({ok:status<400,status,json:async()=>value}) as Response;
const build={id:"build-one",created_at:"2026-10-29",captured_at:"2026-10-29"};
const root={id:"root",kind:"business",label:"Nexa",is_demo:false,source:{resource:"businesses",values:{name:"Nexa"}}};
const product={id:"product-one",kind:"product",label:"NX-PEN-01 · Demo pen",is_demo:true,source:{resource:"products",values:{sku:"NX-PEN-01"}}};
const edge={id:"edge-one",source_id:"root",target_id:"product-one",relationship:"has_product",provenance:{resource:"products",id:"source-product-id",verification:"structured_foreign_key"}};
const summary={build,node_count:2,edge_count:1,kinds:{business:1,product:1},demo_nodes:1,methodology:"Stored foreign keys only"};
const report={id:"report-one",name:"October review",kind:"revenue_expenses",created_at:"2026-10-29",content_hash:"hash",payload:{metadata:{business_name:"Nexa",result_kind:"calculated_historical",currency:"INR",demo_records_present:true},sections:[{title:"Financial results",columns:["metric","value"],rows:[["revenue","123456789012345.99"],["operating_profit",null]],note:"Requires confirmed coverage"}],sources:[{type:"twin_snapshot",id:"snapshot-one",sha256:"source-hash"}],assumptions:["Paid orders only"],limitations:["Unknown costs remain incomplete"]}};

describe("Knowledge graph",()=>{
  it("shows only API relationships and allows keyboard entity exploration with provenance",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>{const path=String(url);if(path.endsWith("/builds"))return response([build]);if(path.includes("/nodes?"))return response({items:[root],total:1});if(path.includes("/nodes/product-one?"))return response({node:product,neighbors:[root],edges:[edge],total_connections:1});if(path.includes("/nodes/root?"))return response({node:root,neighbors:[product],edges:[edge],total_connections:1});return response(summary);});
    render(<KnowledgeWorkspace business={business} csrf="csrf"/>);
    const target=await screen.findByRole("button",{name:"Explore NX-PEN-01 · Demo pen"});
    fireEvent.keyDown(target,{key:"Enter"});
    expect(await screen.findByRole("heading",{name:"NX-PEN-01 · Demo pen"})).toBeInTheDocument();
    expect(screen.getByText(/structured_foreign_key/)).toBeInTheDocument();
    expect(screen.getByText(/Includes 1 labelled demonstration/)).toBeInTheDocument();
    await waitFor(()=>expect(fetch.mock.calls.some(([url])=>String(url).includes("/nodes/product-one?"))).toBe(true));
  });
  it("requires explicit graph refresh and hides build controls from viewers",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/builds")?[]:{build:null,node_count:0,edge_count:0,kinds:{}}));
    render(<KnowledgeWorkspace business={{...business,role:"viewer",permissions:["graph:read"]}} csrf="csrf"/>);
    expect(await screen.findByText(/No graph snapshot yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Refresh graph from records"})).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([,options])=>options?.method==="POST")).toHaveLength(0);
  });
});

describe("Business reports",()=>{
  it("generates only on request, with source ID and CSRF, then exposes real CSV/PDF links",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(url,options)=>{const path=String(url);if(path.endsWith("/twin/snapshots"))return response([{id:"snapshot-one",name:"October baseline",period:{start:"2026-09-29",end:"2026-10-28"}}]);if(path.endsWith("/reports")&&options?.method==="POST")return response(report);if(path.endsWith("/reports"))return response([]);return response([]);});
    render(<ReportsWorkspace business={business} csrf="csrf-token"/>);
    await screen.findByText("No saved reports yet.");
    fireEvent.change(screen.getByLabelText("Report name"),{target:{value:"October review"}});
    fireEvent.change(screen.getByLabelText("Report source snapshot"),{target:{value:"snapshot-one"}});
    fireEvent.submit(screen.getByRole("button",{name:"Generate report"}).closest("form")!);
    expect(await screen.findByText("123456789012345.99")).toBeInTheDocument();
    expect(screen.getByText("Incomplete / undefined")).toBeInTheDocument();
    expect(screen.getByRole("link",{name:/Download report PDF/})).toHaveAttribute("href","/api/backend/businesses/one/reports/report-one/export/pdf");
    const request=fetch.mock.calls.find(([,options])=>options?.method==="POST");
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({name:"October review",kind:"revenue_expenses",snapshot_id:"snapshot-one"});
    expect(request?.[1]?.headers).toEqual(expect.objectContaining({"X-CSRF-Token":"csrf-token"}));
  });
  it("reports invalid sources without fabricating a report",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async(_,options)=>options?.method==="POST"?response({error:{message:"Select a closed calendar-month snapshot"}},422):response([]));
    render(<ReportsWorkspace business={business} csrf="csrf"/>);
    await screen.findByText("No saved reports yet.");
    fireEvent.change(screen.getByLabelText("Report name"),{target:{value:"Monthly review"}});
    fireEvent.submit(screen.getByRole("button",{name:"Generate report"}).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Select a closed calendar-month snapshot");
    expect(screen.queryByRole("link",{name:/Download report PDF/})).not.toBeInTheDocument();
  });
});
