// Real authenticated user journey. Run only through the disposable --all-flows verifier.
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const base = process.env.NEXORA_BASE_URL;
assert.equal(base, 'http://localhost:3001');
assert.match(process.env.NEXORA_ISOLATED_PROJECT || '', /^nexora-acceptance-[0-9a-f]{12}$/);
const data = process.env.NEXORA_BROWSER_DATA_DIR;
const manifest = JSON.parse(fs.readFileSync(path.join(data, 'manifest.json')));
const output = path.join(root, '.local/e2e');
const downloads = fs.mkdtempSync(path.join(output, 'downloads-'));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'nexora-journey-'));
const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + profile,
  '--no-first-run', '--disable-extensions', '--disable-background-networking', 'about:blank'
], {stdio:'ignore'});
let startupError;
chrome.on('error', error => {startupError = error;});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const result = {status:'failed', steps:[], runtimeErrors:[], downloadDirectory:downloads};
const record = () => fs.writeFileSync(path.join(output, 'browser-journey.json'), JSON.stringify(result, null, 2));
let ws, cmd, evaluate, business, baseline, monthly, investigation, scenarios=[];
const email = 'nexora-browser-' + crypto.randomBytes(8).toString('hex') + '@example.com';
const password = crypto.randomBytes(24).toString('base64url');
const q = JSON.stringify;

