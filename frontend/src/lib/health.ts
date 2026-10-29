export interface DependencyCheck {
  status: "healthy" | "unavailable";
  detail: string;
}
export interface Health {
  status: "ready" | "not_ready" | "unreachable";
  checked_at: string;
  version: string;
  checks: Record<string, DependencyCheck>;
}

export function parseHealth(value: unknown): Health {
  if (!value || typeof value !== "object") throw new Error("Invalid service response");
  const object = value as Record<string, unknown>;
  if (!["ready", "not_ready", "unreachable"].includes(String(object.status)) || typeof object.checked_at !== "string" || typeof object.version !== "string" || !object.checks || typeof object.checks !== "object") {
    throw new Error("Invalid service response");
  }
  const checks: Record<string, DependencyCheck> = {};
  for (const [name, item] of Object.entries(object.checks)) {
    if (!item || typeof item !== "object" || !("status" in item) || !("detail" in item) || !["healthy", "unavailable"].includes(String(item.status)) || typeof item.detail !== "string") throw new Error("Invalid dependency response");
    checks[name] = { status: item.status as DependencyCheck["status"], detail: item.detail };
  }
  if (object.status !== "unreachable" && !["database", "pgvector", "migrations", "redis"].every((key) => key in checks)) throw new Error("Incomplete dependency response");
  return { status: object.status as Health["status"], checked_at: object.checked_at, version: object.version, checks };
}
