// Build the DOM in template source order; deferred scripts run after parsing.
// This catches initialization against dialog elements that do not exist yet.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),deferred=[];
let state={settings:{device:'auto',performance:'balanced',threads:0},paused:false,running:false,waiting:0,actual:{message:'Ready'}};
const context={Option:class{constructor(text,value){this.text=text;this.value=value;}},document:{getElementById:id=>elements.get(id)||null},setTimeout(){},confirm:()=>true,
 fetch:async(url,opts)=>{if(url==='/api/stt/hardware')return {ok:true,json:async()=>({cpu:{name:'Test CPU',logical_threads:16},gpus:[{index:0,name:'Test GPU',ready:true,reason:'ready'}]})};if(url==='/api/stt/settings')state.settings=JSON.parse(opts.body);return {ok:true,json:async()=>state};}};
vm.createContext(context);
function run(){vm.runInContext(fs.readFileSync('static/stt_control.js','utf8'),context);}
for(const match of fs.readFileSync('templates/index.html','utf8').matchAll(/<([a-z][\w-]*)\b([^>]*)>/gi)){
 const [,tag,attrs]=match,id=attrs.match(/\bid="([^"]+)"/);
 if(id)elements.set(id[1],{value:'',hidden:false,listeners:{},replaceChildren(...options){this.options=options;},
  addEventListener(name,fn){this.listeners[name]=fn;},
  showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},
  querySelectorAll(){return ['sttDevice','sttPerformance','sttThreads','sttThreadMode'].map(id=>elements.get(id));}});
 if(tag.toLowerCase()==='script'&&attrs.includes('/static/stt_control.js')){
  if(/\bdefer\b/.test(attrs))deferred.push(run);else run();
 }
}
for(const fn of deferred)fn();
(async()=>{
 await new Promise(setImmediate);
 const el=id=>elements.get(id);
 await el('btnAppSettings').onclick();assert.equal(el('appSettings').open,true);
 assert.match(el('sttHardwareStatus').textContent,/Test CPU/);
 assert.equal(el('sttThreadManual').hidden,true);
 assert.match(el('sttThreadHelp').textContent,/8 \/ 16/);
 el('sttThreadMode').value='manual';el('sttThreadMode').listeners.input();
 assert.equal(el('sttThreadManual').hidden,false);el('sttThreads').value='3';
 el('sttDevice').value='cpu';el('sttDevice').listeners.input();
 await el('sttSave').onclick();assert.equal(state.settings.device,'cpu');assert.equal(state.settings.threads,3);
 el('sttSettingsClose').onclick();assert.equal(el('appSettings').open,false);
 await el('btnAppSettings').onclick();assert.equal(el('sttDevice').value,'cpu');
 el('sttThreadMode').value='auto';el('sttThreadMode').listeners.input();
 assert.equal(el('sttThreadManual').hidden,true);await el('sttSave').onclick();
 assert.equal(state.settings.threads,0);
 console.log('Template-order settings open/save/close/reopen passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