async function until(expression, description, timeout=30000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await evaluate(expression)) return;
    await delay(150);
  }
  const alerts = await evaluate('[...document.querySelectorAll("[role=alert]")].map(x=>x.textContent).join("; ")');
  throw Error('Timed out: ' + description + (alerts ? '; UI: ' + alerts : ''));
}
async function value(selector, text) {
  await until(`!!document.querySelector(${q(selector)}) && !document.querySelector(${q(selector)}).matches(':disabled')`, selector);
  await evaluate(`(()=>{const e=document.querySelector(${q(selector)}); const proto=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${q(String(text))});e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()`);
  await delay(60);
}
const aria = name => `[aria-label=${q(name)}]`;
async function button(text) {
  const expression = `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${q(text)} && b.getClientRects().length && !b.matches(':disabled'))`;
  await until(`!!(${expression})`, 'enabled button ' + text);
  await evaluate(`(${expression}).click()`);
  await delay(100);
}
async function checkbox(text) {
  await evaluate(`(()=>{const l=[...document.querySelectorAll('label')].find(l=>l.textContent.includes(${q(text)}));if(!l)throw Error('Checkbox label missing');l.querySelector('input[type=checkbox]').click();return true;})()`);
  await delay(80);
}
async function navigate(name, selector) {await button(name); await until(`!!document.querySelector(${q(selector)})`, name);}
async function upload(selector, filename) {
  const {root:document} = await cmd('DOM.getDocument');
  const {nodeId} = await cmd('DOM.querySelector', {nodeId:document.nodeId,selector});
  assert(nodeId, 'File input not found: ' + selector);
  await cmd('DOM.setFileInputFiles', {nodeId,files:[filename]});
  await delay(100);
}
async function api(route) {
  return evaluate(`fetch('/api/backend/'+${q(route)}).then(async r=>{if(!r.ok)throw Error('Assertion GET failed '+r.status);return r.json()})`);
}
async function screenshot(name) {
  const shot = await cmd('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync(path.join(output, name+'.png'),Buffer.from(shot.data,'base64'));
}
async function stage(name, work) {
  const row = {name,status:'running'};result.steps.push(row);record();console.log('BROWSER START:', name);
  const begun=Date.now();
  try {await work();row.status='passed';}
  catch(error){row.status='failed';row.error=error.message;throw error;}
  finally {row.seconds=+( (Date.now()-begun)/1000).toFixed(2);record();}
  console.log('BROWSER PASS:',name,row.seconds+'s');
}
async function downloadLink(text) {
  const before = new Set(fs.readdirSync(downloads));
  await evaluate(`(()=>{const a=[...document.querySelectorAll('a')].find(a=>a.textContent.includes(${q(text)}));if(!a)throw Error('Download link missing');a.click();return true;})()`);
  for(let i=0;i<160;i++) {
    const name=fs.readdirSync(downloads).find(n=>!before.has(n)&&!n.endsWith('.crdownload'));
    if(name&&fs.statSync(path.join(downloads,name)).size>0)return path.join(downloads,name);
    await delay(125);
  }
  throw Error('Download did not complete: '+text);
}

(async()=>{
 try {
  let pages;
  for(let i=0;i<100;i++){
    if(startupError)throw startupError;
    try {const port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];pages=await(await fetch('http://127.0.0.1:'+port+'/json')).json();break;}catch{await delay(150);}
  }
  assert(pages,'Chrome failed to start');
  ws = new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  let id=0;const pending=new Map();
  ws.addEventListener('message',event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')result.runtimeErrors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);});
  cmd=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;const timer=setTimeout(()=>{pending.delete(n);reject(Error('CDP timeout '+method));},310000);pending.set(n,{resolve,reject,timer});ws.send(JSON.stringify({id:n,method,params}));});
  evaluate=async expression=>{const r=await cmd('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;};
  await cmd('Page.enable');await cmd('Runtime.enable');
  await cmd('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
  await cmd('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});

  await stage('anonymous protection, registration and empty account',async()=>{
    await cmd('Page.navigate',{url:base+'/workspace'});
    await until(`location.pathname==='/login' && !!document.querySelector('input[name=email]')`,'anonymous login redirect');
    await button('Create account');
    await value('input[name=name]','Browser Journey Owner');await value('input[name=email]',email);await value('input[name=password]',password);
    await evaluate('document.querySelector("form").requestSubmit()');
    await until(`location.pathname==='/workspace' && !![...document.querySelectorAll('button')].find(b=>b.textContent.includes('Create your first business'))`,'registered empty workspace');
  });
  await stage('business creation and empty dashboard',async()=>{
    await button('+ New business');await value('.business-form input[name=name]','E2E Browser Retail');await button('Create empty workspace');
    await until(`!!document.querySelector('.operational-dashboard') && document.body.textContent.includes('Your business is ready for its data.')`,'empty business');
    business=(await api('businesses'))[0];result.businessId=business.id;
    assert.equal(business.currency,'INR');
  });
  await stage('six CSV imports, preview isolation and explicit confirmation',async()=>{
    await navigate('Import data','.data-importer');
    for(const resource of ['customers','suppliers','products','inventory','orders','expenses']){
      await value(aria('Import record type'),resource);
      await upload(aria('Choose data file'),path.join(data,resource+'.csv'));
      await button('Upload & preview');
      await until(`!![...document.querySelectorAll('.outline-badge')].find(e=>e.textContent==='VALIDATED')`,'validated '+resource);
      assert.equal((await api(`businesses/${business.id}/${resource}`)).total,0,'Preview unexpectedly wrote '+resource);
      await checkbox('I reviewed this preview and confirm importing');await button('Confirm import');
      await until(`document.body.textContent.includes('Import complete:')`,'committed '+resource);
      const expected=resource==='orders'?manifest.orders:manifest.resource_rows[resource];
      assert.equal((await api(`businesses/${business.id}/${resource}`)).total,expected);
    }
  });
  await stage('dashboard arithmetic and expense-completeness confirmation',async()=>{
    await navigate('Overview','.operational-dashboard');
    await value(aria('Report start'),manifest.report_start);await value(aria('Report end'),manifest.report_end);await button('Apply dates');
    await until(`!!document.querySelector('.metric-grid') && document.querySelector('[aria-label="Report start"]').value===${q(manifest.report_start)}`,'report dates');
    let report=await api(`businesses/${business.id}/dashboard?start=${manifest.report_start}&end=${manifest.report_end}`);
    assert.equal(report.metrics.revenue,manifest.expected_metrics.revenue);assert.equal(report.metrics.operating_profit,null);
    await checkbox('I confirm that every operating expense');await button('Confirm period coverage');
    await until(`document.body.textContent.includes('Mark expense coverage incomplete')`,'expense confirmation');
    report=await api(`businesses/${business.id}/dashboard?start=${manifest.report_start}&end=${manifest.report_end}`);
    assert.equal(report.metrics.operating_profit,manifest.expected_metrics.operating_profit);
    await screenshot('dashboard-desktop');
  });
  await stage('data explorer inspection',async()=>{
    await navigate('Data explorer','.data-explorer');await until(`document.body.textContent.includes('NX-')||document.body.textContent.includes('Nexa')||!!document.querySelector('tbody tr')`,'data records');
  });
  await stage('document upload, real worker indexing and local-model cited answer',async()=>{
    await navigate('Documents & answers','.document-library');await value('input[name=title]','E2E Returns Policy');
    await upload(aria('Choose document'),path.join(data,'documents/demo-returns-policy.txt'));await button('Upload document');
    await until(`document.body.textContent.includes('Active version: 1')`,'document indexing',200000);
    const docs=await api(`businesses/${business.id}/documents`);await value(aria('Document scope'),docs[0].id);
    await button('Preview text');await until(`!!document.querySelector('.source-excerpt')`,'extracted source');
    await value(aria('Your question'),'How long do customers have to return an item, and what proof is required?');await button('Ask with citations');
    await until(`!!document.querySelector('.document-answer blockquote')`,'grounded answer',300000);
    assert.match(await evaluate('document.querySelector(".document-answer").textContent'),/thirty days|30 days/i);
  });
  await stage('sales, demand and inactivity training, evaluation and activation',async()=>{
    await navigate('Forecasts & risk','.forecast-workspace');
    for(const task of ['sales','demand','churn']){
      await value(aria('Model task'),task);await value(aria('Training data'),'demo');
      if(task!=='churn')await value(aria('History starts'),manifest.history_start);
      await value(aria('Observed through'),manifest.history_end);
      if(task==='demand')await value('input[name=product_sku]',manifest.demand_sku);
      const checked=await evaluate('document.querySelector("input[name=coverage]").checked');if(!checked)await checkbox('I confirm the required history');
      await button('Train & evaluate');
      await until(`!!document.querySelector('.model-provenance') && [...document.querySelectorAll('button')].some(b=>b.textContent==='Train & evaluate'&&!b.matches(':disabled'))`,'evaluated '+task,60000);
      const runs=await api(`businesses/${business.id}/ml/runs`);assert(runs.some(r=>r.task===task),'Missing saved '+task);
      if(task==='sales'){
        const buttons=await evaluate('[...document.querySelectorAll("button")].map(b=>b.textContent.trim())');
        const activate=buttons.find(t=>t.toLowerCase().includes('activate'));assert(activate,'Activation control missing');await button(activate);
        await until(`document.body.textContent.includes('This saved model is active')`,'explicit activation');
      }
    }
    assert.equal((await api(`businesses/${business.id}/ml/runs`)).length,3);
  });
  await stage('snapshots, captured sources and comparison',async()=>{
    await navigate('Digital twin','.twin-workspace');
    const monthEnd=new Date(manifest.report_end+'T12:00:00Z');monthEnd.setUTCDate(0);const monthStart=new Date(monthEnd);monthStart.setUTCDate(1);
    for(const [name,start,end] of [['E2E October baseline',manifest.report_start,manifest.report_end],['E2E previous calendar month',monthStart.toISOString().slice(0,10),monthEnd.toISOString().slice(0,10)]]){
      await value(aria('Twin reporting starts'),start);await value(aria('Twin reporting ends'),end);await value(aria('Snapshot name'),name);await button('Save snapshot');
      await until(`document.body.textContent.includes('Snapshot saved with source values.') && [...document.querySelectorAll('button')].some(b=>b.textContent==='Save snapshot'&&!b.matches(':disabled'))`,'saved '+name);
      const saved=(await api(`businesses/${business.id}/twin/snapshots`)).find(row=>row.name===name);assert(saved);
      await value(aria('State to inspect'),'current');await value(aria('State to inspect'),saved.id);
      await until(`document.body.textContent.includes('Integrity verified and state reproduced')`,'reopened and verified '+name);
    }
    const snapshots=await api(`businesses/${business.id}/twin/snapshots`);baseline=snapshots.find(s=>s.name==='E2E October baseline');monthly=snapshots.find(s=>s.name==='E2E previous calendar month');assert(baseline&&monthly);
    await value(aria('Left snapshot'),monthly.id);await value(aria('Right snapshot'),baseline.id);await button('Compare snapshots');await until(`document.body.textContent.includes('Changed sources:')`,'snapshot comparison');
  });
  await stage('two reviewed scenarios, sensitivity and comparison',async()=>{
    await navigate('What-If Lab','.simulation-workspace');await value(aria('Scenario baseline'),baseline.id);
    for(const elasticity of ['-1','-2']){
      await value(aria('Scenario name'),'E2E price +10 elasticity '+elasticity);await value(aria('Product price change (%)'),'10');await value(aria('Price elasticity assumption'),elasticity);await button('Preview assumptions');
      await until(`!!document.querySelector('[aria-label="Confirm scenario assumptions"]')`,'scenario preview');
      await evaluate(`document.querySelector(${q(aria('Confirm scenario assumptions'))}).click()`);await button('Run & save scenario');
      await until(`document.body.textContent.includes('Hypothetical scenario saved.')`,'saved scenario');
    }
    scenarios=await api(`businesses/${business.id}/simulations/runs`);assert.equal(scenarios.length,2);
    await value(aria('Left scenario'),scenarios[0].id);await value(aria('Right scenario'),scenarios[1].id);await button('Compare scenarios');
    await until(`document.querySelectorAll('.simulation-workspace table').length>=3`,'scenario comparison table');
  });
  await stage('live analyst investigation and captured evidence',async()=>{
    await navigate('AI analyst','.analyst-workspace');await value(aria('Business question'),'Compare recorded revenue, COGS and gross profit with the previous equal-length period.');await value(aria('Analyst reporting starts'),manifest.report_start);await value(aria('Analyst reporting ends'),manifest.report_end);await button('Investigate question');
    await until(`document.body.textContent.includes('Tool execution trail')`,'completed analyst',300000);
    const history=await api(`businesses/${business.id}/analyst/investigations`);investigation=history[0];assert(['completed','partial'].includes(investigation.status));
    await screenshot('analyst-desktop');
  });
  await stage('graph refresh, SKU search and source relationships',async()=>{
    await navigate('Knowledge graph','.knowledge-workspace');await button('Refresh graph from records');
    await until(`document.body.textContent.includes('source-backed graph snapshot was saved')`,'graph build');
    await value(aria('Graph entity type'),'product');await value(aria('Graph entity search'),'NX-PEN-01');await button('Search entities');
    await until(`!!document.querySelector('.graph-entities button') && document.querySelector('.graph-entities button').textContent.includes('NX-PEN-01')`,'SKU search');
    await evaluate('document.querySelector(".graph-entities button").click()');
    await until(`!!document.querySelector('.relationship-map')`,'graph relationships');
    await value(aria('Graph relationship filter'),'has_balance');
    await until(`document.querySelectorAll('.relationship-map [role=button]').length===2`,'stock relationship filter');
    await evaluate('document.querySelector(".relationship-map [role=button]").focus()');
    await cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    const graph=await api(`businesses/${business.id}/knowledge-graph`);assert(graph.node_count>1000&&graph.edge_count>2000);
  });
  await stage('all seven report types and real CSV/PDF downloads',async()=>{
    await navigate('Reports & exports','.reports-workspace');
    const models=await api(`businesses/${business.id}/ml/runs`);
    for(const kind of ['revenue_expenses','monthly','inventory_risk','sales_forecast','customer_inactivity','scenario_comparison','investigation']){
      await value(aria('Report type'),kind);await value(aria('Report name'),'E2E '+kind);
      if(['revenue_expenses','monthly','inventory_risk'].includes(kind))await value(aria('Report source snapshot'),kind==='monthly'?monthly.id:baseline.id);
      if(['sales_forecast','customer_inactivity'].includes(kind))await value(aria('Report model source'),models.find(m=>m.task===(kind==='sales_forecast'?'sales':'churn')).id);
      if(kind==='scenario_comparison'){await value(aria('Report left scenario'),scenarios[0].id);await value(aria('Report right scenario'),scenarios[1].id);}
      if(kind==='investigation')await value(aria('Report investigation source'),investigation.id);
      await button('Generate report');await until(`!!document.querySelector('.report-sheet h2')&&document.querySelector('.report-sheet h2').textContent===${q('E2E '+kind)}`,'report '+kind);
      const csv=await downloadLink('Download report CSV');assert(fs.readFileSync(csv).length>100);
      const pdf=await downloadLink('Download report PDF');assert.equal(fs.readFileSync(pdf).subarray(0,5).toString(),'%PDF-');
    }
    assert.equal((await api(`businesses/${business.id}/reports`)).length,7);await screenshot('reports-desktop');
  });
  await stage('business settings, second business and switching isolation',async()=>{
    await navigate('Business settings','.business-form');await button('Save business settings');await until(`document.body.textContent.includes('Business settings')||!!document.querySelector('.operational-dashboard')`,'settings saved');
    await button('+ New business');await value('.business-form input[name=name]','E2E Empty Restaurant');await value('.business-form select[name=business_type]','restaurant');await button('Create empty workspace');
    await until(`document.body.textContent.includes('Your business is ready for its data.')`,'second empty business');
    const businesses=await api('businesses');const second=businesses.find(b=>b.id!==business.id);assert(second&&second.business_type==='restaurant');
    assert.equal((await api(`businesses/${second.id}/orders`)).total,0);
    await value(aria('Switch business'),business.id);await until(`document.querySelector('main h1')?.textContent==='E2E Browser Retail' && !!document.querySelector('.operational-dashboard')`,'switch back');
  });
  await stage('team and audit screens, mobile workspace and logout/relogin',async()=>{
    await navigate('Team','.team-form');assert.match(await evaluate('document.body.textContent'),/Browser Journey Owner/);
    // A teammate must register first. Use an independent HTTP client for setup so
    // its session cannot replace the owner's actual browser session.
    const response=await fetch(base+'/api/backend/auth/register',{method:'POST',headers:{Origin:base,'Content-Type':'application/json'},body:JSON.stringify({name:'Browser Journey Viewer',email:'viewer-'+email,password:crypto.randomBytes(24).toString('base64url')})});
    assert.equal(response.status,201);const viewer=await response.json();
    const viewerCookie=response.headers.getSetCookie().map(value=>value.split(';')[0]).join('; ');
    await value('.team-form input[name=email]','viewer-'+email);await value('.team-form select[name=role]','viewer');await button('Add teammate');
    await until(`document.body.textContent.includes('Browser Journey Viewer')`,'team member row');
    const viewerRead=await fetch(base+`/api/backend/businesses/${business.id}`,{headers:{Cookie:viewerCookie}});assert.equal(viewerRead.status,200);
    const viewerWrite=await fetch(base+`/api/backend/businesses/${business.id}/customers`,{method:'POST',headers:{Cookie:viewerCookie,Origin:base,'X-CSRF-Token':viewer.csrf_token,'Content-Type':'application/json'},body:JSON.stringify({rows:[{external_id:'DENIED',name:'Must not be created'}]})});assert.equal(viewerWrite.status,403);
    const ownerReports=await api(`businesses/${business.id}/reports`);
    const privateReport=await fetch(base+`/api/backend/businesses/${business.id}/reports/${ownerReports[0].id}`,{headers:{Cookie:viewerCookie}});assert.equal(privateReport.status,404);
    await navigate('Audit history','.audit-list');assert((await api(`businesses/${business.id}/audit-logs`)).length>0);
    await cmd('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await navigate('Overview','.operational-dashboard');await screenshot('workspace-mobile');
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'),false,'Mobile workspace overflows');
    await button('Sign out →');await until(`location.pathname==='/login'`,'logout');
    const unauth=await evaluate(`fetch('/api/backend/auth/me').then(r=>r.status)`);assert.equal(unauth,401);
    await value('input[name=email]',email);await value('input[name=password]',password);await evaluate('document.querySelector("form").requestSubmit()');
    await until(`location.pathname==='/workspace' && !!document.querySelector('.tenant-select')`,'relogin');
    assert.equal((await api('businesses')).length,2);await button('Sign out →');await until(`location.pathname==='/login'`,'final logout');
  });
  assert.equal(result.runtimeErrors.length,0,'Browser runtime exceptions');result.status='passed';record();console.log('Authenticated browser journey passed.');
 }catch(error){result.error=error.message;record();try{if(cmd)await screenshot('failure');}catch{}console.error(error.stack);process.exitCode=1;}
 finally {if(ws)ws.close();chrome.kill('SIGTERM');await delay(500);fs.rmSync(profile,{recursive:true,force:true});}
})();
