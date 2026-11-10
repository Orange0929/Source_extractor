const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync('static/app.js','utf8');
const code=app.slice(app.indexOf('async function doSearch('),app.indexOf('// ===== Manual waveform range editor ====='));
function fixture(count=700){
 let query='old';const calls=[];
 const state={searchRequest:0,PAGE_SIZE:100,lastResults:Array.from({length:count},(_,i)=>({id:String(i)})),totalResults:900,hasMoreResults:true,
  window:{scrollY:1000,scrollX:0,scrollTo(value){this.restored=value;this.scrollY=value.top;}},
  buildSearchUrl:(path,extra={})=>{const u=new URL('http://test'+path);u.searchParams.set('q',query);for(const [k,v] of Object.entries(extra))u.searchParams.set(k,v);return u;},URL,
  updateResultSummary(){},elResults:{children:[]}};
 const row=(item,i)=>({dataset:{clipId:item.id},getBoundingClientRect:()=>({top:i*10-state.window.scrollY})});
 state.elResults.children=state.lastResults.map(row);
 state.renderResults=(items,append)=>{
  state.lastResults=append?[...state.lastResults,...items]:items;
  state.elResults.children=state.lastResults.map(row);
 };
 let data=Array.from({length:900},(_,i)=>({id:String(i)}));
 state.apiGet=async url=>{
  const u=new URL(url),limit=Number(u.searchParams.get('limit')),offset=Number(u.searchParams.get('offset'));calls.push({limit,offset});
  return {results:data.slice(offset,offset+limit),total:data.length,has_more:offset+limit<data.length};
 };
 vm.createContext(state);vm.runInContext(code,state);
 return {state,calls,setData:items=>data=items,setQuery:value=>query=value};
}
(async()=>{
 let f=fixture();await f.state.refreshResultsAfterEdit('650');
 assert.equal(f.state.lastResults.length,700);assert.deepEqual(f.calls,[{limit:500,offset:0},{limit:200,offset:500}]);
 assert.equal(f.state.window.restored.top,1000);assert.equal(f.state.hasMoreResults,true);
 await f.state.doSearch(true);assert.equal(f.state.lastResults.length,800);assert.equal(f.calls.at(-1).offset,700);
 f=fixture();f.setData(Array.from({length:900},(_,i)=>({id:String(i)})).filter(c=>c.id!=='650'));
 await f.state.refreshResultsAfterEdit('650');
 assert.equal(f.state.lastResults.length,700);assert.equal(f.state.lastResults.some(c=>c.id==='650'),false);
 assert.equal(f.state.window.restored.top,990,'next surviving row keeps its visual position');assert.equal(f.state.totalResults,899);
 f=fixture(300);f.setData([{id:'0'},{id:'1'}]);await f.state.refreshResultsAfterEdit('1');
 assert.equal(f.state.lastResults.length,2);assert.equal(f.state.hasMoreResults,false);
 f=fixture();const get=f.state.apiGet;let finish;
 f.state.apiGet=url=>new Promise(resolve=>{finish=()=>get(url).then(resolve);});
 const old=f.state.refreshResultsAfterEdit('650');
 f.setQuery('new');f.state.apiGet=get;await f.state.doSearch(false);await finish();await old;
 assert.equal(f.state.lastResults.length,100,'obsolete edit refresh cannot replace a newer search');
 assert.equal(f.state.window.restored,undefined,'obsolete refresh cannot move the viewport');
 assert.match(app,/await refreshResultsAfterEdit\(c.id\)/);
 console.log('Expanded results, removal, scroll anchoring, next-page offset and superseded search checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
