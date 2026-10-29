import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentLibrary } from "../src/components/document-library";
import type { Business } from "../src/lib/api";

const business:Business={id:"business-1",name:"Test",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:[],role:"owner",permissions:["documents:read","documents:write"],data_status:"empty",created_at:"2026-10-01",updated_at:"2026-10-01"};
const configured={embeddings_configured:true,chat_configured:true,provider_health:"Not checked",evaluation:null,ocr:"Not configured"};
function response(value:unknown):Response{return {ok:true,status:200,json:async()=>value} as Response;}

describe("Document intelligence",()=>{
  it("reports absent providers and no evaluation without inventing readiness",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("rag/status")?{...configured,chat_configured:false,embeddings_configured:false}:[]));
    render(<DocumentLibrary business={business} csrf="csrf"/>);
    expect(await screen.findByText(/Evaluation: Not evaluated/)).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Ask with citations"})).toBeDisabled();
    expect(screen.getByText(/administrator must configure/)).toBeInTheDocument();
  });

  it("renders actual cited evidence and keeps follow-ups in the conversation",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("rag/status")?configured:String(url).endsWith("rag/ask")?{answer:"Thirty days.",conversation_id:"conversation-1",citations:[{chunk_id:"chunk-1",document_id:"document-1",title:"Return policy",version:2,page:3,section:"Returns",excerpt:"Returns are accepted within thirty days.",relevance:0.03}],insufficient:false,limitations:["Review evidence."]}:[]));
    render(<DocumentLibrary business={business} csrf="csrf"/>);
    await screen.findByText(/Evaluation: Not evaluated/);
    fireEvent.change(screen.getByLabelText("Your question"),{target:{value:"What is the returns policy?"}});
    fireEvent.click(screen.getByRole("button",{name:"Ask with citations"}));
    expect(await screen.findByText("Returns are accepted within thirty days.")).toBeInTheDocument();
    expect(screen.getByText(/Return policy · Version 2 · Page 3/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your question"),{target:{value:"Does that apply to all orders?"}});
    fireEvent.click(screen.getByRole("button",{name:"Ask with citations"}));
    await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>String(url).endsWith("rag/ask"))).toHaveLength(2));
    const calls=fetch.mock.calls.filter(([url])=>String(url).endsWith("rag/ask"));
    expect(JSON.parse(String(calls[1][1]?.body)).conversation_id).toBe("conversation-1");
  });

  it("hides upload controls from viewers",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(async url=>response(String(url).endsWith("rag/status")?configured:[]));
    render(<DocumentLibrary business={{...business,role:"viewer",permissions:["documents:read"]}} csrf="csrf"/>);
    await screen.findByText(/Evaluation: Not evaluated/);
    expect(screen.queryByLabelText("Choose document")).not.toBeInTheDocument();
  });
});
