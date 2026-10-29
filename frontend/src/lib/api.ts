export type Role = "owner" | "administrator" | "analyst" | "viewer";
export interface SessionInfo {
  user: { id: string; email: string; name: string; is_platform_admin: boolean };
  csrf_token: string;
  expires_at: string;
}
export interface BusinessInput {
  name: string; business_type: string; country: string; currency: string;
  timezone: string; reporting_month: number; modules: string[];
}
export interface Business extends BusinessInput {
  id: string; role: Role; permissions: string[]; created_at: string; updated_at: string; data_status: "empty" | "has_data";
}
export interface Member { user_id: string; name: string; email: string; role: Role }
export interface AuditEvent { id: string; event: string; user_id: string | null; target_id: string | null; created_at: string }
export type Profiles = Record<string, string[]>;
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; csrf?: string; signal?: AbortSignal } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.csrf) headers["X-CSRF-Token"] = options.csrf;
  const response = await fetch(`/api/backend/${path}`, { method: options.method ?? "GET", headers, body: options.body === undefined ? undefined : JSON.stringify(options.body), signal: options.signal, cache: "no-store", credentials: "same-origin" });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    let message = "The request could not be completed. Try again.";
    if (data && typeof data === "object" && "error" in data && data.error && typeof data.error === "object" && "message" in data.error && typeof data.error.message === "string") message = data.error.message;
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}
