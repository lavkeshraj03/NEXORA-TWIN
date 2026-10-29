import { redirect } from "next/navigation";
import { serverSession } from "@/lib/server-api";
import { Workspace } from "@/components/workspace";

export const dynamic = "force-dynamic";
export default async function WorkspacePage() {
  const session = await serverSession();
  if (!session) redirect("/login");
  return <Workspace session={session}/>;
}
