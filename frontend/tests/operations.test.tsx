import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OperationalDashboard } from "../src/components/operational-dashboard";
import { DataImporter } from "../src/components/data-importer";
import { displayMoney, type DashboardData, type ImportPreview } from "../src/lib/data-types";
import type { Business } from "../src/lib/api";

const business:Business={id:"business-1",name:"Test business",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:["orders","inventory"],role:"owner",permissions:["business:read","data:read","data:write"],data_status:"empty",created_at:"2026-10-01",updated_at:"2026-10-01"};
const report:DashboardData={business_id:business.id,currency:"INR",timezone:business.timezone,start_date:"2026-10-01",end_date:"2026-10-28",calculation_type:"calculated_historical",metrics:{revenue:"100.00",cogs:null,gross_profit:null,gross_margin_pct:null,recorded_expenses:"10.00",operating_profit:null,average_order_value:"100.00",paid_orders:1},expenses_complete:false,missing_cost_lines:1,active_customers:1,retention:{eligible:0,retained:0,percentage:null},inventory:null,counts:{orders:1},demo_records:1,labels:{customers:"Customers"},trend:[{date:"2026-10-01",revenue:"100.00",expenses:"10.00"}],data_updated_at:null,calculated_at:"2026-10-28T00:00:00Z",methodology:["Paid orders only"]};
const catalog={resources:{customers:{label:"Customers",fields:[{name:"external_id",label:"external id",type:"string",required:true,options:[],default:null},{name:"name",label:"name",type:"string",required:true,options:[],default:null}]}},currency:"INR",max_import_rows:1000,max_upload_bytes:2097152};
const preview:ImportPreview={id:"batch-1",business_id:business.id,resource:"customers",currency:"INR",filename:"customers.csv",status:"validated",columns:["external_id","name"],row_count:1,preview:[{external_id:"C1",name:"Test customer"}],mapping:{external_id:"external_id",name:"name"},transformed_preview:[{external_id:"C1",name:"Test customer"}],errors:[],error_count:0,valid_count:1,imported_count:0,is_demo:false,updated_at:"2026-10-28T00:00:00Z"};
function response(data:unknown,status=200):Response{return {ok:status<400,status,json:async()=>data} as Response;}

describe("Operational reporting and imports",()=>{
  it("keeps exact monetary strings and incomplete costs visible",async()=>{
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response(report));
    render(<OperationalDashboard business={business} csrf="csrf-test"/>);
    expect(await screen.findByText("1 sale lines have unknown costs")).toBeInTheDocument();
    expect(screen.getAllByText("Incomplete").length).toBeGreaterThan(0);
    expect(screen.getByText(/explicitly labelled demonstration records/)).toBeInTheDocument();
    expect(displayMoney("123456789012345.99","INR")).toBe("INR 123,456,789,012,345.99");
  });

  it("requires explicit period coverage acknowledgement",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async input=>String(input).endsWith("expense-coverage")?response({complete:true}):response(report));
    render(<OperationalDashboard business={business} csrf="csrf-test"/>);
    const button=await screen.findByRole("button",{name:"Confirm period coverage"});
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(button);
    await waitFor(()=>expect(fetch).toHaveBeenCalledWith(expect.stringContaining("expense-coverage"),expect.objectContaining({method:"PUT",headers:expect.objectContaining({"X-CSRF-Token":"csrf-test"})})));
  });

  it("shows recoverable dashboard failures",async()=>{
    vi.spyOn(globalThis,"fetch").mockRejectedValue(new Error("Database unavailable"));
    render(<OperationalDashboard business={business} csrf="csrf-test"/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
    expect(screen.getByRole("button",{name:"Retry dashboard"})).toBeInTheDocument();
  });

  it("does not commit an upload until the reviewed preview is confirmed",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async(input,options)=>{
      const url=String(input);
      if(url.endsWith("data-schema"))return response(catalog);
      if(url.includes("imports?limit="))return response([]);
      if(url.endsWith("/commit"))return response({...preview,status:"committed",imported_count:1});
      if(options?.body instanceof File)return response(preview);
      throw new Error("Unexpected request: "+url);
    });
    render(<DataImporter business={business} csrf="csrf-test"/>);
    fireEvent.change(screen.getByLabelText("Choose data file"),{target:{files:[new File(["external_id,name\nC1,Test customer"],"customers.csv",{type:"text/csv"})]}});
    await waitFor(()=>expect(screen.getByRole("button",{name:"Upload & preview"})).toBeEnabled());
    fireEvent.click(screen.getByRole("button",{name:"Upload & preview"}));
    const confirm=await screen.findByRole("button",{name:"Confirm import"});
    expect(confirm).toBeDisabled();
    expect(fetch.mock.calls.filter(([url])=>String(url).endsWith("/commit"))).toHaveLength(0);
    fireEvent.click(screen.getByLabelText(/I reviewed this preview/));
    fireEvent.click(confirm);
    expect(await screen.findByRole("status")).toHaveTextContent("Import complete: 1 rows persisted");
    const call=fetch.mock.calls.find(([url])=>String(url).endsWith("/commit"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({confirmed:true,preview_updated_at:preview.updated_at});
  });

  it("blocks confirmation when a preview contains validation errors",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async(input,options)=>String(input).endsWith("data-schema")?response(catalog):options?.body instanceof File?response({...preview,error_count:1,valid_count:0,errors:[{row:2,field:"email",message:"Invalid email"}]}):response([]));
    render(<DataImporter business={business} csrf="csrf-test"/>);
    fireEvent.change(screen.getByLabelText("Choose data file"),{target:{files:[new File(["x"],"bad.csv")]}});
    await waitFor(()=>expect(screen.getByRole("button",{name:"Upload & preview"})).toBeEnabled());
    fireEvent.click(screen.getByRole("button",{name:"Upload & preview"}));
    expect(await screen.findByRole("button",{name:"Confirm import"})).toBeDisabled();
    expect(screen.getByRole("link",{name:"Download error report"})).toBeInTheDocument();
  });
});
