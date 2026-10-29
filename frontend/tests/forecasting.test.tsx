import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ForecastWorkspace } from "../src/components/forecast-workspace";
import type { Business } from "../src/lib/api";

const business:Business={id:"one",name:"Test",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:[],role:"owner",permissions:["ml:read","ml:train","ml:deploy"],data_status:"has_data",created_at:"2026-10-01",updated_at:"2026-10-01"};
const run={id:"run-1",task:"sales",algorithm:"seasonal_naive",implementation_version:"1",data_scope:"demo",active:false,created_at:"2026-10-28",dataset_hash:"test-fingerprint",config:{start:"2026-10-01",end:"2026-10-28",aggregation:"daily",currency:"INR",horizon:7},history:[{date:"2026-10-28",value:"123456789012345.99"}],source_count:28,result:{forecast:[{date:"2026-10-29",prediction:"123456789012345.99",lower:null,upper:null}],baseline_only:true,candidates:{seasonal_naive:{validation:{mae:2,rmse:2,wape_pct:5,observations:5},test:{mae:3,rmse:3,wape_pct:null,observations:6}}},selection:"Lowest validation MAE",limitations:["Sparse history limits this baseline."],band_description:"Residual bands are not guaranteed prediction intervals.",anomalies:[]}};
function response(value:unknown,status=200):Response{return {ok:status<400,status,json:async()=>value} as Response;}

describe("Forecasting workspace",()=>{
  it("shows baseline, demo labels, exact estimates and missing intervals honestly",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/runs")?[run]:run));
    render(<ForecastWorkspace business={business} csrf="csrf"/>);
    expect(await screen.findByText(/Baseline only: there is not enough history/)).toBeInTheDocument();
    expect(screen.getByText(/SYNTHETIC DEMONSTRATION/)).toBeInTheDocument();
    expect(screen.getByText("INR 123,456,789,012,345.99")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.getByText("Undefined")).toBeInTheDocument();
  });

  it("sends explicit import coverage and handles insufficient history",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>String(url).endsWith("/forecasts")?response({error:{message:"Insufficient history: need 28 days"}},422):response([]));
    render(<ForecastWorkspace business={business} csrf="csrf-token"/>);
    expect(screen.getByRole("checkbox")).toBeRequired();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.submit(screen.getByRole("button",{name:"Train & evaluate"}).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Insufficient history");
    const request=fetch.mock.calls.find(([url])=>String(url).endsWith("/forecasts"));
    expect(JSON.parse(String(request?.[1]?.body)).coverage_confirmed).toBe(true);
    expect(request?.[1]?.headers).toEqual(expect.objectContaining({"X-CSRF-Token":"csrf-token"}));
  });

  it("requires an explicit activation action and reports source changes",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/runs")?[run]:String(url).endsWith("/monitor")?{source_changed:true}:String(url).endsWith("/activate")?{...run,active:true}:run));
    render(<ForecastWorkspace business={business} csrf="csrf"/>);
    await screen.findByText(/Baseline only:/);
    expect(fetch.mock.calls.filter(([url])=>String(url).endsWith("/activate"))).toHaveLength(0);
    fireEvent.click(screen.getByRole("button",{name:"Activate this model"}));
    await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>String(url).endsWith("/activate"))).toHaveLength(1));
    fireEvent.click(screen.getByRole("button",{name:"Check source changes"}));
    expect(await screen.findByText(/Training sources have changed/)).toBeInTheDocument();
  });

  it("gives viewers model history without training or activation controls",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("/runs")?[run]:run));
    render(<ForecastWorkspace business={{...business,role:"viewer",permissions:["ml:read"]}} csrf="csrf"/>);
    await screen.findByText(/Baseline only:/);
    expect(screen.queryByRole("button",{name:"Train & evaluate"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Activate this model"})).not.toBeInTheDocument();
  });
});
