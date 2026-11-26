'use strict';
/* Offline desktop explorer contract without a browser, credentials or providers. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

const application=fs.readFileSync(path.join(__dirname,'app','app.js'),'utf8');
const elements=new Map(),events=new Map();
const document={
 body:{dataset:{}},activeElement:null,
 getElementById(id){
  if(!elements.has(id)){
   const element={id,value:'',innerHTML:'',textContent:'',dataset:{},open:false,
    tagName:id==='globalSearch'?'INPUT':'DIV',hidden:false,
    showModal(){this.open=true},close(){this.open=false},
    focus(){document.activeElement=this}};
   elements.set(id,element);
  }
  return elements.get(id);
 },
 addEventListener(type,cb){(events.get(type)??events.set(type,[]).get(type)).push(cb)}
};
const context=vm.createContext({
 document,window:{addEventListener(){},scrollTo(){}},
 sessionStorage:{getItem(){return null},setItem(){}},
 history:{replaceState(){}},location:{hash:'#offline~verify',pathname:'/'},
 fetch(){return new Promise(()=>{})},
 setInterval(){},setTimeout(){return 1},clearTimeout(){},devicePixelRatio:1,
 Intl,Date,Math,Number,console
});
vm.runInContext(application,context,{filename:'app/app.js'});
const run=expression=>vm.runInContext(expression,context);
const el=id=>document.getElementById(id);

context.exampleCatalog=[
 {symbol:'7203.T',name:'Toyota Motor',country:'Japan',exchange:'Tokyo Stock Exchange',currency:'JPY',execution:'research-only'},
 {symbol:'SHEL.L',name:'Shell',country:'United Kingdom',exchange:'London Stock Exchange',currency:'GBp',execution:'research-only'},
 {symbol:'NVDA',name:'NVIDIA',country:'United States',exchange:'Nasdaq',currency:'USD',execution:'research-only'}
];
run('globalCatalog=exampleCatalog');
run('state={symbol:"DEMO",watch:[{symbol:"DEMO",name:"Sample",price:80,kind:"SIM",change:0}],market:null,analysis:null,error:"",portfolio:{halted:0}}');
(async()=>{
 await run('openGlobalExplorer()');
 assert.equal(el('modal').open,true,'Existing dialog is used for catalog browse');
 assert.match(el('modalBody').innerHTML,/Research only|RESEARCH-ONLY|No live trading/i);
 assert.match(el('globalResults').innerHTML,/Toyota Motor/);
 assert.match(el('globalResults').innerHTML,/Shell/);
 assert.match(el('globalResults').innerHTML,/NVIDIA/);
 el('globalSearch').value='japan';
 run('renderGlobalExplorer()');
 assert.match(el('globalResults').innerHTML,/Toyota/);
 assert.doesNotMatch(el('globalResults').innerHTML,/NVIDIA/);
 el('globalSearch').value='';
 el('globalRegion').value='United Kingdom';
 run('renderGlobalExplorer()');
 assert.match(el('globalResults').innerHTML,/SHEL.L/);
 assert.doesNotMatch(el('globalResults').innerHTML,/7203.T/);
 el('globalRegion').value='';
 const button={dataset:{globalSymbol:'7203.T'}};
 for(const handler of events.get('click')||[]){
  await handler({target:{closest(selector){return button}},preventDefault(){}});
 }
 assert.equal(run('symbol'),'7203.T');
 assert.equal(run('state.instrument.currency'),'JPY');
 assert.equal(el('modal').open,false);
 assert.ok(!el('pageActions').innerHTML.includes('data-act="ticket"'),
  'Global research-only equities cannot expose paper ticket button');
 assert.match(el('content').innerHTML,/Research only/);
 assert.match(el('content').innerHTML,/Japan/);

 // All original eight symbols retain their original selection contract.
 assert.equal(run('instrumentMeta("BTC-USD")[0]'),'BTC');
 assert.equal(run('instrumentMeta("SHEL.L")[0]'),'SHEL.L');
 console.log('PASS: global explorer, country filter, research-only UI, and default watchlist compatibility');
})().catch(error=>{console.error(error);process.exitCode=1});
