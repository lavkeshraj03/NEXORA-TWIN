import { NextResponse } from "next/server";
import { parseHealth } from "@/lib/health";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(`${base}/api/v1/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(12000) });
    const health = parseHealth(await response.json());
    return NextResponse.json(health, { status: response.ok ? 200 : 503 });
  } catch {
    return NextResponse.json({ status: "unreachable", checked_at: new Date().toISOString(), version: "0.1.0", checks: {} }, { status: 503 });
  }
}
