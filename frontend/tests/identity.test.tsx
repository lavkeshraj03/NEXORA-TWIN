import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuthForm } from "../src/components/auth-form";
import { BusinessForm } from "../src/components/business-form";
import { Workspace } from "../src/components/workspace";
import type { Business, SessionInfo } from "../src/lib/api";

const navigation = vi.hoisted(() => ({replace: vi.fn(), refresh: vi.fn()}));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
const session: SessionInfo = {user:{id:"account-1",name:"Owner",email:"owner@example.com",is_platform_admin:false},csrf_token:"csrf-test",expires_at:"2026-10-29T00:00:00Z"};
const first: Business = {id:"business-1",name:"NovaMart",business_type:"retail",country:"IN",currency:"INR",timezone:"Asia/Kolkata",reporting_month:1,modules:["orders"],role:"viewer",permissions:["business:read"],data_status:"empty",created_at:"2026-10-28T00:00:00Z",updated_at:"2026-10-28T00:00:00Z"};
const second: Business = {...first,id:"business-2",name:"FoodSphere",business_type:"restaurant",currency:"USD",timezone:"America/New_York"};
function response(data: unknown, status=200): Response {return {ok:status<400,status,json:async()=>data} as Response;}

describe("Identity and workspaces", () => {
  it("submits credentials and navigates only after successful login", async () => {
    const fetch = vi.spyOn(globalThis,"fetch").mockResolvedValue(response(session));
    render(<AuthForm/>);
    fireEvent.change(screen.getByLabelText("Email address"),{target:{value:"owner@example.com"}});
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"a correct horse battery staple"}});
    fireEvent.submit(screen.getByLabelText("Password").closest("form")!);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/workspace"));
    expect(fetch).toHaveBeenCalledWith("/api/backend/auth/login",expect.objectContaining({method:"POST",credentials:"same-origin"}));
  });

  it("shows authentication failures and restores the form", async () => {
    vi.spyOn(globalThis,"fetch").mockResolvedValue(response({error:{message:"Email or password is incorrect"}},401));
    render(<AuthForm/>);
    fireEvent.change(screen.getByLabelText("Email address"),{target:{value:"owner@example.com"}});
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"incorrect password"}});
    fireEvent.submit(screen.getByLabelText("Password").closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect");
    expect(screen.getByLabelText("Password")).toBeEnabled();
  });

  it("creates businesses with profile-specific modules and CSRF protection", async () => {
    const saved = vi.fn();
    const fetch = vi.spyOn(globalThis,"fetch").mockResolvedValue(response(second,201));
    render(<BusinessForm profiles={{retail:["orders","products"],restaurant:["orders","ingredients"]}} csrf="csrf-test" onSaved={saved}/>);
    fireEvent.change(screen.getByLabelText("Business name"),{target:{value:"FoodSphere"}});
    fireEvent.change(screen.getByLabelText("Business type"),{target:{value:"restaurant"}});
    expect(screen.getByLabelText("ingredients")).toBeChecked();
    expect(screen.queryByLabelText("products")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Create empty workspace"}));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(second));
    const options = fetch.mock.calls[0][1];
    expect(options?.headers).toEqual(expect.objectContaining({"X-CSRF-Token":"csrf-test"}));
    expect(JSON.parse(String(options?.body))).toEqual(expect.objectContaining({business_type:"restaurant",modules:["orders","ingredients"]}));
  });

  it("clears old business data while switching and hides viewer mutations", async () => {
    let release: ((value: Response) => void) | undefined;
    vi.spyOn(globalThis,"fetch").mockImplementation(async input => {
      const url=String(input);
      if (url.endsWith("/businesses")) return response([first,second]);
      if (url.endsWith("/businesses/profiles")) return response({retail:["orders"],restaurant:["orders"]});
      if (url.endsWith("/businesses/business-1")) return response(first);
      if (url.endsWith("/businesses/business-2")) return new Promise<Response>(resolve => {release=resolve;});
      throw new Error("Unexpected API request: "+url);
    });
    render(<Workspace session={session}/>);
    expect(await screen.findByRole("heading",{name:"NovaMart"})).toBeInTheDocument();
    expect(screen.getByText("INR")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("button", {name:"Overview"})).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button",{name:"Business settings"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Team"})).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Switch business"),{target:{value:second.id}});
    await waitFor(() => expect(release).toBeDefined());
    expect(screen.queryByText("INR")).not.toBeInTheDocument();
    expect(screen.getByText("Loading the selected business…")).toBeInTheDocument();
    await act(async () => {release?.(response(second));});
    expect(await screen.findByRole("heading",{name:"FoodSphere"})).toBeInTheDocument();
    expect(screen.getByText("USD")).toBeInTheDocument();
  });

  it("provides a recoverable loading error", async () => {
    vi.spyOn(globalThis,"fetch").mockRejectedValue(new Error("The account service is unavailable"));
    render(<Workspace session={session}/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("The account service is unavailable");
    expect(screen.getByRole("button",{name:"Retry loading"})).toBeInTheDocument();
  });
});
