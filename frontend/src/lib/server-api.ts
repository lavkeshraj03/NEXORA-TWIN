import { cookies } from "next/headers";
import { ApiError, type SessionInfo } from "@/lib/api";

export async function serverSession(): Promise<SessionInfo | null> {
  const cookie = (await cookies()).get("nexora_session");
  if (!cookie) return null;
  let response: Response;
  try {
    response = await fetch(`${process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000"}/api/v1/auth/me`, { headers: { cookie: `nexora_session=${encodeURIComponent(cookie.value)}` }, cache: "no-store", signal: AbortSignal.timeout(8000) });
  } catch { throw new ApiError(503, "The account service is unavailable. Try again shortly."); }
  if (response.status === 401) return null;
  if (!response.ok) throw new ApiError(response.status, "The account service is unavailable. Try again shortly.");
  return await response.json() as SessionInfo;
}
