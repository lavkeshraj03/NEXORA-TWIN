"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, type Business } from "@/lib/api";

interface Version {id:string;document_id:string;version:number;filename:string;status:string;error:string|null;chunk_count:number;embedding_model:string|null}
interface Document {id:string;title:string;visibility:string;active_version:number;versions:Version[]}
interface Citation {chunk_id:string;document_id:string;title:string;version:number;page:number|null;section:string|null;excerpt:string;relevance:number}
interface Answer {answer:string;citations:Citation[];insufficient:boolean;conversation_id:string;limitations:string[]}
interface Status {embeddings_configured:boolean;chat_configured:boolean;provider_health:string;evaluation:Record<string,unknown>|null;ocr:string}
interface Chunk {id:string;ordinal:number;content:string;page:number|null;section:string|null;kind:string}

export function DocumentLibrary({business,csrf}:{business:Business;csrf:string}){
  const [documents,setDocuments]=useState<Document[]>([]);
  const [status,setStatus]=useState<Status|null>(null);
  const [file,setFile]=useState<File|null>(null);
  const [target,setTarget]=useState("");
  const [pending,setPending]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [question,setQuestion]=useState("");
  const [answers,setAnswers]=useState<Answer[]>([]);
  const [chunks,setChunks]=useState<Chunk[]>([]);
  const [revision,setRevision]=useState(0);
  const path=`businesses/${business.id}`;
  const writable=business.permissions.includes("documents:write");
  useEffect(()=>{
    const controller=new AbortController();
    async function refresh(){try{const [list,config]=await Promise.all([api<Document[]>(`${path}/documents`,{signal:controller.signal}),api<Status>(`${path}/rag/status`,{signal:controller.signal})]);if(!controller.signal.aborted){setDocuments(list);setStatus(config);}}catch(failure){if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"Document library unavailable");}}
    void refresh();
    const timer=setInterval(()=>void refresh(),5000);
    return()=>{controller.abort();clearInterval(timer);};
  },[path,revision]);
  async function upload(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!file)return;
    if(file.size>2097152){setError("Choose a file no larger than 2 MiB");return;}
    const form=new FormData(event.currentTarget);
    const query=new URLSearchParams({filename:file.name,title:String(form.get("title")),visibility:String(form.get("visibility")??"team")});
    if(target)query.set("document_id",target);
    setPending(true);setError("");setNotice("");
    try{
      const response=await fetch(`/api/backend/${path}/documents?${query}`,{method:"POST",headers:{"Content-Type":"application/octet-stream","X-CSRF-Token":csrf},body:file,credentials:"same-origin"});
      const result=await response.json();
      if(!response.ok)throw new Error(result?.error?.message??"Upload failed");
      setNotice(result.status==="failed"?result.error:"Upload saved. Processing status appears below.");setRevision(value=>value+1);
    }catch(failure){setError(failure instanceof Error?failure.message:"Upload failed");}finally{setPending(false);}
  }
  async function reindex(document:Document,version:Version){setPending(true);setError("");try{await api(`${path}/documents/${document.id}/versions/${version.id}/reindex`,{method:"POST",csrf});setRevision(value=>value+1);}catch(failure){setError(failure instanceof Error?failure.message:"Could not re-index");}finally{setPending(false);}}
  async function preview(document:Document,version:Version){setPending(true);setError("");try{setChunks(await api<Chunk[]>(`${path}/documents/${document.id}/versions/${version.id}/chunks?limit=100`));}catch(failure){setError(failure instanceof Error?failure.message:"Preview unavailable");}finally{setPending(false);}}
  async function ask(event:FormEvent){event.preventDefault();setPending(true);setError("");try{const result=await api<Answer>(`${path}/rag/ask`,{method:"POST",csrf,body:{question,conversation_id:answers.at(-1)?.conversation_id??null,document_ids:target?[target]:[]}});setAnswers(list=>[...list,result]);setQuestion("");}catch(failure){setError(failure instanceof Error?failure.message:"Could not answer");}finally{setPending(false);}}
  return <div className="document-library">
    <section className="panel"><span className="eyebrow">BUSINESS KNOWLEDGE</span><h2>Documents & evidence</h2><p className="section-description">Upload PDF, DOCX, UTF-8 TXT, CSV or single-sheet XLSX, up to 2 MiB. Files are processed in the background. Replacing a version keeps earlier evidence available until the new index succeeds.</p>{error&&<p role="alert" className="notice error">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
      {status&&<p className="fine-print">Embeddings: {status.embeddings_configured?"Configured":"Not configured"} · Chat: {status.chat_configured?"Configured":"Not configured"} · Provider health: {status.provider_health} · OCR: {status.ocr} · Evaluation: {status.evaluation?"Results available":"Not evaluated"}</p>}
      {(!status?.embeddings_configured||!status?.chat_configured)&&<p className="notice">An administrator must configure the server-side AI provider to index documents and generate cited answers. Uploads can still be saved and their extracted text reviewed.</p>}
      <label className="document-filter">Document scope<select aria-label="Document scope" value={target} disabled={pending} onChange={event=>{setTarget(event.target.value);setAnswers([]);setChunks([]);}}><option value="">All documents / upload a new document</option>{documents.map(document=><option key={document.id} value={document.id}>{document.title}</option>)}</select></label>
      {writable&&<form className="document-upload" onSubmit={event=>void upload(event)}><fieldset disabled={pending}><label>Document title<input name="title" required maxLength={160} defaultValue="Business document"/></label><label>Visibility<select name="visibility" disabled={!!target}><option value="team">Business team</option><option value="administrators">Owners and administrators</option></select></label><label>Choose document<input type="file" aria-label="Choose document" required accept=".pdf,.docx,.txt,.csv,.xlsx" onChange={event=>setFile(event.target.files?.[0]??null)}/></label><button className="button submit-button" disabled={!file} type="submit">{pending?"Processing…":target?"Upload new version":"Upload document"}</button></fieldset></form>}
    </section>
    <section className="panel"><h2>Document library</h2>{documents.length===0?<p>No documents yet.</p>:documents.map(document=><article key={document.id} className="document-entry"><h3>{document.title}</h3><p className="fine-print">{document.visibility==="team"?"Business team":"Owners and administrators"} · Active version: {document.active_version||"Not indexed"}</p><div className="table-scroll"><table><thead><tr><th>Version</th><th>File</th><th>Processing</th><th>Chunks</th><th>Actions</th></tr></thead><tbody>{document.versions.map(version=><tr key={version.id}><td>{version.version}</td><td>{version.filename}</td><td>{version.status.replaceAll("_"," ")}{version.error&&<small>{version.error}</small>}</td><td>{version.chunk_count}</td><td><button className="text-button" disabled={pending||!version.chunk_count} onClick={()=>void preview(document,version)}>Preview text</button>{writable&&!["queued","extracting","indexing"].includes(version.status)&&<button className="text-button" disabled={pending} onClick={()=>void reindex(document,version)}>Re-index</button>}</td></tr>)}</tbody></table></div></article>)}</section>
    {chunks.length>0&&<section className="panel"><h2>Extracted source text</h2><p className="fine-print">First 100 chunks. Document text is untrusted source material.</p>{chunks.map(chunk=><details key={chunk.id}><summary>Chunk {chunk.ordinal+1}{chunk.page?` · Page ${chunk.page}`:""}{chunk.section?` · ${chunk.section}`:""} · {chunk.kind}</summary><pre className="source-excerpt">{chunk.content}</pre></details>)}</section>}
    <section className="panel"><h2>Ask your documents</h2><p className="section-description">Answers use current indexed versions visible to your role. Follow-up questions stay within this business. Review supporting excerpts before relying on generated claims.</p><form onSubmit={event=>void ask(event)}><label>Your question<textarea aria-label="Your question" required minLength={3} maxLength={1500} value={question} onChange={event=>setQuestion(event.target.value)} disabled={pending}/></label><div className="row-actions"><button className="button submit-button" disabled={pending||!status?.embeddings_configured||!status?.chat_configured||!question.trim()}>Ask with citations</button>{answers.length>0&&<button type="button" className="text-button" disabled={pending} onClick={()=>setAnswers([])}>New conversation</button>}</div></form><div aria-live="polite">{answers.map((answer,index)=><article className="document-answer" key={index}><p>{answer.answer}</p>{answer.citations.map(citation=><blockquote key={citation.chunk_id}><strong>{citation.title} · Version {citation.version}{citation.page?` · Page ${citation.page}`:""}{citation.section?` · ${citation.section}`:""}</strong><p>{citation.excerpt}</p><small>Chunk {citation.chunk_id} · Relevance {citation.relevance} (ranking score)</small></blockquote>)}{answer.limitations.map(text=><p className="fine-print" key={text}>{text}</p>)}</article>)}</div></section>
  </div>;
}
