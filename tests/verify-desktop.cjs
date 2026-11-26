'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require('./browser-tools/node_modules/playwright-core');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname,'..');
if (path.parse(root).root.toLowerCase() !== 'e:\\') throw Error('GUI acceptance requires the E: project.');
const tests = __dirname, base = path.join(root,'cache','gui-acceptance');
fs.mkdirSync(base,{recursive:true});
const run = fs.mkdtempSync(path.join(base,'run-'));
const profile = path.join(run,'edge'), temp = path.join(run,'temp');
fs.mkdirSync(temp,{recursive:true});
const env = {...process.env, TEMP:temp, TMP:temp, TMPDIR:temp, HOMEDRIVE:'E:', PYTHONDONTWRITEBYTECODE:'1',
    PYTHONUTF8:'1', MERIDIAN_BROKER:'disabled', NODE_DISABLE_COMPILE_CACHE:'1'};
for (const key of Object.keys(env)) {
    if (key.endsWith('_API_KEY') || key.endsWith('_TOKEN') || key.startsWith('APCA_') ||
        key.startsWith('TRADINGAGENTS_')) delete env[key];
}
const edgePath = path.join(process.env['ProgramFiles(x86)'] || process.env.ProgramFiles,'Microsoft','Edge','Application','msedge.exe');
const serve = `import sys, secrets, threading, tempfile
from pathlib import Path
from desk import Desk, serve
root = Path(sys.argv[1])
d = Desk(root / "acceptance.sqlite3", verification=True)
token = secrets.token_urlsafe(32)
h = serve(d,token)
def close():
    sys.stdin.readline()
    h.shutdown()
threading.Thread(target=close,daemon=True).start()
d.start()
print("http://127.0.0.1:" + str(h.server_port) + "/#" + token, flush=True)
try: h.serve_forever(.1)
finally:
    h.server_close()
    d.stop()
`;
const pause = ms => new Promise(r=>setTimeout(r,ms));
const report = {started:new Date().toISOString(),checks:[], screenshot:'desktop-preview.png'};
let server, edge, browser, page, privateURL;
function record(check, detail){ report.checks.push({check, detail});console.log('PASS '+check); }
async function until(probe, ms=20000){
    const end = Date.now()+ms;
    while (Date.now()<end) {const val=await probe(); if(val) return val; await pause(200);}
    throw Error('Timed out waiting for a verified desktop state.');
}
async function nav(key){await page.locator('nav [data-page="'+key+'"]').click();}
async function receipt({kind,button,expected}) {
    const row = page.locator('.results-table tbody tr').filter({has:page.locator('td:first-child',{hasText:kind})}).first();
    await row.locator('[data-act=result]').waitFor({timeout:125000});
    await row.locator('[data-act=result]').click();
    const output = await page.locator('#modalBody').innerText();
    assert.match(output,expected);
    assert.equal(await page.locator('#modalLabel').innerText(),'COMPLETE');
    await page.locator('#closeModal').click();
    return output;
}

