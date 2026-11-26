
'use strict';
const $=id=>document.getElementById(id);
const parts=location.hash.slice(1).split('~');
const token=parts[0]||sessionStorage.getItem('session');
if(token)sessionStorage.setItem('session',token);
history.replaceState(null,'',location.pathname);
let symbol=parts[1]==='verify'?'DEMO':'BTC-USD',page='market',state=null,windowBars=90,chartStyle='Candles',inFlight=false,toastTimer=null;
const sections={
 market:['Market overview','MARKET INTELLIGENCE','Prices, market risk and the latest specialist assessments.'],
 research:['Research swarm','RESEARCH WORKSPACE','Review specialist findings and run a focused investigation.'],
 portfolio:['Portfolio','EXECUTION DESK','Review positions, limit orders and trading controls.'],
 audit:['Activity log','WORKSPACE HISTORY','Inspect recorded research, order decisions and account changes.'],
 connections:['Connections','DATA & MODELS','Inspect research engines, filing sources and MetaTrader reports.']
};
const glyphs={market:'M3 17l5-6 4 3 8-10 M3 4v16h18',research:'M5 8l7-5 7 5v8l-7 5-7-5z M5 8l7 5 7-5 M12 13v8',portfolio:'M3 8h18v12H3z M8 8V5h8v3 M3 13h18',audit:'M6 3h12v18H6z M9 8h6 M9 12h6 M9 16h4',connections:'M5 4v5m5-5v5M3 9h9v2a4.5 4.5 0 01-4.5 4.5V19h6a4 4 0 004-4v-2'};
let globalCatalog=null;
const watchMeta={'BTC-USD':['BTC','₿','btc'],'ETH-USD':['ETH','Ξ','eth'],'SPY':['SPY','S','spy'],'AAPL':['AAPL','A',''],'MSFT':['MSFT','M',''],'EURUSD=X':['EUR/USD','€',''],'GC=F':['Gold','Au','gc'],'DEMO':['DEMO','D','']};
function svg(k){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${glyphs[k]}"/></svg>`}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function badge(v,kind=''){return `<span class="badge ${esc(kind)}">${esc(v)}</span>`}
function panel(title,body,action=''){return `<section class="panel"><div class="panel-head"><h2>${esc(title)}</h2>${action}</div><div class="panel-body">${body}</div></section>`}
function price(x){return Number.isFinite(x)?x.toLocaleString('en-US',{minimumFractionDigits:x>0&&x<2?4:2,maximumFractionDigits:x>0&&x<2?5:2}):'—'}
function pc(x,signed=false){return Number.isFinite(x)?(signed&&x>0?'+':'')+(x*100).toFixed(2)+'%':'—'}
function tone(x){return x>0?'positive':x<0?'negative':'flat'}
function clock(t){return new Date(t*1000).toISOString().slice(11,19)+' UTC'}
function stamp(t){return new Date(t*1000).toISOString().replace('T',' ').slice(0,19)+' UTC'}
function instrumentMeta(s){return watchMeta[s]||[s,s.slice(0,2),'']}
async function openGlobalExplorer(){
 if(!globalCatalog)globalCatalog=await api('/api/catalog');
 const regions=[...new Set(globalCatalog.map(record=>record.country))].sort((a,b)=>a.localeCompare(b));
 modal('Global stock explorer','RESEARCH-ONLY · INDICATIVE FEEDS',
   '<div class="global-help">Explore international equity listings. Prices load only when you select an instrument. Public observations may be delayed, unavailable, or in local currency. No live trading is enabled for these listings.</div>'+
   '<div class="global-controls"><input id="globalSearch" type="search" autocomplete="off" placeholder="Search issuer, ticker or exchange" aria-label="Search global companies">'+
   '<select id="globalRegion" aria-label="Filter stock market"><option value="">All countries</option>'+
   regions.map(country=>'<option value="'+esc(country)+'">'+esc(country)+'</option>').join('')+'</select></div>'+
   '<p class="global-summary" id="globalSummary" role="status"></p><div class="global-results" id="globalResults"></div>');
 $('globalSearch').oninput=renderGlobalExplorer;
 $('globalRegion').onchange=renderGlobalExplorer;
 renderGlobalExplorer();
 $('globalSearch').focus();
}
function renderGlobalExplorer(){
 if(!$('globalResults')||!globalCatalog)return;
 const query=$('globalSearch').value.trim().toLowerCase();
 const country=$('globalRegion').value;
 const matches=globalCatalog.filter(record=>(!country||record.country===country)&&
   [record.symbol,record.name,record.country,record.exchange].join(' ').toLowerCase().includes(query));
 matches.sort((a,b)=>Number((state?.pinned||[]).includes(b.symbol))-Number((state?.pinned||[]).includes(a.symbol)));
 $('globalSummary').textContent=matches.length+' listings match · '+globalCatalog.length+' curated worldwide · browse or search';
 $('globalResults').innerHTML=matches.slice(0,55).map(record=>
  '<button type="button" data-global-symbol="'+esc(record.symbol)+'" class="global-result">'+
  '<span class="global-symbol">'+esc(record.symbol)+'</span>'+
  '<span class="global-title"><strong>'+esc(record.name)+'</strong><small>'+
  esc(record.country)+' · '+esc(record.exchange)+'</small></span>'+
  '<span class="global-currency">'+((state?.pinned||[]).includes(record.symbol)?'PINNED · ':'')+esc(record.currency)+'</span></button>').join('')||
  '<div class="empty">No matching listing in the curated directory.</div>';
 if(matches.length>55)$('globalSummary').textContent+=' · showing first 55; use search to narrow';
}
function instrumentSelect(){return `<select class="instrument-select" aria-label="Selected instrument">${state.watch.map(w=>`<option value="${esc(w.symbol)}" ${symbol===w.symbol?'selected':''}>${esc(w.symbol)} · ${esc(w.name)}</option>`).join('')}</select>`}
function modal(title,label,html){$('modalTitle').textContent=title;$('modalLabel').textContent=label;$('modalBody').innerHTML=html;if(!$('modal').open)$('modal').showModal()}
function toast(text){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,6500)}
async function api(path,body){
 const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const data=await r.json();if(!r.ok)throw Error(data.error||'Local request failed.');return data
}
async function refresh(){
 if(inFlight)return;inFlight=true;const s=symbol;
 try{const snap=await api('/api/state?symbol='+encodeURIComponent(s));if(s!==symbol)return;
  const old=state;state=snap;for(const j of state.jobs){if(old?.jobs.find(x=>x.id===j.id)?.state==='running'&&j.state!=='running')toast(`${j.task} · ${j.symbol} · ${j.state}`)}
  if(!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)||$('modal').open)render();
 }catch(e){$('health').textContent='Local service offline';if(!state)$('content').innerHTML=`<div class="panel empty">${esc(e.message)}</div>`}
 finally{inFlight=false;if(s!==symbol)void refresh()}
}
function navigate(id){if(sections[id]){page=id;render();window.scrollTo(0,0)}}
function selectInstrument(s){
 const selected=globalCatalog?.find(record=>record.symbol===s);
 const fromWatch=state?.watch.find(record=>record.symbol===s);
 if(!watchMeta[s]&&!selected&&!fromWatch)return;
 const global=selected||(!watchMeta[s]&&fromWatch?
  {symbol:s,name:fromWatch.name,country:'International',exchange:'View listing details',currency:fromWatch.currency}:null);
 symbol=s;
 if(state?.symbol!==s){
  const watch=state?.watch||[];
  const extra=global&&!watch.some(item=>item.symbol===s)?
   [{symbol:s,name:global.name,price:null,change:null,kind:'WAIT',currency:global.currency,spark:[]}]:[];
  state={...state,symbol:s,market:null,analysis:null,
   error:global?'Requesting public observation on demand…':'',
   instrument:global,watch:watch.concat(extra)};
  render();
 }
 refresh();
}
function render(){
 $('navigation').innerHTML=Object.keys(sections).map(k=>`<button data-page="${k}" title="${sections[k][0]}" class="${k===page?'active':''}">${svg(k)}<span>${sections[k][0]}</span></button>`).join('');
 const [title,kicker,subtitle]=sections[page];$('title').textContent=title;$('crumb').textContent=title;$('kicker').textContent=kicker;$('subtitle').textContent=subtitle;
 $('pageActions').innerHTML=page==='market'?
  '<button data-act="catalog">Explore global stocks</button>'+
  (state?.instrument?
   '<button data-act="watch-toggle">'+((state?.pinned||[]).includes(symbol)?'Unpin stock':'Pin to watchlist')+'</button>':
   '<button data-act="ticket" class="primary">New paper order</button>'):
  page==='portfolio'?'<button class="danger" data-act="halt">'+(state?.portfolio.halted?'Resume trading':'Halt new orders')+'</button>'+
  (state?.instrument?'':'<button data-act="ticket">New paper order</button>'):'';
 if(!state)return;
 $('health').innerHTML='<i class="dot"></i> Desk online';$('footerInfo').textContent=(state.portfolio.halted?'New orders halted':'Paper account enabled')+'  ·  Data stored on E:';
 $('content').innerHTML=page==='market'?renderMarket():page==='research'?renderResearch():page==='connections'?renderConnections():page==='portfolio'?renderPortfolio():renderAudit();
 if(page==='market'&&state.market)drawChart();
 if(state.market&&state.analysis)document.body.dataset.ready='yes';
}
function renderMarket(){
 const m=state.market,a=state.analysis,r=a?.risk||{},
 w=state.watch.find(x=>x.symbol===symbol)||state.instrument||{symbol,name:symbol};
 const isGlobal=!!state.instrument,unit=m?.currency||state.instrument?.currency;
 const tiles=state.watch.filter(w=>['BTC-USD','ETH-USD','SPY','GC=F'].includes(w.symbol)).map(w=>`<button class="quote ${w.symbol===symbol?'sel':''}" data-symbol="${esc(w.symbol)}"><div><strong>${esc(watchMeta[w.symbol][0])}</strong><span class="sub">${esc(w.kind)}</span></div><div class="big">${price(w.price)}</div><span class="mono ${tone(w.change)}">${pc(w.change,true)}</span> <small>last bar</small></button>`).join('');
 const list=state.watch.map(w=>{const [name,mark,cls]=instrumentMeta(w.symbol);return `<button data-symbol="${esc(w.symbol)}" class="${w.symbol===symbol?'selected':''}"><span class="row-start"><span class="asset ${cls}">${esc(mark)}</span><span><strong>${esc(name)}</strong><small>${esc(w.name)}</small></span></span><span class="price">${price(w.price)}<small>${esc(w.kind)}</small></span></button>`}).join('');
 const chart=m?`<div class="chart-top"><div><div class="chart-title">${esc(w.name)}</div><div class="big">${price(w.price)}${unit?'<small class="price-unit"> '+esc(unit)+'</small>':''}</div><div class="chart-sub"><span class="${tone(w.change)}">${pc(w.change,true)}</span> · previous ${esc(m.interval)} bar</div></div><div class="chart-tool"><div class="tabs">${[30,90,240].map(n=>`<button class="${n===windowBars?'on':''}" title="Show ${n} bars" data-act="range" data-val="${n}">${n}</button>`).join('')}</div><div class="tabs"><button data-act="style">${chartStyle}</button></div></div></div><div class="canvas-wrap"><canvas id="chart" aria-label="${esc(symbol)} price and volume history"></canvas></div><div class="chart-foot"><span>${esc(m.source)}</span><span>${esc(m.interval)} · ${clock(m.asof)}</span></div>`:`<div class="empty tall">Waiting for ${esc(symbol)} market data. ${esc(state.error)}<p class="section-gap">Select DEMO for offline research.</p></div>`;
 const metrics=[['One-bar CVaR 99%',pc(r.cvar99)],['Peak drawdown',pc(r.max_drawdown)],['Volatility / bar',pc(r.bar_volatility)]].map(([k,v])=>`<div><label>${k}</label><b>${v}</b></div>`).join('');
 return `${isGlobal?'<div class="global-disclosure">'+esc(w.name)+' · '+esc(state.instrument.country)+' / '+esc(state.instrument.exchange)+' · '+esc(state.instrument.currency)+' · Research only. Public indicative or delayed data; no trading authorization.</div>':''}<div class="quotes">${tiles}</div><div class="grid-main"><section class="panel"><div class="panel-head"><h2>Price action</h2>${badge(m?(m.live?(m.stale?'Stale observation':m.transport||'Public feed'):'Simulated'):'Awaiting feed',m?.stale?'hold':m?.live?'good':'')}</div>${chart}</section><section class="panel"><div class="panel-head"><h2>Watchlist</h2><span class="sub">${state.watch.length} instruments</span></div><div class="watch">${list}</div></section></div><div class="grid-main lower">${panel('Risk assessment',`<div class="metric-grid">${metrics}</div><p class="note ${a?.veto?'amber':''}">${esc(!a?'Waiting for a usable price history.':m?.stale?'Market data are stale. New orders are on hold.':a.reasons.slice(0,2).join(' ')||'No entry veto recorded for this snapshot.')}</p>`,badge(a?(a.veto||m?.stale?'Entry on hold':'Research gate clear'):'Awaiting data',a?.veto||m?.stale?'hold':a?'good':''))}${panel('Research swarm',`<div class="row"><h3>${a?a.agents.length:0} specialist checks</h3>${badge('8 pods')}</div><p class="tagline">${esc(a?.verdict||'Awaiting analysis')}</p><button data-page="research" class="text-btn section-gap">Inspect findings →</button>`)}</div>`
}
function drawChart(){
 const c=$('chart');if(!c||!state.market)return;
 const b=state.market.bars.slice(-windowBars),w=c.clientWidth,h=c.clientHeight,ratio=Math.min(2,devicePixelRatio||1);if(!b.length||!w||!h)return;
 c.width=w*ratio;c.height=h*ratio;const g=c.getContext('2d');g.scale(ratio,ratio);const left=8,right=w-73,top=22,bottom=h-23;
 const low=Math.min(...b.map(x=>x.low)),high=Math.max(...b.map(x=>x.high)),span=(high-low)||high*.001||1;const lo=low-span*.1,hi=high+span*.12;
 const x=i=>left+(i+.5)*(right-left)/b.length,y=p=>top+(hi-p)/(hi-lo)*(bottom-top),bw=Math.max(1,(right-left)/b.length*.65);
 function line(x1,y1,x2,y2,col){g.strokeStyle=col;g.beginPath();g.moveTo(x1,y1);g.lineTo(x2,y2);g.stroke()}
 function paint(at=null){
  g.clearRect(0,0,w,h);g.font='10px Consolas, monospace';g.textBaseline='middle';g.lineWidth=1;
  for(let j=0;j<=4;j++){const row=top+j*(bottom-top)/4;g.setLineDash([3,4]);line(left,row,right,row,'#2b3b3e');g.setLineDash([]);g.fillStyle='#99acae';g.fillText(price(hi-j*(hi-lo)/4),right+8,row)}
  const v=Math.max(1,...b.map(p=>p.volume));b.forEach((p,i)=>{g.fillStyle=p.close>=p.open?'#2c483f':'#493935';const vol=27*p.volume/v;g.fillRect(x(i)-bw/2,bottom-vol,bw,vol)});
  if(chartStyle==='Candles'){b.forEach((p,i)=>{const col=p.close>=p.open?'#91deb5':'#e4a59d';line(x(i),y(p.high),x(i),y(p.low),col);g.fillStyle=col;g.fillRect(x(i)-bw/2,Math.min(y(p.open),y(p.close)),bw,Math.max(1,Math.abs(y(p.open)-y(p.close))))})}
  else{g.beginPath();b.forEach((p,i)=>i?g.lineTo(x(i),y(p.close)):g.moveTo(x(i),y(p.close)));g.strokeStyle='#9fe7be';g.lineWidth=2;g.stroke();g.lineTo(x(b.length-1),bottom);g.lineTo(x(0),bottom);g.closePath();const grad=g.createLinearGradient(0,top,0,bottom);grad.addColorStop(0,'#75d39e40');grad.addColorStop(1,'#75d39e02');g.fillStyle=grad;g.fill()}
  g.fillStyle='#91a6a8';[0,.33,.66,1].forEach(f=>{const i=Math.round(f*(b.length-1));g.fillText(clock(b[i].time).slice(0,5),Math.max(left,Math.min(x(i)-14,right-32)),h-9)});
  if(at!==null){const p=b[at];line(x(at),top,x(at),bottom,'#647b78');g.fillStyle='#d5e5dd';g.fillText(`${clock(p.time).slice(0,5)} UTC   O ${price(p.open)}   H ${price(p.high)}   L ${price(p.low)}   C ${price(p.close)}`,left,9)}
 }
 paint();c.onpointermove=e=>paint(Math.max(0,Math.min(b.length-1,Math.floor((e.clientX-c.getBoundingClientRect().left-left)/(right-left)*b.length))));c.onpointerleave=()=>paint()
}

