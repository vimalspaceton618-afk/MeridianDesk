'use strict';
/* Actual hosted Windows + Edge screenshot acceptance of the existing MeridianDesk UI.
   All market observations are explicit synthetic test fixtures. Not user's E: machine. */
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('../.previewdeps/node_modules/playwright-core');

const root=path.join(__dirname,'..'),output=path.join(root,'global-preview-output');
const frames=path.join(output,'frames');fs.mkdirSync(frames,{recursive:true});
const env={...process.env,MERIDIAN_BROKER:'off',APCA_API_KEY_ID:'',
 APCA_API_SECRET_KEY:'',PYTHONDONTWRITEBYTECODE:'1'};
for(const key of Object.keys(env)){
 if(key.endsWith('_API_KEY')||key.endsWith('_TOKEN')||key.startsWith('TRADINGAGENTS_')){
  if(key!=='APCA_API_KEY_ID'&&key!=='APCA_API_SECRET_KEY')delete env[key];
 }
}
let service,browser;const results=[],captures=[];
function check(name){results.push(name);console.log('PASS '+name)}
async function screenshot(page,name,ms=1350){
 const filename=String(captures.length+1).padStart(2,'0')+'-'+name+'.png';
 await page.screenshot({path:path.join(frames,filename),animations:'disabled'});
 captures.push({filename,name,duration_ms:ms});
 console.log('CAPTURE '+filename);
}
function startService(){
 service=spawn('python',['-u','tests/hosted_global_windows.py'],{
  cwd:root,env,windowsHide:true,stdio:['pipe','pipe','pipe']});
 return new Promise((resolve,reject)=>{
  let output='';const timeout=setTimeout(()=>reject(Error('Local server startup timed out')),30000);
  service.stdout.on('data',b=>{
   output+=b.toString();
   const match=output.match(/(?:^|\r?\n)READY (http:\/\/127\.0\.0\.1:\d+\/#[^\r\n]+)/);
   if(match){clearTimeout(timeout);resolve(match[1])}
  });
  service.on('exit',code=>reject(Error('Local server stopped early with code '+code)));
  service.on('error',reject);
 });
}
async function main(){
 const url=await startService();
 browser=await chromium.launch({channel:'msedge',headless:true,
  args:['--disable-background-networking','--disable-sync','--no-first-run']});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url,{waitUntil:'domcontentloaded'});
 await page.locator('.watch [data-symbol="DEMO"]').waitFor({timeout:20000});
 await page.locator('#chart').waitFor();
 check('Actual MeridianDesk UI started in hosted Windows Edge with DEMO');
 await screenshot(page,'existing-market-overview',1700);

 await page.locator('[data-act="catalog"]').click();
 await page.locator('#modal[open]').waitFor();
 assert.match(await page.locator('#modalLabel').innerText(),/RESEARCH-ONLY/);
 assert.match(await page.locator('#globalSummary').innerText(),/curated worldwide/);
 check('Authenticated worldwide catalog loaded into existing dialog');
 await screenshot(page,'worldwide-stock-explorer',1850);

 await page.locator('#globalRegion').selectOption('Japan');
 await page.locator('#globalSearch').fill('Toyota');
 await page.locator('button[data-global-symbol="7203.T"]').waitFor();
 assert.equal(await page.locator('button[data-global-symbol]').count(),1);
 check('Country filter and company search locate Toyota in Japan');
 await screenshot(page,'country-filtered-equity-search',1500);

 await page.locator('button[data-global-symbol="7203.T"]').click();
 await page.locator('#modal').waitFor({state:'hidden'});
 await page.locator('canvas[aria-label^="7203.T"]').waitFor({timeout:15000});
 assert.match(await page.locator('.global-disclosure').innerText(),/Research only/);
 assert.match(await page.locator('.chart-foot').innerText(),/SYNTHETIC TEST FIXTURE/);
 assert.match(await page.locator('.price-unit').innerText(),/JPY/);
 assert.equal(await page.locator('[data-act="ticket"]').count(),0);
 check('Research-only international chart has explicit synthetic fixture source and JPY unit; no order button');
 await screenshot(page,'japan-quote-synthetic-validation',2200);

 await page.locator('nav [data-page="research"]').click();
 const mission=page.locator('.panel').filter({has:page.getByRole('heading',{name:'Autonomous research mission',exact:true})});
 await mission.waitFor();
 await mission.getByText('ABSTAIN',{exact:true}).first().waitFor({timeout:15000});
 assert.match(await mission.innerText(),/Source: SYNTHETIC TEST FIXTURE/);
 assert.match(await mission.innerText(),/Execution disabled/);
 check('On-demand global stock automatically ran six local evidence agents and abstained on synthetic data');
 await screenshot(page,'autonomous-agent-research',2200);
 await mission.locator('button[data-act="result"]').click();
 await page.locator('#modal[open]').waitFor();
 const report=await page.locator('#modalBody').innerText();
 assert.match(report,/"schema": "research-agents.v1"/);
 assert.match(report,/"execution": "DISABLED"/);
 assert.match(report,/"passed": true/);
 assert.match(report,/"agents": \[/);
 check('Structured evidence report displays SHA256 input proof and independently checked six-agent workflow');
 await screenshot(page,'autonomous-evidence-report',1800);
 await page.locator('#closeModal').click();
 await page.locator('nav [data-page="market"]').click();
 await page.locator('button[data-act="watch-toggle"]').waitFor();

 await page.locator('button[data-act="watch-toggle"]').click();
 await page.getByRole('button',{name:'Unpin stock'}).waitFor({timeout:12000});
 assert.ok(await page.locator('.watch button[data-symbol="7203.T"]').isVisible());
 check('Pin stock persisted to local database and appears in watchlist');
 await screenshot(page,'pinned-international-watchlist',1900);

 await page.locator('[data-act="watch-toggle"]').click();
 await page.getByRole('button',{name:'Pin to watchlist'}).waitFor({timeout:12000});
 await page.locator('div.watch button[data-symbol="DEMO"]').click();
 await page.locator('#chart').waitFor();
 assert.equal(await page.locator('[data-act="ticket"]').count(),1);
 check('Unpin stock restores original DEMO workflow with paper-order button');
 await screenshot(page,'original-paper-market-restored',1400);

 assert.deepEqual(errors,[]);
 check('No JavaScript page errors during hosted Windows UI scenario');
 const meta={scope:'GitHub-hosted Windows Microsoft Edge browser (not local E: installation)',
  source:'Actual PR branch MeridianDesk frontend; modified market provider returns only explicit synthetic TEST FIXTURE',
  market_data_real:false, broker_mode:'off', no_live_orders:true,
  checks:results,captures,created_utc:new Date().toISOString()};
 fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify(meta,null,2));
 console.log('GLOBAL_WINDOWS_SUCCESS '+results.length+' checks and '+captures.length+' screenshots');
}
main().catch(err=>{console.error('GLOBAL_WINDOWS_FAILURE '+err.stack);process.exitCode=1})
 .finally(async()=>{
  if(browser)await browser.close().catch(()=>{});
  if(service){service.stdin.end();setTimeout(()=>{if(!service.killed)service.kill()},5000).unref()}
 });
