import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TwinWorkspace } from "../src/components/twin-workspace";
import type { Business } from "../src/lib/api";

const business:Business={id:"one",name:"Nexa",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:["inventory"],role:"owner",permissions:["twin:read","twin:write"],data_status:"has_data",created_at:"2026-10-01",updated_at:"2026-10-01"};
const state={captured_at:"2026-10-29T00:00:00+00:00",period:{start:"2026-10-01",end:"2026-10-28",days:28},business:{name:"Nexa",currency:"INR",timezone:"Asia/Kolkata"},metrics:{revenue:"123456789012345.99",operating_profit:null},metric_provenance:{revenue:{kind:"calculated_historical",recorded_at:"2026-10-29",definition:"Paid sale lines; tax excluded.",sources:{order_items:["item-one"]}}},demo_records:10,counts:{orders:2},data_updated_at:null,inventory_value:null,inventory:[],customers:{total:1,active_in_period:1,eligible_retention:0,retained:0,retention_pct:null},orders:{paid:1,pending:1},suppliers:{total:0,linked_products:0,purchasing_state:"Purchasing unavailable"},health:[{key:"expense_coverage",status:"unknown",detail:"Expense coverage incomplete"}],assumptions:["Current inventory at capture"],source_versions:{orders:{records:2,sha256:"source-hash"}},forecasts:[]};
const snapshot={id:"saved-one",name:"October review",created_at:"2026-10-29",content_hash:"full-hash",implementation_version:"1",period:state.period,currency:"INR",demo_records:10};
function response(value:unknown,status=200):Response{return {ok:status<400,status,json:async()=>value} as Response;}

describe("Digital twin",()=>{
  it("shows exact metrics, missing coverage, demo labels and no invented forecasts",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/snapshots")?[]:{state}));
    render(<TwinWorkspace business={business} csrf="csrf"/>);
    expect(await screen.findByText("123456789012345.99")).toBeInTheDocument();
    expect(screen.getByText(/Includes 10 labelled demonstration/)).toBeInTheDocument();
    expect(screen.getByText("Expense coverage incomplete")).toBeInTheDocument();
    expect(screen.getByText(/No active model was selected/)).toBeInTheDocument();
    expect(screen.getByText(/No saved snapshots yet/)).toBeInTheDocument();
    expect(screen.getByText("Paid sale lines; tax excluded.")).toBeInTheDocument();
  });

  it("saves only on explicit action with dates and CSRF, then inspects frozen sources",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(url,options)=>{
      const path=String(url);
      if(path.includes("/sources?"))return response({items:[{id:"order-one",status:"paid"}],total:1,source_hash:"source-hash",definition:"Saved source values at capture"});
      if(path.endsWith("/snapshots"))return response(options?.method==="POST"?{...snapshot,state}:[]);
      return response({state,integrity:"verified_and_reproduced"});
    });
    render(<TwinWorkspace business={business} csrf="csrf-token"/>);
    await screen.findByText("123456789012345.99");
    expect(fetch.mock.calls.filter(([,options])=>options?.method==="POST")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Snapshot name"),{target:{value:"October review"}});
    fireEvent.change(screen.getByLabelText("Twin reporting starts"),{target:{value:"2026-10-01"}});
    fireEvent.change(screen.getByLabelText("Twin reporting ends"),{target:{value:"2026-10-28"}});
    fireEvent.click(screen.getByRole("button",{name:"Save snapshot"}));
    expect(await screen.findByText(/Snapshot saved with source values/)).toBeInTheDocument();
    expect(await screen.findByText("order-one")).toBeInTheDocument();
    const request=fetch.mock.calls.find(([,options])=>options?.method==="POST");
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({name:"October review",start:"2026-10-01",end:"2026-10-28"});
    expect(request?.[1]?.headers).toEqual(expect.objectContaining({"X-CSRF-Token":"csrf-token"}));
  });

  it("compares saved snapshots and labels unequal periods",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>{
      const path=String(url);
      return response(path.endsWith("/snapshots")?[snapshot,{...snapshot,id:"saved-two",name:"Next review"}]:path.includes("/compare?")?{same_period:false,equal_period_length:false,definition:"Right minus left",source_changes:["orders"],metrics:{revenue:{before:"0.00",after:"10.00",absolute_change:"10.00",percentage_change:null,unit:"INR"}}}:{state});
    });
    render(<TwinWorkspace business={business} csrf="csrf"/>);
    await screen.findByText("123456789012345.99");
    fireEvent.change(screen.getByLabelText("Left snapshot"),{target:{value:"saved-one"}});
    fireEvent.change(screen.getByLabelText("Right snapshot"),{target:{value:"saved-two"}});
    fireEvent.click(screen.getByRole("button",{name:"Compare snapshots"}));
    expect(await screen.findByText(/These periods have different lengths/)).toBeInTheDocument();
    expect(screen.getByText("Undefined")).toBeInTheDocument();
    await waitFor(()=>expect(fetch.mock.calls.some(([url])=>String(url).includes("left=saved-one&right=saved-two"))).toBe(true));
  });

  it("hides snapshot creation from viewers and reports failed requests",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({error:{message:"Snapshot source limit exceeded"}},422));
    render(<TwinWorkspace business={{...business,role:"viewer",permissions:["twin:read"]}} csrf="csrf"/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Snapshot source limit exceeded");
    expect(screen.queryByRole("button",{name:"Save snapshot"})).not.toBeInTheDocument();
  });
});
