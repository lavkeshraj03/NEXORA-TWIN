import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context) {
  const { path } = await context.params;
  if (!["auth", "businesses"].includes(path[0])) return NextResponse.json({error:{message:"Route not found"}}, {status:404});
  const headers=new Headers();
  for (const name of ["origin","content-type","x-csrf-token"]) {
    const value=request.headers.get(name);
    if(value)headers.set(name,value);
  }
  const cookie=request.cookies.get("nexora_session");
  if(cookie)headers.set("cookie",`nexora_session=${encodeURIComponent(cookie.value)}`);
  let body:ArrayBuffer|undefined;
  const importUpload=path.length===3&&path[0]==="businesses"&&["imports","documents"].includes(path[2])&&request.method==="POST";
  const limit=importUpload?2*1024*1024:16384;
  if(!["GET","HEAD"].includes(request.method)) {
    const tooLarge=()=>NextResponse.json({error:{message:"Request is too large"}},{status:413});
    if(Number(request.headers.get("content-length")??0)>limit)return tooLarge();
    const reader=request.body?.getReader();
    const chunks:Uint8Array[]=[];
    let size=0;
    if(reader)while(true){
      const chunk=await reader.read();
      if(chunk.done)break;
      size+=chunk.value.byteLength;
      if(size>limit){await reader.cancel();return tooLarge();}
      chunks.push(chunk.value);
    }
    body=new ArrayBuffer(size);
    const combined=new Uint8Array(body);
    let offset=0;
    for(const chunk of chunks){combined.set(chunk,offset);offset+=chunk.byteLength;}
  }
  try {
    const base=process.env.API_INTERNAL_URL??"http://127.0.0.1:8000";
    const target=`${base}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
    const response=await fetch(target,{method:request.method,headers,body,cache:"no-store",redirect:"manual",signal:AbortSignal.timeout(path.includes("rag")||path.includes("analyst")?300000:path.includes("ml")?60000:path.includes("imports")||path.includes("documents")||path.includes("export")?60000:15000)});
    const outgoing=new Headers({"Cache-Control":"no-store","Content-Type":response.headers.get("Content-Type")??"application/json"});
    for(const cookieHeader of response.headers.getSetCookie())outgoing.append("Set-Cookie",cookieHeader);
    const disposition=response.headers.get("Content-Disposition");
    if(disposition)outgoing.set("Content-Disposition",disposition);
    const requestId=response.headers.get("x-request-id");
    if(requestId)outgoing.set("X-Request-ID",requestId);
    return new Response(response.status===204?null:await response.arrayBuffer(),{status:response.status,headers:outgoing});
  } catch {
    return NextResponse.json({error:{message:"The application service is unavailable. Try again shortly."}},{status:503});
  }
}

export {forward as GET,forward as POST,forward as PUT,forward as PATCH,forward as DELETE};
