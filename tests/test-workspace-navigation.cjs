'use strict';
/* Offline UI behavior contract: no browser, broker connection, or paid service needed. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.join(__dirname,'..'),html=fs.readFileSync(path.join(root,'app','index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'app','app.js'),'utf8');
for(const id of ['commandLauncher','commandPalette','commandSearch','commandResults','modal','content','navigation']){
 assert.match(html,new RegExp('id="'+id+'"'),id+' must exist in the desktop markup');
}
assert.match(html,/\/app\.js/);

const listeners=new Map(),elements=new Map();
const document={
 activeElement:null,
 body:{dataset:{}},
 getElementById(id){
  if(!elements.has(id)){
   const element={id,innerHTML:'',textContent:'',value:'',hidden:false,open:false,tagName:'DIV',
    dataset:{},callbacks:{},
    addEventListener(type,fn){(this.callbacks[type]??=[]).push(fn)},
    focus(){document.activeElement=this},
    close(){this.open=false;for(const handler of this.callbacks.close||[])handler()},
    showModal(){this.open=true},
    querySelector(){return {scrollIntoView(){}}}};
   if(id==='commandSearch')element.tagName='INPUT';
   if(id==='commandLauncher')element.tagName='BUTTON';
   elements.set(id,element);
  }
  return elements.get(id);
 },
 addEventListener(type,fn){(listeners.get(type)??listeners.set(type,[]).get(type)).push(fn)}
};
const context=vm.createContext({
 document,history:{replaceState(){}},location:{hash:'#ci~verify',pathname:'/'},
 sessionStorage:{getItem(){return null},setItem(){}},
 window:{addEventListener(){},scrollTo(){}},
 fetch(){return new Promise(()=>{})},setInterval(){},setTimeout(){return 0},clearTimeout(){},
 crypto:{randomUUID(){return '00000000-0000-4000-8000-000000000000'}},
 console,Date,Math,Intl,Number,devicePixelRatio:1
});
vm.runInContext(script,context,{filename:'app/app.js'});
const call=expr=>vm.runInContext(expr,context);
const el=id=>document.getElementById(id);
function emit(target,kind,event={}){
 for(const f of target.callbacks?.[kind]||[])f(event);
}
function key(key,rest={}){
 const event={key,ctrlKey:false,metaKey:false,altKey:false,preventDefault(){this.prevented=true},...rest};
 for(const f of listeners.get('keydown')||[])f(event);
 return event;
}
assert.equal(el('commandPalette').open,false,'The palette is closed by default');
const open=key('k',{ctrlKey:true});
assert.equal(open.prevented,true);
assert.equal(el('commandPalette').open,true,'Ctrl+K opens local quick switch');
assert.equal(document.activeElement,el('commandSearch'));
assert.match(el('commandResults').innerHTML,/Market overview/);
assert.match(el('commandResults').innerHTML,/Research swarm/);
assert.doesNotMatch(el('commandResults').innerHTML,/Submit.*order/i);

// Filter to a specific instrument before the first network snapshot arrives.
el('commandSearch').value='ETH';
emit(el('commandSearch'),'input');
assert.match(el('commandResults').innerHTML,/ETH-USD/);
assert.doesNotMatch(el('commandResults').innerHTML,/BTC-USD/);
emit(el('commandSearch'),'keydown',{key:'Enter',preventDefault(){}});
assert.equal(el('commandPalette').open,false);
assert.equal(call('symbol'),'ETH-USD');
assert.equal(call('page'),'market');

// Page navigation is available even without a market connection.
key('k',{ctrlKey:true});
el('commandSearch').value='Research swarm';
emit(el('commandSearch'),'input');
emit(el('commandSearch'),'keydown',{key:'Enter',preventDefault(){}});
assert.equal(call('page'),'research');
assert.equal(el('title').textContent,'Research swarm');

// Typing / inside a normal field must not hijack focus.
el('commandPalette').close();
document.activeElement={tagName:'INPUT',isContentEditable:false};
key('/');
assert.equal(el('commandPalette').open,false);
document.activeElement={tagName:'DIV',isContentEditable:false};
const slash=key('/');
assert.equal(slash.prevented,true);
assert.equal(el('commandPalette').open,true);

// Palette must never contain privileged action types.
const kinds=call('commandOptions().map(entry=>entry.kind)');
assert.equal(kinds.length,13);
assert.ok(kinds.every(kind=>kind==='page'||kind==='instrument'));
assert.ok(!call("commandOptions().some(entry=>/halt|broker order|live trading/i.test(entry.id))"));

// Verify labels match observation type and escape untrusted provider text.
context.fixture={market:{live:false,stale:false,transport:'SIMULATION',source:'Synthetic fixture',
 asof:1780000000,age_seconds:0,session:'Simulation',bid:null,ask:null},
 analysis:{veto:false}};
call('state=fixture');
assert.match(call('renderProvenance()'),/SIMULATED/);
assert.match(call('renderProvenance()'),/No two-sided quote/);
context.fixture.market.stale=true;
assert.match(call('renderProvenance()'),/STALE/);
assert.match(call('renderProvenance()'),/Stale observations cannot authorize orders/);
context.fixture.market.live=true;
context.fixture.market.stale=false;
context.fixture.market.transport='REST';
context.fixture.market.source='<script>alert(1)</script>';
assert.match(call('renderProvenance()'),/PUBLIC BAR/);
assert.ok(!call('renderProvenance()').includes('<script>'));
assert.match(call('renderProvenance()'),/&lt;script&gt;/);
context.fixture.market.transport='WebSocket';
assert.match(call('renderProvenance()'),/EXCHANGE TICKER/);
context.fixture.analysis.veto=true;
assert.match(call('renderProvenance()'),/Research entry veto applies/);

console.log('PASS: quick switch keyboard, routing, pre-data navigation, no privileged commands, provenance and escaping.');
