const {spawn}=require('node:child_process');
const fs=require('node:fs'); const os=require('node:os');
const path=require('node:path');
const WS=WebSocket;
const root=path.resolve(__dirname,'..');
const base=process.env.NEXORA_BASE_URL || 'http://localhost:3000';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'nexora-browser-'));
// Uses only Node 22+ built-ins and an installed Chrome/Chromium binary.
const chrome=spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless=new','--remote-debugging-port=0','--user-data-dir='+dir,'--no-first-run','--disable-extensions','--disable-background-networking','about:blank'],{stdio:'ignore'});
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{let ws;try{
 fs.mkdirSync(root+'/.local',{recursive:true});
 let pages;for(let i=0;i<80;i++){try{const port=fs.readFileSync(path.join(dir,'DevToolsActivePort'),'utf8').split('\n')[0];pages=await (await fetch('http://127.0.0.1:'+port+'/json')).json();break;}catch{await wait(250);}}
 if(!pages)throw Error('Chrome did not start');
 ws=new WS(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 let id=0;const pending=new Map(),errors=[];
 ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);});
 const cmd=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
 const evaluate=async expression=>(await cmd('Runtime.evaluate',{expression,returnByValue:true})).result.value;
 await cmd('Page.enable');await cmd('Runtime.enable');const checks=[];
 for(const [path,width,height] of [['/login',1280,900],['/login',390,844],['/',390,844]]){
  await cmd('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
  await cmd('Page.navigate',{url:base+path});
  for(let i=0;i<80;i++){if(await evaluate('document.readyState === "complete" && !!document.getElementById("main-content")'))break;await wait(250);}
  const main=await evaluate('!!document.querySelector("main#main-content")');if(!main)throw Error('Missing main landmark');
  const ax=await cmd('Accessibility.getFullAXTree');if(!ax.nodes.some(n=>n.role?.value==='main'))throw Error('Missing accessibility main role');
  const overflow=await evaluate('document.documentElement.scrollWidth > innerWidth');if(overflow)throw Error('Horizontal overflow at '+width+' '+path);
  await evaluate('document.activeElement.blur()');
  await cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  if(!await evaluate('document.activeElement.classList.contains("skip-link")'))throw Error('Skip link is not first keyboard stop');
  await cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  if(!await evaluate('document.activeElement.id === "main-content"'))throw Error('Skip link did not focus main');
  if(path==='/login'&&!ax.nodes.some(n=>n.role?.value==='textbox'&&n.name?.value==='Email address'))throw Error('Email accessible name missing');
  const shot=await cmd('Page.captureScreenshot',{format:'png'});fs.writeFileSync(root+'/.local/phase10-'+(path==='/login'?'login':'home')+'-'+width+'.png',Buffer.from(shot.data,'base64'));
  checks.push({path,width,mainLandmark:true,skipLinkFocus:true,horizontalOverflow:false});
 }
 if(errors.length)throw Error('Browser runtime errors: '+errors.join(', '));
 fs.writeFileSync(root+'/.local/phase10-browser.json',JSON.stringify({status:'passed',checks,runtimeErrors:errors},null,2));console.log('Chrome keyboard, accessibility tree and mobile layout checks passed.');
 }finally{if(ws)ws.close();chrome.kill('SIGTERM');await wait(500);fs.rmSync(dir,{recursive:true,force:true});}})().catch(e=>{console.error(e.message);process.exitCode=1;});