(async()=>{
    server=spawn(path.join(root,'runtime','python','python.exe'),['-B','-c',serve,run],
        {cwd:root,env,windowsHide:true,stdio:['pipe','pipe','inherit']});
    const lines=createInterface({input:server.stdout});
    privateURL=(await Promise.race([once(lines,'line'),once(server,'exit').then(()=>{throw Error('Desk service stopped during startup.');})]))[0];
    assert.ok(/^http:\/\/127\.0\.0\.1:\d+\/#/.test(privateURL));
    const flags=['--app='+privateURL,'--user-data-dir='+profile,'--disk-cache-dir='+path.join(run,'web-cache'),
        '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--no-first-run','--no-default-browser-check',
        '--disable-background-networking','--disable-sync','--window-size=1440,970','--disable-features=msEdgeSidebarV2'];
    edge=spawn(edgePath,flags,{cwd:run,env,windowsHide:true,stdio:'ignore'});
    const active=path.join(profile,'DevToolsActivePort');
    const port=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split(/\r?\n/)[0],30000);
    browser=await chromium.connectOverCDP('http://127.0.0.1:'+port);
    const context=browser.contexts()[0];
    const origin=new URL(privateURL).origin;
    page=await until(()=>context.pages().find(p=>p.url().startsWith(origin)),30000);
    page.setDefaultTimeout(13000);
    await page.setViewportSize({width:1440,height:960});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.waitForSelector('div.watch button[data-symbol=DEMO]');
    record('Edge app-mode attached',await browser.version());
    await page.locator('div.watch [data-symbol=DEMO]').click();
    await page.locator('canvas[aria-label^=DEMO]').waitFor();
    await page.locator('[data-act=range][data-val="30"]').click();
    await page.locator('[data-act=range][data-val="30"].on').waitFor();
    await page.locator('[data-act=style]').click();
    await page.getByRole('button',{name:'Line',exact:true}).waitFor();
    const ink=await page.locator('#chart').evaluate(c=>{
        const rgba=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let count=0;
        for(let i=3;i<rgba.length;i+=4)if(rgba[i])count++;return count;
    });
    assert.ok(ink>500);
    await page.getByRole('heading',{name:'Risk assessment',exact:true}).waitFor();
    await page.getByText('Peak drawdown',{exact:true}).first().waitFor();
    record('DEMO chart, range, line style and market risk',ink+' painted pixels');
    await nav('research');
    await page.getByRole('heading',{name:'Risk and valuation'}).waitFor();
    await page.getByText('Realized volatility / bar',{exact:true}).waitFor();
    await page.locator('[data-act=rs-registry]').click();
    assert.equal(await page.locator('#rs-count').innerText(),'300 of 300 cards');
    await page.locator('#rs-search').fill('Owner earnings');
    await page.waitForFunction(()=>{const e=document.getElementById('rs-count');return e && /^6 of/.test(e.textContent);});
    await page.locator('#closeModal').click(); record('Research evidence and registry','300 cards; six owner-earnings profiles');
    await page.locator('[data-act=rs-backtest]').click();
    const backtest=await receipt({kind:'Backtest',expected:/Source\s+.*[Ss]im|Source\s+.*[Ss]ynth|DEMO/i});
    record('Backtest completed through UI',backtest.split('\n').slice(0,4).join(' | '));
    await page.locator('[data-act=rs-swarm]').click();
    await page.locator('[data-act=rs-swarm-provider]').waitFor();
    await page.locator('[data-act=rs-swarm-local]').click();
    const combined=await receipt({kind:'Swarm review',expected:/Ruflo completed 4 assigned tasks/});
    assert.match(combined,/Model close/);
    record('Combined local swarm completed','Specialist panel, actual Ruflo tasks and actual Kronos prediction');
    await nav('portfolio');
    await page.locator('[data-act=ticket]').click();
    await page.locator('#qty').fill('1');
    await page.getByRole('button',{name:'Submit paper order'}).click();
    await page.locator('#modal').waitFor({state:'hidden'});
    await page.locator('.panel').filter({has:page.getByRole('heading',{name:'Paper fills',exact:true})}).getByText('DEMO').waitFor();
    record('Local paper fill','One DEMO unit in isolated verification ledger');
    await page.locator('[data-act=halt]').click();
    await page.getByRole('button',{name:'Resume trading'}).waitFor();
    await page.locator('[data-act=ticket]').click();
    await page.getByRole('button',{name:'Submit paper order'}).click();
    await page.locator('#ticketError').getByText(/halted/i).waitFor();
    await page.locator('#closeModal').click();
    record('Halt blocked second paper order','Trading is halted');
    await nav('audit');
    for(const type of ['PAPER FILL','ORDER BLOCKED','CONTROL']){
        await page.locator('.audit-item').getByText(type,{exact:true}).first().waitFor();
    }
    record('Activity log preserved decisions','PAPER FILL, CONTROL and ORDER BLOCKED');
    await nav('connections');
    for(const name of ['TradingAgents','Kronos','Ruflo']){
        await page.getByRole('heading',{name,exact:true}).waitFor();
    }
    record('Connection status pages',await page.locator('.engine-row').allTextContents());
    await nav('portfolio');
    await page.getByRole('button',{name:'Resume trading'}).click();
    await page.getByRole('button',{name:'Halt new orders'}).waitFor();
    await nav('market');
    await page.locator('div.watch [data-symbol="BTC-USD"]').click();
    let actual='BTC-USD';
    try { await page.locator('canvas[aria-label^="BTC-USD"]').waitFor({timeout:12000}); }
    catch {actual='DEMO';await page.locator('div.watch [data-symbol=DEMO]').click();await page.locator('canvas[aria-label^=DEMO]').waitFor();}
    await page.locator('[data-act=range][data-val="90"]').click();
    if(await page.locator('[data-act=style]').innerText()==='Line')await page.locator('[data-act=style]').click();
    await page.locator('#chart').scrollIntoViewIfNeeded();
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.mouse.move(15,14);
    await page.locator('#toast').waitFor({state:'hidden',timeout:12000});
    await page.screenshot({path:path.join(tests,'desktop-preview.png')});
    record('Desk screenshot',actual+' · '+await page.locator('.chart-foot').innerText());
    assert.deepEqual(errors,[]);record('Page runtime errors',0);
    report.passed=true;
})().catch(error=>{let message=String(error.message || error);if(privateURL)message=message.replaceAll(privateURL,'[local test session]');report.error=message;report.passed=false;process.exitCode=1;console.error(message);}).finally(async()=>{
    if(browser)await browser.close().catch(()=>{});
    if(edge && edge.exitCode===null)edge.kill();
    if(server && server.exitCode===null)server.stdin.end('\n');
    report.finished=new Date().toISOString();
    fs.writeFileSync(path.join(tests,'desktop-verification.json'),JSON.stringify(report,null,2)+'\n');
});
