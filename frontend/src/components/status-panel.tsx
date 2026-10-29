"use client";

import { useEffect, useRef, useState } from "react";
import { parseHealth, type Health } from "@/lib/health";

const services = [
  ["database", "PostgreSQL", "Business data & tenant storage"],
  ["pgvector", "Vector engine", "Document embeddings & retrieval"],
  ["migrations", "Database schema", "Version-controlled migrations"],
  ["redis", "Redis", "Background job infrastructure"],
] as const;

export function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);

  async function refresh() {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    setLoading(true);
    setError("");
    setHealth(null);
    try {
      const response = await fetch("/api/health", { signal: next.signal, cache: "no-store" });
      const result = parseHealth(await response.json());
      if (!next.signal.aborted) setHealth(result);
    } catch {
      if (!next.signal.aborted) setError("Could not check service status. Try again.");
    } finally {
      if (!next.signal.aborted) setLoading(false);
    }
  }

  useEffect(() => { void refresh(); return () => controller.current?.abort(); }, []);

  return <section className="panel status-panel" aria-labelledby="status-title" aria-busy={loading}>
    <div className="panel-heading"><div><span className="eyebrow">SYSTEM HEALTH</span><h2 id="status-title">Your foundation, connected.</h2></div><button className="icon-button" disabled={loading} onClick={() => void refresh()} aria-label="Refresh service status"><span className={loading ? "spinning" : ""}>↻</span></button></div>
    <div aria-live="polite">
      {error && <p className="notice error" role="alert">{error}</p>}
      {health?.status === "unreachable" && <p className="notice">The API is unreachable. Start the backend to check your services.</p>}
      {services.map(([key, title, description]) => {
        const check = health?.checks[key];
        const state = loading ? "Checking" : check?.status === "healthy" ? "Connected" : check ? "Needs attention" : "Not checked";
        return <div className="service-row" key={key}><span className="service-icon">{key === "database" ? "▱" : key === "pgvector" ? "◇" : key === "redis" ? "ϟ" : "≡"}</span><div className="service-description"><strong>{title}</strong><small>{check?.detail ?? description}</small></div><span className={`service-state ${check?.status === "healthy" ? "healthy" : ""}`}><i />{state}</span></div>;
      })}
      <div className="status-footer"><span className={`dot ${health?.status === "ready" ? "green" : ""}`} />{loading ? "Checking live infrastructure…" : health?.status === "ready" ? "All foundation services are ready" : "Setup is not yet complete"}<span className="checked-at">{health && !loading ? new Date(health.checked_at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : ""}</span></div>
    </div>
  </section>;
}
