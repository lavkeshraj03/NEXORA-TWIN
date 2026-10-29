"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, type SessionInfo } from "@/lib/api";

export function AuthForm() {
  const router = useRouter();
  const [register, setRegister] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setPending(true); setError("");
    try {
      await api<SessionInfo>(`auth/${register ? "register" : "login"}`, {method: "POST", body: { email: fields.get("email"), password: fields.get("password"), ...(register ? {name: fields.get("name")} : {}) }});
      router.replace("/workspace"); router.refresh();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to sign in"); }
    finally { setPending(false); }
  }
  return <section className="auth-card panel"><span className="eyebrow">YOUR BUSINESS STARTS HERE</span><h1>{register ? "Create your account." : "Welcome back."}</h1><p>{register ? "One account. Independent workspaces for every business." : "Sign in to your business workspace."}</p><div className="auth-tabs" role="group" aria-label="Account action"><button aria-pressed={!register} disabled={pending} onClick={() => {setRegister(false); setError("");}}>Sign in</button><button aria-pressed={register} disabled={pending} onClick={() => {setRegister(true); setError("");}}>Create account</button></div><form onSubmit={event => void submit(event)}>
    <fieldset disabled={pending}>{register && <label>Your name<input name="name" autoComplete="name" required maxLength={100}/></label>}<label>Email address<input type="email" name="email" autoComplete="email" required maxLength={254}/></label><label>Password<input type="password" name="password" autoComplete={register ? "new-password" : "current-password"} required minLength={12} maxLength={128}/></label>{register && <small>Use 12–128 characters. Spaces count as part of your password.</small>}<button className="button submit-button" type="submit">{pending ? "Please wait…" : register ? "Create account" : "Sign in"}<span>→</span></button></fieldset>{error && <p role="alert" className="notice error">{error}</p>}</form><p className="fine-print">New businesses start empty. No demonstration records are added automatically.</p></section>;
}
