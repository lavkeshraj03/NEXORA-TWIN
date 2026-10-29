import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SimulationWorkspace } from "../src/components/simulation-workspace";
import type { Business } from "../src/lib/api";

const business:Business={id:"one",name:"Nexa",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:["inventory"],role:"owner",permissions:["simulation:read","simulation:run","twin:read"],data_status:"has_data",created_at:"2026-10-01",updated_at:"2026-10-01"};
const snapshot={id:"snapshot-one",name:"Demo October baseline",period:{start:"2026-09-29",end:"2026-10-28"}};
const result={kind:"hypothetical_simulation",currency:"INR",demo_records_present:true,baseline_period:snapshot.period,baseline_captured_at:"2026-10-29",metrics:{revenue:"123456789012345.99",operating_profit:null},changes:{revenue:{baseline:"100.00",scenario:"123456789012345.99",absolute_change:"123456789012245.99",percentage_change:null,unit:"currency"}},demand_units:"10.000",replenishment_cash_outlay:"400.00",warnings:["Operating profit remains incomplete"],methodology:["Elasticity is an operator assumption, not a fitted estimate."],inventory:[],sensitivity:[],sensitivity_extremes:{best_operating_profit:null,worst_operating_profit:null,definition:"Only among supplied assumptions"}};
const run={id:"run-one",name:"Demo price assumption",baseline_snapshot_id:snapshot.id,created_at:"2026-10-29",content_hash:"hash",parameters:{name:"Demo price assumption",baseline_snapshot_id:snapshot.id},result,integrity:"verified_and_reproduced"};
function response(value:unknown,status=200):Response{return {ok:status<400,status,json:async()=>value} as Response;}

describe("What-If Lab",()=>{
  it("previews explicit assumptions, requires confirmation and invalidates previews after edits",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(url,options)=>{
      const path=String(url);
      if(path.endsWith("/twin/snapshots"))return response([snapshot]);
      if(path.endsWith("/preview"))return response({preview_hash:"reviewed-hash",parameters:JSON.parse(String(options?.body)),result});
      if(path.endsWith("/runs")&&options?.method==="POST")return response(run);
      return response([]);
    });
    render(<SimulationWorkspace business={business} csrf="csrf-token"/>);
    await screen.findByText("No saved scenarios yet.");
    expect(fetch.mock.calls.filter(([,options])=>options?.method==="POST")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Scenario name"),{target:{value:"Price +10%"}});
    fireEvent.change(screen.getByLabelText("Product price change (%)"),{target:{value:"10"}});
    expect(screen.getByLabelText("Price elasticity assumption")).toBeRequired();
    fireEvent.change(screen.getByLabelText("Price elasticity assumption"),{target:{value:"-1"}});
    fireEvent.submit(screen.getByRole("button",{name:"Preview assumptions"}).closest("form")!);
    await screen.findByText("Review before saving");
    expect(screen.getByRole("button",{name:"Run & save scenario"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Additional demand change (%)"),{target:{value:"5"}});
    expect(screen.queryByText("Review before saving")).not.toBeInTheDocument();
    fireEvent.submit(screen.getByRole("button",{name:"Preview assumptions"}).closest("form")!);
    await screen.findByText("Review before saving");
    fireEvent.click(screen.getByLabelText("Confirm scenario assumptions"));
    fireEvent.click(screen.getByRole("button",{name:"Run & save scenario"}));
    expect(await screen.findByText(/Hypothetical scenario saved/)).toBeInTheDocument();
    const request=fetch.mock.calls.find(([url,options])=>String(url).endsWith("/runs")&&options?.method==="POST");
    const body=JSON.parse(String(request?.[1]?.body));
    expect(body.preview_hash).toBe("reviewed-hash");expect(body.assumptions_confirmed).toBe(true);expect(body.price_elasticity).toBe("-1");
    expect(request?.[1]?.headers).toEqual(expect.objectContaining({"X-CSRF-Token":"csrf-token"}));
  });

  it("shows hypothetical labels, exact values, separate cash outlay and CSV export",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/twin/snapshots")?[snapshot]:String(url).endsWith("/runs")?[run]:run));
    render(<SimulationWorkspace business={business} csrf="csrf"/>);
    await screen.findByText("Save at least two scenarios to compare.");
    fireEvent.change(screen.getByLabelText("Saved scenario"),{target:{value:"run-one"}});
    expect(await screen.findByText(/HYPOTHETICAL SIMULATION/)).toBeInTheDocument();
    expect(screen.getByText("123456789012345.99")).toBeInTheDocument();
    expect(screen.getByText(/Replenishment cash outlay: 400.00 INR, separate/)).toBeInTheDocument();
    expect(screen.getByText(/Baseline includes labelled demonstration/)).toBeInTheDocument();
    expect(screen.getByRole("link",{name:/Download scenario CSV/})).toHaveAttribute("href","/api/backend/businesses/one/simulations/runs/run-one/export");
  });

  it("gives viewers saved results without execution controls",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/twin/snapshots")?[snapshot]:[run]));
    render(<SimulationWorkspace business={{...business,role:"viewer",permissions:["simulation:read","twin:read"]}} csrf="csrf"/>);
    await screen.findByText("Save at least two scenarios to compare.");
    expect(screen.queryByRole("button",{name:"Preview assumptions"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Run & save scenario"})).not.toBeInTheDocument();
  });

  it("reports baseline errors without presenting fake scenario results",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async()=>response({error:{message:"Baseline is unavailable"}},404));
    render(<SimulationWorkspace business={business} csrf="csrf"/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Baseline is unavailable");
    expect(screen.queryByText(/HYPOTHETICAL SIMULATION/)).not.toBeInTheDocument();
  });
});
