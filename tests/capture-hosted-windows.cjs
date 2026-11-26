'use strict';
/*
 * Capture real frames from MeridianDesk loaded in Microsoft Edge on a clean
 * GitHub-hosted Windows runner. This is NOT validation of the user's E: drive.
 * Synthetic DEMO only; no broker credentials or live market connections.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {chromium} = require('../.previewdeps/node_modules/playwright-core');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'preview-output');
const frames = path.join(output, 'frames');
fs.mkdirSync(frames, {recursive:true});
const checks = [];
const captures = [];
let server, browser;
const env = {...process.env, MERIDIAN_BROKER:'off',
 APCA_API_KEY_ID:'',APCA_API_SECRET_KEY:'', PYTHONDONTWRITEBYTECODE:'1'};
for (const k of Object.keys(env)) {
 if (k.endsWith('_API_KEY') || k.endsWith('_TOKEN') || k.startsWith('TRADINGAGENTS_')) {
   if (k !== 'APCA_API_KEY_ID' && k !== 'APCA_API_SECRET_KEY') delete env[k];
 }
}
function record(name, detail){
 checks.push({name, result:'PASS', detail}); console.log('PASS '+name+': '+detail);
}
async function frame(page, name, duration=1400){
 const filename = String(captures.length+1).padStart(2,'0')+'-'+name+'.png';
 await page.screenshot({path:path.join(frames,filename), animations:'disabled'});
 captures.push({filename, name, duration_ms:duration});
 console.log('CAPTURE '+filename);
}
async function untilReady(child){
 let pending='';
 return await new Promise((resolve,reject)=>{
  const timeout=setTimeout(()=>reject(new Error('Local server not ready within 30 seconds')),30000);
  function success(url){clearTimeout(timeout);resolve(url)}
  child.stdout.on('data', buffer=>{
   pending += buffer.toString('utf8');
   const match=pending.match(/(?:^|\r?\n)READY (http:\/\/127\.0\.0\.1:\d+\/#[^\r\n]+)/);
   if(match) success(match[1]);
  });
  child.on('exit',()=>reject(new Error('Preview server quit before startup')));
  child.on('error',reject);
 });
}
async function run(){
 assert.equal(env.MERIDIAN_BROKER,'off');
 assert.equal(env.APCA_API_KEY_ID,'');
 assert.equal(env.APCA_API_SECRET_KEY,'');
 server=spawn('python',['-u','tests/hosted_windows_preview.py'],
  {cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
 const privateUrl=await untilReady(server);
 // Do not log privateUrl, which contains the loopback session token.
 browser=await chromium.launch({channel:'msedge',headless:true,
  args:['--disable-background-networking','--disable-sync','--no-first-run']});
 const page=await browser.newPage({viewport:{width:1440,height:900},
  deviceScaleFactor:1});
 const errors=[];
 page.on('pageerror', err=>errors.push(err.message));
 await page.goto(privateUrl,{waitUntil:'domcontentloaded'});
 await page.locator('.watch [data-symbol="DEMO"]').waitFor({timeout:25000});
 await page.locator('.data-integrity .origin-flag').waitFor();
 await page.locator('canvas#chart').waitFor();
 assert.match(await page.locator('.data-integrity').innerText(),/SIMULATED/);
 record('Startup','Existing source app loaded in hosted Windows Microsoft Edge');
 record('Source honesty','DEMO price history visibly labeled SIMULATED');
 await frame(page,'market-demo',2200);

 await page.locator('#chart').hover({position:{x:410,y:100}});
 await frame(page,'price-chart-interaction',1000);
 record('Chart','Interactive price canvas rendered and accepts pointer hover');

 await page.keyboard.press('Control+K');
 await page.locator('#commandPalette[open]').waitFor();
 await frame(page,'quick-switcher',1800);
 await page.locator('#commandSearch').fill('Research swarm');
 await frame(page,'search-research',1100);
 await page.keyboard.press('Enter');
 await page.getByRole('heading',{name:'Research swarm',exact:true}).first().waitFor();
 await frame(page,'research-workspace',2200);
 record('Navigation','Ctrl+K search changed the active workspace');

 await page.locator('[data-act="rs-review"]').click();
 await page.waitForTimeout(1200);
 await frame(page,'research-review-run',1400);
 record('Research','DEMO research review was requested through the actual UI');

 await page.keyboard.press('Control+K');
 await page.locator('#commandSearch').fill('Portfolio');
 await page.keyboard.press('Enter');
 await page.getByRole('heading',{name:'Portfolio',exact:true}).first().waitFor();
 await frame(page,'paper-portfolio',1900);
 const brokerInfo=await page.locator('.panel').filter({hasText:'Alpaca account'}).first().innerText();
 assert.match(brokerInfo,/Disconnected|not configured|set MERIDIAN_BROKER/i);
 record('Broker safety','No broker connection configured');

 await page.locator('[data-act="ticket"]').first().click();
 await page.locator('#ticket').waitFor();
 const dialogLabel=await page.locator('#modalLabel').innerText();
 assert.equal(dialogLabel,'LOCAL PAPER');
 await frame(page,'paper-ticket',1600);
 record('Paper mode','Order ticket explicitly displays LOCAL PAPER, never LIVE');

 await page.locator('#qty').fill('1');
 await page.locator('#ticket button[type="submit"]').click();
 await page.locator('#modal').waitFor({state:'hidden',timeout:12000});
 await page.locator('.panel').filter({has:page.getByRole('heading',{name:'Paper fills',exact:true})})
  .getByText('DEMO').first().waitFor();
 await frame(page,'simulated-paper-fill',1800);
 record('Paper order','One synthetic DEMO fill shown in temporary local SQLite portfolio');

 await page.locator('nav [data-page="audit"]').click();
 await page.getByRole('heading',{name:'Activity log',exact:true}).first().waitFor();
 await page.getByText('PAPER FILL',{exact:true}).first().waitFor();
 await frame(page,'audit-record',1800);
 record('Audit','Simulated paper fill recorded in visible local activity log');

 await page.locator('nav [data-page="market"]').click();
 await page.locator('#chart').waitFor();
 await frame(page,'back-to-market',1400);
 if(errors.length) throw new Error('Browser errors: '+errors.join('; '));
 record('Browser console','No uncaught page errors');
 const results={scope:'GitHub-hosted Windows / Microsoft Edge (headless)',
  not_validated:'User device E:\\MeridianDesk, native WebView2 launcher, model worker bundles, real feeds, broker execution',
  simulated:true, broker_mode:'off', checks,captures, created_utc:new Date().toISOString()};
 fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify(results,null,2));
 console.log('WINDOWS_PREVIEW_SUCCESS '+checks.length+' validated checks, '+captures.length+' screenshot frames');
}
run().catch(err=>{console.error('WINDOWS_PREVIEW_FAILURE '+err.stack);process.exitCode=1})
 .finally(async()=>{if(browser)await browser.close().catch(()=>{});if(server)server.kill();});
