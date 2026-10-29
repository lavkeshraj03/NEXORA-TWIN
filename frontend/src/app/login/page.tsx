import { redirect } from "next/navigation";
import { AuthForm } from "@/components/auth-form";
import { serverSession } from "@/lib/server-api";

export default async function Login() {
  if (await serverSession()) redirect("/workspace");
  return <main id="main-content" tabIndex={-1} className="auth-page"><a href="/" className="brand auth-brand"><span className="brand-mark">N</span>NEXORA TWIN</a><AuthForm/><a className="back-link" href="/">← Back to overview</a></main>;
}
