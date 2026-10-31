const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const deferred = () => { let resolve; const promise = new Promise(r=>resolve=r); return {promise,resolve}; };
const metadata = new Map(), analyses = new Map(), lists = new Map();
const element = () => ({value:'old',style:{},classList:{add(){},remove(){}},appendChild(){}});
const state = {
  editorLoadToken:0, analysisController:null, AbortController,
  editorTransport:{stop(){},place(t){state.cursor=t;}},
  audioPlot:{data:{old:true},points:['old'],clear(){this.data=null;this.points=[];},activate(){},horizontal(){},draw(){}},
  pitchStatus:element(), waveformStatus:element(), waveformViewport:element(),
  sourceAudioPlayer:{duration:10,pause(){},load(){}},
  rangeStart:element(),rangeEnd:element(),rangeDuration:element(),manualTranscript:element(),
  wavePlayhead:element(),btnLoadWaveform:element(),waveContextSeconds:{value:0},
  editorClipTitle:element(),clipEditor:element(),activeEditorRow:null,
  selectionStart:5,selectionEnd:9,editorDuration:10,editorAudioId:'old',editorViewStart:0,editorViewEnd:10,
  waitForMediaMetadata(_,token){const d=deferred();metadata.set(token,d);return d.promise;},
  analysisRequest(_,token){const d=deferred();analyses.set(token,d);return d.promise;},
  refreshAudios(id,token){const d=deferred();lists.set(token,d);return d.promise;},
  clamp:(x,a,b)=>Math.max(a,Math.min(x,b)),formatTime:String,
  requestAnimationFrame:fn=>setImmediate(fn),
  setSelection(a,b){state.selectionStart=a;state.selectionEnd=b;},
  loadSelectionPreview(){state.prepared=state.editorAudioId;},loadPitch(token){state.pitchToken=token;}
};
const app=fs.readFileSync('static/app.js','utf8');
vm.createContext(state);
vm.runInContext(app.slice(app.indexOf('async function loadWaveform('),app.indexOf('function pointerTime(')),state);
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
  const a=state.openClipInEditor({audio_id:'A',start_s:1,end_s:2},element());
  assert.equal(state.audioPlot.data,null,'old waveform disappears before audio-list request finishes');
  assert.equal(state.audioPlot.points.length,0);
  assert.equal(state.selectionStart,0);assert.equal(state.manualTranscript.value,'');
  const b=state.openClipInEditor({audio_id:'B',start_s:3,end_s:4,transcript:'B text'},element());
  metadata.get(2).resolve();await tick();analyses.get(2).resolve({audio:'B'});
  await tick();await tick();await tick();
  lists.get(2).resolve();await b;
  assert.equal(state.audioPlot.data.audio,'B');assert.equal(state.prepared,'B');
  assert.equal(state.selectionStart,3);assert.equal(state.selectionEnd,4);
  metadata.get(1).resolve();lists.get(1).resolve();await a;
  assert.equal(state.audioPlot.data.audio,'B','late A cannot overwrite B');
  assert.equal(state.manualTranscript.value,'B text');assert.equal(state.pitchToken,2);
  console.log('Editor loading regression checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
