const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/app.js','utf8'),html=fs.readFileSync('templates/index.html','utf8');
const boxes=['ko','ja','en','other'].map(value=>({value,checked:false}));
const elements={codaOnly:{checked:false},advancedSearchSummary:{},languageExclusions:{addEventListener(_,fn){this.change=fn;}}};
let refreshed=false;
const context={URL,window:{location:{origin:'http://test'}},elSearchInput:{value:'안'},elSearchMode:{value:'basic'},currentProfileId:()=> 'p',
 document:{getElementById:id=>elements[id],querySelectorAll:()=>boxes.filter(b=>b.checked)},selectedClipIds:new Set(['old']),updateBulkDeleteButton(){},
 doSearch:async append=>{assert.equal(append,false);refreshed=true;},alert(){}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function buildSearchUrl('),source.indexOf('async function refreshProfiles(')),context);
vm.runInContext(source.slice(source.indexOf('// Language exclusions are view filters;')),context);
assert.equal(elements.advancedSearchSummary.textContent,'추가 검색 옵션');
boxes[0].checked=boxes[2].checked=true;elements.languageExclusions.change();
assert.equal(context.selectedClipIds.size,0);assert.equal(refreshed,true);
assert.match(elements.advancedSearchSummary.textContent,/2개 적용 중/);
for(const path of ['/api/search','/api/search/ids']){
 const u=context.buildSearchUrl(path,{offset:100});assert.equal(u.searchParams.get('exclude_languages'),'ko,en');assert.equal(u.searchParams.get('offset'),'100');
}
elements.codaOnly.checked=true;context.updateAdvancedSearchSummary();assert.match(elements.advancedSearchSummary.textContent,/3개 적용 중/);
const options=html.match(/<details id="advancedSearchOptions"[^>]*>([\s\S]*?)<\/details>/);
assert.ok(options);assert.ok(!/<details id="advancedSearchOptions"[^>]*\bopen\b/.test(options[0]));
assert.match(options[1],/id="codaOnly"/);assert.match(options[1],/id="languageExclusions"/);
console.log('Collapsed search filters, active summary, selection clearing and shared query checks passed');
