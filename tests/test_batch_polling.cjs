const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('static/app.js','utf8');
let requests=0, updates=0, master=0, intervals=0;
const ctx={jobTimers:new Map(), cancelAllRequested:false, AbortSignal,
 setInterval:()=>++intervals, clearInterval:()=>{},
 updateJobCard:()=>updates++, updateMasterFromCards:()=>master++, scheduleJobRefresh:()=>{},
 fetch:async (url, opts)=>{
  requests++; const ids=JSON.parse(opts.body).ids;
  assert.equal(ids.length,699);
  return {ok:true,json:async()=>({jobs:Object.fromEntries(ids.map(id=>[id,{status:'done',progress:100}]))})};
 }};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('let batchPollTimer'),source.indexOf('// ===== Upload with')),ctx);
(async()=>{
 for(let i=0;i<699;i++)ctx.startJobPolling(String(i),{},String(i));
 assert.equal(intervals,1);
 await ctx.pollJobBatch();
 assert.equal(requests,1);assert.equal(updates,699);assert.equal(master,1);
 assert.equal(ctx.jobTimers.size,0);
 console.log('699 jobs: one request, one master update, all polling entries removed');
})().catch(e=>{console.error(e);process.exitCode=1});
