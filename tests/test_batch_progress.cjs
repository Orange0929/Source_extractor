const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const code = source.slice(source.indexOf('function updateMasterFromCards()'), source.indexOf('function markAllCardsCancelledUI()'));
const cards = Array.from({length:699}, (_, i) => ({
  dataset:{status:i < 630 ? 'done' : 'error'},
  querySelector:() => ({value:i < 630 ? 100 : 0})
}));
const ctx = {jobsArea:{querySelectorAll:()=>cards}, masterProgress:{}, masterPct:{},
  btnCancelAll:{}, setMasterVisible:()=>{}};
vm.createContext(ctx); vm.runInContext(code, ctx);
ctx.updateMasterFromCards();
assert.equal(ctx.masterProgress.value, 100);
assert.match(ctx.masterPct.textContent, /성공 630 \/ 실패 69/);
assert.equal(ctx.btnCancelAll.disabled, true);
cards[0] = {dataset:{status:'running'}, querySelector:()=>({value:0})};
ctx.updateMasterFromCards();
assert.equal(ctx.btnCancelAll.disabled, false);
assert.match(ctx.masterPct.textContent, /진행·대기 1/);
console.log('699-file completion and active-job progress passed');