function table(headers,rows,empty){
 if(!rows.length)return `<div class="empty">${esc(empty)}</div>`;
 return `<div class="scroll"><table><thead><tr>${headers.map(t=>`<th>${esc(t)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('')}</tbody></table></div>`
}
function renderPortfolio(){
 const p=state.portfolio,b=state.broker;
 const stats=[['Paper equity',p.equity],['Available paper cash',p.cash],['Invested value',p.equity-p.cash]].map(([k,v])=>`<div class="panel metric"><label>${esc(k)}</label><b>$${price(v)}</b></div>`).join('');
 const positions=table(['Instrument','Units','Average cost','Mark','P&L'],p.positions.map(r=>[esc(r.symbol),esc(r.qty),price(r.basis),price(r.mark)+(r.estimated?' *':''),`<span class="${tone(r.pnl)}">$${price(r.pnl)}</span>`]),'Your paper account has no positions. Filled paper orders appear here.');
 const fills=table(['Time','Instrument','Side','Units','Fill','Fee'],p.orders.map(r=>[clock(r.ts),esc(r.symbol),esc(r.side.toUpperCase()),esc(r.qty),price(r.price),'$'+price(r.fee)]),'No paper fills recorded.');
 const tickets=table(['Time','Symbol','Side','Status',''],state.broker_orders.map(r=>[clock(r.ts),esc(r.symbol),esc(r.side),esc(r.status),`<button data-act="reconcile" data-id="${esc(r.id)}" class="text-btn">Reconcile</button>`]),'No broker tickets recorded for this mode.');
 return `<div class="overview-stats">${stats}</div><div class="stack"><section class="panel"><div class="panel-head"><h2>Paper positions</h2>${badge(p.halted?'Halted':'Enabled',p.halted?'hold':'good')}</div>${positions}</section><section class="panel"><div class="panel-head"><h2>Paper fills</h2><span class="sub">USD · fees included</span></div>${fills}</section>${panel('Alpaca account',`<p>${b.configured?'Alpaca '+esc(b.mode)+' credentials are configured.':'To connect Alpaca, set MERIDIAN_BROKER to paper or live and supply APCA_API_KEY_ID and APCA_API_SECRET_KEY before launching the desk.'}</p><div class="controls section-gap">${instrumentSelect()}${b.configured?'<button data-act="broker-account">Account status</button><button data-act="broker-ticket">New broker limit order</button>':''}</div>${tickets}<p class="foot-note">Halting blocks new submissions. Review working orders in Alpaca.</p>`,badge(b.configured?b.mode.toUpperCase():'Disconnected',b.mode==='live'?'hold':''))}</div>`
}
function renderAudit(){
 return `<section class="panel"><div class="panel-head"><h2>Desk activity</h2><span class="sub">Latest ${state.audit.length} events</span></div>${state.audit.length?state.audit.map(r=>`<div class="audit-item"><span class="mono muted">${esc(stamp(r.ts))}</span><span>${esc(r.category)}</span><b>${esc(r.symbol)}</b><span><span class="audit-preview">${esc(r.detail)}</span><button class="text-btn" data-act="record" data-id="${r.id}">View record</button></span></div>`).join(''):'<div class="empty">Research runs, trades and risk decisions will appear here.</div>'}</section>`
}
async function job(kind,engine){const j=await api('/api/job',{kind,engine,symbol});toast(`${j.task} queued for ${symbol}.`);await refresh();return j}
function showResult(id){const j=state.jobs.find(x=>x.id===id);if(!j)return;const out=typeof j.result==='object'?Object.entries(j.result).map(([k,v])=>`${k}   ${v}`).join('\n'):j.result;modal(`${j.task} · ${j.symbol}`,j.state.toUpperCase(),`<pre class="result">${esc(out||'Research is in progress.')}</pre>`)}
function ticket(remote){
 if(state?.instrument){toast('Global catalog instruments are research-only; broker and paper orders remain disabled.');return}
 const m=state?.market;if(!m){toast('Select an instrument with market observations.');return}
 const s=symbol,p=m.bars.at(-1).close,mode=remote?state.broker.mode.toUpperCase():'LOCAL PAPER',digits=p<2?5:2,ref=crypto.randomUUID();
 modal(remote?'Broker limit order':'Paper limit order',mode,`<form id="ticket"><p><strong>${esc(s)}</strong> · ${esc(m.source)}<br>Latest observation ${price(p)} · ${clock(m.asof)}</p><div class="form-pair"><div class="field"><label for="side">Side</label><select id="side"><option value="buy">Buy</option><option value="sell">Sell</option></select></div><div class="field"><label for="qty">Quantity</label><input id="qty" type="number" min="0.00000001" step="any" required value="${p>10000?.01:1}"></div></div><div class="field"><label for="limit">Limit price (USD)</label><input id="limit" type="number" step="any" min="0.00000001" required value="${(p*1.001).toFixed(digits)}"></div>${remote?`<div class="field"><label for="confirmation" id="confirmLabel">Type ${mode} BUY ${esc(s)} to submit</label><input id="confirmation" autocomplete="off" required></div>`:'<p class="foot-note">Immediate-or-cancel paper fill. Modeled slippage is 2 bp and fees are 1 bp, with a $0.01 minimum.</p>'}<div class="dialog-error" id="ticketError" role="alert"></div><button type="submit" class="${mode==='LIVE'?'danger':'primary'}">${remote?'Submit '+mode.toLowerCase()+' broker order':'Submit paper order'}</button></form>`);
 $('side').onchange=()=>{$('limit').value=(p*($('side').value==='buy'?1.001:.999)).toFixed(digits);if(remote)$('confirmLabel').textContent=`Type ${mode} ${$('side').value.toUpperCase()} ${s} to submit`};
 $('ticket').onsubmit=async e=>{e.preventDefault();const button=e.currentTarget.querySelector('button');button.disabled=true;
  try{const r=await api(remote?'/api/broker/order':'/api/paper',{symbol:s,side:$('side').value,qty:Number($('qty').value),limit:Number($('limit').value),id:ref,confirmation:remote?$('confirmation').value:''});$('modal').close();toast(remote?'Broker ticket: '+r.status:`Paper fill · ${r.qty} ${s} at ${price(r.price)}`);await refresh()}
  catch(err){$('ticketError').textContent=err.message;button.disabled=false}
 };
}
document.addEventListener('click',async e=>{
 const el=e.target.closest('button,[data-act]');if(!el)return;
 try{
  if(el.dataset.page){navigate(el.dataset.page);return}
  if(el.dataset.symbol){selectInstrument(el.dataset.symbol);return}
  if(el.dataset.globalSymbol){$('modal').close();selectInstrument(el.dataset.globalSymbol);return}
  const act=el.dataset.act;
  if(act==='catalog')await openGlobalExplorer();
  else if(act==='watch-toggle'){
   if(!state?.instrument)throw Error('Select an international catalog listing first.');
   const enable=!(state.pinned||[]).includes(symbol);
   await api('/api/watchlist',{symbol,enabled:enable});
   toast(enable?'Stock pinned locally. Quotes load when selected.':'Stock removed from saved watchlist.');
   await refresh();
  }
  else if(act==='range'){windowBars=Number(el.dataset.val);render()}
  else if(act==='style'){chartStyle=chartStyle==='Candles'?'Line':'Candles';render()}
  else if(act==='ticket'||act==='broker-ticket')ticket(act==='broker-ticket');
  else if(act==='result')showResult(el.dataset.id);
  else if(act==='record'){const r=state.audit.find(r=>String(r.id)===el.dataset.id);modal(r.category,r.symbol,`<p>${esc(stamp(r.ts))}</p><pre>${esc(r.detail)}</pre>`)}
  else if(act==='halt'){const enabled=!state.portfolio.halted;await api('/api/halt',{enabled});toast(enabled?'New order submissions halted.':'Trading resumed.');await refresh()}
  else if(act==='broker-account'){const r=await api('/api/broker/account',{});modal('Alpaca account',state.broker.mode.toUpperCase(),`<pre>${esc(JSON.stringify(r,null,2))}</pre>`)}
  else if(act==='reconcile'){const r=await api('/api/broker/reconcile',{id:el.dataset.id});toast('Broker status: '+r.status);await refresh()}
  else if(act)await researchClick(act,el)
 }catch(err){toast(err.message)}
});
document.addEventListener('change',async e=>{try{if(e.target.classList.contains('instrument-select'))selectInstrument(e.target.value);else await researchChange(e.target)}catch(err){toast(err.message)}});
$('closeModal').onclick=()=>$('modal').close();
window.addEventListener('resize',()=>{if(page==='market')drawChart()});
window.verifyNavigation=()=>{for(const k of Object.keys(sections)){navigate(k);if(!$('content').textContent.trim()||$('title').textContent!==sections[k][0])return false}navigate('market');return !!$('chart')&&$('chart').width>100&&state.watch.length===8};
function tick(){$('clock').textContent=clock(Date.now()/1000)}
tick();setInterval(tick,1000);render();refresh();setInterval(refresh,1500);
