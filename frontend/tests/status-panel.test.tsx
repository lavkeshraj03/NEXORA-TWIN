import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StatusPanel } from "../src/components/status-panel";
import { parseHealth } from "../src/lib/health";

describe("Infrastructure status", () => {
  it("shows real dependency failures and allows retry", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ json: async () => ({ status: "not_ready", checked_at: "2026-10-27T12:00:00Z", version: "0.1.0", checks: Object.fromEntries(["database", "pgvector", "migrations", "redis"].map(key => [key, {status: "unavailable", detail: "Service offline"}])) }) } as Response);
    render(<StatusPanel />);
    expect(screen.getByText("Checking live infrastructure…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Needs attention")).toHaveLength(4));
    expect(screen.queryByText("All foundation services are ready")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Refresh service status"}));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
  it("shows unreachable backend without inventing service health", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ json: async () => ({status: "unreachable", checked_at: "2026-10-27T12:00:00Z", version: "0.1.0", checks: {}}) } as Response);
    render(<StatusPanel />);
    expect(await screen.findByText(/The API is unreachable/)).toBeInTheDocument();
    expect(screen.getAllByText("Not checked")).toHaveLength(4);
  });
  it("rejects malformed and incomplete API contracts", () => {
    expect(() => parseHealth({status: "ready"})).toThrow();
    expect(() => parseHealth({status: "ready", checked_at: "now", version: "1", checks: {}})).toThrow();
  });
  it("shows a recoverable error for invalid responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ json: async () => ({surprise: true}) } as Response);
    render(<StatusPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not check service status");
  });
});
